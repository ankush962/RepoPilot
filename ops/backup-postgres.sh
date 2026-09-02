#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"

mkdir -p "$BACKUP_DIR"

docker compose exec -T db \
  pg_dump \
  -U "${POSTGRES_USER:-repopilot}" \
  -d "${POSTGRES_DB:-ai_copilot}" \
  -Fc \
  > "${BACKUP_DIR}/ai_copilot_${TIMESTAMP}.dump"

echo "Backup created:"
echo "${BACKUP_DIR}/ai_copilot_${TIMESTAMP}.dump"
