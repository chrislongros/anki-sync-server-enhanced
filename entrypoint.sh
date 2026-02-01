#!/bin/bash
set -e

# Build user list from SYNC_USER* environment variables
USERS=""
for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sort); do
    value="${var#*=}"
    if [ -n "$USERS" ]; then
        USERS="$USERS,$value"
    else
        USERS="$value"
    fi
done

if [ -z "$USERS" ]; then
    echo "Error: No users defined. Set SYNC_USER1=username:password"
    exit 1
fi

export SYNC_USER="$USERS"
export SYNC_BASE="${SYNC_BASE:-/data}"
export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-8080}"

exec anki-sync-server
