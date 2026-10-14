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
пешеходный маршрут. Для COFFEE и RESTAURANT действует одинаковый жёсткий лимит
25 минут в одну сторону и предпочтение до 20 минут. Категория не даёт
безусловного приоритета: выигрывает ближайшее доступное действующее предложение.

Поиск выполняется только для активных подтверждённых брендов с действующим
приглашением. Филиалы всех таких сетей объединяются в один пул, явно далёкие
отсеиваются по географическому расстоянию, а Routing API вызывается максимум
пять раз суммарно на одно определение предложения. Время и окончательный выбор
всегда основаны на пешеходном `durationSeconds`, а не на прямом расстоянии.
Координаты Places-поиска округляются до GPS-ячейки около 110 м, чтобы штатный
TTL-кэш поглощал дрожание позиции и не создавал новый поиск при каждом fix.

## Проверка идентификаторов 2ГИС

`partner_admin` и backend используют один путь: переменную `GULYAY_DB_PATH`,
а при её отсутствии — `backend/data/gulyay.sqlite3`. Для production-проверки
задайте путь явно и не создавайте отдельную базу.

Из каталога `backend`:

```powershell
python -m gulyay.partner_admin list
python -m gulyay.partner_admin discover --city moscow --brand cofix
python -m gulyay.partner_admin preview-references --city moscow |
  Tee-Object -FilePath partner-brand-preview.jsonl
python -m gulyay.partner_admin confirm --city moscow --brand cofix --dgis-brand-id <ID>
```

`discover` использует `DGIS_PLACES_API_KEY`, выводит все найденные варианты и
ничего не сохраняет. `confirm` повторно запрашивает филиалы по выбранному ID,
проверяет город, имя и `items.brand.id`, после чего сохраняет ID. Команда не
активирует коммерческий статус и откажется молча заменить другой уже
подтверждённый ID.

`preview-references` выполняет один пакетный запрос `/3.0/items/byid` для девяти
справочных филиалов, извлекает исключительно `items.brand.id`, затем повторно
проверяет каждый ID поиском московских филиалов. `items.org.id` выводится только
для аудита и никогда не используется вместо brand ID. Статусы
`VERIFIED_CANDIDATE`, `AMBIGUOUS` и `NOT_FOUND` в JSONL являются результатом
предварительного просмотра: команда не меняет БД. Справочные branch ID находятся
только в операторской CLI и не участвуют в поиске предложения во время прогулки.

Рекомендуемый production-запуск:

```powershell
$env:DGIS_PLACES_API_KEY='<существующий ключ>'
$env:GULYAY_DB_PATH=(Resolve-Path '.\data\gulyay.sqlite3').Path
python -m gulyay.partner_admin preview-references --city moscow |
  Tee-Object -FilePath partner-brand-preview.jsonl
```

После ручного просмотра выполнять `confirm` отдельно для каждой строки со
статусом `VERIFIED_CANDIDATE`. После этого проверить `list`: допустимо изменение
только `dgis_brand_id` и `dgis_id_status=VERIFIED`; поля
`partnership_status=CANDIDATE`, `is_active_partner=false` и
`partner_discovery_enabled=false` должны сохраниться.

## Ручная проверка production-состояния

1. Запустить backend с обычной БД и собрать московский маршрут.
2. Начать прогулку и войти в `VISITING` штатным GPS-сценарием.
3. Убедиться, что секундомер работает, карточка полностью отсутствует и пустое
   место под неё не резервируется.
4. Проверить паузу, продолжение, выход из точки и переход к следующей точке.
5. Повторить без сети: прогулка и секундомер должны продолжить работу.

Это основной сценарий, пока все девять записей остаются кандидатами.

## Изолированный позитивный сценарий

Нужны тестовая БД и вручную подтверждённые brand ID. Можно включить одну из
девяти сетей или все сети. Команда имеет две защиты:
требует `GULYAY_ENV=test` и отказывается изменять штатный файл
`backend/data/gulyay.sqlite3`.

```powershell
$env:GULYAY_ENV='test'
$env:GULYAY_DB_PATH="$env:TEMP\gulyay-partner-test.sqlite3"
python -m gulyay.partner_test_fixture --db-path $env:GULYAY_DB_PATH `
  --brand cofix --brand-id cofix=<ID>
python -m uvicorn gulyay.api:app --host 0.0.0.0 --port 8000
```

Для всех девяти сетей передаются девять явно проверенных значений:

```powershell
python -m gulyay.partner_test_fixture --db-path $env:GULYAY_DB_PATH --all `
  --brand-id cofix=<ID> --brand-id surf=<ID> --brand-id drinkit=<ID> `
  --brand-id oneprice=<ID> --brand-id thebull=<ID> --brand-id tanuki=<ID> `
  --brand-id frank=<ID> --brand-id chaihona1=<ID> --brand-id syrovarnya=<ID>
```

Каждый ID повторно проверяется через Places API до изменения тестовой БД. Это
синтетические приглашения для технической проверки, а не коммерческие акции.

В `VISITING` карточка должна показать маркировку, конкретный филиал, проверенное
время пешком и кнопку открытия 2ГИС. Она не добавляет филиал в маршрут.

После проверки:

```powershell
python -m gulyay.partner_test_fixture --db-path $env:GULYAY_DB_PATH --all --disable
```

При переходе на другую точку, паузе или завершении прогулки карточка немедленно
скрывается. Запоздалый ответ от старой точки игнорируется по сочетанию
`walkId + pointOrder + requestGeneration`.

После ответа без предложения или временной ошибки Android может повторить
запрос на той же точке только после нового синхронизированного состояния
прогулки и не чаще одного раза в 60 секунд. Фоновый цикл опроса не создаётся.
До наличия активного предложения повторный endpoint-вызов завершается локальной
проверкой БД и не обращается к 2ГИС.
