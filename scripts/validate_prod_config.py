#!/usr/bin/env python3
"""Production preflight - validate the environment BEFORE exposing the stack.

Reads the same env vars the API reads and asserts the production posture. Run it inside the api
container (or with the prod env loaded) as the go/no-go gate the checklist points at:

    docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api \
        python /app/scripts/validate_prod_config.py

Exit 0 = safe to expose. Exit 1 = hard failures (fix before go-live). Warnings don't fail the run
but are printed for review. Stdlib only."""
from __future__ import annotations

import os
import sys

FAIL: list[str] = []
WARN: list[str] = []


def env(k: str) -> str:
    return (os.environ.get(k) or "").strip()


db = env("DATABASE_URL")
is_postgres = db.startswith(("postgres://", "postgresql://", "postgresql+"))

# --- hard requirements on a real database -------------------------------------------------------
if not is_postgres:
    WARN.append(f"DATABASE_URL is not Postgres ({db or 'unset'}) - this looks like a dev/desktop "
                "profile, not production.")
if env("AEC_RBAC") != "1":
    FAIL.append("AEC_RBAC must be '1' - without it every authenticated user sees every project.")
if not env("AEC_AUTH_SECRET"):
    FAIL.append("AEC_AUTH_SECRET is unset - auth tokens are forgeable (public dev secret).")
elif len(env("AEC_AUTH_SECRET")) < 32:
    WARN.append("AEC_AUTH_SECRET is short (<32 chars) - use a long random value.")
if env("AEC_REQUIRE_SECRET") != "1":
    WARN.append("AEC_REQUIRE_SECRET should be '1' so a missing secret is a boot failure.")
if env("AEC_TRUST_XUSER") == "1":
    FAIL.append("AEC_TRUST_XUSER=1 trusts the X-User header - dev/test only, never production.")
if env("AEC_ALLOW_OPEN") == "1":
    WARN.append("AEC_ALLOW_OPEN=1 disables the production guard - make sure this is intentional.")

# --- transport / headers -------------------------------------------------------------------------
if env("AEC_HSTS") != "1":
    WARN.append("AEC_HSTS should be '1' behind TLS (Caddy/nginx).")
if env("AEC_COOKIE_SECURE") != "1":
    FAIL.append("AEC_COOKIE_SECURE must be '1' - otherwise the auth cookie travels over plain HTTP.")
if env("AEC_CSP") != "1":
    WARN.append("AEC_CSP should be '1' for the strict Content-Security-Policy (defense-in-depth).")
if not env("AEC_ALLOWED_HOSTS"):
    WARN.append("AEC_ALLOWED_HOSTS is unset - consider pinning the public hostname "
                "(include 'localhost' for container healthchecks).")

# --- rate limiting / multi-worker ----------------------------------------------------------------
workers = env("UVICORN_WORKERS") or env("WEB_CONCURRENCY") or "1"
rpm = env("AEC_RATE_LIMIT_RPM") or "0"
try:
    many_workers = int(workers) > 1
except ValueError:
    many_workers = False
if rpm in ("", "0"):
    WARN.append("AEC_RATE_LIMIT_RPM is 0 - no per-IP throttle on the public API.")
elif many_workers and not env("AEC_REDIS_URL"):
    FAIL.append(f"AEC_RATE_LIMIT_RPM is set with {workers} workers but no AEC_REDIS_URL - the "
                "limit is per-worker, not global. Point AEC_REDIS_URL at the redis service.")

# --- storage / data ------------------------------------------------------------------------------
if not env("S3_ENDPOINT") and not env("STORAGE_DIR"):
    WARN.append("Neither S3_ENDPOINT nor STORAGE_DIR set - storage falls back to ./storage.")
if env("S3_ENDPOINT") and env("S3_SECRET_KEY") in ("", "minioadmin"):
    FAIL.append("S3_SECRET_KEY is default/unset - change the MinIO credentials.")
pg_pass_default = "postgres" in db and ":postgres@" in db
if is_postgres and pg_pass_default:
    FAIL.append("DATABASE_URL uses the default postgres password - set a real one.")

# --- report --------------------------------------------------------------------------------------
print("Production preflight")
print("=" * 60)
for f in FAIL:
    print(f"  FAIL  {f}")
for w in WARN:
    print(f"  warn  {w}")
if not FAIL and not WARN:
    print("  all checks passed")
print("=" * 60)
print(f"{len(FAIL)} failure(s), {len(WARN)} warning(s)")
sys.exit(1 if FAIL else 0)
