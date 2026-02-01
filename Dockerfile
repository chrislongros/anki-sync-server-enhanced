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

# Use Alpine for smaller image
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
    && adduser -D -s /bin/false -h /home/anki anki

# Copy binary and version info
COPY --from=builder /usr/local/cargo/bin/anki-sync-server /usr/local/bin/
COPY --from=builder /anki_version.txt /anki_version.txt

# Copy scripts
COPY entrypoint.sh /entrypoint.sh
COPY backup.sh /usr/local/bin/backup.sh
COPY healthcheck.sh /usr/local/bin/healthcheck.sh

RUN chmod +x /entrypoint.sh /usr/local/bin/backup.sh /usr/local/bin/healthcheck.sh && \
    mkdir -p /data /backups /config && \
    chown -R anki:anki /data /backups /config /home/anki

EXPOSE 8080
VOLUME ["/data", "/backups", "/config"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/entrypoint.sh"]
