#!/bin/bash
# =============================================================================
# Anki Sync Server - Backup Script with S3 Support
# =============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${SYNC_BASE:-/data}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="anki_backup_${TIMESTAMP}.tar.gz"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [BACKUP] $*"
}

# Send notification
notify() {
    local message="$1"
    
    if [ "$NOTIFY_ENABLED" = "true" ] && [ -n "$NOTIFY_WEBHOOK_URL" ]; then
        case "$NOTIFY_TYPE" in
            discord)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"content\": \"**Anki Backup**\n$message\"}" > /dev/null 2>&1 &
                ;;
            telegram)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -d "text=Anki Backup: $message" > /dev/null 2>&1 &
                ;;
            slack)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"text\": \"*Anki Backup*\n$message\"}" > /dev/null 2>&1 &
                ;;
            ntfy)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Title: Anki Backup" \
                    -d "$message" > /dev/null 2>&1 &
                ;;
            *)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"title\": \"Anki Backup\", \"message\": \"$message\"}" > /dev/null 2>&1 &
                ;;
        esac
    fi
    
    if [ "$EMAIL_ENABLED" = "true" ] && [ -n "$EMAIL_TO" ]; then
        echo -e "Subject: Anki Backup\n\n$message" | msmtp "$EMAIL_TO" 2>/dev/null &
    fi
}

# Upload to S3/S3-compatible storage
upload_to_s3() {
    local file="$1"
    
    if [ "$S3_BACKUP_ENABLED" != "true" ] || [ -z "$S3_BUCKET" ]; then
        return 0
    fi
    
    log "Uploading to S3: $S3_BUCKET"
    
    python3 << EOF
import boto3
import os
import sys
from botocore.config import Config

endpoint = os.environ.get('S3_ENDPOINT', '')
bucket = os.environ.get('S3_BUCKET', '')
access_key = os.environ.get('S3_ACCESS_KEY', '')
secret_key = os.environ.get('S3_SECRET_KEY', '')
region = os.environ.get('S3_REGION', 'us-east-1')

if not bucket or not access_key or not secret_key:
    print("S3 credentials not fully configured")
    sys.exit(1)

config = Config(signature_version='s3v4')

try:
    if endpoint:
        s3 = boto3.client('s3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=config
        )
    else:
        s3 = boto3.client('s3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=config
        )

    local_file = "${BACKUP_DIR}/${BACKUP_FILE}"
    s3_key = "anki-backups/${BACKUP_FILE}"

    print(f"Uploading {local_file} to s3://{bucket}/{s3_key}")
    s3.upload_file(local_file, bucket, s3_key)
    print("Upload complete")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
    return $?
}

# Cleanup old S3 backups
cleanup_s3() {
    if [ "$S3_BACKUP_ENABLED" != "true" ] || [ -z "$S3_BUCKET" ]; then
        return 0
    fi
    
    log "Cleaning up old S3 backups..."
    
    python3 << EOF
import boto3
import os
from datetime import datetime, timedelta, timezone
from botocore.config import Config

endpoint = os.environ.get('S3_ENDPOINT', '')
bucket = os.environ.get('S3_BUCKET', '')
access_key = os.environ.get('S3_ACCESS_KEY', '')
secret_key = os.environ.get('S3_SECRET_KEY', '')
region = os.environ.get('S3_REGION', 'us-east-1')
retention_days = int(os.environ.get('BACKUP_RETENTION_DAYS', '7'))

config = Config(signature_version='s3v4')

try:
    if endpoint:
        s3 = boto3.client('s3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=config
        )
    else:
        s3 = boto3.client('s3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=config
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0

    response = s3.list_objects_v2(Bucket=bucket, Prefix='anki-backups/')
    if 'Contents' in response:
        for obj in response['Contents']:
            if obj['LastModified'] < cutoff:
                s3.delete_object(Bucket=bucket, Key=obj['Key'])
                print(f"Deleted: {obj['Key']}")
                deleted += 1
    print(f"Deleted {deleted} old S3 backups")
except Exception as e:
    print(f"S3 cleanup error: {e}")
EOF
}

# =============================================================================
# Main
# =============================================================================

log "Starting backup..."

mkdir -p "$BACKUP_DIR"

# Get data size
DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 || echo "unknown")
log "Data directory size: $DATA_SIZE"

# Create backup
cd "$DATA_DIR"
tar -czf "${BACKUP_DIR}/${BACKUP_FILE}" .

BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
log "Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Update sync count metric
SYNC_COUNT=$(cat /var/lib/anki/sync_count.txt 2>/dev/null || echo 0)
echo "$SYNC_COUNT" > /var/lib/anki/sync_count.txt

# Upload to S3
S3_STATUS="N/A"
if [ "$S3_BACKUP_ENABLED" = "true" ]; then
    if upload_to_s3; then
        S3_STATUS="OK"
        cleanup_s3
    else
        S3_STATUS="FAILED"
    fi
fi

# Cleanup old local backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "anki_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete -print 2>/dev/null | wc -l || echo 0)
log "Deleted $DELETED_COUNT old local backup(s)"

# Stats
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/anki_backup_*.tar.gz 2>/dev/null | wc -l || echo 0)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "unknown")

log "Backup complete. Total: $BACKUP_COUNT backups, $TOTAL_SIZE"

# Send notification
notify "Backup complete
File: $BACKUP_FILE
Size: $BACKUP_SIZE
S3: $S3_STATUS
Total: $BACKUP_COUNT backups"

exit 0
