# Build the Vite app, then serve the static bundle with nginx.
# Build context = repo root (this is an npm workspace: the only lockfile is the root package-lock.json).
FROM node:26-slim@sha256:715e55e4b84e4bb0ff48e49b398a848f08e55daed8eb6a0ea1839ae53bc57583 AS build
WORKDIR /repo
# Manifests + lockfile first, so `npm ci` is a reproducible, cache-friendly layer that only re-runs when
# deps change — not on every source edit. `npm ci` (vs `npm install`) installs EXACTLY the locked tree
# and fails if package.json and the lockfile disagree (B3: reproducible builds).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web/ apps/web/
RUN npm run build --workspace apps/web   # prebuild copies web-ifc WASM into public/wasm/

FROM nginx:alpine@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
