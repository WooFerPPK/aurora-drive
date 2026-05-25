FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# Default to loopback — fh-racer is single-driver, local-only.
# compose overrides FH6_LISTEN_ADDR / FH6_HTTP_HOST to 0.0.0.0 because the
# host-side port mapping (127.0.0.1:PORT:PORT) is the actual loopback gate.
# Direct `docker run` invocations stay safe.
ENV FH6_LISTEN_ADDR=127.0.0.1 \
    FH6_LISTEN_PORT=5302 \
    FH6_HTTP_HOST=127.0.0.1 \
    FH6_HTTP_PORT=8000

EXPOSE 8000/tcp
EXPOSE 5302/udp
ENTRYPOINT ["python", "-m", "fh6.main"]
