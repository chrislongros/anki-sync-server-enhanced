# Anki Sync Server Enhanced

[![Docker Hub](https://img.shields.io/docker/pulls/chrislongros/anki-sync-server-enhanced)](https://hub.docker.com/r/chrislongros/anki-sync-server-enhanced)
[![GitHub Actions](https://github.com/chrislongros/anki-sync-server-enhanced/actions/workflows/build.yml/badge.svg)](https://github.com/chrislongros/anki-sync-server-enhanced/actions)

Enhanced Docker image for self-hosted Anki sync server, built directly from the official [Anki source code](https://github.com/ankitects/anki).

## Features

- **Auto-updated** to latest Anki releases via GitHub Actions
- **Multi-architecture** support (amd64, arm64)
- **Multi-user support** via numbered environment variables
- **Docker secrets support** for secure password handling
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

## Using Docker Secrets (recommended for production)
```yaml
services:
  anki-sync-server:
    image: chrislongros/anki-sync-server-enhanced:latest
    ports:
      - "8080:8080"
    environment:
      - SYNC_USER1_FILE=/run/secrets/anki_user1
    secrets:
      - anki_user1
    volumes:
      - anki_data:/data
    restart: unless-stopped

secrets:
  anki_user1:
    file: ./secrets/user1.txt  # Contains: username:password

volumes:
  anki_data:
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNC_USER1` to `SYNC_USER99` | User credentials (`username:password`) | Required |
| `SYNC_USER1_FILE` to `SYNC_USER99_FILE` | Path to file containing credentials | - |
| `SYNC_BASE` | Data directory | `/data` |
| `SYNC_HOST` | Listen address | `0.0.0.0` |
| `SYNC_PORT` | Listen port | `8080` |

## Configuring Anki Desktop

1. Open Anki → Tools → Preferences → Syncing
2. Set "Self-hosted sync server" to: `http://your-server:8080/`
3. Log out and log back in with your sync credentials

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
