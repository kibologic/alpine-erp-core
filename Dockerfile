FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

RUN pnpm install --frozen-lockfile

WORKDIR /app/apps/server

CMD ["node", "dev.mjs"]
