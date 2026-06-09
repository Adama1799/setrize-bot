FROM node:24-slim

ENV OPENCLAW_CONFIG_PATH=/root/.openclaw/openclaw.json
ENV OPENCLAW_WORKSPACE_DIR=/workspace

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g openclaw@latest \
    && mkdir -p /root/.openclaw

COPY . /workspace
COPY openclaw.json /root/.openclaw/openclaw.json

EXPOSE 18789

CMD ["openclaw", "gateway", "--port", "18789", "--verbose"]
