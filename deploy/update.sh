#!/usr/bin/env bash
# Pull newer images and recreate the services whose image changed. Safe to run often, e.g. from cron:
#   */5 * * * * ~/docker/pod-manager/update.sh >> ~/.cache/pod-manager-update.log 2>&1
# Before production is recreated, its database is backed up to prod-data/backups/.
set -euo pipefail
cd "$(dirname "$0")"

running_image() { local c; c=$(docker compose ps -q "$1"); [[ -n "$c" ]] && docker inspect -f '{{.Image}}' "$c" || true; }

before_prod=$(running_image prod)
docker compose pull --quiet
after_prod=$(docker image inspect -f '{{.Id}}' "$(docker compose config --images prod | head -n1)" 2>/dev/null || true)

if [[ -n "$before_prod" && -n "$after_prod" && "$before_prod" != "$after_prod" && -f prod-data/pod.db ]]; then
  mkdir -p prod-data/backups
  stamp=$(date -u +%Y%m%d-%H%M%S)
  docker compose exec -T prod python -c \
    "import sqlite3; s=sqlite3.connect('/data/pod.db'); d=sqlite3.connect('/data/backups/pod-$stamp.db'); s.backup(d)"
  # Names sort by time (UTC stamp); keep the newest 10.
  find prod-data/backups -name 'pod-*.db' | sort | head -n -10 | xargs -r rm --
  echo "$(date -Is) backed up prod database before update"
fi

docker compose up -d --remove-orphans
docker image prune -f --filter "label=org.opencontainers.image.title=POD Manager" >/dev/null
echo "$(date -Is) prod=$(docker compose exec -T prod python -c 'import os;print(os.environ.get("APP_VERSION"))' 2>/dev/null || echo '?')" \
     "preview=$(docker compose exec -T preview python -c 'import os;print(os.environ.get("APP_VERSION"))' 2>/dev/null || echo '?')"
