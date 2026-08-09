# Serves the vault over MCP (`pipeline mcp-serve`). This image does not bundle
# Ollama or the vault itself — both are expected to be reachable from the
# container (Ollama via OLLAMA_HOST, the vault via a mounted volume). See
# docs/reference/configuration.md for every other env var.
FROM python:3.12-slim AS base

# libgl1/libglib2.0-0: Docling's PDF/image pipeline (via its OCR/vision deps)
# needs these even when never touching a display.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies before copying source so this layer only rebuilds when
# pyproject.toml/uv.lock change, not on every code edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# The vault must be mounted here and VAULT_PATH pointed at it — there is no
# vault baked into the image:
#   docker run -v /path/to/vault:/vault -e VAULT_PATH=/vault \
#     -e OLLAMA_HOST=http://host.docker.internal:11434 \
#     -p 8000:8000 <image>
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health', timeout=3).status_code == 200 else 1)"

CMD ["pipeline", "mcp-serve"]
