# Гуляй — Android Java и backend

Версия `0.5.2` — корректирующий проверяемый этап разработки полного MVP `1.0`. Главный источник требований — `docs/source/2ГИС Системная аналитика.docx`; решения и открытые вопросы записаны в `docs/DECISIONS.md`, границы выпусков — в `docs/RELEASES.md`. Для прибытия к точке принято N = 75 м; само прохождение начинается в 0.6.

## Что добавлено в 0.5.2

После построения маршрута доступна кнопка **«Показать на карте 2ГИС»**. Отдельный экран показывает точки по координатам backend, маршрут — по реальной геометрии его пеших участков Routing API, а при разрешённой геопозиции — старт пользователя. Android не рисует выдуманную прямую линию при отсутствии геометрии.

При запуске приложение проверяет последнюю системную позицию и одновременно запрашивает свежую через GPS и сетевой источник. Тула, Владимир или Москва выбираются автоматически по координатам. Если определить поддерживаемый город не удалось, список показывает **«Локация не определена»**, после чего пользователь выбирает город вручную. Ввод координат не требуется. В API-06 уходят координаты и точность измерения; при ручном выборе используется явно обозначенный приблизительный старт. Запрос и текущий маршрут сохраняются при повороте главного экрана.

Если позиция определена или сброшена после расчёта, кнопка предлагает перестроить маршрут от нового старта. При ошибке старый маршрут не удаляется.

Android Map SDK зафиксирован на версии `13.6.0`. Мобильный `dgissdk.key` подставляется локально или через секрет Actions и никогда не коммитится. Если ключ отсутствует или не подходит тарифу, приложение показывает понятную ошибку вместо падения. До решения `CONSENT-01` диагностическая статистика SDK отключена через `PersonalDataCollectionConsent.DENIED`.

## Что проверять в 0.5.2

1. Запустите backend и разрешите приложению доступ к геопозиции.
2. Если системная позиция находится в Москве, Туле или Владимире, соответствующий город должен выбираться автоматически без ввода координат.
3. Постройте маршрут и откройте карту: должны появиться пронумерованные точки, зелёный пеший путь и маркер старта.
4. Поверните экран карты и вернитесь назад: камера, введённый запрос и текущий маршрут не должны исчезнуть.
5. Запретите геопозицию: в списке должно появиться «Локация не определена». Выберите город вручную и постройте маршрут от его области.
6. Соберите APK без мобильного ключа: кнопка карты должна открыть понятное сообщение о `dgissdk.key`, а не завершить приложение.

Функции 0.2–0.4.2 сохранены: LLM-разбор любых геоуточнений, реальные Places/Routing, защита от частых запросов, SQLite, изменение текста и ручное редактирование точек. Прохождения маршрута и партнёрских предложений в 0.5 ещё нет. Правило посещений 40/60 минут остаётся открытым вопросом `VISIT-01`.

## Мобильный ключ 2ГИС

Нужен именно файл мобильного Android Map SDK `dgissdk.key`, выданный 2ГИС для `applicationId` `ru.gulyay.app`. Это не серверные ключи Places/Routing. Для локальной сборки на Windows:

```powershell
New-Item -ItemType Directory -Force ".\app\src\main\assets"
Copy-Item "C:\путь\к\dgissdk.key" ".\app\src\main\assets\dgissdk.key"
```

Для GitHub Actions преобразуйте весь файл в Base64:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\путь\к\dgissdk.key")) | Set-Clipboard
```

Добавьте скопированное значение в *Settings → Secrets and variables → Actions → Secrets → New repository secret* с именем `DGIS_SDK_KEY_BASE64`. Сам файл и Base64 нельзя публиковать в Git или сообщениях.

## Backend на компьютере с эмулятором

Нужны Python 3.12+, Android Studio / SDK 35, JDK 17 и Gradle 8.13. Из корня проекта установите backend и запустите тесты:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e './backend[test]'
pytest backend/tests -q
```

На Windows PowerShell используйте `py -3 -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -e ".\backend[test]"` и `python -m pytest backend/tests -q`. Установленный у заказчика Python 3.13 подходит.

Для живого маршрута укажите в терминале backend четыре значения. Один ключ 2ГИС можно поставить в обе переменные только если для него подключены оба продукта:

```powershell
$env:OPENAI_API_KEY="<ключ OpenAI API>"
$env:OPENAI_MODEL="gpt-4o-mini"
$env:DGIS_PLACES_API_KEY="<ключ Places API 2ГИС>"
$env:DGIS_ROUTING_API_KEY="<ключ Routing API 2ГИС>"
.\.venv\Scripts\python.exe -m uvicorn gulyay.api:app --host 127.0.0.1 --port 8000
```

Проверьте в браузере компьютера `http://127.0.0.1:8000/health`: ответ должен содержать версию `0.5`. Окно PowerShell нужно оставить открытым во время проверки. Ключи не вставляйте в приложение, репозиторий или скриншоты; они хранятся только в окружении backend.

## APK для Android Emulator

Из корня проекта соберите отладочную сборку с адресом **запущенного на этом компьютере** backend. В bash:

```bash
DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000 gradle :app:assembleDebug
```

В PowerShell: `$env:DEBUG_BACKEND_BASE_URL="http://10.0.2.2:8000"; $env:DGIS_SDK_VERSION="13.6.0"; gradle :app:assembleDebug`. Установите `app/build/outputs/apk/debug/app-debug.apk` на эмулятор. В APK по умолчанию остаётся `https://example.invalid`: такая сборка может показать интерфейс, но не сможет построить маршрут. Специальный адрес `10.0.2.2` доступен только из Android Emulator на том же компьютере. Для backend на внешнем сервере вместо локального адреса задайте `BACKEND_BASE_URL=https://<ваш-домен>` при сборке; опубликованный сервер должен работать по HTTPS. Локальный HTTP разрешён только для `10.0.2.2` в отладочной сборке.

На GitHub Actions workflow **Verify and build APK** проверяет backend и собирает установочный APK в разделе **Artifacts** запуска. Чтобы APK работал с локальным backend эмулятора, задайте в *Settings → Secrets and variables → Actions → Variables* `DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000`; для карты добавьте секрет `DGIS_SDK_KEY_BASE64`. Для внешнего HTTPS-сервера используйте переменную `BACKEND_BASE_URL`. После успешной проверки этапа исходники можно отметить тегом `v0.5`; артефакт Action хранится 30 дней.

Карта и геопозиция описаны в `docs/MAP-0.5.md`; предыдущие этапы — в `docs/GEO-0.4.md`, `docs/STORAGE-0.4.1.md` и `docs/EDIT-0.4.2.md`. `/v1/routes/interpret` сохранён для отдельной проверки разбора, а нормативный `POST /v1/routes` строит маршрут только из ответов 2ГИС.

## Справочная документация

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Сеть Android Emulator](https://developer.android.com/studio/run/emulator-networking)
- [Android Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)
- [Android SDK 2ГИС и `dgissdk.key`](https://docs.2gis.com/en/android/sdk/start)
- [Примеры карты Android SDK 2ГИС](https://docs.2gis.com/en/android/sdk/examples/map)
- [Places API 2ГИС](https://docs.2gis.com/en/api/search/places/reference/3.0/items)
- [Получение объектов 2ГИС по идентификаторам](https://docs.2gis.com/en/api/search/places/reference/3.0/items/byid)
- [Routing API 2ГИС](https://docs.2gis.com/en/api/navigation/routing/reference/routing)
