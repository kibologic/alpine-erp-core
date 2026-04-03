FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

# Show what's in the workspace
RUN ls -F packages/

# Try install with verbose output to debug resolution issues on Railway
RUN pnpm install --no-frozen-lockfile --reporter=default 2>&1 || \
    (ls -R /root/.local/share/pnpm/store/v3/tmp/ 2>/dev/null; cat /root/.local/share/pnpm/store/v3/tmp/*/last-error.log 2>/dev/null; exit 1)

ENV PORT=3000
# Run from root /app so Node's module resolution finds everything in /app/node_modules
CMD ["node", "apps/server/dev.mjs"]
