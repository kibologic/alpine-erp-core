FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

# .npmrc uses ${GITHUB_TOKEN} env var — safe to copy
COPY .npmrc ./
COPY . .

RUN pnpm install --no-frozen-lockfile

ENV PORT=3000
CMD ["node", "apps/server/dev.mjs"]
