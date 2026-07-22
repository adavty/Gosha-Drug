# Gosha AI — desk research protocol

> **Статус:** метод и source register; внешние факты не заменяют user evidence
> **Обновлено:** 19 июля 2026 года

## 1. Цель

Кабинетное исследование проверяет продуктовый контекст до интервью: существующие механики, ограничения платформы, научные и профессиональные evidence по координации и AI UX, а также рыночные альтернативы. Оно формирует вопросы для field research, но не подтверждает частоту боли, выбор пользователей или готовность платить.

## 2. Потоки

| Поток | Что исследуется | Допустимый вывод |
|---|---|---|
| AS IS и substitutes | Telegram search/pins/topics/Saved Messages, ручной дайджест, LMS, календарь, task/reminder bots | функция существует; сравнение требуется в incident interviews |
| Platform constraints | Bot API, privacy mode, replies, callbacks, admin checks, delivery | техническое ограничение и design implication |
| Problem context | shared/prospective memory, coordination cost, retrieval в group chat, notification fatigue, source-of-truth conflicts | внешний prior, не prevalence Gosha |
| AI UX | calibrated trust, automation bias, provenance, confirmation, recovery, fallback | design principle и риск |
| Market/viability | учебные программы, интенсивы, L&D-когорты, pricing/procurement | segment/offer hypothesis |

## 3. Source register

| source_id | Тип | Название/URL | Издатель | Published | Checked | Извлечённый факт | Ограничение | Hypothesis |
|---|---|---|---|---|---|---|---|---|

Каждая строка получает один статус:

- `EXTERNAL_FACT` — буквально поддерживается первичным источником;
- `EXTERNAL_INTERPRETATION` — интерпретация источника для Gosha;
- `PRODUCT_HYPOTHESIS` — требует user/business evidence.

Правила:

- для функций, API и цен использовать официальный источник;
- сохранять дату проверки и прямую ссылку;
- отделять текущую функцию конкурента от поведения его пользователей;
- не делать TAM/SAM/SOM без защищаемых исходных данных;
- не считать feature matrix доказательством превосходства;
- реально используемая в последнем incident альтернатива весит сильнее списка возможностей на сайте.

## 4. Task-based alternatives map

| Job/incident | Реальная альтернатива | Почему выбрана | Где сработала | Где возникла friction | Negative case | Evidence/status |
|---|---|---|---|---|---|---|

Desk research заполняет колонки о подтверждённых функциях. Причины выбора, friction и negative cases заполняются только по field evidence.

## 5. Platform constraint register

| Constraint | Primary source | Product implication | Test | Owner | Checked/version |
|---|---|---|---|---|---|

Минимальный набор: privacy mode, явный invocation, group/admin identity, message/source reference, callback ownership, retry/delivery semantics, data deletion/export, API/policy dependency.

## 6. Выход

Кабинетный этап завершается четырьмя артефактами:

1. dated source register;
2. alternatives map с отделёнными внешними фактами и гипотезами;
3. platform constraint register;
4. список вопросов для R-01, которые нельзя закрыть desk research.

Актуальный рыночный срез и первичные ссылки находятся в [market and business model](../market-and-business-model.md).
