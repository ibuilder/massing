# IFC→Fragments converter (Node). Build context = repo root.
FROM node:25-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370
WORKDIR /app

# install just what the converter needs; web-ifc ships its own WASM. Pin to the SAME versions as the
# client parser (apps/web/package.json) — CI enforces this via scripts/check-fragments-version.mjs.
ARG FRAGMENTS_VERSION=3.4.7
ARG WEBIFC_VERSION=0.0.77
RUN npm init -y >/dev/null 2>&1 \
    && npm install @thatopen/fragments@${FRAGMENTS_VERSION} web-ifc@${WEBIFC_VERSION}

COPY services/converter /app/services/converter

# Drop root. This image is a CLI entrypoint — it binds no port, so there is no privileged-port
# problem and nothing to trade away. `--chown` on the app tree so the non-root user can read
# what it was given and write nothing it was not.
RUN addgroup -S app && adduser -S -G app app && chown -R app:app /app
USER app

# usage: docker compose run --rm converter /data/model.ifc /data/model.frag
ENTRYPOINT ["node", "services/converter/src/cli.mjs"]
