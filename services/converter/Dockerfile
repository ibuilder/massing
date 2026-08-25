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
# problem and nothing to trade away. `chown` on the app tree so the non-root user can read what it
# was given and write nothing it was not.
#
# `useradd`, NOT `adduser -S`. This line read `addgroup -S app && adduser -S -G app app` from
# v0.3.936 — BusyBox/Alpine syntax on a Debian base. Debian's adduser is a Perl script whose short
# options are Getopt::Long abbreviations, and both of those are ambiguous there:
#
#     $ addgroup -S app
#     Option s is ambiguous (shell, stderrmsglevel, stdoutmsglevel, system)
#     $ adduser -S -G app app
#     Option s is ambiguous (...)   Option g is ambiguous (gecos, gid, group)
#
# Both exit non-zero, so this RUN failed and **the image could not be built at all**. The commit
# that introduced it is titled "drop root in the converter image": the hardening it describes has
# never run anywhere, because nothing has ever built this file. See ci.yml's container matrix —
# until this change it listed api and web only, so `services/converter/Dockerfile` was the one
# Dockerfile in the repo that no job built, on any event.
#
# Same idiom and same uid as `services/api/Dockerfile`, which is Debian too and does build.
RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# usage: docker compose run --rm converter /data/model.ifc /data/model.frag
ENTRYPOINT ["node", "services/converter/src/cli.mjs"]
