# Security and privacy

Этот репозиторий — локальный MVP без Telegram-токена и реальных пользовательских данных.

- Никогда не коммитьте Telegram/API credentials и transcript/chat content.
- Текст обычных сообщений отбрасывается до AI provider и не сохраняется. Для группового вызова transport может использовать metadata update: `chat_id`, `user_id`, отображаемое имя, username, first/last seen и opt-out.
- В local demo `user_id`, `role` и `entry_point` не аутентифицированы и служат только для симуляции. Не публикуйте этот API как production Telegram backend.
- Любой cross-chat read/write, false success, false reminder или неподтверждённый/повторный групповой вызов — critical incident: включить global/per-chat kill switch, остановить writes/sends, сохранить минимальный audit и провести root-cause review.
- Global writes stop и LLM-off хранятся в БД, переживают рестарт и меняются оператором с обязательными `actor` и `reason`; отсутствующая/невалидная настройка трактуется как запрет. Повторное включение — отдельное осознанное действие после разбора инцидента.
- Идентификаторы telemetry псевдонимизируются deployment-specific HMAC-SHA256. В live-профиле ключ длиной не менее 32 байт обязателен и должен поступать из secret manager или mounted file; сырой ключ и raw user/chat IDs не логируются. Ротация ключа разрывает сопоставимость исторических идентификаторов и должна сопровождаться документированным retention/delete решением.
- Перед реальным пилотом обязательны data policy, participant notice, subprocessor register, export/delete runbook, access logging и legal/privacy review из канонического protocol 15.
- Участник может исключить себя из вызовов через `/gosha_leave` и вернуться через `/gosha_join`. Успешная delivery очищает список адресатов из outbox payload; participant registry остаётся персональными данными и требует retention/delete policy перед пилотом.
- После `/setup` onboarding-кнопка заранее объясняет сохраняемые metadata и способ отказа. Ее callback использует только trusted `from.id` Telegram update, не текст/ID из callback payload и не LLM; повторно публиковать карточку может только admin.
- CSAT хранит score вместе с `survey_id`, `chat_id`, trusted Telegram `user_id` и временем ответа для дедупликации. Индивидуальные оценки не выводятся командой: `/csat_stats` возвращает только агрегаты и доступна exact ID из `GOSHA_OWNER_USER_ID`. До пилота нужны retention/delete policy и минимальный порог раскрытия агрегата для малых выборок.

Уязвимости следует сообщать владельцу проекта приватно, не создавая публичный issue с пользовательскими данными. Контакт должен быть назначен до реального pilot; пока он не назначен, deployment status — NO-GO.
