#!/usr/bin/env bash
set -e

HOST="${VPS_HOST:-root@31.77.203.213}"
REMOTE_DIR="~/testovoe_g0rkyc0d3"

echo "=== 1. Отправка изменений в Git ==="
git push origin main

echo "=== 2. Обновление на сервере $HOST ==="
ssh -t "$HOST" "cd $REMOTE_DIR && git pull origin main && docker compose up -d --build && docker compose ps"

echo "=== Готово! Сервер обновлен ==="
