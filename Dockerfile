FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

RUN pnpm install --frozen-lockfile || true

# Manually ensure @swissjs/swite resolves
# pnpm symlinks don't work reliably in Docker
RUN mkdir -p /app/apps/server/node_modules/@swissjs && \
    cp -r /app/packages/swite /app/apps/server/node_modules/@swissjs/swite && \
    mkdir -p /app/node_modules/@swissjs && \
    cp -r /app/packages/swite /app/node_modules/@swissjs/swite

# Manually copy all @swissjs core/plugin packages into node_modules
# This allows them to be found by swite and swiss-lib internal dependencies
RUN cp -r /app/packages/swiss-lib/packages/core /app/apps/server/node_modules/@swissjs/core && \
    cp -r /app/packages/swiss-lib/packages/compiler /app/apps/server/node_modules/@swissjs/compiler && \
    cp -r /app/packages/swiss-lib/packages/plugins/file-router /app/apps/server/node_modules/@swissjs/plugin-file-router && \
    cp -r /app/packages/swiss-lib/packages/router /app/apps/server/node_modules/@swissjs/router && \
    cp -r /app/packages/swiss-lib/packages/utils /app/apps/server/node_modules/@swissjs/utils && \
    cp -r /app/packages/swiss-lib/packages/security /app/apps/server/node_modules/@swissjs/security && \
    # Also copy to root node_modules for good measure
    cp -r /app/packages/swiss-lib/packages/core /app/node_modules/@swissjs/core && \
    cp -r /app/packages/swiss-lib/packages/compiler /app/node_modules/@swissjs/compiler && \
    cp -r /app/packages/swiss-lib/packages/plugins/file-router /app/node_modules/@swissjs/plugin-file-router && \
    cp -r /app/packages/swiss-lib/packages/router /app/node_modules/@swissjs/router && \
    cp -r /app/packages/swiss-lib/packages/utils /app/node_modules/@swissjs/utils && \
    cp -r /app/packages/swiss-lib/packages/security /app/node_modules/@swissjs/security

WORKDIR /app/apps/server

CMD ["node", "dev.mjs"]
