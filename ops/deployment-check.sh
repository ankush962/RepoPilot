#!/usr/bin/env bash
set -euo pipefail

echo "== Production deployment configuration =="

missing=0

check_required() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "MISSING: $name"
    missing=1
  else
    echo "OK: $name"
  fi
}

check_required "PUBLIC_DOMAIN"
check_required "OFFSITE_BACKUP_URL"

if [[ "${PUBLIC_DOMAIN:-}" == "localhost" ]]; then
  echo "WARN: PUBLIC_DOMAIN is still localhost"
fi

if [[ "${OFFSITE_BACKUP_URL:-}" == *"example"* || \
      "${OFFSITE_BACKUP_URL:-}" == *"change-this"* ]]; then
  echo "WARN: OFFSITE_BACKUP_URL still looks like a placeholder"
fi

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Deployment configuration incomplete."
  exit 1
fi

echo
echo "Deployment configuration ready."
