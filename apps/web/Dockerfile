# Build the Vite app, then serve the static bundle with nginx.
# Build context = repo root (this is an npm workspace: the only lockfile is the root package-lock.json).
FROM node:24-slim@sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df AS build
WORKDIR /repo
# Manifests + lockfile first, so `npm ci` is a reproducible, cache-friendly layer that only re-runs when
# deps change — not on every source edit. `npm ci` (vs `npm install`) installs EXACTLY the locked tree
# and fails if package.json and the lockfile disagree (B3: reproducible builds).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web/ apps/web/
RUN npm run build --workspace apps/web   # prebuild copies web-ifc WASM into public/wasm/

FROM nginx:1.31-alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
