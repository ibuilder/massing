# Security audit — July 2026

**Scope:** the whole shipped platform — API (`services/api`, 60 routers), data engine (`services/data`),
web app (`apps/web`), container/deploy config, CI, and dependencies.
**Branch:** `security/audit-2026-07`, cut from `main` @ `d62401f0`.
**Method:** stack-specific best-practice research (OWASP API Top 10 2023, current Starlette/FastAPI and
SQLAlchemy advisories), then targeted review of each vulnerability class against this codebase.
Anything that looked reachable was confirmed against a live build before being reported, and anything
that could not be confirmed is labelled as such.

Everything in **Fixed** is implemented and covered by a regression test
(`services/api/test_security_audit.py`, `apps/web/src/ui/sanitizeSvg.test.ts`).

> **Note on detail.** This repository is public, so this document records *what was fixed and why*
> rather than how each issue was reached. The reproduction detail is held privately and is available
> to maintainers on request.

---

## Summary

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | High | Sandbox escape — the snippet could reach the filesystem | Fixed |
| 2 | Med-High | Sandbox DoS — snippet runtime was unbounded | Fixed |
| 3 | Medium | SSRF — redirect following bypassed the outbound-URL guard | Fixed |
| 4 | Medium | Server-generated SVG injected as raw HTML (stored-XSS surface) | Fixed |
| 5 | Medium | Unescaped `href` interpolation in the licence banner | Fixed |
| 6 | Low | Auth gate keyed on `request.url.path` (CVE-2026-48710 bug class) | Fixed |
| 7 | Low | Share links mintable with an unbounded TTL | Fixed |
| R1–R4 | — | Operator/design recommendations | Open — see below |

The codebase has clearly had prior hardening passes, and most of what an audit usually turns up was
already closed: parameterised SQL throughout, storage-key containment, `defusedxml` on every untrusted
XML path, a working decompression-bomb guard, a non-root multi-stage container, a hash-pinned
dependency lock, and zero open CodeQL alerts. The findings below are the residue.

---

## Fixed

### 1. Sandbox escape — filesystem reachable from a snippet (High)

`services/data/src/aec_data/sandbox.py`

The `execute_ifc_code` sandbox builds its safety on an AST allowlist, a curated builtins map, and a
denylist of reflection helpers — so the module docstring claimed IO was unreachable. It wasn't. The
sandbox hands the snippet a live `ifcopenshell.file`, and **that object's own public API includes
file-writing methods**. A builtins denylist cannot see them, so removing `open` from the namespace
never closed the path. Confirmed reachable on a live build.

The consequence was a write primitive at an arbitrary path. The container's `/app` is `chown`ed to the
runtime user, so it reached application source — a persistence path, not just a stray file.

The AST allowlist was never the weak layer. The lesson worth carrying forward is that **an object
handed into a sandbox brings its own API surface with it**, and that surface has to be audited
separately from the namespace.

**Fix:** the file-touching attributes on the exposed model are denied by name. Persisting the model is
the caller's job, so no legitimate snippet needs them. Verified: the write is rejected, no file is
created, and normal authoring (`ifcopenshell.api.run(...)`) still works.

**Reachability:** gated behind `AEC_ALLOW_IFC_CODE=1` (off by default) and editor-role auth, so this
is an escape *within* an already-privileged, opt-in feature rather than an unauthenticated RCE. That
gating is what holds the severity to High rather than Critical.

### 2. Sandbox DoS — unbounded runtime (Medium-High)

Same file. The docstring justified rejecting `while` as "no infinite loops", but the allowlist permits
`for`, which expresses the same unbounded loop; and certain arithmetic shapes compute inside CPython's
integer routines where no interrupt is possible. Both were confirmed to run indefinitely.

Each such request pins a uvicorn worker permanently, and the compose default is a small worker count,
so very few requests were needed to take the API down.

**Fix:** a wall-clock deadline (`AEC_IFC_CODE_TIMEOUT`, default 5s) enforced by a line-level trace hook
scoped to the snippet's own frames — library code runs untraced and unslowed. The arithmetic shapes the
hook cannot interrupt are rejected at the AST instead.

**Residual limit (documented in the module):** the deadline fires between snippet lines, so a single
call into a slow library routine is bounded by that routine, not by the hook. Closing that properly
needs process isolation, which the live `ifcopenshell.file` handle does not currently allow.

### 3. SSRF — redirect following bypassed the guard (Medium)

`services/api/src/aec_api/net.py` and five call sites.

`validate_outbound_url` validated the URL it was handed, and the caller then used
`urllib.request.urlopen`, which follows 3xx redirects by default. A validated endpoint that answers
with a redirect to an internal address therefore walked the guard straight past its own check.

This affected `webhooks.py`, `esign_bridge.py`, `re_bridge.py`, `securities_bridge.py` and
`license_cloud.py` — including the `allow_private=False` mode that exists specifically to block
cloud-metadata and intranet access.

**Fix:** `safe_urlopen()` installs a redirect handler that re-runs the same validation on every hop,
and all five call sites now use it. The scheme check applies to redirects even in the permissive
on-prem mode, so a redirect to a non-http(s) scheme is refused regardless of configuration.

### 4. Server-generated SVG injected as raw HTML (Medium)

`apps/web/src/drawings/drawings.ts`, `apps/web/src/drawings/layoutEditor.ts`

Both rendered a sheet by assigning API-returned SVG straight to `innerHTML`. SVG is not inert —
several of its elements and attributes execute when parsed into a live document. That SVG is generated
from the project's IFC model, and IFC files arrive from consultants, subs and clients, so markup that
survived the generator would have become stored XSS for every user who opened the sheet.

The generator (`services/data/src/aec_data/drawing.py`) does escape its text nodes today, so this was
**not exploitable**. The problem was structural: a ~600-line SVG string builder sat one missed escape
away from account compromise, with nothing in between.

**Fix:** `apps/web/src/ui/sanitizeSvg.ts` — parse inertly with `DOMParser`, strip executable elements,
event handlers and unsafe URL schemes, then serialise. Both call sites go through it, making the viewer
safe by construction so a future generator slip is a rendering bug rather than a compromise. Confirmed
the generator emits none of the stripped elements, so nothing legitimate is lost.

### 5. Unescaped `href` interpolation (Medium)

`apps/web/src/main.ts` — the licence banner escaped every field it rendered *except* the URL it placed
in an `href`. Two problems: a quote in the value escapes the attribute, and HTML-escaping alone would
not have been sufficient anyway, since a script-bearing URL scheme contains no escapable character.

**Fix:** a new `safeUrl()` helper (HTML-escape **and** scheme-allowlist, collapsing anything else to
`#`), applied at both sites.

### 6. Auth gate keyed on the reconstructed URL (Low)

`services/api/src/aec_api/main.py`, plus the signed-URL checks in `routers/bim.py` and
`routers/realestate.py`.

The RBAC gate decided which prefixes require identity using `request.url.path`. Starlette
*reconstructs* that value by re-parsing `http://{host}{path}`, so a crafted Host header can make it
disagree with the path routing actually used — the bug class behind **CVE-2026-48710 (BadHost)**.

**Not exploitable here:** the lock pins `starlette==1.3.1`, past the 1.0.1 fix that validates the Host
header. Reported because an auth gate should not depend on a transport-layer parsing detail for its
correctness.

**Fix:** these decisions now read `request.scope["path"]` — the path the router matched on.

### 7. Unbounded share-link TTL (Low)

`services/api/src/aec_api/routers/realestate.py` — the investor-statement and public-listing share
endpoints accepted `ttl` with a floor (`ge=60`) but no ceiling, so a member could mint an effectively
permanent anonymous link to a capital-account statement. **Fix:** capped at 365 days.

---

## Verified sound — no change needed

Recorded so a future pass doesn't re-litigate them.

- **Authentication crypto.** PBKDF2-HMAC-SHA256 at 200k rounds, `hmac.compare_digest` everywhere,
  an `iat`/`token_epoch` revocation path, and `purpose`-claim separation that stops a password-reset
  token being replayed as a bearer token.
- **SQL injection.** No query is built by string interpolation. The one dynamic DDL statement
  (`db.py`) takes its identifiers from SQLAlchemy metadata, not from request data.
- **Path traversal.** `storage.safe_seg` allowlists segments and `LocalBackend._p` re-checks
  containment after `resolve()`.
- **Decompression bombs.** The BCF guard caps declared and cumulative uncompressed size. It looked
  bypassable via forged metadata, so it was tested directly — it is not: Python's `zipfile` stops
  decompressing at the declared size and fails CRC. The guard holds.
- **XXE / billion laughs.** `defusedxml` is used consistently for every untrusted XML input (BCF,
  CityGML, clash imports).
- **CORS.** Explicit origin allowlist, no wildcard, credentials not enabled.
- **Secrets.** No credentials in tracked files; `preview.db`, `preview_storage` and `.env` are all
  untracked.
- **CodeQL.** 0 open alerts (queried the alerts API, not the workflow status).
- **Dependencies.** No known-vulnerable pins found; the runtime lock is hash-pinned with
  `--require-hashes`, which is the right defence against the package-substitution attacks that have
  been active this year.
- **Container.** Non-root user, multi-stage build leaving the compiler and the npm CLI out of the
  runtime image.

---

## Recommendations — open, need an owner decision

**R1 — Webhook SSRF default (product posture).** `AEC_WEBHOOK_ALLOW_PRIVATE` defaults to `1`. That is
right for the on-prem/LAN posture the docstring describes and wrong for a hosted multi-tenant one,
where it permits internal network access from a compromised settings key. Recommend setting it to `0`
in `docker-compose.prod.yml` and in the SECURITY.md hardening table, keeping the permissive default
only for local/desktop. Not changed here because it is a deployment-posture call, not a bug.

**R2 — DNS rebinding in the outbound guard.** With `allow_private=False`, the guard resolves the host
and the connection then resolves it again, so a hostile name can answer differently on the second
lookup. Closing this properly means pinning the validated address into the connection. Meaningful only
once R1 is adopted.

**R3 — Key separation.** `AEC_AUTH_SECRET` is used both to sign auth tokens and as the HMAC key for
signed download URLs. Cross-protocol confusion was checked for and is not possible — the two message
formats cannot collide. Still worth deriving two subkeys (e.g. HKDF with distinct labels) so the
property is structural rather than incidental.

**R4 — Sandbox memory bound.** The CPU bound is now in place; memory is not. An oversized allocation
raises `MemoryError` and is caught cleanly, but under a container limit it would OOM-kill the worker
first. Recommend running the API with an explicit container memory limit.

---

## Notes for the concurrent roadmap work

This branch touches only security-relevant lines and does not overlap the feature work in progress on
`continue-roadmap`. Files changed: `sandbox.py`, `net.py`, `main.py`, the four bridge modules,
`webhooks.py`, `routers/bim.py`, `routers/realestate.py`, `run_tests.py` (one manifest entry), and in
the web app `ui/feedback.ts`, `ui/sanitizeSvg.ts` (new), `main.ts`, `drawings/drawings.ts`,
`drawings/layoutEditor.ts`.
