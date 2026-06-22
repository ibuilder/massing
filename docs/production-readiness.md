# Production-readiness — audit, fixes, and the prioritized plan

A grounded pass over the codebase for **security, performance, modularity, UX, testing and
deployment**, measured against current best practice (FastAPI security guide, OWASP API Top-10, Vite
build guidance). Highest-impact, production-*blocking* items were fixed in this pass; the rest is a
prioritized backlog. Sources: [FastAPI security](https://davidmuraya.com/blog/fastapi-security-guide/),
[FastAPI prod deploy](https://render.com/articles/fastapi-production-deployment-best-practices),
[Vite build](https://v3.vitejs.dev/guide/build/), [Vite code-splitting](https://dev.to/markliu2013/vite-code-splitting-strategy-5a69).

## Security

### ✅ Fixed in this pass
- **`X-User` header no longer trusted in production.** The dev convenience header could impersonate
  any user. Now honored only when RBAC is off (dev/local) or `AEC_TRUST_XUSER=1` (tests); in
  production the only trusted identity is a signed bearer token / cookie / API key. (`rbac.py`,
  `test_security`.)
- **Auth-secret fail-safe.** Tokens are signed with `AEC_AUTH_SECRET`; if unset they fall back to a
  public dev secret (forgeable). The app now logs `CRITICAL` when RBAC is on without a secret, and
  **hard-fails to start** when `AEC_REQUIRE_SECRET=1`. (`auth.secret_is_default`, `main.lifespan`.)

### ✅ Already sound (verified)
- **CORS** is explicit (no `*`), env-driven (`AEC_CORS_ORIGINS`), defaults to the dev origin only.
- **SQL browse console** is read-only: single `SELECT`/`WITH` only, a write/DDL keyword regex block,
  and row caps (`connectors.query`).
- **Passwords** are PBKDF2-HMAC-SHA256 (200k rounds, salted); tokens are HMAC-signed with TTL +
  single-use reset tokens; deactivation revokes live tokens.
- **Secrets** (OAuth/AI/ERP) are write-only/masked via `settings_store`; never echoed.

### ✅ Fixed in this pass
- **First-layer rate limiting.** A per-IP fixed-window middleware, opt-in via `AEC_RATE_LIMIT_RPM>0`
  (off in dev/test); `/health` + `/metrics` exempt; returns 429 + `Retry-After`. In-process (single
  worker) — multi-worker still wants a shared store (Redis); documented.
- **Security headers / HSTS.** nginx now sends `Strict-Transport-Security`, `X-Content-Type-Options:
  nosniff`, `Referrer-Policy`, and `X-Frame-Options: SAMEORIGIN` (server-level + repeated on the
  index.html location). `client_max_body_size 1024m` + proxy timeouts were already set.

### ▢ Remaining (prioritized)
1. **Per-user rate limits + Redis backend** for multi-worker, paired with Cloudflare/WAF bot
   protection (the in-process limiter above is the single-worker first layer).
2. **`TrustedHostMiddleware`** once the production host set is fixed; consider a CSP header.
3. **Bonsai bridge** — `execute_blender_code` runs arbitrary Python; keep it gated/off by default in
   any hosted context (already isolated in `apps/editor-bridge`, dry-run default).
4. **Dependency + container scanning** in CI (pip-audit / npm audit / image scan).

## Performance

### ✅ Already good (verified)
- **Frontend code-splitting is in place** — `vite.config` `manualChunks` separates `thatopen`
  (6 MB) and `three` (734 KB) into their own chunks, and the **viewer is lazy-loaded**
  (`import("./viewer/app")` on first Model-workspace use). Initial payload is the ~137 KB `index`
  chunk (gzips small); the heavy 3D libs load only when needed.
- **Convert once, serve `.frag`** — IFC→Fragments is pre-computed server-side; geometry streams as
  tiles, metadata via the API (never parse full IFC in the browser).
- Background publish (off-thread) + polled status; PWA runtime-caches WASM/tiles.

### ✅ Fixed in this pass
- **Takeoff caching.** `qto.takeoff_file` now caches results keyed by `(path, mtime, …)` — content-safe
  (a new published version is a new path; any change bumps mtime). Measured on the 52 MB sample: first
  takeoff **169 s**, repeat **0.000 s**. Estimate + QTO export + closeout package now share the cache.
- **Composite DB index.** Module tables gain `(project_id, workflow_state)` (the dashboard/list hot
  path), with an idempotent `_ensure_indexes()` that backfills it on existing DBs (SQLite + Postgres).

### ✅ Also fixed in this pass
- **First-call takeoff backgrounded.** The background publish now warms the takeoff cache (size-gated:
  skips >25 MB imports to not waste the worker), so the first estimate after a publish is instant for
  typical/generated models.

### ▢ Remaining (prioritized)
1. **Dashboard / portfolio rollups** query each module table once (71 tables) and read the full row
   incl. the `data` JSON (needed for `due_date`). The `(project_id, workflow_state)` index helps the
   filter; a deeper win needs DB-specific JSON extraction (`json_extract` / `->>`) to fetch only the
   light columns — deferred to keep it cross-DB-safe.
2. **First takeoff on a >25 MB import** is still ~minutes on first request (not pre-warmed); add an
   async compute + progress poll if that path matters.
4. **SSE feed** keeps a long-lived connection (correct), but add a heartbeat + capped reconnect
   backoff; it also defeats "network-idle" tooling (a test note, not a user bug).

## Modularity / maintainability

- **`apps/web/src/main.ts` split (in progress).** ✅ Extracted so far: the shared `modalShell` →
  `ui/modal.ts` and the Open/Save dropdown helpers → `ui/menus.ts` (both behavior-preserving, verified
  live). ▢ Next (deferred — bigger/riskier, do behind the gate): pull the auth/account modals into
  `ui/account.ts`, connections into `ui/connections.ts`, and a thin `bootstrap.ts`.
- **Backend routers are already well-factored** (one router per domain; a config-driven module engine
  for the 71 GC modules). `massing.py`/`edit.py` generation helpers are cohesive. Keep `services/data`
  pure (no FastAPI imports) — currently true.

## UX

- ✅ First-run onboarding + skippable tour; ✅ viable proforma defaults; ✅ persona-ordered,
  state-aware tools panel; ✅ readable result modals; ✅ mobile field-capture.
- ▢ **Empty-state consistency** — a few panels still show terse "no project" rows; route them through
  the shared empty-state + the onboarding quick-starts.
- ✅ **Modal a11y** — the shared `modalShell` now sets `role="dialog"`/`aria-modal`, closes on Esc +
  backdrop, autofocuses the first field, and restores focus on close — applied to every modal at once.
- ▢ **Accessibility (remaining)** — ARIA labels on the icon-only viewer toolbar, a full focus-trap
  (Tab cycling) in modals, and a contrast check on the light theme.

## Testing

- ✅ **API gate: 23 suites** (`run_tests.py`) incl. auth/RBAC/SSO/security/generate/estimate/closeout;
  ✅ data tests (massing/frame/units/envelope/core, analysis); ✅ web typecheck + vitest; ✅ full
  **lifecycle E2E 63/63** (`e2e_tower.py`).
- ▢ **Coverage gaps** — frontend has unit tests for the API client + model-ids only; add component
  tests for onboarding/field-capture queue logic (jsdom). Add a load/perf smoke on a 50 MB model.

## Deployment

- ✅ Docker Compose (web+API+Postgres+MinIO), signed Tauri desktop installers with auto-update,
  GitHub Pages demo, `/metrics` (Prometheus) + JSON access logs, backup/restore runbook.
- ▢ **Production checklist** (set before go-live): `AEC_RBAC=1`, `AEC_AUTH_SECRET` (strong),
  `AEC_REQUIRE_SECRET=1`, `AEC_CORS_ORIGINS` (real origins), `AEC_ADMIN_EMAILS` (ops), nginx
  `client_max_body_size` + HSTS, managed Postgres backups, and a single autosync scheduler (not
  per-worker).
