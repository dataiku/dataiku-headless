# syntax=docker/dockerfile:1.7
# bench-agents: runtime-only image for sandboxed benchmark agents.
#
# Ships ONLY what an agent run needs at execution time:
#   - claude + codex CLIs
#   - the `dku` CLI (installed as an isolated uv tool; its source is removed)
#   - dataiku-api-client for the vanilla (raw-API) baseline
#
# The dataiku MCP server is NOT here — it runs as a separate `bench-mcp` HTTP
# sidecar (Dockerfile.mcp), so MCP-profile agents get a URL only, never the
# server source or DSS creds.
#
# It deliberately contains NO benchmark repo, scenarios, solutions, .env, or
# skills. The host runner mounts per run: the agent's config dir (/cfg), the
# fixture dir (/work), and only the skills a profile grants. The container is
# the isolation boundary.
#
# Build with benchmark/docker/build.sh.

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git jq tini build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# uv (for the dku install and the MCP `uv run`)
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Agent CLIs
RUN npm install -g --omit=dev @anthropic-ai/claude-code @openai/codex \
    && npm cache clean --force

# Raw-API client for the vanilla baseline profile (system python).
RUN pip install --no-cache-dir dataiku-api-client

# Non-root agent user.
ARG AGENT_UID=1000
ARG AGENT_GID=1000
RUN groupadd -g ${AGENT_GID} agent \
    && useradd -m -u ${AGENT_UID} -g ${AGENT_GID} -s /bin/bash agent \
    && mkdir -p /opt/bench && chown -R agent:agent /opt/bench

# Install dku from source, then drop the source so agents can't read it.
COPY --chown=agent:agent dku-cli /tmp/dku-src
USER agent
ENV PATH="/home/agent/.local/bin:${PATH}"
RUN uv tool install --from /tmp/dku-src dku-cli && rm -rf /tmp/dku-src

# The MCP server is deliberately NOT in this image. MCP profiles connect to a
# separate `bench-mcp` HTTP sidecar (see Dockerfile.mcp); the agent never has
# the server source on disk and never receives DSS creds. This keeps the MCP
# comparison realistic — the agent uses the tools blind, as in a real deployment.

# Provenance (git SHAs + build time) so each run is attributable. Written by build.sh.
COPY --chown=agent:agent build-info.json /opt/bench/BUILD_INFO.json

WORKDIR /work
COPY --chown=agent:agent benchmark-entrypoint.sh /usr/local/bin/bench-entrypoint
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/bench-entrypoint"]
CMD ["bash"]
