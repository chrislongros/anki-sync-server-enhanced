# TrueNAS SCALE Installation

## Option 1: Custom App (Easiest)

1. In TrueNAS SCALE, go to **Apps > Discover Apps > Custom App**

2. Fill in the form:
   - **Application Name**: `anki-sync-server`
   - **Image Repository**: `chrislongros/anki-sync-server-enhanced`
   - **Image Tag**: `latest`

3. Add environment variables:
   ```
   SYNC_USER1=username:password
   TZ=Your/Timezone
   BACKUP_ENABLED=true
   ```

4. Add storage:
   - Host Path or PVC for `/data`
   - Host Path or PVC for `/backups`

5. Set port: `8080`

6. Click **Install**

## Option 2: Helm Chart

1. Add this repository as a catalog or use Helm directly:

```bash
# From the truenas directory
helm install anki-sync-server ./anki-sync-server \
  --set users[0]="user1:password1" \
  --set timezone="Europe/Berlin" \
  --set backup.enabled=true
```

## Option 3: docker-compose via Custom App

1. SSH into TrueNAS
2. Navigate to your apps directory
3. Create docker-compose.yml:

```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    container_name: anki-sync-server
    ports:
      - "8080:8080"
    environment:
      - SYNC_USER1=user1:password
      - TZ=Europe/Berlin
      - PUID=568
      - PGID=568
      - BACKUP_ENABLED=true
    volumes:
      - /mnt/pool/apps/anki/data:/data
      - /mnt/pool/apps/anki/backups:/backups
    restart: unless-stopped
```

4. Run: `docker-compose up -d`

## Configuration

After installation, configure your Anki clients:

**Desktop**: Tools > Preferences > Syncing > Set server to `http://TRUENAS_IP:8080/`

**AnkiDroid**: Settings > Sync > Custom sync server > `http://TRUENAS_IP:8080/`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_USER1` | First user (username:password) | Required |
| `SYNC_USER2`...`SYNC_USER99` | Additional users | Optional |
| `TZ` | Timezone | UTC |
| `PUID` | User ID | 568 (apps user) |
| `PGID` | Group ID | 568 (apps group) |
| `BACKUP_ENABLED` | Enable backups | false |
| `BACKUP_SCHEDULE` | Cron schedule | 0 3 * * * |
| `BACKUP_RETENTION_DAYS` | Days to keep | 7 |
| `METRICS_ENABLED` | Prometheus metrics | false |
| `NOTIFY_ENABLED` | Notifications | false |
| `NOTIFY_TYPE` | discord/telegram/slack | discord |
| `NOTIFY_WEBHOOK_URL` | Webhook URL | - |

## Troubleshooting

**Cannot connect from Anki client:**
- Check TrueNAS firewall allows port 8080
- Verify the container is running: `docker ps | grep anki`
- Check logs: `docker logs anki-sync-server`

**Permission denied errors:**
- Set PUID/PGID to match your TrueNAS apps user (usually 568)
- Or use the host path permissions that match your dataset

**Backups not working:**
- Verify `/backups` volume is mounted
- Check cron is running: `docker exec anki-sync-server ps aux | grep cron`
