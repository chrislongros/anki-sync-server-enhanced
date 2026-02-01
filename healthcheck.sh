#!/bin/bash
# =============================================================================
# Anki Sync Server - Health Check
# =============================================================================

SYNC_PORT="${SYNC_PORT:-8080}"

# Check the /health endpoint (available since Anki 24.06)
if wget -q -O /dev/null --timeout=5 "http://localhost:${SYNC_PORT}/health" 2>/dev/null; then
    exit 0
else
    # Fallback to root endpoint for older versions
    if wget -q --spider --timeout=5 "http://localhost:${SYNC_PORT}/" 2>/dev/null; then
        exit 0
    fi
    exit 1
fi
