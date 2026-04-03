FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . .

# Railway passes GITHUB_TOKEN as env var at build time
# Try secret mount first, fall back to env var
RUN --mount=type=secret,id=GITHUB_TOKEN \
    TOKEN=$(cat /run/secrets/GITHUB_TOKEN 2>/dev/null || echo "$GITHUB_TOKEN") && \
    echo "//npm.pkg.github.com/:_authToken=$TOKEN" >> .npmrc && \
    pnpm install --no-frozen-lockfile && \
    rm -f .npmrc

ENV PORT=3000
CMD ["node", "apps/server/dev.mjs"]
