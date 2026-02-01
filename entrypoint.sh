#!/bin/bash
set -e

# =============================================================================
# Anki Sync Server Enhanced - Entrypoint
# =============================================================================

# -----------------------------------------------------------------------------
# Handle PUID/PGID for file permissions
# -----------------------------------------------------------------------------
PUID=${PUID:-1000}
PGID=${PGID:-1000}

if [ "$PUID" != "1000" ] || [ "$PGID" != "1000" ]; then
    groupmod -o -g "$PGID" anki 2>/dev/null || true
    usermod -o -u "$PUID" anki 2>/dev/null || true
    chown -R anki:anki /data /backups /config 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Configuration with defaults
# -----------------------------------------------------------------------------
export SYNC_BASE="${SYNC_BASE:-/data}"
export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-8080}"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export TZ="${TZ:-UTC}"

# Backup settings
export BACKUP_ENABLED="${BACKUP_ENABLED:-false}"
export BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-0 3 * * *}"
export BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# TLS settings
export TLS_ENABLED="${TLS_ENABLED:-false}"
export TLS_CERT="${TLS_CERT:-/config/cert.pem}"
export TLS_KEY="${TLS_KEY:-/config/key.pem}"

# Notification settings
export NOTIFY_ENABLED="${NOTIFY_ENABLED:-false}"
export NOTIFY_WEBHOOK_URL="${NOTIFY_WEBHOOK_URL:-}"
export NOTIFY_TYPE="${NOTIFY_TYPE:-discord}"

# Metrics settings
export METRICS_ENABLED="${METRICS_ENABLED:-false}"
export METRICS_PORT="${METRICS_PORT:-9090}"

# Version info
ANKI_VERSION=$(cat /anki_version.txt 2>/dev/null || echo "unknown")

# -----------------------------------------------------------------------------
# Logging functions
# -----------------------------------------------------------------------------
log_level_num() {
    case "$1" in
        debug) echo 0 ;;
        info)  echo 1 ;;
        warn)  echo 2 ;;
        error) echo 3 ;;
        *)     echo 1 ;;
    esac
}

CURRENT_LOG_LEVEL=$(log_level_num "$LOG_LEVEL")

log() {
    local level="$1"
    shift
    local level_num=$(log_level_num "$level")
    if [ "$level_num" -ge "$CURRENT_LOG_LEVEL" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level^^}] $*"
    fi
}

log_debug() { log debug "$@"; }
log_info()  { log info "$@"; }
log_warn()  { log warn "$@"; }
log_error() { log error "$@"; }

# -----------------------------------------------------------------------------
# Notification function
# -----------------------------------------------------------------------------
send_notification() {
    local message="$1"
    local title="${2:-Anki Sync Server}"
    
    if [ "$NOTIFY_ENABLED" != "true" ] || [ -z "$NOTIFY_WEBHOOK_URL" ]; then
        return
    fi
    
    log_debug "Sending notification: $message"
    
    case "$NOTIFY_TYPE" in
        discord)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"content\": \"**${title}**\n${message}\"}" > /dev/null 2>&1 || true
            ;;
        telegram)
            # NOTIFY_WEBHOOK_URL should be: https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -d "text=${title}: ${message}" > /dev/null 2>&1 || true
            ;;
        slack)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"text\": \"*${title}*\n${message}\"}" > /dev/null 2>&1 || true
            ;;
        generic)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"title\": \"${title}\", \"message\": \"${message}\"}" > /dev/null 2>&1 || true
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Graceful shutdown handler
# -----------------------------------------------------------------------------
shutdown_handler() {
    log_info "Received shutdown signal, stopping gracefully..."
    send_notification "Server shutting down" "Anki Sync Server"
    
    # Kill the sync server process
    if [ -n "$SYNC_PID" ]; then
        kill -TERM "$SYNC_PID" 2>/dev/null || true
        wait "$SYNC_PID" 2>/dev/null || true
    fi
    
    # Kill metrics server if running
    if [ -n "$METRICS_PID" ]; then
        kill -TERM "$METRICS_PID" 2>/dev/null || true
    fi
    
    # Stop cron if running
    if [ -f /var/run/crond.pid ]; then
        kill $(cat /var/run/crond.pid) 2>/dev/null || true
    fi
    
    log_info "Shutdown complete"
    exit 0
}

trap shutdown_handler SIGTERM SIGINT SIGQUIT

# -----------------------------------------------------------------------------
# Docker secrets support
# -----------------------------------------------------------------------------
for var in $(env | grep -E '^SYNC_USER[0-9]+_FILE=' | sort); do
    name="${var%%=*}"
    file="${var#*=}"
    base_name="${name%_FILE}"
    if [ -f "$file" ]; then
        export "$base_name"="$(cat "$file")"
        log_debug "Loaded secret from $file"
    else
        log_warn "Secret file not found: $file"
    fi
done

# Load webhook from file if specified
if [ -n "$NOTIFY_WEBHOOK_URL_FILE" ] && [ -f "$NOTIFY_WEBHOOK_URL_FILE" ]; then
    export NOTIFY_WEBHOOK_URL="$(cat "$NOTIFY_WEBHOOK_URL_FILE")"
    log_debug "Loaded webhook URL from file"
fi

# -----------------------------------------------------------------------------
# Build user list
# -----------------------------------------------------------------------------
USERS=""
USER_COUNT=0
USER_NAMES=""

for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sort -t= -k1 -V); do
    value="${var#*=}"
    username="${value%%:*}"
    
    if [ -n "$USERS" ]; then
        USERS="$USERS,$value"
        USER_NAMES="$USER_NAMES, $username"
    else
        USERS="$value"
        USER_NAMES="$username"
    fi
    USER_COUNT=$((USER_COUNT + 1))
done

if [ -z "$USERS" ]; then
    log_error "No users defined. Set SYNC_USER1=username:password"
    exit 1
fi

export SYNC_USER="$USERS"

# -----------------------------------------------------------------------------
# Setup automated backups
# -----------------------------------------------------------------------------
if [ "$BACKUP_ENABLED" = "true" ]; then
    log_info "Setting up automated backups (schedule: $BACKUP_SCHEDULE)"
    
    # Create cron job
    echo "$BACKUP_SCHEDULE /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1" > /etc/crontabs/root
    
    # Start cron daemon
    crond -b -l 8
    
    log_info "Backup cron started"
fi

# -----------------------------------------------------------------------------
# Setup metrics endpoint
# -----------------------------------------------------------------------------
if [ "$METRICS_ENABLED" = "true" ]; then
    log_info "Starting metrics server on port $METRICS_PORT"
    
    START_TIME=$(date +%s)
    
    # Start simple metrics server in background
    (
        while true; do
            # Collect metrics
            USERS_TOTAL=$USER_COUNT
            DATA_SIZE=$(du -sb "$SYNC_BASE" 2>/dev/null | cut -f1 || echo 0)
            BACKUP_COUNT=$(ls -1 /backups/*.tar.gz 2>/dev/null | wc -l || echo 0)
            UPTIME=$(($(date +%s) - START_TIME))
            
            # Create metrics response
            METRICS="# HELP anki_sync_users_total Total number of configured users
# TYPE anki_sync_users_total gauge
anki_sync_users_total $USERS_TOTAL

# HELP anki_sync_data_bytes Total data size in bytes
# TYPE anki_sync_data_bytes gauge
anki_sync_data_bytes $DATA_SIZE

# HELP anki_sync_backup_count Number of backup files
# TYPE anki_sync_backup_count gauge
anki_sync_backup_count $BACKUP_COUNT

# HELP anki_sync_uptime_seconds Server uptime in seconds
# TYPE anki_sync_uptime_seconds counter
anki_sync_uptime_seconds $UPTIME

# HELP anki_sync_info Server information
# TYPE anki_sync_info gauge
anki_sync_info{version=\"$ANKI_VERSION\"} 1
"
            # Simple HTTP server using netcat
            echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n$METRICS" | nc -l -p "$METRICS_PORT" -q 1 > /dev/null 2>&1 || true
        done
    ) &
    METRICS_PID=$!
fi

# -----------------------------------------------------------------------------
# Create version endpoint file
# -----------------------------------------------------------------------------
mkdir -p /tmp/anki-info
cat > /tmp/anki-info/version.json << VEOF
{
    "anki_version": "$ANKI_VERSION",
    "server": "anki-sync-server-enhanced",
    "users": $USER_COUNT,
    "backup_enabled": $BACKUP_ENABLED,
    "tls_enabled": $TLS_ENABLED,
    "metrics_enabled": $METRICS_ENABLED
}
VEOF

# -----------------------------------------------------------------------------
# Print startup banner
# -----------------------------------------------------------------------------
START_TIME=$(date +%s)

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           Anki Sync Server Enhanced                          ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  %-60s ║\n" "Version:     $ANKI_VERSION"
printf "║  %-60s ║\n" "Host:        ${SYNC_HOST}:${SYNC_PORT}"
printf "║  %-60s ║\n" "Users:       ${USER_COUNT} (${USER_NAMES})"
printf "║  %-60s ║\n" "Data:        ${SYNC_BASE}"
printf "║  %-60s ║\n" "Log Level:   ${LOG_LEVEL}"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Features:                                                   ║"
printf "║    - Backups:     %-42s ║\n" "$([ "$BACKUP_ENABLED" = "true" ] && echo "Enabled ($BACKUP_SCHEDULE)" || echo "Disabled")"
printf "║    - Metrics:     %-42s ║\n" "$([ "$METRICS_ENABLED" = "true" ] && echo "Enabled (port $METRICS_PORT)" || echo "Disabled")"
printf "║    - TLS:         %-42s ║\n" "$([ "$TLS_ENABLED" = "true" ] && echo "Enabled" || echo "Disabled")"
printf "║    - Alerts:      %-42s ║\n" "$([ "$NOTIFY_ENABLED" = "true" ] && echo "Enabled ($NOTIFY_TYPE)" || echo "Disabled")"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# -----------------------------------------------------------------------------
# Send startup notification
# -----------------------------------------------------------------------------
send_notification "Server started with $USER_COUNT users" "Anki Sync Server"

# -----------------------------------------------------------------------------
# Start the sync server
# -----------------------------------------------------------------------------
log_info "Starting Anki sync server..."

if [ "$TLS_ENABLED" = "true" ] && [ -f "$TLS_CERT" ] && [ -f "$TLS_KEY" ]; then
    log_info "TLS enabled, using certificates from $TLS_CERT"
    log_warn "Native TLS not yet supported, use reverse proxy (nginx/traefik) for HTTPS"
fi

# Run sync server in background and capture PID
anki-sync-server &
SYNC_PID=$!

log_info "Sync server started with PID $SYNC_PID"

# Wait for the sync server process
wait "$SYNC_PID"
EXIT_CODE=$?

log_info "Sync server exited with code $EXIT_CODE"
send_notification "Server stopped (exit code: $EXIT_CODE)" "Anki Sync Server"

exit $EXIT_CODE
