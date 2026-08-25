# IFC→Fragments converter (Node). Build context = repo root.
# Node 24 LTS, the same pinned digest as `services/api/Dockerfile` and `apps/web/Dockerfile` —
# one Node runtime across the product, which is what those two already say in as many words. The
# previous pin here was node:25-slim, an EOL major with no security patches: #117 and #116 raised
# both converter images together, the api one was reverted to 24 four days later for that reason,
# and this file was not. `scripts/check-fragments-version.mjs` gates the two ARGs below across
# both Dockerfiles and stops one line short of the base image.
FROM node:24-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0
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
