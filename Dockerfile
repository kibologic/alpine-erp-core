FROM node:20-slim

RUN npm install -g pnpm@9

WORKDIR /app

# Copy the entire mono-repo (now including bundled swite/swiss-lib)
COPY . /app

# Install dependencies (will use pnpm workspace context)
RUN pnpm install --frozen-lockfile

# Start the frontend service
CMD ["node", "apps/server/dev.mjs"]
