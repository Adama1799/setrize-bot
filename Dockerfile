FROM node:24-slim

WORKDIR /app

RUN npm install -g openclaw@latest

COPY workspace/ /root/.openclaw/workspace/
COPY openclaw.json /root/.openclaw/openclaw.json

EXPOSE 18789

CMD ["openclaw", "gateway", "--port", "18789", "--verbose"]
