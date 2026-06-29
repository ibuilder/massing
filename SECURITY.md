# Security policy

## Reporting a vulnerability
Please report security issues privately via a [GitHub security advisory](https://github.com/ibuilder/massing/security/advisories/new)
(or email the maintainer). Do not open a public issue for an unpatched vulnerability. We aim to
acknowledge within a few days and to ship a fix or mitigation promptly.

## Threat model
The platform ships in two postures:

- **Local / desktop / demo (default):** single operator, open by design — RBAC is **off** so local
  flows just work. Run it on a trusted machine / network.
- **Team / cloud (multi-user):** turn on access control and set the secrets below. With RBAC on,
  every request to project, finance, connection, settings, and admin surfaces requires an
  authenticated identity (a defense-in-depth gate enforces this even if an endpoint lacks its own
  role check), and each project-scoped route is authorized by the caller's project role.

## Production hardening checklist
Set these environment variables for a team/cloud deployment:

| Variable | Purpose |
|---|---|
| `AEC_RBAC=1` | **Enforce** role-based access control (viewer < reviewer < editor < admin). |
| `AEC_AUTH_SECRET=<random>` | Sign auth tokens with a private secret. **Required** — without it tokens use a public dev secret and are forgeable (the app logs a warning at startup). |
| `AEC_API_KEY=<random>` | Optional admin bearer for automation/CI. |
| `AEC_REQUIRE_SECRET=1` | **Refuse to start** if `AEC_AUTH_SECRET` is unset (fail-closed for real deployments). |
| `AEC_HSTS=1` | Emit `Strict-Transport-Security` (only when served over HTTPS). |
| `AEC_COOKIE_SECURE=1` | Force the `Secure` flag on the auth cookie (auto-on over HTTPS / behind a TLS proxy). |
| `AEC_CSP=1` | Enforce a strict resource Content-Security-Policy (or set `AEC_CSP=<policy>` to supply your own). Default is framing-only. |
| `AEC_SIGNED_URL_TTL=3600` | Lifetime (seconds) of signed download URLs for `model.frag` / attachments. |
| `AEC_CORS_ORIGINS=https://app.example.com` | Lock CORS to your web origin (dev default is `http://localhost:5173`). |
| `AEC_MAX_UPLOAD_MB=1024` | Cap request body size (oversized uploads → `413`). |
| `AEC_LOGIN_MAX_FAILS` / `AEC_LOGIN_WINDOW_SEC` | Login brute-force lockout (default 8 fails / 5 min → `429`). |
| `AEC_RATE_LIMIT_RPM=<n>` (+ `AEC_REDIS_URL`) | Per-IP rate limiting (multi-worker via Redis). |
| `AEC_REDIS_URL=redis://redis:6379/0` | Shares the rate-limit **and** login-lockout counters across workers (the API runs multi-worker). Fail-open: any Redis error falls back to per-process counters. |
| `AEC_TRUST_XUSER` | **Leave unset in production.** The `X-User` header is a dev-only impersonation shim, honored only when RBAC is off or this flag is set. |

The bundled `docker-compose.prod.yml` sets these (RBAC, require-secret, HSTS, secure cookie, strict CSP,
Redis) and ships a `redis` service; you only supply the secrets in `.env` (`AEC_AUTH_SECRET`,
`POSTGRES_PASSWORD`, `S3_*`).

## Schema migrations
There is **no Alembic** — by design. The schema is partly **config-driven**: each GC-portal module
(`module.json`) registers its own `mod_<key>` table at startup, so the table set isn't fixed in code.
On boot `init_db()` runs an **additive, dbDelta-style sync**: `create_all` (new tables, including the
dynamic module tables) → `_ensure_columns` (ALTER-ADD any model column missing from an existing table)
→ `_ensure_indexes` (backfill new indexes). It is **additive only** — it never drops or retypes a
column, so deploying a newer build over an existing Postgres/SQLite DB is safe and automatic. This is
covered by `test_migrate.py`.

**Non-additive changes** (dropping/renaming/retyping a column, backfilling data, adding a NOT-NULL
column with no default) are **not** handled automatically — run a one-off SQL migration against the
DB during the deploy for those. Take a backup first; the additive sync intentionally won't destroy data.

## Built-in protections
- **Identity:** signed bearer tokens / httpOnly `samesite=lax` cookie; the `X-User` header is never
  trusted in production. Accounts can be deactivated (token revocation takes effect immediately).
- **Authorization:** project-scoped RBAC on read/write routes + a global gate that blocks anonymous
  access to protected prefixes when RBAC is on. Attachment downloads verify project membership (no IDOR).
- **Response headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  a `Content-Security-Policy` (framing-only by default; opt-in strict resource policy), optional HSTS.
- **Direct downloads:** `model.frag` and attachments accept short-lived **HMAC-signed URLs** as an
  alternative to a session (for QR share / worker fetch / deep links); the auth cookie is `Secure` over HTTPS.
- **Signed share links (disposition & investor portal):** two intentionally-anonymous surfaces, both
  requiring a valid **HMAC-signed URL even when RBAC is off**, read-only, scoped to one project + record
  (no id-swapping), and rate-limited; minting a link requires a project member (`viewer`):
  - the **public listing** (`GET /projects/{id}/listings/{lid}/public`) returns **only owner-authored
    public fields** (price, description, beds/baths, tour link — never internal financials like NOI/cap);
  - the **investor statement** (`GET /projects/{id}/investors/{iid}/statement.public.pdf`) serves that
    one investor's capital-account statement PDF for the no-login LP portal.
- **Container:** the API image runs as a **non-root user** (`appuser`, uid 10001).
- **Input / data:** Pydantic-validated request models; SQLAlchemy parameterized queries; the data-source
  SQL browser is **read-only** (single SELECT/WITH, no DDL/DML, row-capped); storage keys are
  containment-checked (no path traversal) and upload filenames sanitized.
- **Abuse limits:** request body-size cap, login lockout, optional per-IP rate limiting, bounded
  compute (e.g. Monte Carlo iterations).
- **Supply chain:** CI runs `pip-audit` + `npm audit`; production npm dependencies carry no known
  vulnerabilities (build-only tooling is excluded from the shipped app).
- **IFC is the source of truth** and the in-viewer authoring round-trips through `ifcopenshell` recipes
  (not arbitrary code); the optional Bonsai/Blender desktop bridge that can run Python is gated and
  off by default.

## Disclosure
We credit reporters (unless you prefer to remain anonymous) and note fixes in the
[CHANGELOG](CHANGELOG.md).
