# Партнёрские предложения

Партнёрская функция является необязательной и fail-closed: без одновременно
активного партнёра, подтверждённого `dgis_brand_id` и действующего предложения
backend не обращается к 2ГИС и возвращает `offer: null`. В production seed нет
активных партнёров или предложений.

## Хранение и миграция

`PartnerRegistry` идемпотентно создаёт:

- `partner_brand_registry` — реестр брендов по составному ключу
  `(partner_brand_id, city_id)`;
- `partner_offers` — приглашения с периодом действия и действием `OPEN_DGIS`.

Старые экспериментальные таблицы `partner_brands`, `partner_venues` и
`partner_place_links`, если они присутствуют в пользовательской базе, не
удаляются и не используются для показа. Девять московских брендов добавляются
через `INSERT OR IGNORE` со статусами `CANDIDATE`,
`PENDING_VERIFICATION`, `is_active_partner=0` и
`partner_discovery_enabled=0`.

Последняя уже принятая backend геопозиция сохраняется внутри JSON прогулки как
опциональное поле `lastPosition`. Старый JSON без этого поля остаётся
совместимым. Для предложения принимается позиция с точностью не хуже 50 м и
возрастом не более 60 секунд.

## API

```http
GET /v1/walks/{walkId}/partner-offer
X-Device-Session: <UUID>
```

Backend проверяет владельца прогулки, `status=ACTIVE`, `phase=VISITING`, свежую
позицию и локальные коммерческие записи. Возможные ответы:

```json
{"status":"NONE","offer":null}
```

```json
{
  "status": "AVAILABLE",
  "offer": {
    "offerId": "test_cofix_moscow_001",
    "partnerBrandId": "cofix",
    "dgisPlaceId": "<verified branch id>",
    "title": "Зайти за кофе?",
    "description": "Обычное посещение кофейни. Скидки, бонусы и промокоды не предусмотрены.",
    "venueName": "Cofix",
    "walkingMinutes": 6,
    "isCommercial": true,
    "action": {
      "type": "OPEN_DGIS",
      "label": "Открыть в 2ГИС",
      "url": "https://2gis.ru/moscow/firm/<verified branch id>"
    }
  }
}
```

Сбой 2ГИС возвращает `200` со статусом `PROVIDER_UNAVAILABLE` и `offer: null`,
чтобы не прерывать прогулку. Ошибка или чужой `X-Device-Session` не маскируется
и возвращает штатную ошибку API.

Поиск филиалов выполняется только по подтверждённому `brand_id`. Для ближайших
кандидатов проверяются принадлежность бренду, город, расписание и реальный
пешеходный маршрут. Лимиты в одну сторону: COFFEE — 10 минут (предпочтительно
до 5), RESTAURANT — 20 минут (предпочтительно до 15).

## Проверка идентификаторов 2ГИС

Из каталога `backend`:

```powershell
python -m gulyay.partner_admin list
python -m gulyay.partner_admin discover --city moscow --brand cofix
python -m gulyay.partner_admin confirm --city moscow --brand cofix --dgis-brand-id <ID>
```

`discover` использует `DGIS_PLACES_API_KEY`, выводит все найденные варианты и
ничего не сохраняет. `confirm` повторно запрашивает филиалы по выбранному ID,
проверяет город, имя и `items.brand.id`, после чего сохраняет ID. Команда не
активирует коммерческий статус.

## Ручная проверка production-состояния

1. Запустить backend с обычной БД и собрать московский маршрут.
2. Начать прогулку и войти в `VISITING` штатным GPS-сценарием.
3. Убедиться, что секундомер работает, карточка полностью отсутствует и пустое
   место под неё не резервируется.
4. Проверить паузу, продолжение, выход из точки и переход к следующей точке.
5. Повторить без сети: прогулка и секундомер должны продолжить работу.

Это основной сценарий, пока все девять записей остаются кандидатами.

## Изолированный позитивный сценарий

Нужны тестовая БД и вручную подтверждённый ID Cofix. Команда имеет две защиты:
требует `GULYAY_ENV=test` и отказывается изменять штатный файл
`backend/data/gulyay.sqlite3`.

```powershell
$env:GULYAY_ENV='test'
$env:GULYAY_DB_PATH="$env:TEMP\gulyay-partner-test.sqlite3"
python -m gulyay.partner_test_fixture --db-path $env:GULYAY_DB_PATH --dgis-brand-id <ID>
python -m uvicorn gulyay.api:app --host 0.0.0.0 --port 8000
```

В `VISITING` карточка должна показать маркировку, конкретный филиал, проверенное
время пешком и кнопку открытия 2ГИС. Она не добавляет филиал в маршрут.

После проверки:

```powershell
python -m gulyay.partner_test_fixture --db-path $env:GULYAY_DB_PATH --disable
```

При переходе на другую точку, паузе или завершении прогулки карточка немедленно
скрывается. Запоздалый ответ от старой точки игнорируется по сочетанию
`walkId + pointOrder + requestGeneration`.
