FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . .

# Token injected as build arg from Railway env var
ARG GITHUB_TOKEN
RUN echo "//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}" >> .npmrc && \
    pnpm install --no-frozen-lockfile && \
    rm -f .npmrc

ENV PORT=3000
CMD ["node", "apps/server/dev.mjs"]
