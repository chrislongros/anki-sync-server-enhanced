# TrueNAS SCALE Installation

TrueNAS SCALE 24.10+ uses Docker Compose. Install via Custom App with YAML.

## Installation

1. Go to **Apps > Discover Apps > Custom App**
2. Click the three dots menu and select **Install via YAML**
3. Paste the YAML below and click **Save**

## Basic Configuration

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    container_name: anki-sync-server
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - SYNC_USER1=user1:changeme123
      - TZ=Europe/Berlin
      - PUID=568
      - PGID=568
      - BACKUP_ENABLED=true
    volumes:
      - anki_data:/data
      - anki_backups:/backups

volumes:
  anki_data:
  anki_backups:
```

## Full Configuration (with all features)

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    container_name: anki-sync-server
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "8081:8081"
      - "9090:9090"
    environment:
      # Users
      - SYNC_USER1=alice:password1
      - SYNC_USER2=bob:password2
      
      # Core
      - TZ=Europe/Berlin
      - PUID=568
      - PGID=568
      
      # Backups
      - BACKUP_ENABLED=true
      - BACKUP_SCHEDULE=0 3 * * *
      - BACKUP_RETENTION_DAYS=14
      
      # Monitoring
      - METRICS_ENABLED=true
      - DASHBOARD_ENABLED=true
      - DASHBOARD_AUTH=admin:dashpass
      
      # Notifications (optional)
      - NOTIFY_ENABLED=false
      - NOTIFY_TYPE=discord
      - NOTIFY_WEBHOOK_URL=
    volumes:
      - anki_data:/data
      - anki_backups:/backups

volumes:
  anki_data:
  anki_backups:
```

## Client Setup

**Desktop:** Tools > Preferences > Syncing > `http://TRUENAS_IP:8080/`

**AnkiDroid:** Settings > Sync > Custom sync server > `http://TRUENAS_IP:8080/`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_USER1` | First user (user:pass) | Required |
| `TZ` | Timezone | UTC |
| `PUID` | User ID (568 for TrueNAS) | 568 |
| `PGID` | Group ID | 568 |
| `BACKUP_ENABLED` | Enable backups | false |
| `METRICS_ENABLED` | Prometheus metrics | false |
| `DASHBOARD_ENABLED` | Web dashboard | false |
| `NOTIFY_ENABLED` | Webhook notifications | false |

## Troubleshooting

**Cannot connect:** Check firewall allows port 8080, verify app is running in Apps dashboard.

**Permission errors:** Set PUID/PGID to 568 (TrueNAS apps user).

**View logs:** Apps > anki-sync-server > Logs
