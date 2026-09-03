#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Compose validation =="
docker compose config >/dev/null
echo "OK"

echo "== Service status =="
docker compose ps

echo "== API health =="
curl -ksSf https://localhost:18443/api/health >/dev/null
echo "OK"

echo "== API readiness =="
curl -ksSf https://localhost:18443/api/ready >/dev/null
echo "OK"

echo "== Frontend HTTPS =="
curl -ksSf https://localhost:18443/ >/dev/null
echo "OK"

echo "== Direct API blocked =="
if curl -sSf http://localhost:8000/health >/dev/null 2>&1; then
  echo "FAIL: API is directly exposed"
  exit 1
fi
echo "OK"

echo "== Direct frontend blocked =="
if curl -sSf http://localhost:3000/ >/dev/null 2>&1; then
  echo "FAIL: frontend is directly exposed"
  exit 1
fi
echo "OK"

echo "== Backup script =="
test -x ops/backup-postgres.sh
echo "OK"

echo "== Restore script =="
test -x ops/verify-restore.sh
echo "OK"

echo "Production audit OK"
