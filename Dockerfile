FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . .

ARG GITHUB_TOKEN
RUN if [ -n "$GITHUB_TOKEN" ]; then \
      echo "//npm.pkg.github.com/:_authToken=$GITHUB_TOKEN" >> .npmrc; \
    fi && \
    pnpm install --no-frozen-lockfile && \
    rm -f .npmrc

ENV PORT=3000
CMD ["node", "apps/server/dev.mjs"]
