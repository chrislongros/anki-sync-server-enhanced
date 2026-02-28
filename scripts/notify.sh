#!/bin/bash
# =============================================================================
# Anki Sync Server Enhanced - Notification Script
# Sends notifications via webhook (Discord/Telegram/Slack/ntfy/generic) or email
# =============================================================================

MESSAGE="${1:-Test notification from Anki Sync Server}"
TITLE="${2:-Anki Sync Server}"

NOTIFY_ENABLED="${NOTIFY_ENABLED:-false}"
NOTIFY_WEBHOOK_URL="${NOTIFY_WEBHOOK_URL:-}"
NOTIFY_TYPE="${NOTIFY_TYPE:-discord}"

EMAIL_ENABLED="${EMAIL_ENABLED:-false}"
EMAIL_FROM="${EMAIL_FROM:-}"
EMAIL_TO="${EMAIL_TO:-}"

SENT=false

# Webhook notifications
if [ "$NOTIFY_ENABLED" = "true" ] && [ -n "$NOTIFY_WEBHOOK_URL" ]; then
    case "$NOTIFY_TYPE" in
        discord)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"content\": \"**${TITLE}**\n${MESSAGE}\"}" > /dev/null 2>&1
            ;;
        telegram)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -d "text=${TITLE}: ${MESSAGE}" > /dev/null 2>&1
            ;;
        slack)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"text\": \"*${TITLE}*\n${MESSAGE}\"}" > /dev/null 2>&1
            ;;
        ntfy)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Title: ${TITLE}" \
                -d "${MESSAGE}" > /dev/null 2>&1
            ;;
        generic|*)
            curl -s -X POST "$NOTIFY_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "{\"title\": \"${TITLE}\", \"message\": \"${MESSAGE}\", \"timestamp\": \"$(date -Iseconds)\"}" > /dev/null 2>&1
            ;;
    esac
    SENT=true
fi

# Email notifications
if [ "$EMAIL_ENABLED" = "true" ] && [ -n "$EMAIL_TO" ]; then
    echo -e "Subject: ${TITLE}\nFrom: ${EMAIL_FROM}\nTo: ${EMAIL_TO}\n\n${MESSAGE}" | msmtp "$EMAIL_TO" 2>/dev/null
    SENT=true
fi

if [ "$SENT" = "true" ]; then
    exit 0
else
    echo "No notification method configured (set NOTIFY_ENABLED=true or EMAIL_ENABLED=true)"
    exit 1
fi
