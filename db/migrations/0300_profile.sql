-- Agency Profile & Context Steward (A3). Owned by services/profile.

-- HITL-0: protected profile changes wait here until a second person approves them.
CREATE TABLE profile_change_proposals (
  proposal_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants,
  agency_id         uuid NOT NULL REFERENCES agencies,
  base_version      int  NOT NULL,
  patch             jsonb NOT NULL,
  diff              jsonb NOT NULL,
  provenance        jsonb,
  content_hash      text NOT NULL,
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
  proposed_by       text NOT NULL,
  proposed_at       timestamptz NOT NULL DEFAULT now(),
  decided_by        text,
  decided_at        timestamptz,
  decision_comment  text,
  committed_version int,
  CHECK (decided_by IS NULL OR decided_by <> proposed_by)
);
CREATE INDEX profile_change_proposals_pending
  ON profile_change_proposals (agency_id) WHERE status = 'pending';

-- One row per (field, threshold) alert already emitted, so daily scans do not repeat alerts.
CREATE TABLE profile_stale_alerts (
  tenant_id    uuid NOT NULL REFERENCES tenants,
  agency_id    uuid NOT NULL REFERENCES agencies,
  field        text NOT NULL,
  threshold    text NOT NULL,
  ref_date     date NOT NULL,
  emitted_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (agency_id, field, threshold, ref_date)
);

-- Semantic memory: chunked narrative assets (boilerplate, outcomes, bios) for matching/drafting.
-- The dimension is left open so the embedding model can change; search filters on it.
CREATE TABLE narrative_chunks (
  chunk_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenants,
  agency_id           uuid NOT NULL REFERENCES agencies,
  asset_id            text NOT NULL,
  asset_kind          text NOT NULL,
  chunk_index         int  NOT NULL,
  content             text NOT NULL,
  content_hash        text NOT NULL,
  embedding           vector NOT NULL,
  approved_for_reuse  boolean NOT NULL DEFAULT false,
  provenance          jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, asset_id, chunk_index)
);
CREATE INDEX narrative_chunks_tenant ON narrative_chunks (tenant_id, approved_for_reuse);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['profile_change_proposals','profile_stale_alerts','narrative_chunks']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO hope_app, hope_system', t);
  END LOOP;
END $$;
