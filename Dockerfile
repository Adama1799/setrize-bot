FROM node:24-slim

ENV OPENCLAW_CONFIG_PATH=/root/.openclaw/openclaw.json
WORKDIR /app

RUN npm install -g openclaw@latest \
    && mkdir -p /root/.openclaw/workspace

COPY workspace/ /root/.openclaw/workspace/
COPY openclaw.json /root/.openclaw/openclaw.json

EXPOSE 18789

CMD ["openclaw", "gateway", "--port", "18789", "--verbose"]
