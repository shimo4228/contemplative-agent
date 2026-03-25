# --- Build stage ---
FROM python:3.13-slim AS builder
WORKDIR /build
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .

# --- Runtime stage ---
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -g 1000 agent && \
    useradd -u 1000 -g agent -s /bin/bash -m agent

# Install the package from build stage
COPY --from=builder /install /usr/local

# Copy config templates only (prompts, domain.json, templates/).
# Runtime data (identity, knowledge, constitution, ...) lives in /data (MOLTBOOK_HOME).
COPY config/ /app/config/

# Entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Create data directory
RUN mkdir -p /data && chown agent:agent /data

# Defaults
ENV MOLTBOOK_HOME=/data \
    CONTEMPLATIVE_CONFIG_DIR=/app/config \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER agent

ENTRYPOINT ["/app/docker-entrypoint.sh"]
