FROM rustlang/rust:nightly-slim AS builder

RUN apt-get update && apt-get install -y \
    git \
    pkg-config \
    libssl-dev \
    protobuf-compiler \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Auto-detect latest Anki version if not provided
ARG ANKI_VERSION=""
RUN if [ -z "$ANKI_VERSION" ]; then \
      ANKI_VERSION=$(curl -s https://api.github.com/repos/ankitects/anki/releases/latest | jq -r '.tag_name'); \
    fi && \
    echo "Building Anki sync server version: $ANKI_VERSION" && \
    cargo install --git https://github.com/ankitects/anki.git \
      --tag ${ANKI_VERSION} \
      anki-sync-server

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /bin/false -m anki

COPY --from=builder /usr/local/cargo/bin/anki-sync-server /usr/local/bin/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER anki
EXPOSE 8080
VOLUME ["/data", "/backups"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:8080/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
