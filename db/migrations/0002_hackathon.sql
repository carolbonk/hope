-- Hackathon (H0): users, background jobs and grant candidates. Owned by the orchestrator.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
  user_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants,
  email          citext NOT NULL,
  password_hash  text NOT NULL,
  display_name   text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE jobs (
  job_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  kind         text NOT NULL,
  subject_id   text,
  status       text NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued','running','done','failed')),
  progress     jsonb NOT NULL DEFAULT '{}',
  result       jsonb,
  error        text,
  created_by   uuid REFERENCES users,
  started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at  timestamptz
);
CREATE INDEX jobs_latest ON jobs (tenant_id, kind, started_at DESC);

CREATE TABLE grant_candidates (
  grant_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenants,
  url                  text NOT NULL,
  title                text NOT NULL,
  funder               text NOT NULL,
  summary              text NOT NULL,
  amount_text          text,
  amount_max           jsonb,
  deadline_text        text,
  deadline             date,
  eligibility_summary  text,
  fit_score            int  NOT NULL CHECK (fit_score BETWEEN 0 AND 100),
  fit_reasons          jsonb NOT NULL DEFAULT '[]',
  concerns             jsonb NOT NULL DEFAULT '[]',
  citations            jsonb NOT NULL DEFAULT '[]',
  status               text NOT NULL DEFAULT 'new' CHECK (status IN ('new','saved','passed')),
  found_by_job_id      uuid REFERENCES jobs,
  discovered_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  status_changed_at    timestamptz,
  status_changed_by    uuid REFERENCES users,
  pass_reason          text,
  pass_reason_text     text,
  UNIQUE (tenant_id, url)
);
CREATE INDEX grant_candidates_status ON grant_candidates (tenant_id, status, fit_score DESC);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['users','jobs','grant_candidates']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO hope_app, hope_system', t);
  END LOOP;
END $$;
