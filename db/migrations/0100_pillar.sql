-- Grant Operations Pillar (blueprint 7.3, 7.4). Owned by services/pillar.

-- Versioned canonical state behind PillarPort.get_state/put_state (optimistic concurrency).
-- tenant_id is taken from app.tenant_id; NULL rows are platform state.
CREATE TABLE pillar_state (
  tenant_id    uuid REFERENCES tenants DEFAULT current_tenant(),
  entity       text NOT NULL,
  entity_id    text NOT NULL,
  version      int  NOT NULL CHECK (version >= 1),
  state        jsonb NOT NULL,
  recorded_at  timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX pillar_state_version ON pillar_state
  (coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), entity, entity_id, version);
CREATE TRIGGER pillar_state_append_only BEFORE UPDATE OR DELETE ON pillar_state
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Idempotency-Key ledger for POST /v1/ingest/*.
CREATE TABLE pillar_ingest_requests (
  tenant_id        uuid NOT NULL REFERENCES tenants,
  idempotency_key  text NOT NULL,
  ingest_id        uuid NOT NULL,
  request_hash     text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, idempotency_key)
);

-- Projection of hitl.requested / hitl.decided, used to reject stale artifact hashes.
CREATE TABLE pillar_gate_requests (
  request_id      uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  workflow_id     text NOT NULL,
  subject_id      text NOT NULL,
  gate            text NOT NULL,
  artifact_hash   text NOT NULL,
  approver_roles  text[] NOT NULL DEFAULT '{}',
  due_at          timestamptz,
  summary         text NOT NULL DEFAULT '',
  payload_ref     text,
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'decided', 'superseded')),
  decision        text,
  decided_by      text,
  requested_at    timestamptz NOT NULL DEFAULT now(),
  decided_at      timestamptz
);
CREATE UNIQUE INDEX pillar_gate_one_open ON pillar_gate_requests (tenant_id, workflow_id, gate)
  WHERE status = 'open';

-- Projection of every tenant event that carries a workflow id (trace.correlation_id).
CREATE TABLE pillar_workflow_timeline (
  event_id     uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants,
  workflow_id  text NOT NULL,
  event_type   text NOT NULL,
  occurred_at  timestamptz NOT NULL,
  summary      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX pillar_workflow_timeline_wf ON pillar_workflow_timeline (tenant_id, workflow_id, occurred_at);

ALTER TABLE pillar_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE pillar_state FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pillar_state
  USING (tenant_id IS NOT DISTINCT FROM current_tenant())
  WITH CHECK (tenant_id IS NOT DISTINCT FROM current_tenant());

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pillar_ingest_requests','pillar_gate_requests','pillar_workflow_timeline']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;
