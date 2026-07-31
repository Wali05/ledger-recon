FROM python:3.12-slim

# Don't buffer stdout — otherwise container logs appear only when the buffer
# flushes, which makes debugging a live deploy painful.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Build toolchain is needed to compile psycopg2; removed in the same layer so it
# doesn't ship in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. If the container is ever compromised, the attacker
# does not land as root inside it.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Managed platforms (Render, Railway, Fly, Cloud Run) inject the port to bind on
# via $PORT and will consider the deploy failed if the process ignores it.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
