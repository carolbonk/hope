-- My bids: preparing one application for submission. One bid per application, and one row per
-- requirement on the application's checklist (owner, internal due date, status, evidence, review).
CREATE TABLE bids (
  application_id  uuid PRIMARY KEY REFERENCES applications ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  version         int NOT NULL DEFAULT 1,
  final_review    jsonb,
  submission      jsonb,
  created_by      uuid,
  created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE bid_items (
  application_id  uuid NOT NULL REFERENCES bids ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  item_key        text NOT NULL CHECK (length(item_key) BETWEEN 1 AND 300),
  owner           uuid REFERENCES users ON DELETE SET NULL,
  due             date,
  status          text NOT NULL DEFAULT 'missing' CHECK (status IN ('missing','working','ready')),
  note            text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  evidence_ref    text NOT NULL DEFAULT '' CHECK (length(evidence_ref) <= 500),
  review          jsonb,
  updated_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (application_id, item_key)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['bids','bid_items']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO hope_app, hope_system', t);
  END LOOP;
END $$;

-- Bid activity goes on the application's own timeline.
ALTER TABLE application_events DROP CONSTRAINT application_events_kind_check;
ALTER TABLE application_events ADD CONSTRAINT application_events_kind_check CHECK (kind IN
  ('created','stage','comment','evidence','approval','send_back','requirements','draft','edit',
   'fact','ask','bid'));
