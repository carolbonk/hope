-- Jobs record a heartbeat so startup only fails jobs whose worker is gone (not live ones in another process).
ALTER TABLE jobs ADD COLUMN heartbeat_at timestamptz;
