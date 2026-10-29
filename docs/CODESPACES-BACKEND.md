# Запуск backend через GitHub Codespaces

Это **временный тестовый сервер**, а не круглосуточный хостинг. Для этого режима
не нужно запускать backend на домашнем компьютере.

## Запуск

1. Откройте репозиторий на GitHub → **Code** → **Codespaces** →
   **Create codespace on main**. GitHub создаст окружение Python 3.12,
   установит backend и автоматически запустит его на порту **8000**.
2. Добавьте ключи как **Codespaces secrets** в настройках GitHub
   (Settings → Codespaces → Secrets): `OPENAI_API_KEY`,
   `DGIS_PLACES_API_KEY`, `DGIS_ROUTING_API_KEY`.
   После изменения секретов остановите и перезапустите Codespace.
   **Не вставляйте секреты в файлы репозитория или журналы.**
3. В открытом Codespace перейдите на вкладку **PORTS**. Для порта **8000**
   выберите **Port Visibility → Public**. Это необходимо, чтобы APK на телефоне
   мог обращаться к API без GitHub-авторизации.
   Публичный порт доступен любому, кто узнает его URL, поэтому используйте
   только для ограниченного тестирования. После перезапуска видимость
   порта может снова стать Private.
4. Скопируйте HTTPS-адрес порта, например
   `https://<codespace-name>-8000.app.github.dev`. Откройте
   `<адрес>/health`, чтобы убедиться, что backend отвечает.
5. В GitHub репозитории → **Settings → Secrets and variables → Actions →
   Variables** установите `BACKEND_BASE_URL` в **этот адрес без /health**.
   Запустите **Actions → Verify and build APK → Run workflow** на `main`
   и скачайте новый debug APK из артефактов сборки.
   Уже собранный APK не узнаёт новый адрес автоматически.
6. При остановке Codespace нажмите **Resume**. Встроенный
   `postStartCommand` снова запускает backend.
   Для диагностики: `tail -n 100 .devcontainer/logs/backend.log`.

## Ограничения

- GitHub Codespaces останавливается при бездействии и имеет лимиты использования.
- Backend хранит SQLite-файл в рабочем пространстве Codespace:
  перезапуск процесса его сохраняет, но удаление Codespace удалит данные.
- Публичный порт **не является защищённым production API**; текущие ограничения
  запросов в приложении не заменяют полноценную защиту и мониторинг.
- Для обычных пользователей без доступа к GitHub лучше разворачивать backend
  на отдельном хостинге с постоянной базой данных. Codespaces — для
  испытания APK разработчиком.

Подробнее: https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
