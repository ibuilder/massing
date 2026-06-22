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

### ▢ Remaining (prioritized)
1. **Rate limiting** — none today. Add per-IP (anon) + per-user (authed) limits; needs Redis for
   multi-worker (do it once, not half-way). Pair with proxy/Cloudflare bot protection.
2. **Request-size limits + timeouts** — enforce at the nginx layer (`client_max_body_size`, sane
   proxy timeouts); IFC uploads are legitimately large, so this belongs at the proxy, not a global
   app cap.
3. **Security headers / HSTS / TrustedHost** — set HSTS + `X-Content-Type-Options` + frame options at
   the proxy; add `TrustedHostMiddleware` when the host set is known.
4. **Bonsai bridge** — `execute_blender_code` runs arbitrary Python; keep it gated/off by default in
   any hosted context (already isolated in `apps/editor-bridge`, dry-run default).
5. **Dependency + container scanning** in CI (pip-audit / npm audit / image scan).

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

### ▢ Remaining (prioritized)
1. **First-call takeoff on huge imports** is still ~minutes (inherent geometry meshing) — background
   it with a progress poll so the first estimate doesn't block the request.
2. **N+1 in dashboard / portfolio rollups** — the cross-module aggregations re-query per module;
   batch into fewer queries for projects with many records.
4. **SSE feed** keeps a long-lived connection (correct), but add a heartbeat + capped reconnect
   backoff; it also defeats "network-idle" tooling (a test note, not a user bug).

## Modularity / maintainability

- **`apps/web/src/main.ts` split (in progress).** ✅ First extraction done: the shared `modalShell`
  moved to `ui/modal.ts` (and gained Esc-to-close + focus + ARIA — see UX). ▢ Next: pull the
  auth/account modals into `ui/account.ts`, connections into `ui/connections.ts`, and a thin
  `bootstrap.ts`. Behavior-preserving; incremental behind the passing typecheck + vitest.
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
