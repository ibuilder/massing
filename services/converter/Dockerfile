# IFC→Fragments converter (Node). Build context = repo root.
# Node 24 LTS, the same pinned digest as `services/api/Dockerfile` and `apps/web/Dockerfile` —
# one Node runtime across the product, which is what those two already say in as many words. The
# previous pin here was node:25-slim, an EOL major with no security patches: #117 and #116 raised
# both converter images together, the api one was reverted to 24 four days later for that reason,
# and this file was not. `scripts/check-fragments-version.mjs` gates the two ARGs below across
# both Dockerfiles and stops one line short of the base image.
FROM node:24-slim@sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df

# The `libgnutls30` upgrade this file carried is GONE, and the base digest moved instead.
#
# v0.3.1098 patched two CRITICAL CVEs by name — the only way to fix them without moving the pin, and
# recorded in the same commit as a treadmill: *"every future CRITICAL in the base will red this gate
# until the shared digest is re-pinned to a newer node:24-slim. Re-pinning is the right answer and
# accumulating `--only-upgrade` lines is not."* This is that re-pin.
#
#     was  sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0
#     now  sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df
#
# **Whether the new base already carries `libgnutls30 3.7.9-2+deb12u7` could not be checked before
# pushing**, and that is worth stating rather than implying. There is no Docker daemon in the agent
# container, and the proxy denies image *blob* fetches (`production.cloudfront.docker.com`, 403 at
# CONNECT), so the layers cannot be read either. Manifests resolve, which confirms only that the
# digest is real and still covers `linux/amd64`.
#
# So the `--only-upgrade` line is removed as a **hypothesis under test, with Trivy as the
# adjudicator** — the scan that v0.3.1098 made possible by putting this image in the build matrix in
# the first place. If the CRITICAL returns, the line comes back with the scan output as its evidence,
# and the treadmill is then a measured fact rather than a prediction.

WORKDIR /app

# install just what the converter needs; web-ifc ships its own WASM. Pin to the SAME versions as the
# client parser (apps/web/package.json) — CI enforces this via scripts/check-fragments-version.mjs.
ARG FRAGMENTS_VERSION=3.4.7
ARG WEBIFC_VERSION=0.0.77
RUN npm init -y >/dev/null 2>&1 \
    && npm install --no-audit --no-fund \
       @thatopen/fragments@${FRAGMENTS_VERSION} web-ifc@${WEBIFC_VERSION} \
    && npm cache clean --force \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /root/.npm

# npm is a BUILD tool here and must not ship. This image is the only single-stage one in the repo:
# `node:24-slim` is its runtime, so everything the base carries — including npm and the copy of
# node-tar npm bundles — lands in the published image. The first Trivy scan this file has ever had
# failed on exactly that:
#
#     tar (package.json)  CVE-2026-59873  CRITICAL  fixed  installed 6.2.1  fixed in 7.5.19
#
# Nothing in the two lines above installs `tar`; a clean `npm install` of these two packages pulls
# seven packages and none of them is tar. It is `/usr/local/lib/node_modules/npm/node_modules/tar`,
# vendored inside npm itself.
#
# The other two images never had this problem and never had to solve it either — they are
# multi-stage, so npm stays in a build stage. `services/api/Dockerfile` takes exactly two things out
# of its node stage, `/usr/local/bin/node` and `/conv/node_modules`; `apps/web/Dockerfile` ships
# nginx and copies only `dist`. Removing npm here reaches the same end state: the runtime keeps the
# `node` binary and the resolved `node_modules`, which is all the ENTRYPOINT below uses.

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
