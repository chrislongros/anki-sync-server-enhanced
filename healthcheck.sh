#!/bin/bash
# =============================================================================
# Anki Sync Server - Health Check
# =============================================================================

SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
SYNC_PORT="${SYNC_PORT:-8080}"

# Check if the server is responding
if wget -q --spider --timeout=5 "http://localhost:${SYNC_PORT}/" 2>/dev/null; then
    exit 0
else
    exit 1
fi
