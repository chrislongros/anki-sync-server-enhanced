# Anki Sync Server Enhanced

[![Docker Hub](https://img.shields.io/docker/pulls/chrislongros/anki-sync-server-enhanced)](https://hub.docker.com/r/chrislongros/anki-sync-server-enhanced)
[![GitHub Actions](https://github.com/chrislongros/anki-sync-server-enhanced/actions/workflows/build.yml/badge.svg)](https://github.com/chrislongros/anki-sync-server-enhanced/actions)
[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-available-blue)](https://ghcr.io/chrislongros/anki-sync-server-enhanced)

Enhanced Docker image for self-hosted Anki sync server, built directly from the official [Anki source code](https://github.com/ankitects/anki).

## Features

- **Auto-updated** — Automatically builds latest Anki releases via GitHub Actions
- **Multi-architecture** — Supports amd64 and arm64 (Raspberry Pi, Apple Silicon)
- **Multi-user** — Support for up to 99 users via environment variables
- **Docker secrets** — Secure credential management for production
- **Automated backups** — Scheduled backups with configurable retention
- **Prometheus metrics** — Built-in metrics endpoint for monitoring
- **Notifications** — Discord, Telegram, Slack alerts for server events
- **Health checks** — Built-in health monitoring for orchestration
- **Non-root** — Runs as unprivileged user for security
- **Small image** — Alpine-based for minimal footprint

## Quick Start

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    ports:
      - "8080:8080"
    environment:
      - SYNC_USER1=user1:password1
      - SYNC_USER2=user2:password2
    volumes:
      - anki_data:/data
    restart: unless-stopped

volumes:
  anki_data:
```

```bash
docker-compose up -d
```

## Configuration

### Environment Variables

#### User Configuration (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `SYNC_USER1` to `SYNC_USER99` | User credentials | `username:password` |
| `SYNC_USER1_FILE` to `SYNC_USER99_FILE` | Path to credentials file (Docker secrets) | `/run/secrets/user1` |

#### Server Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_HOST` | Listen address | `0.0.0.0` |
| `SYNC_PORT` | Listen port | `8080` |
| `SYNC_BASE` | Data directory | `/data` |
| `LOG_LEVEL` | Log verbosity (debug/info/warn/error) | `info` |
| `TZ` | Timezone | `UTC` |
| `PUID` | User ID for file ownership | `1000` |
| `PGID` | Group ID for file ownership | `1000` |

#### Backup Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BACKUP_ENABLED` | Enable automated backups | `false` |
| `BACKUP_SCHEDULE` | Cron schedule for backups | `0 3 * * *` (3 AM daily) |
| `BACKUP_RETENTION_DAYS` | Days to keep old backups | `7` |

#### Metrics Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_ENABLED` | Enable Prometheus metrics | `false` |
| `METRICS_PORT` | Metrics endpoint port | `9090` |

#### Notification Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFY_ENABLED` | Enable notifications | `false` |
| `NOTIFY_TYPE` | Type: discord/telegram/slack/generic | `discord` |
| `NOTIFY_WEBHOOK_URL` | Webhook URL | - |

## Deployment Examples

### Basic Setup

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    ports:
      - "8080:8080"
    environment:
      - SYNC_USER1=alice:secretpassword
      - TZ=Europe/Berlin
      - BACKUP_ENABLED=true
    volumes:
      - anki_data:/data
      - ./backups:/backups
    restart: unless-stopped

volumes:
  anki_data:
```

### Production with Docker Secrets

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    ports:
      - "8080:8080"
      - "9090:9090"
    environment:
      - SYNC_USER1_FILE=/run/secrets/anki_user1
      - BACKUP_ENABLED=true
      - METRICS_ENABLED=true
      - NOTIFY_ENABLED=true
      - NOTIFY_TYPE=discord
      - NOTIFY_WEBHOOK_URL_FILE=/run/secrets/webhook
    secrets:
      - anki_user1
      - webhook
    volumes:
      - anki_data:/data
      - anki_backups:/backups
    restart: unless-stopped

secrets:
  anki_user1:
    file: ./secrets/user1.txt
  webhook:
    file: ./secrets/discord.txt

volumes:
  anki_data:
  anki_backups:
```

### With Traefik (HTTPS)

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    environment:
      - SYNC_USER1=alice:secretpassword
    volumes:
      - anki_data:/data
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.anki.rule=Host(`anki.yourdomain.com`)"
      - "traefik.http.routers.anki.tls.certresolver=letsencrypt"
    restart: unless-stopped
```

## Configuring Anki Clients

### Desktop (Windows/Mac/Linux)

1. Open Anki
2. Go to **Tools → Preferences → Syncing**
3. Set "Self-hosted sync server" to: `http://your-server:8080/`
4. Click **Log Out** (if logged in)
5. Click **Sync** and enter your credentials

### AnkiDroid (Android)

1. Open AnkiDroid
2. Go to **Settings → Sync → Custom sync server**
3. Set sync URL to: `http://your-server:8080/`
4. Set media URL to: `http://your-server:8080/msync/`
5. Sync with your credentials

### AnkiMobile (iOS)

1. Open AnkiMobile
2. Go to **Settings → Sync → Custom server**
3. Enter: `http://your-server:8080/`
4. Sync with your credentials

## Prometheus Metrics

When `METRICS_ENABLED=true`, the following metrics are available at `http://server:9090/metrics`:

| Metric | Description |
|--------|-------------|
| `anki_sync_users_total` | Total configured users |
| `anki_sync_data_bytes` | Data directory size |
| `anki_sync_backup_count` | Number of backup files |
| `anki_sync_uptime_seconds` | Server uptime |
| `anki_sync_info` | Server version info |

## Manual Backup

```bash
# Trigger immediate backup
docker exec anki-sync-server /usr/local/bin/backup.sh

# List backups
docker exec anki-sync-server ls -la /backups/

# Restore from backup
docker exec anki-sync-server tar -xzf /backups/anki_backup_20240101_030000.tar.gz -C /data
```

## Building Locally

```bash
# Auto-detect latest Anki version
docker build -t anki-sync-server-enhanced .

# Specify version
docker build --build-arg ANKI_VERSION=25.09.2 -t anki-sync-server-enhanced .
```

## Image Registries

This image is available from:

- **Docker Hub**: `chrislongros/anki-sync-server-enhanced`
- **GitHub Container Registry**: `ghcr.io/chrislongros/anki-sync-server-enhanced`

## Credits

Built from the official [Anki](https://github.com/ankitects/anki) project by Ankitects.

## License

This project follows the same license as Anki (AGPL-3.0).
