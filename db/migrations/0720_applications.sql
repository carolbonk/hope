-- H6 application help: one application per saved grant, its requirements, answers and activity.
CREATE TABLE applications (
  application_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants,
  grant_id          uuid NOT NULL REFERENCES grant_candidates ON DELETE CASCADE,
  stage             text NOT NULL DEFAULT 'saved'
                    CHECK (stage IN ('saved','eligibility','approval','drafting','ready')),
  version           int NOT NULL DEFAULT 1,
  approvals         jsonb NOT NULL DEFAULT '{}',
  evidence          jsonb NOT NULL DEFAULT '{}',
  ask_minor         bigint CHECK (ask_minor > 0),
  currency          text NOT NULL DEFAULT 'USD' CHECK (currency ~ '^[A-Z]{3}$'),
  questions_status  text NOT NULL DEFAULT 'unread'
                    CHECK (questions_status IN ('unread','reading','found','not_found')),
  created_by        uuid,
  created_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, grant_id)
);

CREATE TABLE application_requirements (
  application_id  uuid NOT NULL REFERENCES applications ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  revision        int NOT NULL,
  questions       jsonb NOT NULL DEFAULT '[]',
  attachments     jsonb NOT NULL DEFAULT '[]',
  budget          jsonb NOT NULL DEFAULT '{}',
  submission      jsonb NOT NULL DEFAULT '{}',
  eligibility     jsonb NOT NULL DEFAULT '[]',
  pages           jsonb NOT NULL DEFAULT '[]',
  read_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (application_id, revision)
);

CREATE TABLE application_answers (
  application_id  uuid NOT NULL REFERENCES applications ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  question_key    text NOT NULL,
  text            text NOT NULL DEFAULT '',
  origin          text NOT NULL CHECK (origin IN ('ai','template','human')),
  model           text,
  prompt_version  text,
  citations       jsonb NOT NULL DEFAULT '[]',
  to_confirm      jsonb NOT NULL DEFAULT '[]',
  updated_by      uuid,
  updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (application_id, question_key)
);

CREATE TABLE application_events (
  event_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  uuid NOT NULL REFERENCES applications ON DELETE CASCADE,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  kind            text NOT NULL CHECK (kind IN
                  ('created','stage','comment','evidence','approval','send_back','requirements','draft','edit')),
  actor           uuid,
  payload         jsonb NOT NULL DEFAULT '{}',
  at              timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX application_events_by_app ON application_events (application_id, at DESC);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['applications','application_requirements','application_answers','application_events']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant())'
      ' WITH CHECK (tenant_id = current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO hope_app, hope_system', t);
  END LOOP;
END $$;
