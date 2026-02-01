#!/bin/bash
# =============================================================================
# Anki Sync Server - Backup Script
# =============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${SYNC_BASE:-/data}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="anki_backup_${TIMESTAMP}.tar.gz"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Send notification if enabled
notify() {
    if [ "$NOTIFY_ENABLED" = "true" ] && [ -n "$NOTIFY_WEBHOOK_URL" ]; then
        case "$NOTIFY_TYPE" in
            discord)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"content\": \"**Anki Backup**\n$1\"}" > /dev/null 2>&1 || true
                ;;
            telegram)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -d "text=Anki Backup: $1" > /dev/null 2>&1 || true
                ;;
            slack)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"text\": \"*Anki Backup*\n$1\"}" > /dev/null 2>&1 || true
                ;;
        esac
    fi
}

log "Starting backup..."

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Get data size before backup
DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 || echo "unknown")
log "Data directory size: $DATA_SIZE"

# Create compressed backup
cd "$DATA_DIR"
tar -czf "${BACKUP_DIR}/${BACKUP_FILE}" .

# Get backup size
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
log "Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Cleanup old backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "anki_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
log "Deleted $DELETED_COUNT old backup(s)"

# Count remaining backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/anki_backup_*.tar.gz 2>/dev/null | wc -l)
TOTAL_BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "unknown")

log "Backup complete. Total backups: $BACKUP_COUNT, Total size: $TOTAL_BACKUP_SIZE"

# Send notification
notify "✅ Backup complete\nFile: $BACKUP_FILE\nSize: $BACKUP_SIZE\nTotal backups: $BACKUP_COUNT"
