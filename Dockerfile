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
# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates wget curl bash tzdata sqlite3 openssl \
    jq netcat-openbsd python3 python3-pip procps cron msmtp \
    && rm -rf /var/lib/apt/lists/*
# Install Python packages
RUN pip3 install --break-system-packages --no-cache-dir flask boto3 argon2-cffi
# Create user and directories
RUN useradd -m -s /bin/bash -u 1000 anki \
    && mkdir -p /var/log/anki /var/lib/anki /data /backups /config \
    && touch /var/log/anki/sync.log /var/log/anki/auth.log /var/log/anki/backup.log \
    && chown -R anki:anki /var/log/anki /var/lib/anki /data /backups /config /home/anki
# Copy binary and version info
COPY --from=builder /usr/local/cargo/bin/anki-sync-server /usr/local/bin/
COPY --from=builder /anki_version.txt /anki_version.txt
# Copy all scripts
COPY scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py 2>/dev/null || true
EXPOSE 8080 9090 8081
VOLUME ["/data", "/backups", "/config"]
LABEL com.centurylinklabs.watchtower.enable="true"
LABEL org.opencontainers.image.source="https://github.com/chrislongros/anki-sync-server-enhanced"
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
