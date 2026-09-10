# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Build wheel package
RUN pip install --no-cache-dir build && python -m build --wheel

# Runtime Stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user
RUN groupadd -g 10001 textora && \
    useradd -u 10001 -g textora -s /bin/bash -m textora

# Copy wheel from builder and install with server & STT support
COPY --from=builder /app/dist/*.whl /tmp/
RUN WHL=$(ls /tmp/*.whl) && pip install --no-cache-dir "${WHL}[server,stt]" && rm -rf /tmp/*.whl

# Setup data and state directories with proper ownership
RUN mkdir -p /app/output /app/output/.platform && \
    chown -R textora:textora /app

USER textora

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/v1/health || exit 1

ENTRYPOINT ["textora-engine"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000", "--output", "/app/output"]
