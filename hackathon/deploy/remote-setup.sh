#!/usr/bin/env bash
# Запуск из клонированного репозитория; Docker и Compose должны быть установлены.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"
command -v docker >/dev/null || { echo "Установите Docker Engine и Compose."; exit 1; }
docker compose version >/dev/null
[ -f .env ] || { echo "Скопируйте .env.example в .env и задайте RADAR_HOST."; exit 1; }
chmod 600 .env
docker compose -f docker-compose.yml -f hackathon/docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f hackathon/docker-compose.yml up -d --build
docker compose -f docker-compose.yml -f hackathon/docker-compose.yml ps
