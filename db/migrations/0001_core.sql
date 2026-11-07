-- Core canonical state store (blueprint 7.3). Owned by the orchestrator.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END $$;

CREATE TABLE tenants (
  tenant_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agencies (
  agency_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  legal_name  text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Bitemporal: valid_* is business time, recorded_at is system time.
CREATE TABLE agency_profile_versions (
  agency_id    uuid NOT NULL REFERENCES agencies,
  tenant_id    uuid NOT NULL REFERENCES tenants,
  version      int  NOT NULL CHECK (version >= 1),
  profile      jsonb NOT NULL,
  valid_from   timestamptz NOT NULL DEFAULT now(),
  valid_to     timestamptz,
  recorded_at  timestamptz NOT NULL DEFAULT now(),
  recorded_by  text NOT NULL,
  PRIMARY KEY (agency_id, version)
);

-- Opportunities are public data shared across tenants.
CREATE TABLE opportunities (
  opportunity_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_system    text NOT NULL,
  source_id        text NOT NULL,
  current_version  int  NOT NULL DEFAULT 1,
  title            text NOT NULL,
  application_due  timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_id)
);

CREATE TABLE opportunity_versions (
  opportunity_id  uuid NOT NULL REFERENCES opportunities,
  version         int  NOT NULL,
  amendment_seq   int  NOT NULL DEFAULT 0,
  normalized      jsonb NOT NULL,
  content_hash    text NOT NULL,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (opportunity_id, version)
);

CREATE TABLE artifacts (
  artifact_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid REFERENCES tenants,  -- NULL = public artifact
  sha256          text NOT NULL,
  storage_uri     text NOT NULL,
  media_type      text NOT NULL,
  classification  text NOT NULL DEFAULT 'internal'
                  CHECK (classification IN ('public','internal','confidential','restricted')),
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX artifacts_sha256 ON artifacts (sha256);

-- Per-tenant lifecycle projection (mirrors Temporal via outbox events).
CREATE TABLE tenant_opportunity (
  tenant_id        uuid NOT NULL REFERENCES tenants,
  opportunity_id   uuid NOT NULL REFERENCES opportunities,
  agency_id        uuid NOT NULL REFERENCES agencies,
  state            text NOT NULL,
  workflow_id      text,
  composite_score  numeric(5,2),
  recommendation   text,
  internal_deadline timestamptz,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, opportunity_id, agency_id)
);

CREATE TABLE frameworks (
  framework_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants,
  opportunity_id  uuid NOT NULL REFERENCES opportunities,
  agency_id       uuid NOT NULL REFERENCES agencies,
  version         int  NOT NULL,
  status          text NOT NULL CHECK (status IN ('draft','verified','approved_locked','superseded')),
  framework       jsonb NOT NULL,
  content_hash    text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (opportunity_id, agency_id, version)
);

CREATE TABLE budget_ledgers (
  ledger_id       text PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  framework_id    uuid REFERENCES frameworks,
  engine_version  text NOT NULL,
  ledger          jsonb NOT NULL,
  content_hash    text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (ledger->>'computed_by' = 'budget-engine')
);

CREATE TABLE approvals (
  approval_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants,
  workflow_id     text NOT NULL,
  gate            text NOT NULL,
  decision        text NOT NULL,
  artifact_hash   text NOT NULL,
  decided_by      text NOT NULL,
  decided_at      timestamptz NOT NULL DEFAULT now(),
  comment         text,
  esign_envelope_id text
);
CREATE TRIGGER approvals_append_only BEFORE UPDATE OR DELETE ON approvals
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Transactional outbox: written in the same transaction as the state change.
CREATE TABLE outbox (
  outbox_id     bigserial PRIMARY KEY,
  event_id      uuid NOT NULL UNIQUE,
  tenant_id     uuid REFERENCES tenants,
  topic         text NOT NULL,
  partition_key text NOT NULL,
  envelope      jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  published_at  timestamptz
);
CREATE INDEX outbox_unpublished ON outbox (outbox_id) WHERE published_at IS NULL;

CREATE TABLE processed_events (
  consumer      text NOT NULL,
  event_id      uuid NOT NULL,
  processed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer, event_id)
);

-- Append-only, hash-chained per tenant (NULL tenant = platform chain).
CREATE TABLE audit_log (
  audit_id    bigserial PRIMARY KEY,
  tenant_id   uuid REFERENCES tenants,
  actor       text NOT NULL,
  action      text NOT NULL,
  subject     text NOT NULL,
  detail      jsonb NOT NULL DEFAULT '{}',
  at          timestamptz NOT NULL DEFAULT now(),
  prev_hash   text,
  hash        text
);

CREATE OR REPLACE FUNCTION audit_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(coalesce(NEW.tenant_id::text, 'platform')));
  SELECT hash INTO NEW.prev_hash FROM audit_log
    WHERE tenant_id IS NOT DISTINCT FROM NEW.tenant_id
    ORDER BY audit_id DESC LIMIT 1;
  NEW.hash := encode(digest(
    coalesce(NEW.prev_hash, '') || NEW.actor || NEW.action || NEW.subject ||
    NEW.detail::text || NEW.at::text, 'sha256'), 'hex');
  RETURN NEW;
END $$;
CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_chain();
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Row-level security on every tenant-scoped table.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['agencies','agency_profile_versions','tenant_opportunity',
                           'frameworks','budget_ledgers','approvals','outbox','audit_log']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON tenants USING (tenant_id = current_tenant());

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts FORCE ROW LEVEL SECURITY;
CREATE POLICY artifact_access ON artifacts
  USING (tenant_id IS NULL OR tenant_id = current_tenant())
  WITH CHECK (tenant_id = current_tenant());

GRANT USAGE ON SCHEMA public TO hope_app, hope_system;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hope_app, hope_system;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hope_app, hope_system;
REVOKE INSERT, UPDATE, DELETE ON opportunities, opportunity_versions FROM hope_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hope_app, hope_system;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO hope_app, hope_system;
