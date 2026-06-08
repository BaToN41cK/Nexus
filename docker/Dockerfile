# ------------------------------------------------------------
# Multi-stage Docker build for Nexus
# ------------------------------------------------------------

# ---------- Builder stage ----------
FROM python:3.11-slim AS builder

LABEL maintainer="Nexus AI Assistant"
LABEL description="Nexus — ИИ-ассистент с загрузкой контента из URL"

WORKDIR /app

# Install build dependencies (gcc for any compiled wheels)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . .

# Install the package and its dependencies into /install
RUN pip install --no-cache-dir --target=/install -e .

# Ensure the console script is available in the target directory
RUN cp /usr/local/bin/nexus /install/

# ---------- Runtime stage ----------
FROM python:3.11-alpine AS runtime

WORKDIR /app

# Copy installed packages and the console script from the builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY --from=builder /install/nexus /usr/local/bin/nexus

# Copy the application source (optional, for reference or runtime assets)
COPY --from=builder /app /app

# Create Nexus data directories
RUN mkdir -p /root/.nexus/cache /root/.nexus/history

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["nexus"]
CMD ["--help"]