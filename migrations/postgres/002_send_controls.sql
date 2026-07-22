CREATE TABLE IF NOT EXISTS runtime_settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  reason TEXT NOT NULL
);

INSERT INTO runtime_settings(key,value,updated_at,actor_id,reason)
VALUES('global_sends_enabled','1',CURRENT_TIMESTAMP::TEXT,'bootstrap','default')
ON CONFLICT(key) DO NOTHING;
