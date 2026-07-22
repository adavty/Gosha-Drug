CREATE TABLE IF NOT EXISTS participants(
  chat_id TEXT NOT NULL REFERENCES chats(chat_id),
  user_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  username TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY(chat_id,user_id)
);

CREATE INDEX IF NOT EXISTS idx_participants_chat_status
ON participants(chat_id,status,last_seen_at);
