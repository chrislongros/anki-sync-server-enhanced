# Anki Sync Server Enhanced

[![Docker Hub](https://img.shields.io/docker/pulls/chrislongros/anki-sync-server-enhanced)](https://hub.docker.com/r/chrislongros/anki-sync-server-enhanced)
[![GitHub Actions](https://github.com/chrislongros/anki-sync-server-enhanced/actions/workflows/build.yml/badge.svg)](https://github.com/chrislongros/anki-sync-server-enhanced/actions)
[![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)](https://ghcr.io/chrislongros/anki-sync-server-enhanced)

Production-ready Docker image for self-hosted Anki sync server with backups, monitoring, dashboard, and security features.

## Features

| Feature | This Image |
|---------|------------|
| Pre-built Docker image | Yes |
| Auto-updates (daily builds) | Yes |
| Multi-arch (amd64, arm64, arm/v7) | Yes |
| Automated backups with retention | Yes |
| S3/MinIO backup upload | Yes |
| Prometheus metrics | Yes |
| Web dashboard | Yes |
| Discord/Telegram/Slack/Email alerts | Yes |
| Docker secrets support | Yes |
| Hashed passwords | Yes |
| Fail2ban integration | Yes |
| Rate limiting | Yes |
| User management CLI | Yes |
| PUID/PGID support | Yes |

## Quick Start

```bash
docker run -d \
  --name anki-sync \
  -p 8080:8080 \
  -e SYNC_USER1=user:password \
  -v anki_data:/data \
  chrislongros/anki-sync-server-enhanced
```

## Docker Compose

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    ports:
      - "8080:8080"   # Sync server
      - "8081:8081"   # Dashboard (optional)
      - "9090:9090"   # Metrics (optional)
    environment:
      - SYNC_USER1=alice:password1
      - SYNC_USER2=bob:password2
      - TZ=Europe/Berlin
      - BACKUP_ENABLED=true
      - METRICS_ENABLED=true
      - DASHBOARD_ENABLED=true
    volumes:
      - anki_data:/data
      - anki_backups:/backups
    restart: unless-stopped

volumes:
  anki_data:
  anki_backups:
```

## Configuration Reference

### Core

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_USER1`-`SYNC_USER99` | User credentials (user:pass) | Required |
| `SYNC_HOST` | Listen address | `0.0.0.0` |
| `SYNC_PORT` | Listen port | `8080` |
| `LOG_LEVEL` | debug/info/warn/error | `info` |
| `TZ` | Timezone | `UTC` |
| `PUID` / `PGID` | File permissions | `1000` |
| `PASSWORDS_HASHED` | Use hashed passwords | `0` |

### Backups

| Variable | Description | Default |
|----------|-------------|---------|
| `BACKUP_ENABLED` | Enable backups | `false` |
| `BACKUP_SCHEDULE` | Cron schedule | `0 3 * * *` |
| `BACKUP_RETENTION_DAYS` | Keep days | `7` |

### S3 Upload

| Variable | Description | Default |
|----------|-------------|---------|
| `S3_BACKUP_ENABLED` | Upload to S3 | `false` |
| `S3_ENDPOINT` | S3 endpoint (MinIO/Garage) | - |
| `S3_BUCKET` | Bucket name | - |
| `S3_ACCESS_KEY` | Access key | - |
| `S3_SECRET_KEY` | Secret key | - |
| `S3_REGION` | Region | `us-east-1` |

### Monitoring

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_ENABLED` | Prometheus metrics | `false` |
| `METRICS_PORT` | Metrics port | `9090` |
| `DASHBOARD_ENABLED` | Web dashboard | `false` |
| `DASHBOARD_PORT` | Dashboard port | `8081` |
| `DASHBOARD_AUTH` | Auth (user:pass) | - |

### Notifications

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFY_ENABLED` | Enable webhooks | `false` |
| `NOTIFY_TYPE` | discord/telegram/slack/ntfy | `discord` |
| `NOTIFY_WEBHOOK_URL` | Webhook URL | - |
| `EMAIL_ENABLED` | Enable email | `false` |
| `EMAIL_HOST` | SMTP host | - |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_USER` / `EMAIL_PASS` | SMTP credentials | - |
| `EMAIL_FROM` / `EMAIL_TO` | Email addresses | - |

### Security

| Variable | Description | Default |
|----------|-------------|---------|
| `FAIL2BAN_ENABLED` | Enable fail2ban | `false` |
| `FAIL2BAN_MAX_RETRIES` | Max failures | `5` |
| `FAIL2BAN_BAN_TIME` | Ban seconds | `3600` |
| `RATE_LIMIT_ENABLED` | Enable rate limit | `false` |
| `RATE_LIMIT_REQUESTS` | Max requests | `100` |
| `RATE_LIMIT_WINDOW` | Window seconds | `60` |

## CLI Tools

```bash
# User management
docker exec anki-sync user-manager.sh list
docker exec anki-sync user-manager.sh add john
docker exec anki-sync user-manager.sh add john mypassword
docker exec anki-sync user-manager.sh reset john newpass
docker exec anki-sync user-manager.sh hash mypassword

# Backup management
docker exec anki-sync backup.sh
docker exec anki-sync restore.sh --list
docker exec anki-sync restore.sh --list-s3
docker exec anki-sync restore.sh backup_file.tar.gz
docker exec anki-sync restore.sh --s3 backup_file.tar.gz
```

## Client Configuration

**Desktop:** Tools > Preferences > Syncing > `http://server:8080/`

**AnkiDroid:** Settings > Sync > Custom server > `http://server:8080/`

**AnkiMobile:** Settings > Sync > Custom server > `http://server:8080/`

## Prometheus Metrics

Available at `http://server:9090/metrics`:

- `anki_sync_users_total` - User count
- `anki_sync_data_bytes` - Data size
- `anki_sync_backup_count` - Backup count
- `anki_sync_uptime_seconds` - Uptime
- `anki_auth_success_total` - Auth successes
- `anki_auth_failed_total` - Auth failures

## Web Dashboard

Access at `http://server:8081/` (when enabled). Shows server status, users, backups, and statistics.

## Docker Secrets

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    environment:
      - SYNC_USER1_FILE=/run/secrets/anki_user1
    secrets:
      - anki_user1

secrets:
  anki_user1:
    file: ./secrets/user1.txt  # Contains: username:password
```

## Image Sources

- Docker Hub: `chrislongros/anki-sync-server-enhanced`
- GHCR: `ghcr.io/chrislongros/anki-sync-server-enhanced`

## NAS Installation

- **TrueNAS SCALE:** See [truenas/README.md](truenas/README.md)
- **Unraid:** Use [unraid/anki-sync-server.xml](unraid/anki-sync-server.xml)

## Building

```bash
docker build -t anki-sync-server-enhanced .
docker build --build-arg ANKI_VERSION=25.09.2 -t anki-sync-server-enhanced .
```

## Credits

Built from the official [Anki](https://github.com/ankitects/anki) project.

## License

AGPL-3.0
