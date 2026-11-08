# ─── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt pyproject.toml setup.py README.md MANIFEST.in ./
COPY veloroute/ ./veloroute/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# ─── Stage 2: Production Runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="VeloRoute" \
      org.opencontainers.image.description="Enterprise Universal AI Gateway, High-Availability LLM Routing & Token-Saviour Engine" \
      org.opencontainers.image.url="https://github.com/mrgusux/veloroute" \
      org.opencontainers.image.source="https://github.com/mrgusux/veloroute" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VELOROUTE_STORAGE_BACKEND="sqlite" \
    VELOROUTE_STORAGE_URL="sqlite+aiosqlite:////data/veloroute.db" \
    VELOROUTE_UI_HOST="0.0.0.0" \
    VELOROUTE_UI_PORT=8000

# Create dedicated unprivileged user and directories
RUN groupadd -g 10001 veloroute && \
    useradd -u 10001 -g veloroute -s /bin/bash -m veloroute && \
    mkdir -p /app /data && \
    chown -R veloroute:veloroute /app /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=veloroute:veloroute . /app

USER veloroute

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).getcode() == 200 else 1)"

ENTRYPOINT ["python", "-m", "veloroute.cli"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8000"]
