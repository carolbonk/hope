-- Matching (A4/A5/A6): per-tenant scoring config and append-only matrix snapshots.
CREATE TABLE matching_tenant_config (
  tenant_id   uuid PRIMARY KEY REFERENCES tenants,
  config      jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE opportunity_matrices (
  matrix_id      bigserial PRIMARY KEY,
  tenant_id      uuid NOT NULL REFERENCES tenants,
  agency_id      uuid NOT NULL REFERENCES agencies,
  generated_at   timestamptz NOT NULL,
  model_version  text NOT NULL,
  matrix         jsonb NOT NULL,
  content_hash   text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX opportunity_matrices_latest
  ON opportunity_matrices (tenant_id, agency_id, generated_at DESC);
CREATE TRIGGER opportunity_matrices_append_only BEFORE UPDATE OR DELETE ON opportunity_matrices
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['matching_tenant_config','opportunity_matrices']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON matching_tenant_config, opportunity_matrices
  TO hope_app, hope_system;
GRANT USAGE, SELECT ON SEQUENCE opportunity_matrices_matrix_id_seq TO hope_app, hope_system;
