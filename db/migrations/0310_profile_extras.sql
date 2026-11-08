-- H1: HQ city/state and website for the hackathon profile, written with every profile save.
-- `AgencyProfile.legal` carries the same values (H0 promoted them); this table keeps them
-- queryable without parsing the version JSON.
CREATE TABLE agency_profile_extras (
  agency_id   uuid PRIMARY KEY REFERENCES agencies,
  tenant_id   uuid NOT NULL REFERENCES tenants,
  hq_city     text NOT NULL,
  hq_state    char(2) NOT NULL,
  website     text,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  updated_by  text NOT NULL
);

ALTER TABLE agency_profile_extras ENABLE ROW LEVEL SECURITY;
ALTER TABLE agency_profile_extras FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON agency_profile_extras
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON agency_profile_extras TO hope_app, hope_system;
