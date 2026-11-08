-- H6: facts staff supply for one application (a timeline, how outcomes are measured, ...).
-- The drafter treats them like profile facts, so it has nothing left to invent.
CREATE TABLE application_facts (
  application_id  uuid NOT NULL REFERENCES applications ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  need            text NOT NULL CHECK (length(need) BETWEEN 1 AND 300),
  answer          text NOT NULL CHECK (length(answer) BETWEEN 1 AND 4000),
  updated_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (application_id, need)
);
ALTER TABLE application_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_facts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON application_facts
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON application_facts TO hope_app, hope_system;

ALTER TABLE application_events DROP CONSTRAINT application_events_kind_check;
ALTER TABLE application_events ADD CONSTRAINT application_events_kind_check CHECK (kind IN
  ('created','stage','comment','evidence','approval','send_back','requirements','draft','edit',
   'fact'));
