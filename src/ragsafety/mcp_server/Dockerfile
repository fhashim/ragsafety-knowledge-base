# MCP server container for Azure Container Apps.
# Build context is the REPO ROOT:
#   docker build -f src/ragsafety/mcp_server/Dockerfile -t ragsafety-mcp .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAGSAFETY_MCP_TRANSPORT=streamable-http

WORKDIR /app

# Install runtime deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code, config and the synthetic data (used in mock mode / local demo).
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/
COPY pyproject.toml ./

ENV PYTHONPATH=/app/src
EXPOSE 8000

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# The MCP server listens on 0.0.0.0:8000 (MCPServer streamable-http default host/port
# is configured via env in server.py defaults). In Azure mode set RAGSAFETY_MOCK_MODE=false
# and provide the platform endpoints via Container App env/secrets.
CMD ["python", "-m", "ragsafety.mcp_server.server"]
