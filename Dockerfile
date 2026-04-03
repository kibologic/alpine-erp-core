FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

# Temporarily force build to continue past install failures to capture debugging info in logs
RUN pnpm install --no-frozen-lockfile; exit 0

ENV PORT=3000
# Run from root /app so Node's module resolution finds everything in /app/node_modules
CMD ["node", "apps/server/dev.mjs"]
