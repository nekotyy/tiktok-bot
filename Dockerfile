FROM rust:1-bookworm AS builder

WORKDIR /usr/src/tiktok-bot
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY tests ./tests
RUN cargo build --release

FROM denoland/deno:bin-2.9.4 AS deno

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=deno /deno /usr/local/bin/deno
COPY --from=builder /usr/src/tiktok-bot/target/release/tiktok-bot /usr/local/bin/tiktok-bot

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && pip install --no-cache-dir yt-dlp curl-cffi \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/data /app/downloads

ENTRYPOINT ["/usr/local/bin/tiktok-bot"]
