CREATE TABLE IF NOT EXISTS csat_surveys(
  id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats(chat_id),
  period TEXT NOT NULL,
  job_key TEXT NOT NULL UNIQUE,
  scheduled_for TEXT NOT NULL,
  sent_at TEXT,
  telegram_message_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(chat_id,period)
);

CREATE INDEX IF NOT EXISTS idx_csat_surveys_period
ON csat_surveys(period,chat_id);

CREATE TABLE IF NOT EXISTS csat_responses(
  survey_id TEXT NOT NULL REFERENCES csat_surveys(id),
  chat_id TEXT NOT NULL REFERENCES chats(chat_id),
  user_id TEXT NOT NULL,
  score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 6),
  responded_at TEXT NOT NULL,
  PRIMARY KEY(survey_id,user_id)
);

CREATE INDEX IF NOT EXISTS idx_csat_responses_chat
ON csat_responses(chat_id,responded_at);
