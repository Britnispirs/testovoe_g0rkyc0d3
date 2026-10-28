#!/usr/bin/env bash
set -e

REPO_DIR="$HOME/testovoe_g0rkyc0d3"

CRON_JOB="* * * * * cd $REPO_DIR && git fetch origin main >/dev/null 2>&1 && [ \$(git rev-parse HEAD) != \$(git rev-parse origin/main) ] && git pull origin main && docker compose up -d --build >> $HOME/deploy.log 2>&1"

(crontab -l 2>/dev/null | grep -v "testovoe_g0rkyc0d3" ; echo "$CRON_JOB") | crontab -

echo "=== Автоматический деплой настроен! ==="
echo "Каждые 60 секунд сервер проверяет репозиторий и при появлении новых коммитов выполняет git pull и перезапуск контейнеров."
echo "Логи деплоя доступны в: $HOME/deploy.log"
