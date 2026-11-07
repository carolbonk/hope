-- Dev/CI only. Production roles and passwords come from the secrets manager.
-- hope_app:    request-scoped service role, always subject to RLS.
-- hope_system: cross-tenant workers (outbox relay, public ingestion), bypasses RLS.
CREATE ROLE hope_app LOGIN PASSWORD 'hope_app';
CREATE ROLE hope_system LOGIN PASSWORD 'hope_system' BYPASSRLS;
