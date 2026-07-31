#!/usr/bin/env bash
# Nightly Postgres dump for the DigitalOcean droplet deployment.
# Run via cron on the host (not inside a container) so it survives
# `docker compose down` / rebuilds:
#
#   0 2 * * * /opt/auditos/scripts/backup_postgres.sh >> /var/log/auditos-backup.log 2>&1
#
# Requires: BACKUP_DIR writable, and rclone configured if uploading offsite
# (recommended — a droplet-only backup dies with the droplet).
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/opt/auditos/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/auditos_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U auditos auditos | gzip > "${DUMP_FILE}"

echo "Backup written: ${DUMP_FILE} ($(du -h "${DUMP_FILE}" | cut -f1))"

# Optional offsite copy — uncomment and configure `rclone config` once,
# pointing a remote named "do-spaces" at a DigitalOcean Space (or any
# rclone-supported target). Local-disk-only backups don't protect you
# if the droplet itself is lost.
# rclone copy "${DUMP_FILE}" do-spaces:auditos-backups/

find "${BACKUP_DIR}" -name "auditos_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
