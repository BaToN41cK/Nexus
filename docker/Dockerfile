FROM python:3.11-slim

LABEL maintainer="Nexus AI Assistant"
LABEL description="Nexus — ИИ-ассистент с загрузкой контента из URL"

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -e .

# Create nexus directories
RUN mkdir -p /root/.nexus/cache /root/.nexus/history

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command
ENTRYPOINT ["nexus"]
CMD ["--help"]