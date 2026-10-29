#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p .devcontainer/logs backend/data
pid_file=".devcontainer/logs/backend.pid"
if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
  echo "Гуляй backend уже запущен (PID $(cat "$pid_file"))."
  exit 0
fi

export GULYAY_DB_PATH="${GULYAY_DB_PATH:-$PWD/backend/data/gulyay.sqlite3}"
nohup python -m uvicorn gulyay.api:app --app-dir backend --host 0.0.0.0 --port 8000 \
  > .devcontainer/logs/backend.log 2>&1 < /dev/null &
echo "$!" > "$pid_file"
echo "Гуляй backend запускается на порту 8000. Логи: .devcontainer/logs/backend.log"
echo "Для доступа из APK переведите порт 8000 в Public на вкладке PORTS."
