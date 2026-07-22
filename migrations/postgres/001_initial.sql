CREATE TABLE IF NOT EXISTS chats(
  chat_id TEXT PRIMARY KEY, timezone_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS deadlines(
  id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(chat_id), title TEXT NOT NULL,
  due_local TEXT NOT NULL, timezone_id TEXT NOT NULL, due_utc TEXT NOT NULL, author_id TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_deadlines_chat ON deadlines(chat_id,status,due_utc);
CREATE TABLE IF NOT EXISTS pending(
  id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
  payload TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit(
  id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
  object_id TEXT, before_json TEXT, after_json TEXT, correlation_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders(
  job_key TEXT PRIMARY KEY, chat_id TEXT NOT NULL, deadline_id TEXT NOT NULL, type TEXT NOT NULL,
  scheduled_for TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled', payload_json TEXT NOT NULL DEFAULT '{}',
  attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5, available_at TEXT,
  claimed_by TEXT, claimed_at TEXT, lease_until TEXT, last_error TEXT, telegram_message_id TEXT, delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status,scheduled_for,available_at);
CREATE TABLE IF NOT EXISTS idempotency(
  key TEXT PRIMARY KEY, request_fingerprint TEXT, response_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, chat_key TEXT NOT NULL, user_key TEXT NOT NULL,
  result TEXT NOT NULL, correlation_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS materials(
  id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(chat_id), description TEXT NOT NULL,
  url TEXT NOT NULL, canonical_url TEXT NOT NULL, domain TEXT NOT NULL, author_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(chat_id,canonical_url)
);
CREATE INDEX IF NOT EXISTS idx_materials_chat ON materials(chat_id,status,created_at);
CREATE TABLE IF NOT EXISTS delivery_attempts(
  id TEXT PRIMARY KEY, job_key TEXT NOT NULL REFERENCES reminders(job_key), attempt_no INTEGER NOT NULL,
  attempted_at TEXT NOT NULL, result TEXT NOT NULL, error TEXT, telegram_message_id TEXT,
  UNIQUE(job_key,attempt_no)
);
