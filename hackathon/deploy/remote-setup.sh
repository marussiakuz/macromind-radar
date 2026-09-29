#!/usr/bin/env bash
# Разворачивает публичный MVP на чистой Ubuntu 24.04.
#
# Запускается на сервере, после того как файлы скопированы в /opt/radar:
#   sudo bash /opt/radar/deploy/remote-setup.sh
#
# Идемпотентен: повторный запуск обновляет образ и перезапускает сервис, ничего не теряя.
# Состояние (учёт расходов, квота, сохранённые разборы) живёт в /opt/radar/radar-runs и
# переживает пересборку.
set -euo pipefail

APP=/opt/radar
UID_IN_CONTAINER=1000

say() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "нужен root: sudo bash $0"; exit 1; }
[ -f "$APP/docker-compose.yml" ] || { echo "нет $APP/docker-compose.yml — сначала скопируйте файлы"; exit 1; }
[ -f "$APP/ui/index.html" ] || { echo "нет $APP/ui/index.html — интерфейс не скопирован, адрес отдавал бы 404"; exit 1; }
[ -f "$APP/.env" ] || { echo "нет $APP/.env с ключами и RADAR_HOST"; exit 1; }
grep -q '^RADAR_HOST=..*' "$APP/.env" || { echo "в .env не задан RADAR_HOST — без имени Caddy не получит сертификат"; exit 1; }

say "Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
else
  echo "уже установлен: $(docker --version)"
fi
docker compose version >/dev/null 2>&1 || { echo "нет плагина docker compose"; exit 1; }

say "Состояние прогонов"
cd "$APP"
if [ -f runs-seed.tar.gz ]; then
  tar -xzf runs-seed.tar.gz
  echo "посылка распакована: $(ls radar-runs | wc -l) элементов в radar-runs"
  rm -f runs-seed.tar.gz
fi
mkdir -p radar-runs
# Приложение в контейнере работает не от root: без этого оно прочитает сохранённые
# разборы, но не сможет записать расход и квоту — и упадёт на первом живом прогоне.
chown -R "$UID_IN_CONTAINER:$UID_IN_CONTAINER" radar-runs
chmod 600 .env

say "Проверка конфигурации HTTPS"
# Ошибка в Caddyfile иначе выяснилась бы уже после остановки старого контейнера.
docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile

say "Сборка и запуск"
docker compose up -d --build

say "Ожидание готовности"
host=$(grep '^RADAR_HOST=' .env | cut -d= -f2-)
for i in $(seq 1 60); do
  if docker compose exec -T radar python -c "
import urllib.request, sys
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)
" >/dev/null 2>&1; then
    echo "сервис ответил через ~$((i * 5)) с"
    break
  fi
  sleep 5
done

say "Проверка"
docker compose exec -T radar python -c "
import json, urllib.request
for path in ('/api/health', '/api/limits'):
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=10) as r:
        print(path, json.dumps(json.load(r), ensure_ascii=False)[:400])
"
echo
echo "снаружи проверять так (сертификат выдаётся при первом обращении, это до минуты):"
echo "  curl -s https://$host/api/health"
echo "  curl -s https://$host/api/limits"
echo "  открыть в браузере: https://$host  и https://$host/docs"
echo
echo "если корзина модели пуста, записать пополнение:"
echo "  docker compose exec radar python -m radar.ledger topup --id ПОПОЛНЕНИЕ --llm 300 --reason 'MVP'"
