# Гуляй — Android Java и backend

Это исходники первого рабочего этапа `0.1` на пути к полному MVP `1.0`. Главный источник требований — `docs/source/2ГИС Системная аналитика.docx`, отдельные вопросы — `docs/DECISIONS.md`, последовательность выпусков — `docs/RELEASES.md`.

## Что уже можно проверить

Android-клиент показывает Тулу и Владимир, принимает текст, сохраняет введённое при повороте, отправляет гостевой запрос через HTTPS и отображает понятную ошибку. Backend отвечает на `/health`, `/v1/cities` и валидирует `/v1/routes`. Версия `0.1` никогда не выдаёт маршруты с вымышленными точками: запрос маршрута возвращает `GEO_UNAVAILABLE`, пока не реализованы и не проверены настоящие адаптеры 2ГИС. Карты, прохождения, входа, истории и партнёрских заведений в сборке `0.1` ещё нет.

## Backend

Нужны Python 3.12+. Из корня проекта:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e './backend[test]'
pytest backend/tests -q
uvicorn gulyay.api:app --host 127.0.0.1 --port 8000
```

Ключи backend должны поступать из окружения согласно `.env.example`; файл с реальными значениями не коммитится. Публикация сервера и закрытие доступа/журналирования потребуются до подключения реальных пользователей. `/docs` показывает текущий контракт FastAPI.

## Android и APK

Нужны Android Studio / SDK 35, JDK 17, Gradle 8.13. Запустите проект из корня в Android Studio или выполните `gradle :app:assembleDebug`. По умолчанию адрес сервера `https://example.invalid`; при сборке установите `BACKEND_BASE_URL=https://<ваш-домен>`. Реальный backend обязан быть доступен по HTTPS. Локальный HTTP не включён в manifest.

На GitHub Actions workflow `Verify and build APK` запускает backend-тесты и собирает `app-debug.apk`; артефакт назван по ветке или тегу. Для проверяемого этапа ставится тег `v0.1.0`, `v0.2.0` и далее после зелёной сборки. `DGIS_SDK_KEY_BASE64` — secret с содержимым файла `dgissdk.key`, кодированным base64, переменная `BACKEND_BASE_URL` — HTTPS-адрес сервера. До появления мобильной карты файл SDK не используется кодом `0.1`.

## Источники API

- [Android SDK и правила `dgissdk.key`](https://docs.2gis.com/en/android/sdk/start)
- [Places API](https://docs.2gis.com/en/api/search/places/reference/3.0/items)
- [Routing API](https://docs.2gis.com/en/api/navigation/routing/reference/routing)
- [Совместимость Android Gradle Plugin 8.13](https://developer.android.com/build/releases/agp-8-13-0-release-notes)
