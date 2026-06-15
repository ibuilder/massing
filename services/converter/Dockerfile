# IFC→Fragments converter (Node). Build context = repo root.
FROM node:20-slim
WORKDIR /app

# install just what the converter needs; web-ifc ships its own WASM
RUN npm init -y >/dev/null 2>&1 \
    && npm install @thatopen/fragments@3.4.5 web-ifc@0.0.77

COPY services/converter /app/services/converter

# usage: docker compose run --rm converter /data/model.ifc /data/model.frag
ENTRYPOINT ["node", "services/converter/src/cli.mjs"]
