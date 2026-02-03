# TLS Configuration

Anki Sync Server Enhanced supports three TLS modes via built-in Caddy reverse proxy.

## TLS Modes

### 1. Let's Encrypt (Automatic HTTPS)

Best for public servers with a domain name. Caddy automatically obtains and renews certificates.

```yaml
environment:
  - TLS_ENABLED=true
  - TLS_DOMAIN=anki.yourdomain.com
  - TLS_EMAIL=your@email.com  # Optional but recommended
```

**Requirements:**
- Port 80 and 443 must be accessible from the internet
- DNS must point to your server
- Valid domain name

### 2. Manual Certificates

Use your own certificates (e.g., from a corporate CA or wildcard cert).

```yaml
environment:
  - TLS_ENABLED=true
  - TLS_CERT=/config/certs/fullchain.pem
  - TLS_KEY=/config/certs/privkey.pem
volumes:
  - ./certs:/config/certs:ro
```

**Certificate format:**
- `TLS_CERT`: Full certificate chain (PEM format)
- `TLS_KEY`: Private key (PEM format)

### 3. Self-Signed (Local/Testing)

Automatically generates a self-signed certificate. Good for local networks.

```yaml
environment:
  - TLS_ENABLED=true
  - TLS_PORT=8443
```

**Note:** Clients will show certificate warnings. You may need to add an exception.

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `TLS_ENABLED` | Enable TLS | `false` |
| `TLS_PORT` | HTTPS port | `8443` |
| `TLS_DOMAIN` | Domain for Let's Encrypt | - |
| `TLS_EMAIL` | Email for Let's Encrypt | - |
| `TLS_CERT` | Path to certificate file | - |
| `TLS_KEY` | Path to private key file | - |

## Quick Start Examples

### Let's Encrypt

```bash
docker run -d \
  --name anki-sync \
  -p 80:80 \
  -p 443:443 \
  -e SYNC_USER1=user:password \
  -e TLS_ENABLED=true \
  -e TLS_DOMAIN=anki.example.com \
  -e TLS_EMAIL=admin@example.com \
  -v anki_data:/data \
  -v anki_config:/config \
  chrislongros/anki-sync-server-enhanced
```

### Self-Signed (Local)

```bash
docker run -d \
  --name anki-sync \
  -p 8080:8080 \
  -p 8443:8443 \
  -e SYNC_USER1=user:password \
  -e TLS_ENABLED=true \
  -v anki_data:/data \
  chrislongros/anki-sync-server-enhanced
```

Then configure Anki client to: `https://your-server:8443/`

## Client Configuration

### Desktop (Windows/Mac/Linux)

1. Open Anki → Tools → Preferences → Syncing
2. Set custom sync server: `https://anki.yourdomain.com/` or `https://192.168.1.100:8443/`
3. Sync with your credentials

### AnkiDroid

1. Settings → Sync → Custom sync server
2. Sync URL: `https://anki.yourdomain.com/`
3. Media URL: `https://anki.yourdomain.com/msync/`

### AnkiMobile (iOS)

1. Settings → Sync → Custom server
2. Enter: `https://anki.yourdomain.com/`

## Troubleshooting

### Certificate errors

- **Self-signed:** Accept the security exception in your browser/client
- **Let's Encrypt:** Ensure ports 80/443 are open and DNS is correct
- **Manual:** Check certificate chain is complete and paths are correct

### Let's Encrypt not working

```bash
# Check Caddy logs
docker logs anki-sync 2>&1 | grep -i caddy

# Verify DNS
nslookup anki.yourdomain.com

# Test port accessibility
curl -v http://anki.yourdomain.com
```

### Mixed HTTP/HTTPS

The server always runs HTTP internally on port 8080. Caddy handles TLS termination and proxies to it. You can still access HTTP directly if needed (for health checks, internal networks, etc.).
