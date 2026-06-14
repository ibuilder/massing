# IFC→Fragments converter worker (Node). web-ifc WASM is bundled via node_modules.
FROM node:20-slim

WORKDIR /app
# converter deps are hoisted at the monorepo root; copy root manifest + installed modules.
COPY package.json package-lock.json* ./
COPY services/converter/package.json ./services/converter/package.json
RUN npm install --omit=dev --workspaces --include-workspace-root || npm install --omit=dev

COPY services/converter ./services/converter
COPY node_modules ./node_modules

WORKDIR /app/services/converter
ENTRYPOINT ["node", "src/cli.mjs"]
