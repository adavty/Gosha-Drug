INSERT INTO runtime_settings(key,value,updated_at,actor_id,reason)
VALUES
  ('global_writes_enabled','1',CURRENT_TIMESTAMP::TEXT,'migration','explicit_initial_enable'),
  ('global_llm_enabled','1',CURRENT_TIMESTAMP::TEXT,'migration','explicit_initial_enable')
ON CONFLICT(key) DO NOTHING;
