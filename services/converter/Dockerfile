# IFC→Fragments converter (Node). Build context = repo root.
FROM node:26-slim@sha256:715e55e4b84e4bb0ff48e49b398a848f08e55daed8eb6a0ea1839ae53bc57583
WORKDIR /app

# install just what the converter needs; web-ifc ships its own WASM. Pin to the SAME versions as the
# client parser (apps/web/package.json) — CI enforces this via scripts/check-fragments-version.mjs.
ARG FRAGMENTS_VERSION=3.4.5
ARG WEBIFC_VERSION=0.0.77
RUN npm init -y >/dev/null 2>&1 \
    && npm install @thatopen/fragments@${FRAGMENTS_VERSION} web-ifc@${WEBIFC_VERSION}

COPY services/converter /app/services/converter

# usage: docker compose run --rm converter /data/model.ifc /data/model.frag
ENTRYPOINT ["node", "services/converter/src/cli.mjs"]
