# Build the Vite app, then serve the static bundle with nginx.
# Build context = repo root (this is an npm workspace: the only lockfile is the root package-lock.json).
FROM node:20-slim AS build
WORKDIR /repo
# Manifests + lockfile first, so `npm ci` is a reproducible, cache-friendly layer that only re-runs when
# deps change — not on every source edit. `npm ci` (vs `npm install`) installs EXACTLY the locked tree
# and fails if package.json and the lockfile disagree (B3: reproducible builds).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web/ apps/web/
RUN npm run build --workspace apps/web   # prebuild copies web-ifc WASM into public/wasm/

FROM nginx:alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
