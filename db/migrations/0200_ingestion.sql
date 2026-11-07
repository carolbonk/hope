-- Ingestion (A1/A2) state. Public cross-tenant data, written only by hope_system.

CREATE TABLE connector_cursors (
  source_system  text NOT NULL,
  search_key     text NOT NULL,
  cursor         jsonb NOT NULL DEFAULT '{}',
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source_system, search_key)
);

-- MinHash signatures (datasketch values fit in bigint) to rebuild the near-dup index.
CREATE TABLE opportunity_minhash (
  opportunity_id  uuid PRIMARY KEY REFERENCES opportunities,
  num_perm        int NOT NULL,
  hashvalues      bigint[] NOT NULL,
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifact_quarantine (
  quarantine_id  bigserial PRIMARY KEY,
  sha256         text NOT NULL,
  source_ref     text,
  reason         text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX artifact_quarantine_sha256 ON artifact_quarantine (sha256);

CREATE UNIQUE INDEX artifacts_public_sha256 ON artifacts (sha256) WHERE tenant_id IS NULL;

REVOKE INSERT, UPDATE, DELETE ON connector_cursors, opportunity_minhash, artifact_quarantine
  FROM hope_app;
