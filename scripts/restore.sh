#!/bin/bash
# =============================================================================
# Anki Sync Server - Restore Script
# =============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${SYNC_BASE:-/data}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [RESTORE] $*"
}

usage() {
    cat << EOF
Usage: restore.sh [OPTIONS] [backup_file]

Restore Anki sync server data from a backup.

Options:
  -l, --list       List available local backups
  -L, --list-s3    List available S3 backups
  -s, --s3         Download and restore from S3
  -d, --download   Download from S3 only (don't restore)
  -f, --force      Skip confirmation prompt
  -h, --help       Show this help message

Examples:
  restore.sh --list
  restore.sh --list-s3
  restore.sh anki_backup_20240101_030000.tar.gz
  restore.sh --s3 anki_backup_20240101_030000.tar.gz
  restore.sh --download anki_backup_20240101_030000.tar.gz
EOF
}

list_local_backups() {
    echo ""
    echo "Local backups in $BACKUP_DIR:"
    echo "============================================"
    if ls "$BACKUP_DIR"/anki_backup_*.tar.gz 1>/dev/null 2>&1; then
        for f in $(ls -1t "$BACKUP_DIR"/anki_backup_*.tar.gz); do
            size=$(du -h "$f" | cut -f1)
            date=$(stat -c %y "$f" | cut -d. -f1)
            name=$(basename "$f")
            echo "  $name  ($size)  $date"
        done
    else
        echo "  No backups found."
    fi
    echo ""
}

list_s3_backups() {
    if [ "$S3_BACKUP_ENABLED" != "true" ] || [ -z "$S3_BUCKET" ]; then
        echo "S3 backup not configured."
        return 1
    fi
    
    echo ""
    echo "S3 backups in $S3_BUCKET:"
    echo "============================================"
    
    python3 << 'EOF'
import boto3
import os
from botocore.config import Config

endpoint = os.environ.get('S3_ENDPOINT', '')
bucket = os.environ.get('S3_BUCKET', '')
access_key = os.environ.get('S3_ACCESS_KEY', '')
secret_key = os.environ.get('S3_SECRET_KEY', '')
region = os.environ.get('S3_REGION', 'us-east-1')

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

    response = s3.list_objects_v2(Bucket=bucket, Prefix='anki-backups/')
    if 'Contents' in response:
        for obj in sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True):
            size_mb = obj['Size'] / (1024 * 1024)
            name = obj['Key'].replace('anki-backups/', '')
            date = obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {name}  ({size_mb:.1f} MB)  {date}")
    else:
        print("  No backups found.")
except Exception as e:
    print(f"  Error: {e}")
EOF
    echo ""
}

download_from_s3() {
    local backup_file="$1"
    local dest="${BACKUP_DIR}/${backup_file}"
    
    log "Downloading $backup_file from S3..."
    
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

    s3_key = "anki-backups/${backup_file}"
    local_file = "${dest}"

    print(f"Downloading s3://{bucket}/{s3_key}")
    s3.download_file(bucket, s3_key, local_file)
    print(f"Downloaded to {local_file}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
    return $?
}

do_restore() {
    local backup_path="$1"
    
    log "Restoring from $(basename "$backup_path")..."
    
    # Create safety backup
    SAFETY_BACKUP="pre_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
    if [ -d "$DATA_DIR" ] && [ "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
        log "Creating safety backup: $SAFETY_BACKUP"
        cd "$DATA_DIR"
        tar -czf "${BACKUP_DIR}/${SAFETY_BACKUP}" . 2>/dev/null || true
    fi
    
    # Clear and restore
    log "Clearing current data..."
    rm -rf "${DATA_DIR:?}"/* 2>/dev/null || true
    
    log "Extracting backup..."
    tar -xzf "$backup_path" -C "$DATA_DIR"
    
    # Fix permissions
    chown -R anki:anki "$DATA_DIR" 2>/dev/null || true
    
    log "Restore complete!"
    [ -f "${BACKUP_DIR}/${SAFETY_BACKUP}" ] && log "Safety backup: $SAFETY_BACKUP"
    echo ""
    echo "IMPORTANT: Restart the container to apply changes."
}

# =============================================================================
# Parse arguments
# =============================================================================

LIST_LOCAL=false
LIST_S3=false
FROM_S3=false
DOWNLOAD_ONLY=false
FORCE=false
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--list)
            LIST_LOCAL=true
            shift
            ;;
        -L|--list-s3)
            LIST_S3=true
            shift
            ;;
        -s|--s3)
            FROM_S3=true
            shift
            ;;
        -d|--download)
            DOWNLOAD_ONLY=true
            FROM_S3=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# List backups
if [ "$LIST_LOCAL" = "true" ] || [ "$LIST_S3" = "true" ]; then
    [ "$LIST_LOCAL" = "true" ] && list_local_backups
    [ "$LIST_S3" = "true" ] && list_s3_backups
    exit 0
fi

# No file specified - show both lists
if [ -z "$BACKUP_FILE" ]; then
    list_local_backups
    list_s3_backups
    echo "Usage: restore.sh [backup_file]"
    exit 0
fi

# Download from S3 if requested
if [ "$FROM_S3" = "true" ]; then
    download_from_s3 "$BACKUP_FILE" || exit 1
    [ "$DOWNLOAD_ONLY" = "true" ] && { log "Download complete."; exit 0; }
fi

# Check backup exists
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"
if [ ! -f "$BACKUP_PATH" ]; then
    log "Error: Backup not found: $BACKUP_PATH"
    list_local_backups
    exit 1
fi

# Confirmation
if [ "$FORCE" != "true" ]; then
    echo ""
    echo "WARNING: This will overwrite all data in $DATA_DIR"
    echo "Backup: $BACKUP_PATH"
    echo ""
    read -p "Proceed? (yes/no): " confirm
    [ "$confirm" != "yes" ] && { echo "Cancelled."; exit 0; }
fi

do_restore "$BACKUP_PATH"
