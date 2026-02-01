#!/bin/bash
# =============================================================================
# Anki Sync Server - Health Check
# =============================================================================

SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
SYNC_PORT="${SYNC_PORT:-8080}"

# Try the /health endpoint first (available in Anki 24.06+)
if curl -sf "http://127.0.0.1:${SYNC_PORT}/health" > /dev/null 2>&1; then
    exit 0
fi

# Fallback: check if the port is responding
if nc -z 127.0.0.1 "$SYNC_PORT" 2>/dev/null; then
    exit 0
fi

# Server not healthy
exit 1
