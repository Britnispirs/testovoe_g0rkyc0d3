#!/usr/bin/env bash
set -e

if [ "$EUID" -ne 0 ]; then
  echo "Пожалуйста, запустите скрипт с правами root: sudo bash deploy/setup_vps.sh"
  exit 1
fi

echo "=== Обновление пакетов и установка зависимостей ==="
apt-get update -y
apt-get install -y curl git ufw

if ! command -v docker &> /dev/null; then
    echo "=== Установка Docker ==="
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

echo "=== Настройка фаервола UFW ==="
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw --force enable

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Создан файл .env. Пожалуйста, укажите ваши API ключи:"
    echo "nano .env"
fi

mkdir -p backend/data
chmod 777 backend/data

echo "=== Сборка и запуск контейнеров ==="
docker compose build
docker compose up -d

echo "=== Статус контейнеров ==="
docker compose ps

echo "Готово! Сервис доступен на http://$(curl -s ifconfig.me):8000"
