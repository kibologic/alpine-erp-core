FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

# Using --no-frozen-lockfile because we have local bundled workspace packages
# that pnpm needs to resolve correctly in the build environment
RUN pnpm install --no-frozen-lockfile

# Verify the swite framework is correctly resolved by the monorepo
RUN node -e "import('@swissjs/swite').then(m => console.log('swite OK')).catch(e => { console.error('swite MISSING', e.message); process.exit(1); })"

ENV PORT=3000
ENV NODE_ENV=production

# Run from root /app so Node's module resolution finds everything in /app/node_modules
CMD ["node", "apps/server/dev.mjs"]
