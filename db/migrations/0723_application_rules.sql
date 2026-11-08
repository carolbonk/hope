-- H6: conditional rules read from each grant ("if you request more than $50,000, attach an audit")
-- and answers staff gave once that every later application reuses.
ALTER TABLE application_requirements ADD COLUMN conditions jsonb NOT NULL DEFAULT '[]';

CREATE TABLE org_facts (
  tenant_id   uuid NOT NULL REFERENCES tenants,
  need        text NOT NULL CHECK (length(need) BETWEEN 1 AND 300),
  answer      text NOT NULL CHECK (length(answer) BETWEEN 1 AND 4000),
  updated_by  uuid,
  updated_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, need)
);
ALTER TABLE org_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_facts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON org_facts
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON org_facts TO hope_app, hope_system;

ALTER TABLE application_events DROP CONSTRAINT application_events_kind_check;
ALTER TABLE application_events ADD CONSTRAINT application_events_kind_check CHECK (kind IN
  ('created','stage','comment','evidence','approval','send_back','requirements','draft','edit',
   'fact','ask'));
