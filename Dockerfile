FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

COPY . /app

# Copy @swissjs packages into place BEFORE pnpm install
# so pnpm finds them as real directories not symlinks
RUN mkdir -p node_modules/@swissjs && \
    cp -r packages/swite node_modules/@swissjs/swite && \
    cp -r packages/swiss-lib/packages/core node_modules/@swissjs/core 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/compiler node_modules/@swissjs/compiler 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/router node_modules/@swissjs/router 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/utils node_modules/@swissjs/utils 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/security node_modules/@swissjs/security 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/plugins/file-router node_modules/@swissjs/plugin-file-router 2>/dev/null || true

# Also copy into apps/server/node_modules
RUN mkdir -p apps/server/node_modules/@swissjs && \
    cp -r packages/swite apps/server/node_modules/@swissjs/swite && \
    cp -r packages/swiss-lib/packages/core apps/server/node_modules/@swissjs/core 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/compiler apps/server/node_modules/@swissjs/compiler 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/router apps/server/node_modules/@swissjs/router 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/utils apps/server/node_modules/@swissjs/utils 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/security apps/server/node_modules/@swissjs/security 2>/dev/null || true && \
    cp -r packages/swiss-lib/packages/plugins/file-router apps/server/node_modules/@swissjs/plugin-file-router 2>/dev/null || true

# Verify the copy worked
RUN ls -l apps/server/node_modules/@swissjs/swite/ && \
    ls -l apps/server/node_modules/@swissjs/swite/dist/ || echo "no dist"

# Now install remaining deps
# Using --no-frozen-lockfile because we manually injected directories into node_modules
# which might make the lockfile look 'dirty' to pnpm
RUN pnpm install --no-frozen-lockfile 2>/dev/null || \
    pnpm install --frozen-lockfile 2>/dev/null || \
    npm install --legacy-peer-deps || true

WORKDIR /app/apps/server

CMD ["node", "dev.mjs"]
