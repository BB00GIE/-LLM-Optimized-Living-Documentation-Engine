# Multi-stage lightweight Dockerfile for Living Documentation Engine MCP Server
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY living_docs ./living_docs

RUN pip install --no-cache-dir --user .

# Final runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

# Create non-root user and group for security
RUN groupadd -r livingdocs && useradd -r -g livingdocs -m -d /app livingdocs

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /home/livingdocs/.local
ENV PATH=/home/livingdocs/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy source code and default examples into container
COPY --chown=livingdocs:livingdocs pyproject.toml README.md ./
COPY --chown=livingdocs:livingdocs living_docs ./living_docs
COPY --chown=livingdocs:livingdocs examples ./examples

USER livingdocs

# Pre-build index for example spec so container is immediately runnable out of the box
RUN mkdir -p /app/build && \
    python -m living_docs.cli build \
      --openapi examples/openapi.yaml \
      --markdown examples/docs \
      --python examples/src/client.py \
      --typescript examples/src/types.ts \
      --output /app/build \
      --project-name "Example Living Docs"

EXPOSE 8000

# Default command runs MCP server over Server-Sent Events (SSE) bound to 0.0.0.0
ENTRYPOINT ["living-docs", "serve", "--index", "/app/build/docs-index.json", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
