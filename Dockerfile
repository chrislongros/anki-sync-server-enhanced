# =============================================================================
# Anki Sync Server Enhanced - Comprehensive Docker Image
# =============================================================================
# Features:
# - Auto-version detection from GitHub
# - Multi-architecture (amd64, arm64, arm/v7)
# - Multi-user with hashed password support
# - Docker secrets support
# - Automated backups with S3 upload
# - Prometheus metrics
# - Web dashboard
# - Email/webhook notifications
# - Rate limiting
# - Fail2ban
# - Sync logging
# - User management CLI
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

# Final image - Alpine for small size
FROM alpine:3.21

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    wget \
    curl \
    bash \
    tzdata \
    sqlite \
    openssl \
    dcron \
    jq \
    netcat-openbsd \
    shadow \
    python3 \
    py3-pip \
    py3-boto3 \
    
    msmtp \
    msmtp-mta \
    fail2ban \
    iptables \
    ip6tables \
    && pip3 install --break-system-packages flask argon2-cffi \
    && adduser -D -s /bin/bash -h /home/anki -u 1000 anki \
    && mkdir -p /var/log/anki /var/lib/anki /run/fail2ban \
    && touch /var/log/anki/sync.log /var/log/anki/auth.log /var/log/anki/backup.log \
    && chown -R anki:anki /var/log/anki /var/lib/anki

# Copy binary and version info
COPY --from=builder /usr/local/cargo/bin/anki-sync-server /usr/local/bin/
COPY --from=builder /anki_version.txt /anki_version.txt

# Copy all scripts
COPY scripts/ /usr/local/bin/
COPY dashboard.py /usr/local/bin/dashboard.py

# Copy fail2ban config
COPY fail2ban/ /etc/fail2ban/

RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py \
    && mkdir -p /data /backups /config \
    && chown -R anki:anki /data /backups /config /home/anki

# Ports
# 8080 - Anki sync server
# 9090 - Prometheus metrics
# 8081 - Web dashboard
EXPOSE 8080 9090 8081

VOLUME ["/data", "/backups", "/config"]

# Watchtower labels
LABEL com.centurylinklabs.watchtower.enable="true"
LABEL org.opencontainers.image.source="https://github.com/chrislongros/anki-sync-server-enhanced"
LABEL org.opencontainers.image.description="Self-hosted Anki sync server with backups, metrics, dashboard, and notifications"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
