# IFC→Fragments converter (Node). Build context = repo root.
FROM node:20-slim
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
