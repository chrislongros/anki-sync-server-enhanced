# =============================================================================
# Anki Sync Server Enhanced - Comprehensive Docker Image
# =============================================================================
FROM rustlang/rust:nightly-slim AS builder
RUN apt-get update && apt-get install -y \
    git \
    pkg-config \
    libssl-dev \
    protobuf-compiler \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*
ARG ANKI_VERSION=""
RUN if [ -z "$ANKI_VERSION" ]; then \
      ANKI_VERSION=$(curl -s https://api.github.com/repos/ankitects/anki/releases/latest | jq -r '.tag_name'); \
    fi && \
    echo "Building Anki sync server version: $ANKI_VERSION" && \
    echo "$ANKI_VERSION" > /anki_version.txt && \
    cargo install --git https://github.com/ankitects/anki.git \
      --tag ${ANKI_VERSION} \
      anki-sync-server

# Final image - Debian for glibc compatibility
FROM debian:bookworm-slim

# Install runtime dependencies including Caddy for TLS
RUN apt-get update && apt-get install -y \
    ca-certificates wget curl bash tzdata sqlite3 openssl \
    jq netcat-openbsd python3 python3-pip procps cron msmtp \
    debian-keyring debian-archive-keyring apt-transport-https \
    && rm -rf /var/lib/apt/lists/*

# Install Caddy for automatic HTTPS
RUN curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y caddy \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install --break-system-packages --no-cache-dir flask boto3 argon2-cffi

# Create user and directories
RUN useradd -m -s /bin/bash -u 1000 anki \
    && mkdir -p /var/log/anki /var/lib/anki /data /backups /config /config/caddy \
    && touch /var/log/anki/sync.log /var/log/anki/auth.log /var/log/anki/backup.log \
    && chown -R anki:anki /var/log/anki /var/lib/anki /data /backups /config /home/anki

# Copy binary and version info
COPY --from=builder /usr/local/cargo/bin/anki-sync-server /usr/local/bin/
COPY --from=builder /anki_version.txt /anki_version.txt

# Copy all scripts
COPY scripts/ /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/
COPY healthcheck.sh /usr/local/bin/
COPY backup.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py 2>/dev/null || true

# Expose ports: HTTP, HTTPS, Metrics, Dashboard
EXPOSE 8080 8443 9090 8081

VOLUME ["/data", "/backups", "/config"]

LABEL com.centurylinklabs.watchtower.enable="true"
LABEL org.opencontainers.image.source="https://github.com/chrislongros/anki-sync-server-enhanced"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
