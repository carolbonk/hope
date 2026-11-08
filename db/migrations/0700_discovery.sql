-- H2 discovery: one row per run and its step log. Rows go with their job.
CREATE TABLE discovery_runs (
  job_id          uuid PRIMARY KEY REFERENCES jobs ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  focus_keywords  text[] NOT NULL DEFAULT '{}',
  location        text,
  queries         text[] NOT NULL DEFAULT '{}',
  profile_version int,
  counts          jsonb NOT NULL DEFAULT '{}',
  created_by      uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE discovery_job_events (
  job_id        uuid NOT NULL REFERENCES jobs ON DELETE CASCADE,
  tenant_id     uuid NOT NULL REFERENCES tenants,
  seq           int NOT NULL,
  at            timestamptz NOT NULL DEFAULT now(),
  kind          text NOT NULL
                CHECK (kind IN ('info','query','page','skip','candidate','warning','error')),
  text          text NOT NULL CHECK (length(text) <= 300),
  query         text,
  url           text,
  grant_id      uuid,
  is_new        boolean,
  result_count  int,
  PRIMARY KEY (job_id, seq)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['discovery_runs','discovery_job_events']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO hope_app, hope_system', t);
  END LOOP;
END $$;
