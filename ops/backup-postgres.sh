#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

mkdir -p "$BACKUP_DIR"

STAMP="$(date +"%Y%m%d_%H%M%S")"
FILE="$BACKUP_DIR/repopilot_${STAMP}.dump"

docker exec -i repopilot-db   pg_dump     -U "${POSTGRES_USER:-repopilot}"     -d "${POSTGRES_DB:-ai_copilot}"     -Fc > "$FILE"

gzip -f "$FILE"

echo "Backup written: ${FILE}.gz"
