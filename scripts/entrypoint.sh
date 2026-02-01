#!/bin/bash
set -e

# =============================================================================
# Anki Sync Server Enhanced - Entrypoint
# =============================================================================

# -----------------------------------------------------------------------------
# Configuration with defaults
# -----------------------------------------------------------------------------

# Core settings
export SYNC_BASE="${SYNC_BASE:-/data}"
export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-8080}"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export TZ="${TZ:-UTC}"

# File permissions
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Password hashing (compatible with official Anki)
export PASSWORDS_HASHED="${PASSWORDS_HASHED:-0}"

# Backup settings
export BACKUP_ENABLED="${BACKUP_ENABLED:-false}"
export BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-0 3 * * *}"
export BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# S3 backup settings
export S3_BACKUP_ENABLED="${S3_BACKUP_ENABLED:-false}"
export S3_ENDPOINT="${S3_ENDPOINT:-}"
export S3_BUCKET="${S3_BUCKET:-}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-}"
export S3_REGION="${S3_REGION:-us-east-1}"

# Notification settings (webhook)
export NOTIFY_ENABLED="${NOTIFY_ENABLED:-false}"
export NOTIFY_WEBHOOK_URL="${NOTIFY_WEBHOOK_URL:-}"
export NOTIFY_TYPE="${NOTIFY_TYPE:-discord}"

# Email notification settings
export EMAIL_ENABLED="${EMAIL_ENABLED:-false}"
export EMAIL_HOST="${EMAIL_HOST:-}"
export EMAIL_PORT="${EMAIL_PORT:-587}"
export EMAIL_USER="${EMAIL_USER:-}"
export EMAIL_PASS="${EMAIL_PASS:-}"
export EMAIL_FROM="${EMAIL_FROM:-}"
export EMAIL_TO="${EMAIL_TO:-}"
export EMAIL_TLS="${EMAIL_TLS:-on}"

# Metrics settings
export METRICS_ENABLED="${METRICS_ENABLED:-false}"
export METRICS_PORT="${METRICS_PORT:-9090}"

# Dashboard settings
export DASHBOARD_ENABLED="${DASHBOARD_ENABLED:-false}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-8081}"
export DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"

# Rate limiting settings
export RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-false}"
export RATE_LIMIT_REQUESTS="${RATE_LIMIT_REQUESTS:-100}"
export RATE_LIMIT_WINDOW="${RATE_LIMIT_WINDOW:-60}"

# Fail2ban settings
export FAIL2BAN_ENABLED="${FAIL2BAN_ENABLED:-false}"
export FAIL2BAN_MAX_RETRIES="${FAIL2BAN_MAX_RETRIES:-5}"
export FAIL2BAN_BAN_TIME="${FAIL2BAN_BAN_TIME:-3600}"
export FAIL2BAN_FIND_TIME="${FAIL2BAN_FIND_TIME:-600}"

# Sync logging
export SYNC_LOGGING_ENABLED="${SYNC_LOGGING_ENABLED:-true}"

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

# Log to sync log file
log_sync() {
    if [ "$SYNC_LOGGING_ENABLED" = "true" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> /var/log/anki/sync.log
    fi
}

# Log auth attempts (for fail2ban)
log_auth() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> /var/log/anki/auth.log
}

# -----------------------------------------------------------------------------
# Handle PUID/PGID for file permissions
# -----------------------------------------------------------------------------
setup_permissions() {
    if [ "$PUID" != "1000" ] || [ "$PGID" != "1000" ]; then
        log_info "Setting PUID=$PUID PGID=$PGID"
        groupmod -o -g "$PGID" anki 2>/dev/null || true
        usermod -o -u "$PUID" anki 2>/dev/null || true
    fi
    chown -R anki:anki /data /backups /config /var/log/anki /var/lib/anki 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Docker secrets support
# -----------------------------------------------------------------------------
load_secret() {
    local var_name="$1"
    local file_var="${var_name}_FILE"
    local file_path="${!file_var}"
    
    if [ -n "$file_path" ] && [ -f "$file_path" ]; then
        export "$var_name"="$(cat "$file_path")"
        log_debug "Loaded secret for $var_name"
    fi
}

load_secrets() {
    # Load user secrets
    for var in $(env | grep -E '^SYNC_USER[0-9]+_FILE=' | sed 's/_FILE=.*//' | sort); do
        load_secret "$var"
    done
    
    # Load other secrets
    load_secret "NOTIFY_WEBHOOK_URL"
    load_secret "EMAIL_PASS"
    load_secret "S3_ACCESS_KEY"
    load_secret "S3_SECRET_KEY"
    load_secret "DASHBOARD_AUTH"
}

# -----------------------------------------------------------------------------
# Email configuration
# -----------------------------------------------------------------------------
setup_email() {
    if [ "$EMAIL_ENABLED" = "true" ] && [ -n "$EMAIL_HOST" ]; then
        log_info "Configuring email via $EMAIL_HOST"
        cat > /etc/msmtprc << EOF
defaults
auth           on
tls            ${EMAIL_TLS}
tls_trust_file /etc/ssl/certs/ca-certificates.crt
logfile        /var/log/anki/email.log

account        default
host           ${EMAIL_HOST}
port           ${EMAIL_PORT}
from           ${EMAIL_FROM}
user           ${EMAIL_USER}
password       ${EMAIL_PASS}
EOF
        chmod 600 /etc/msmtprc
    fi
}

# -----------------------------------------------------------------------------
# Notification function (supports all types)
# -----------------------------------------------------------------------------
send_notification() {
    local message="$1"
    local title="${2:-Anki Sync Server}"
    
    # Webhook notifications
    if [ "$NOTIFY_ENABLED" = "true" ] && [ -n "$NOTIFY_WEBHOOK_URL" ]; then
        log_debug "Sending webhook notification"
        
        case "$NOTIFY_TYPE" in
            discord)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"content\": \"**${title}**\n${message}\"}" > /dev/null 2>&1 &
                ;;
            telegram)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -d "text=${title}: ${message}" > /dev/null 2>&1 &
                ;;
            slack)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"text\": \"*${title}*\n${message}\"}" > /dev/null 2>&1 &
                ;;
            ntfy)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Title: ${title}" \
                    -d "${message}" > /dev/null 2>&1 &
                ;;
            generic|*)
                curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                    -H "Content-Type: application/json" \
                    -d "{\"title\": \"${title}\", \"message\": \"${message}\", \"timestamp\": \"$(date -Iseconds)\"}" > /dev/null 2>&1 &
                ;;
        esac
    fi
    
    # Email notifications
    if [ "$EMAIL_ENABLED" = "true" ] && [ -n "$EMAIL_TO" ]; then
        log_debug "Sending email notification"
        echo -e "Subject: ${title}\nFrom: ${EMAIL_FROM}\nTo: ${EMAIL_TO}\n\n${message}" | msmtp "$EMAIL_TO" 2>/dev/null &
    fi
}

# -----------------------------------------------------------------------------
# Build user list
# -----------------------------------------------------------------------------
setup_users() {
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
    export USER_COUNT
    export USER_NAMES

    # Export password hashing setting
    if [ "$PASSWORDS_HASHED" = "1" ] || [ "$PASSWORDS_HASHED" = "true" ]; then
        export PASSWORDS_HASHED="1"
    fi

    # Save user list for dashboard
    echo "$USER_NAMES" > /var/lib/anki/users.txt
    echo "$USER_COUNT" > /var/lib/anki/user_count.txt
}

# -----------------------------------------------------------------------------
# Setup automated backups
# -----------------------------------------------------------------------------
setup_backups() {
    if [ "$BACKUP_ENABLED" = "true" ]; then
        log_info "Setting up automated backups (schedule: $BACKUP_SCHEDULE)"
        
        # Create cron job
        echo "$BACKUP_SCHEDULE /usr/local/bin/backup.sh >> /var/log/anki/backup.log 2>&1" > /etc/crontabs/root
        
        # Start cron daemon
        crond -b -l 8
        log_info "Backup cron started"
    fi
}

# -----------------------------------------------------------------------------
# Setup fail2ban
# -----------------------------------------------------------------------------
setup_fail2ban() {
    if [ "$FAIL2BAN_ENABLED" = "true" ]; then
        log_info "Setting up fail2ban (max retries: $FAIL2BAN_MAX_RETRIES, ban time: ${FAIL2BAN_BAN_TIME}s)"
        
        # Update fail2ban config
        cat > /etc/fail2ban/jail.d/anki.local << EOF
[anki-auth]
enabled = true
filter = anki-auth
logpath = /var/log/anki/auth.log
maxretry = ${FAIL2BAN_MAX_RETRIES}
bantime = ${FAIL2BAN_BAN_TIME}
findtime = ${FAIL2BAN_FIND_TIME}
action = iptables-allports[name=anki, protocol=all]
EOF
        
        # Start fail2ban
        fail2ban-server -b -x
        log_info "Fail2ban started"
    fi
}

# -----------------------------------------------------------------------------
# Initialize metrics tracking files
# -----------------------------------------------------------------------------
init_metrics() {
    echo "0" > /var/lib/anki/sync_count.txt
    echo "0" > /var/lib/anki/bytes_synced.txt
    echo "$(date +%s)" > /var/lib/anki/start_time.txt
    echo "$ANKI_VERSION" > /var/lib/anki/version.txt
}

# -----------------------------------------------------------------------------
# Metrics server
# -----------------------------------------------------------------------------
start_metrics_server() {
    if [ "$METRICS_ENABLED" != "true" ]; then
        return
    fi
    
    log_info "Starting metrics server on port $METRICS_PORT"
    
    (
        while true; do
            # Collect metrics
            USERS_TOTAL=$(cat /var/lib/anki/user_count.txt 2>/dev/null || echo 0)
            DATA_SIZE=$(du -sb "$SYNC_BASE" 2>/dev/null | cut -f1 || echo 0)
            BACKUP_COUNT=$(ls -1 /backups/*.tar.gz 2>/dev/null | wc -l || echo 0)
            START_TIME=$(cat /var/lib/anki/start_time.txt 2>/dev/null || echo "$(date +%s)")
            UPTIME=$(($(date +%s) - START_TIME))
            SYNC_COUNT=$(cat /var/lib/anki/sync_count.txt 2>/dev/null || echo 0)
            BYTES_SYNCED=$(cat /var/lib/anki/bytes_synced.txt 2>/dev/null || echo 0)
            AUTH_SUCCESS=$(grep -c "AUTH_SUCCESS" /var/log/anki/auth.log 2>/dev/null || echo 0)
            AUTH_FAILED=$(grep -c "AUTH_FAILED" /var/log/anki/auth.log 2>/dev/null || echo 0)
            LAST_BACKUP=$(stat -c %Y /backups/$(ls -1t /backups/*.tar.gz 2>/dev/null | head -1) 2>/dev/null || echo 0)
            
            # Create Prometheus metrics response
            METRICS="# HELP anki_sync_users_total Total number of configured users
# TYPE anki_sync_users_total gauge
anki_sync_users_total $USERS_TOTAL

# HELP anki_sync_data_bytes Total data size in bytes
# TYPE anki_sync_data_bytes gauge
anki_sync_data_bytes $DATA_SIZE

# HELP anki_sync_backup_count Number of backup files
# TYPE anki_sync_backup_count gauge
anki_sync_backup_count $BACKUP_COUNT

# HELP anki_sync_backup_last_timestamp Last backup timestamp
# TYPE anki_sync_backup_last_timestamp gauge
anki_sync_backup_last_timestamp $LAST_BACKUP

# HELP anki_sync_uptime_seconds Server uptime in seconds
# TYPE anki_sync_uptime_seconds counter
anki_sync_uptime_seconds $UPTIME

# HELP anki_sync_operations_total Total sync operations
# TYPE anki_sync_operations_total counter
anki_sync_operations_total $SYNC_COUNT

# HELP anki_sync_bytes_total Total bytes synced
# TYPE anki_sync_bytes_total counter
anki_sync_bytes_total $BYTES_SYNCED

# HELP anki_auth_success_total Successful authentications
# TYPE anki_auth_success_total counter
anki_auth_success_total $AUTH_SUCCESS

# HELP anki_auth_failed_total Failed authentications
# TYPE anki_auth_failed_total counter
anki_auth_failed_total $AUTH_FAILED

# HELP anki_sync_info Server information
# TYPE anki_sync_info gauge
anki_sync_info{version=\"$ANKI_VERSION\"} 1
"
            # Serve metrics
            echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\n\r\n$METRICS" | nc -l -p "$METRICS_PORT" -q 1 > /dev/null 2>&1 || sleep 1
        done
    ) &
    METRICS_PID=$!
}

# -----------------------------------------------------------------------------
# Dashboard server
# -----------------------------------------------------------------------------
start_dashboard() {
    if [ "$DASHBOARD_ENABLED" != "true" ]; then
        return
    fi
    
    log_info "Starting dashboard on port $DASHBOARD_PORT"
    python3 /usr/local/bin/dashboard.py &
    DASHBOARD_PID=$!
}

# -----------------------------------------------------------------------------
# Update status file for dashboard
# -----------------------------------------------------------------------------
start_status_updater() {
    (
        while true; do
            cat > /var/lib/anki/status.json << EOF
{
    "anki_version": "$ANKI_VERSION",
    "server": "anki-sync-server-enhanced",
    "status": "running",
    "users": $(cat /var/lib/anki/user_count.txt 2>/dev/null || echo 0),
    "user_names": "$(cat /var/lib/anki/users.txt 2>/dev/null | tr -d '\n')",
    "uptime_seconds": $(($(date +%s) - $(cat /var/lib/anki/start_time.txt 2>/dev/null || echo $(date +%s)))),
    "sync_count": $(cat /var/lib/anki/sync_count.txt 2>/dev/null || echo 0),
    "data_size_bytes": $(du -sb "$SYNC_BASE" 2>/dev/null | cut -f1 || echo 0),
    "backup_count": $(ls -1 /backups/*.tar.gz 2>/dev/null | wc -l || echo 0),
    "backup_enabled": "$BACKUP_ENABLED",
    "metrics_enabled": "$METRICS_ENABLED",
    "dashboard_enabled": "$DASHBOARD_ENABLED",
    "fail2ban_enabled": "$FAIL2BAN_ENABLED",
    "s3_enabled": "$S3_BACKUP_ENABLED",
    "last_updated": "$(date -Iseconds)"
}
EOF
            sleep 30
        done
    ) &
}

# -----------------------------------------------------------------------------
# Graceful shutdown handler
# -----------------------------------------------------------------------------
shutdown_handler() {
    log_info "Received shutdown signal, stopping gracefully..."
    send_notification "Server shutting down"
    
    # Kill processes
    [ -n "$SYNC_PID" ] && kill -TERM "$SYNC_PID" 2>/dev/null
    [ -n "$DASHBOARD_PID" ] && kill -TERM "$DASHBOARD_PID" 2>/dev/null
    [ -n "$METRICS_PID" ] && kill -TERM "$METRICS_PID" 2>/dev/null
    
    # Stop services
    pkill crond 2>/dev/null || true
    pkill fail2ban 2>/dev/null || true
    
    # Wait for sync server
    [ -n "$SYNC_PID" ] && wait "$SYNC_PID" 2>/dev/null
    
    log_info "Shutdown complete"
    log_sync "SERVER_STOP"
    exit 0
}

trap shutdown_handler SIGTERM SIGINT SIGQUIT

# -----------------------------------------------------------------------------
# Print startup banner
# -----------------------------------------------------------------------------
print_banner() {
    echo ""
    echo "=============================================================="
    echo "           Anki Sync Server Enhanced"
    echo "=============================================================="
    echo "  Version:       $ANKI_VERSION"
    echo "  Host:          ${SYNC_HOST}:${SYNC_PORT}"
    echo "  Users:         ${USER_COUNT} (${USER_NAMES})"
    echo "  Data:          ${SYNC_BASE}"
    echo "  Log Level:     ${LOG_LEVEL}"
    echo "  PUID/PGID:     ${PUID}/${PGID}"
    echo "  Hashed Pass:   $([ "$PASSWORDS_HASHED" = "1" ] && echo "Yes" || echo "No")"
    echo "--------------------------------------------------------------"
    echo "  Features:"
    echo "    Backups:     $([ "$BACKUP_ENABLED" = "true" ] && echo "ON ($BACKUP_SCHEDULE)" || echo "OFF")"
    echo "    S3 Upload:   $([ "$S3_BACKUP_ENABLED" = "true" ] && echo "ON ($S3_BUCKET)" || echo "OFF")"
    echo "    Metrics:     $([ "$METRICS_ENABLED" = "true" ] && echo "ON (port $METRICS_PORT)" || echo "OFF")"
    echo "    Dashboard:   $([ "$DASHBOARD_ENABLED" = "true" ] && echo "ON (port $DASHBOARD_PORT)" || echo "OFF")"
    echo "    Webhook:     $([ "$NOTIFY_ENABLED" = "true" ] && echo "ON ($NOTIFY_TYPE)" || echo "OFF")"
    echo "    Email:       $([ "$EMAIL_ENABLED" = "true" ] && echo "ON ($EMAIL_TO)" || echo "OFF")"
    echo "    Rate Limit:  $([ "$RATE_LIMIT_ENABLED" = "true" ] && echo "ON ($RATE_LIMIT_REQUESTS/${RATE_LIMIT_WINDOW}s)" || echo "OFF")"
    echo "    Fail2Ban:    $([ "$FAIL2BAN_ENABLED" = "true" ] && echo "ON ($FAIL2BAN_MAX_RETRIES retries)" || echo "OFF")"
    echo "    Sync Log:    $([ "$SYNC_LOGGING_ENABLED" = "true" ] && echo "ON" || echo "OFF")"
    echo "=============================================================="
    echo ""
}

# =============================================================================
# Main
# =============================================================================

log_info "Starting Anki Sync Server Enhanced..."

# Setup
setup_permissions
load_secrets
setup_users
setup_email
init_metrics

# Start services
setup_backups
setup_fail2ban
start_metrics_server
start_dashboard
start_status_updater

# Print banner
print_banner

# Send startup notification
send_notification "Server started with $USER_COUNT users (v$ANKI_VERSION)"
log_sync "SERVER_START users=$USER_COUNT version=$ANKI_VERSION"

# Start the sync server
log_info "Starting Anki sync server..."
anki-sync-server &
SYNC_PID=$!

log_info "Sync server started (PID: $SYNC_PID)"

# Wait for sync server
wait "$SYNC_PID"
EXIT_CODE=$?

log_info "Sync server exited with code $EXIT_CODE"
log_sync "SERVER_STOP exit_code=$EXIT_CODE"
send_notification "Server stopped (exit code: $EXIT_CODE)"

exit $EXIT_CODE
