#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${1:?Usage: ops/offsite-backup.sh <backup-file>}"
OFFSITE_BACKUP_URL="${OFFSITE_BACKUP_URL:-}"

if [[ -z "$OFFSITE_BACKUP_URL" ]]; then
  echo "OFFSITE_BACKUP_URL is not configured."
  echo "Upload the backup to S3-compatible/object storage using your provider's CLI."
  exit 2
fi

curl --fail --retry 3 --upload-file "$BACKUP_FILE" "$OFFSITE_BACKUP_URL"
echo "Off-site backup upload completed."
