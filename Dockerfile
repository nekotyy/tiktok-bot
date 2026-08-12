FROM denoland/deno:bin-2.9.4 AS deno
FROM ghcr.io/astral-sh/uv:0.7 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY --from=deno /deno /usr/local/bin/deno
COPY --from=uv /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/data /app/downloads

CMD ["uv", "run", "python", "-m", "bot.main"]
