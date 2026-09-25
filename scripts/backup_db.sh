#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
temporary_file="$(mktemp "backups/sapartravel-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
trap 'rm -f "$temporary_file"' EXIT
docker compose exec -T db pg_dump -U sapar -d sapartravel --format=custom > "$temporary_file"
if [[ ! -s "$temporary_file" ]]; then
  echo "Backup failed: empty archive." >&2
  exit 1
fi
backup_file="${temporary_file}.dump"
mv "$temporary_file" "$backup_file"
echo "Backup saved to $backup_file"
