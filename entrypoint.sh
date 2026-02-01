#!/bin/bash
set -e

# Support Docker secrets (files in /run/secrets/)
# Usage: -e SYNC_USER1_FILE=/run/secrets/anki_user1
for var in $(env | grep -E '^SYNC_USER[0-9]+_FILE=' | sort); do
    name="${var%%=*}"
    file="${var#*=}"
    base_name="${name%_FILE}"
    if [ -f "$file" ]; then
        export "$base_name"="$(cat "$file")"
    fi
done

# Build user list from SYNC_USER* environment variables
USERS=""
USER_COUNT=0
for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sort); do
    value="${var#*=}"
    if [ -n "$USERS" ]; then
        USERS="$USERS,$value"
    else
        USERS="$value"
    fi
    USER_COUNT=$((USER_COUNT + 1))
done

if [ -z "$USERS" ]; then
    echo "Error: No users defined. Set SYNC_USER1=username:password"
    exit 1
fi

export SYNC_USER="$USERS"
export SYNC_BASE="${SYNC_BASE:-/data}"
export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-8080}"

echo "========================================"
echo "  Anki Sync Server Enhanced"
echo "========================================"
echo "  Host: ${SYNC_HOST}:${SYNC_PORT}"
echo "  Users: ${USER_COUNT}"
echo "  Data: ${SYNC_BASE}"
echo "========================================"

exec anki-sync-server
