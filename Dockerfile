FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

# .npmrc uses ${GITHUB_TOKEN} env var — safe to copy
COPY .npmrc ./
COPY package.json pnpm-workspace.yaml ./
COPY pnpm-lock.yaml ./
COPY apps/ apps/
COPY modules/ modules/
COPY packages/ packages/

RUN pnpm install --no-frozen-lockfile

ENV PORT=3000
CMD ["node", "apps/server/dev.mjs"]
