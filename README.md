# Гуляй — Android Java и backend

Версия `0.3.0` — проверяемый этап разработки полного MVP `1.0`. Главный источник требований — `docs/source/2ГИС Системная аналитика.docx`; решения и открытые вопросы записаны в `docs/DECISIONS.md`, границы выпусков — в `docs/RELEASES.md`. Для прибытия к точке принято N = 75 м.

## Что проверять в 0.3

Приложение позволяет выбрать Тулу или Владимир, написать пожелания и нажать **«Построить маршрут»**. Backend разбирает запрос через LLM, ищет настоящие места через Places API 2ГИС и получает подробный пеший путь до каждой включённой точки через Routing API 2ГИС. Android показывает порядок точек, длительность посещений, расстояние и время переходов, доступность по расписанию и предупреждения. Запрос «в центре» отображается и ограничивает поиск центральной зоной.

В 0.3 порядок основан на релевантности выдачи 2ГИС; полная оптимизация последовательности будет в 0.4. Встроенной карты, прохождения и партнёрских предложений пока нет. Время посещения — явно показанная временная оценка 40/60 минут, потому что оно не поступает из 2ГИС; правило вынесено в `VISIT-01`.

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

Проверьте в браузере компьютера `http://127.0.0.1:8000/health`: ответ должен содержать версию `0.3.0`. Окно PowerShell нужно оставить открытым во время проверки. Ключи не вставляйте в приложение, репозиторий или скриншоты; они хранятся только в окружении backend.

## APK для Android Emulator

Из корня проекта соберите отладочную сборку с адресом **запущенного на этом компьютере** backend. В bash:

```bash
DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000 gradle :app:assembleDebug
```

В PowerShell: `$env:DEBUG_BACKEND_BASE_URL="http://10.0.2.2:8000"; gradle :app:assembleDebug`. Установите `app/build/outputs/apk/debug/app-debug.apk` на эмулятор. В APK по умолчанию остаётся `https://example.invalid`: такая сборка может показать интерфейс, но не сможет построить маршрут. Специальный адрес `10.0.2.2` доступен только из Android Emulator на том же компьютере. Для backend на внешнем сервере вместо локального адреса задайте `BACKEND_BASE_URL=https://<ваш-домен>` при сборке; опубликованный сервер должен работать по HTTPS. Локальный HTTP разрешён только для `10.0.2.2` в отладочной сборке.

На GitHub Actions workflow **Verify and build APK** проверяет backend и собирает установочный APK в разделе **Artifacts** запуска. Чтобы скачать APK, который работает с локальным backend на вашем эмуляторе, задайте в репозитории *Settings → Secrets and variables → Actions → Variables* значение `DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000`, затем запустите workflow. Для внешнего HTTPS-сервера используйте переменную `BACKEND_BASE_URL`. Секрет `DGIS_SDK_KEY_BASE64` понадобится при подключении мобильной карты 2ГИС; значения всех переменных указаны в `.env.example`. После успешной проверки этапа можно пометить исходники тегом `v0.3.0`; артефакт Action хранится 30 дней и при необходимости сборку можно запустить снова.

Правила интеграции описаны в `docs/GEO-0.3.md`. `/v1/routes/interpret` сохранён для отдельной проверки разбора, а нормативный `POST /v1/routes` теперь строит маршрут только из ответов 2ГИС.

## Справочная документация

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Сеть Android Emulator](https://developer.android.com/studio/run/emulator-networking)
- [Android Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)
- [Android SDK 2ГИС и `dgissdk.key`](https://docs.2gis.com/en/android/sdk/start)
- [Places API 2ГИС](https://docs.2gis.com/en/api/search/places/reference/3.0/items)
- [Routing API 2ГИС](https://docs.2gis.com/en/api/navigation/routing/reference/routing)
