-- Public artifacts (tenant_id IS NULL) are readable by every tenant but writable by none:
-- 0001's single artifact_access policy let its USING clause govern DELETE and UPDATE too.
DROP POLICY artifact_access ON artifacts;
CREATE POLICY artifact_read ON artifacts FOR SELECT
  USING (tenant_id IS NULL OR tenant_id = current_tenant());
CREATE POLICY artifact_insert ON artifacts FOR INSERT
  WITH CHECK (tenant_id = current_tenant());
CREATE POLICY artifact_update ON artifacts FOR UPDATE
  USING (tenant_id = current_tenant())
  WITH CHECK (tenant_id = current_tenant());
CREATE POLICY artifact_delete ON artifacts FOR DELETE
  USING (tenant_id = current_tenant());
