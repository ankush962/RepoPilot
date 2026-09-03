#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

LATEST="$(ls -1t "$BACKUP_DIR"/*.dump.gz 2>/dev/null | head -1 || true)"

if [[ -z "$LATEST" ]]; then
  echo "No backup found in $BACKUP_DIR"
  exit 1
fi

TEMP_CONTAINER="repopilot-restore-test-$$"

cleanup() {
  docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d   --name "$TEMP_CONTAINER"   -e POSTGRES_DB=restore_test   -e POSTGRES_USER=repopilot   -e POSTGRES_PASSWORD=restore_test_password   pgvector/pgvector:pg17 >/dev/null

for i in {1..30}; do
  if docker exec "$TEMP_CONTAINER" pg_isready       -U repopilot       -d restore_test >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

gunzip -c "$LATEST" | docker exec -i "$TEMP_CONTAINER"   pg_restore     -U repopilot     -d restore_test     --clean     --if-exists     --no-owner     --no-acl

COUNT="$(
  docker exec "$TEMP_CONTAINER" psql     -U repopilot     -d restore_test     -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
)"

echo "Restored public tables: $COUNT"

test "$COUNT" -gt 0
echo "Restore verification OK"
