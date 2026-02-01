# Anki Sync Server Enhanced

Enhanced Docker image for self-hosted Anki sync server.

## Features
- Multi-user support via environment variables
- Built-in healthcheck
- Backup volume support
- Non-root execution

## Usage
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
      - ./backups:/backups
```

## Environment Variables
- `SYNC_USER1` to `SYNC_USER99`: User credentials in `username:password` format
- `SYNC_BASE`: Data directory (default: `/data`)
- `SYNC_HOST`: Listen address (default: `0.0.0.0`)
- `SYNC_PORT`: Listen port (default: `8080`)
