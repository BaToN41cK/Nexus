# ------------------------------------------------------------
# Multi-stage Docker build for Nexus
# ------------------------------------------------------------
# Build:
#   docker build -t nexus:latest -f docker/Dockerfile .
# Run:
#   docker run --rm -it \
#     -v ~/.nexus:/root/.nexus \
#     -e GROQ_API_KEY=your_key \
#     nexus run "What is Python?"
#
# Optional dependencies:
#   docker build --build-arg INSTALL_OPENAI=1 --build-arg INSTALL_ANTHROPIC=1 ... .
# ------------------------------------------------------------

# ---------- Builder stage ----------
FROM python:3.11-slim AS builder

LABEL maintainer="Nexus AI Assistant"
LABEL description="Nexus — ИИ-ассистент с загрузкой контента из URL и web-поиском"
LABEL version="1.0.0"

WORKDIR /app

# Install build dependencies (gcc for any compiled wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first for better layer caching
COPY pyproject.toml requirements.txt ./

# Install the package and all dependencies into /install
RUN pip install --no-cache-dir --target=/install -e .[all]

# Copy application source
COPY . .

# Re-install to include the source
RUN pip install --no-cache-dir --target=/install -e .[all]

# Copy the console entry point
RUN cp /usr/local/bin/nexus /install/bin/nexus 2>/dev/null || true

# ---------- Runtime stage ----------
FROM python:3.11-alpine AS runtime

LABEL maintainer="Nexus AI Assistant"
LABEL description="Nexus — AI assistant with URL content loading and web search"
LABEL version="1.0.0"

WORKDIR /app

# Install runtime system dependencies
RUN apk add --no-cache ca-certificates

# Copy installed packages from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY --from=builder /install/bin/nexus /usr/local/bin/nexus

# Copy the application source for runtime assets (locale, config)
COPY --from=builder /app /app

# Create Nexus data directories
RUN mkdir -p /root/.nexus/cache \
    /root/.nexus/history \
    /root/.nexus/search_cache

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NEXUS_DOCKER=1

ENTRYPOINT ["nexus"]
CMD ["--help"]