# API image. Build context = repo root (needs services/data for exports/clash/validate/drawings).
# Mirrors the repo layout so routers' relative paths to ../data/src resolve.

# --- converter stage: Node deps for the IFC->Fragments republish (authoring round-trip) ---
# Pin the fragments/web-ifc pair to the SAME versions as the client parser (apps/web/package.json).
# CI enforces this (scripts/check-fragments-version.mjs) — a mismatch means the server emits .frag the
# browser can't parse.
FROM node:20-slim AS converter
WORKDIR /conv
ARG FRAGMENTS_VERSION=3.4.5
ARG WEBIFC_VERSION=0.0.77
RUN npm init -y >/dev/null 2>&1 && npm install --no-audit --no-fund \
    @thatopen/fragments@${FRAGMENTS_VERSION} web-ifc@${WEBIFC_VERSION}

# --- python build stage (B3): a full toolchain compiles any source-only wheel HERE, then we lift only
# the installed packages into the runtime image below. gcc + headers never ship to production, so the
# runtime image is smaller and carries no compiler in its attack surface. ---
FROM python:3.12-slim AS pybuild
# build toolchain + the same shared libs, so wheels that need to compile can link during install
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*
# resilient to slow/flaky PyPI: longer timeout + retries (heavy scientific wheels)
ENV PIP_DEFAULT_TIMEOUT=180 PIP_RETRIES=8 PIP_NO_CACHE_DIR=1
COPY services/api/requirements.lock /tmp/req/requirements.lock
# B2: the hash-pinned, prod-resolved lock. `--require-hashes` rejects any tampered/substituted wheel
# (supply-chain integrity). This single lock covers the data-service deps (a strict subset) and
# psycopg[binary], so one install replaces the previous two. Install into an isolated prefix we copy
# wholesale into the runtime stage.
RUN pip install --prefix=/install --require-hashes -r /tmp/req/requirements.lock

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api/src:/app/services/data/src \
    IFC_DIR=/app/ifc

# ONLY the shared libs the scientific wheels (ifcopenshell, shapely) dlopen at runtime — the build
# toolchain stays in the pybuild stage above and is deliberately not shipped.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# the pre-built site-packages + console scripts (uvicorn) from the build stage
COPY --from=pybuild /install /usr/local

COPY services/api/src /app/services/api/src
COPY services/data/src /app/services/data/src
# GC portal module definitions (module.json catalog) — the module engine loads these
# at startup from services/api/modules; without them the portal registers 0 modules
COPY services/api/modules /app/services/api/modules
# demo seeder (stdlib-only) so the stack can self-populate via the compose `seed` profile
COPY services/api/seed_demo.py /app/services/api/seed_demo.py
# Alembic migrations + config, so operators can run `alembic stamp/upgrade head` from the running
# container (see services/api/migrations/README.md). NOT run automatically at startup — the runtime
# still builds the schema via create_all + _ensure_* (no cutover in this PR).
COPY services/api/alembic.ini /app/services/api/alembic.ini
COPY services/api/migrations /app/services/api/migrations

# Node runtime + the IFC->Fragments converter so /publish can reconvert authored edits.
# The API invokes the converter with `node <script>` (subprocess) — deps resolve from /app/node_modules
# (node walks up from services/converter/src). It never runs `npm` at runtime, so the global npm CLI at
# /usr/local/lib/node_modules is deliberately NOT copied — that keeps npm's bundled deps (cross-spawn,
# glob, minimatch, sigstore, tar) and their CVEs out of the production image.
COPY --from=converter /usr/local/bin/node /usr/local/bin/node
COPY --from=converter /conv/node_modules /app/node_modules
COPY services/converter /app/services/converter

# Run as a non-root user (defence-in-depth). Create the runtime dirs and chown /app BEFORE the
# named volumes mount: Docker initializes an empty named volume from the image path's contents +
# ownership, so ifc-data (/app/ifc) and the storage dir inherit appuser ownership and stay writable.
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app/ifc /app/storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# container-level liveness (compose also defines this; this covers a bare `docker run`)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]
# multiple workers so one slow request (e.g. an IFC reconvert) can't freeze the whole
# API. Default 1 (safe for sqlite dev); compose sets UVICORN_WORKERS higher for Postgres.
CMD ["sh", "-c", "uvicorn aec_api.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
