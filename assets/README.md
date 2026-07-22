# Asset provenance

`demo.gif` — воспроизводимая визуализация локального MOCK Telegram flow. Генератор `../scripts/generate_demo_gif.py` запускает текущие `TelegramBot`, `GoshaService` и `Store` через deterministic local MockTelegramAPI, извлекает фактические response texts и строит шесть кадров:

1. deadline preview;
2. confirmed deadline;
3. retrieval другим участником;
4. URL-material preview;
5. confirmed material;
6. retrieval другим участником.

Каждый кадр помечен `MOCK SIMULATION`; footer прямо отделяет HTTP mock от live Telegram и пользовательского пилота. Synthetic IDs детерминированы только для воспроизводимости asset. В изображении нет реальных пользователей, токенов, чатов или внешнего Telegram UI capture.
