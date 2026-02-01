# Anki Sync Server Enhanced

Enhanced Docker image for self-hosted Anki sync server, built directly from the official [Anki source code](https://github.com/ankitects/anki).

## Features

- **Auto-updated** to latest Anki releases via GitHub Actions
- **Multi-user support** via numbered environment variables
- **Built-in healthcheck** for container orchestration
- **Backup volume** support
- **Non-root execution** for security

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
      - ./backups:/backups
    restart: unless-stopped

volumes:
  anki_data:
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_USER1` to `SYNC_USER99` | User credentials (`username:password`) | Required |
| `SYNC_BASE` | Data directory | `/data` |
| `SYNC_HOST` | Listen address | `0.0.0.0` |
| `SYNC_PORT` | Listen port | `8080` |

## Building Locally
```bash
# Auto-detect latest version
docker build -t anki-sync-server-enhanced .

# Or specify a version
docker build --build-arg ANKI_VERSION=25.09.2 -t anki-sync-server-enhanced .
```

## Credits

Built from the official [Anki](https://github.com/ankitects/anki) project by Ankitects.

## License

This project follows the same license as Anki (AGPL-3.0).
