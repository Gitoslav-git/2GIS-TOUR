# Гуляй — Android Java и backend

Версия `0.2.0` — проверяемый этап разработки полного MVP `1.0`. Главный источник требований — `docs/source/2ГИС Системная аналитика.docx`; решения и открытые вопросы записаны в `docs/DECISIONS.md`, границы выпусков — в `docs/RELEASES.md`. Для прибытия к точке принято N = 75 м.

## Что проверять в 0.2

Приложение позволяет выбрать Тулу или Владимир, написать пожелания и нажать **«Проверить пожелания»**. Backend отправляет текст в LLM и возвращает разобранные интересы, длительность, еду, прогулку с детьми и необычные места. Если длительность отсутствует, показывает 180 минут; при конфликте текста с явно заданным фильтром приоритет у фильтра. При другом городе или некорректной длительности просит уточнить запрос. Ошибки ключа, недоступной модели и неверного ответа показаны отдельно. Текст и результат сохраняются при повороте. Ключ LLM существует только в окружении backend.

Поиск реальных мест и пеших участков 2ГИС — следующий этап `0.3`. Сейчас `/v1/routes` честно возвращает `GEO_UNAVAILABLE`, а экран показывает **разбор пожеланий, не маршрут**. Карты, прохождения и партнёрских предложений в APK `0.2` ещё нет.

## Backend на компьютере с эмулятором

Нужны Python 3.12+, Android Studio / SDK 35, JDK 17 и Gradle 8.13. Из корня проекта установите backend и запустите тесты:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e './backend[test]'
pytest backend/tests -q
```

На Windows PowerShell используйте `py -3.12 -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -e ".\backend[test]"` и `python -m pytest backend/tests -q`.

Для *живого* разбора запроса укажите в терминале backend действующие `OPENAI_API_KEY` и `OPENAI_MODEL` (модель с поддержкой Structured Outputs). Например, в PowerShell: `$env:OPENAI_API_KEY="<ваш ключ>"` и `$env:OPENAI_MODEL="<модель из вашего аккаунта>"`. Запустите в том же терминале `uvicorn gulyay.api:app --host 127.0.0.1 --port 8000` и проверьте в браузере компьютера `http://127.0.0.1:8000/health`. Ключ не вставляйте в приложение, GitHub или скриншоты. Без ключа `/health` работает, а кнопка возвращает ошибку `LLM_UNAVAILABLE` — это ожидаемо.

## APK для Android Emulator

Из корня проекта соберите отладочную сборку с адресом **запущенного на этом компьютере** backend. В bash:

```bash
DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000 gradle :app:assembleDebug
```

В PowerShell: `$env:DEBUG_BACKEND_BASE_URL="http://10.0.2.2:8000"; gradle :app:assembleDebug`. Установите `app/build/outputs/apk/debug/app-debug.apk` на эмулятор. В APK по умолчанию остаётся `https://example.invalid`: такая сборка может показать интерфейс, но не сможет разобрать запрос. Специальный адрес `10.0.2.2` доступен только из Android Emulator на том же компьютере. Для backend на внешнем сервере вместо локального адреса задайте `BACKEND_BASE_URL=https://<ваш-домен>` при сборке; опубликованный сервер должен работать по HTTPS. Локальный HTTP разрешён только для `10.0.2.2` в отладочной сборке.

На GitHub Actions workflow **Verify and build APK** проверяет backend и собирает установочный APK в разделе **Artifacts** запуска. Чтобы скачать APK, который работает с локальным backend на вашем эмуляторе, задайте в репозитории *Settings → Secrets and variables → Actions → Variables* значение `DEBUG_BACKEND_BASE_URL=http://10.0.2.2:8000`, затем запустите workflow. Для внешнего HTTPS-сервера используйте переменную `BACKEND_BASE_URL`. Секрет `DGIS_SDK_KEY_BASE64` понадобится при подключении мобильной карты 2ГИС; значения всех переменных указаны в `.env.example`. После успешной проверки этапа можно пометить исходники тегом `v0.2.0`; артефакт Action хранится 30 дней и при необходимости сборку можно запустить снова.

Контракт тестового запроса и реакций на ошибки описан в `docs/INTERPRET-0.2.md`. Контракт системной аналитики для построения настоящего маршрута остаётся `POST /v1/routes`; `/v1/routes/interpret` — отдельная проверка этапа `0.2`, не замена построения.

## Справочная документация

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Сеть Android Emulator](https://developer.android.com/studio/run/emulator-networking)
- [Android Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)
- [Android SDK 2ГИС и `dgissdk.key`](https://docs.2gis.com/en/android/sdk/start)
