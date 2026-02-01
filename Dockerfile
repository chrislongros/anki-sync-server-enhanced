FROM rust:1.75-slim-bookworm AS builder

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Clone and build anki-sync-server
RUN git clone --depth 1 https://github.com/ankitects/anki.git /anki
WORKDIR /anki
RUN cargo build --release --package anki-sync-server

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /bin/false anki

COPY --from=builder /anki/target/release/anki-sync-server /usr/local/bin/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER anki
EXPOSE 8080
VOLUME ["/data", "/backups"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:8080/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
