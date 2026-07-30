# Massing — application threat model & security verification

*R19 SEC-THREAT (2026-07-24). A STRIDE-organized threat model over the real attack surfaces of a
self-hosted deployment, plus a verification matrix mapping each control to its implementation and
evidence, and an honest gap backlog. Companion docs: [soc2-readiness](../compliance/soc2-readiness.md)
· [ops-dr](../ops-dr.md) · [runbooks](../ops/runbooks.md).*

## System context

Self-hosted stack: FastAPI API (`services/api`) + Postgres + MinIO/filesystem storage + Redis
(cache/SSE) behind an operator-managed reverse proxy (TLS terminates there); the Vite/TS web app is
static assets; the desktop shell is Tauri. IFC files are converted server-side (ifcopenshell) to
Fragments; the browser never parses raw IFC. Optional outbound: the massing.cloud license check,
feature-flagged connectors (APS, QuickBooks, open-data feeds), webhooks.

**Trust boundaries:** (1) internet → reverse proxy → API · (2) authenticated user → project (RBAC/
tenancy) · (3) public token-holder → curated share surfaces · (4) API → outbound connectors ·
(5) CI/CD → repository → release artifacts · (6) operator host → containers.

## STRIDE by surface

### 1. Authentication & session
| Threat | Control (implementation) |
|---|---|
| Credential stuffing / brute force | Sliding-window per-username lockout on login (`routers/auth.py` — designed so the lockout infra can never take login down; cleared on success) + per-endpoint throttles (`throttle.py`). |
| Password database theft → offline cracking | PBKDF2-SHA256 salted hashing (`auth.py`); no plaintext or reversible storage. |
| Stolen/replayed JWT | Token carries `iat`; account `token_epoch` watermark revokes all prior tokens on password change / "sign out everywhere" (`auth.py`/`rbac.py`). |
| Phished single factor | TOTP MFA (`totp.py`); SAML SSO (`saml.py` + router) lets an enterprise IdP own the factor policy; SCIM (`routers/scim.py`) deprovisions centrally. |
| Session fixation via OAuth | `oauth.py` state validation; social sign-in maps to local accounts. |

### 2. Authorization, tenancy & privilege boundaries
| Threat | Control |
|---|---|
| Cross-project data access (tenant breakout) | Every `/projects/{pid}` route requires `require_role`; **enforced by a test gate** (`test_route_authz` walks the route table). Portfolio/cross-project rollups scope to `member_project_ids`. SEC-TENANT hardening pass (v0.3.413). |
| Privilege escalation via side doors | The audited lesson (HARDEN-2): stricter endpoints must not be reachable through generic gates — job queue kinds carry `_KIND_MIN_ROLE`, bulk/MCP dispatch gate per-operation. Checked in hand-audit passes (see the `security-monitoring` skill checklist). |
| Public share token abuse | ShareTokens are revocable, read-only, serve a **curated** digest only (no financials unless per-token `show_payments` opt-in at mint); the public decision/comment endpoints are hardened (type/action whitelists, 120/500/1000-char caps, 200-decision and 200-comment hard caps, revoked → 404). |
| Privilege escalation on **global** (non-project) routes | A project-scoped gate is not valid on a route with no project in its path: it leaves the project identity to be supplied by the request. Firm-wide writes take `rbac.require_platform_admin`, global reads `rbac.require_identified`. **Enforced by a test gate** (`test_global_mutating_authz`), which asserts as a schema property that no global route accepts a caller-supplied project id — so a new one fails the build rather than joining a list. Two firm-standards routes were corrected under this pass (v0.3.800). |
| Client-side authz bypass | All checks server-side; the web app's role gating is presentation only. |

### 3. File upload & conversion pipeline
| Threat | Control |
|---|---|
| Resource-exhaustion upload | Content-length middleware cap (`AEC_MAX_UPLOAD_MB`, default 1 GB) before body read. |
| Malicious IFC/XML → parser exploit | IFC parsed server-side by ifcopenshell (memory-safe wrapper over a maintained C++ core, pinned); untrusted XML goes through `defusedxml` (XXE-safe); BCF zips size-capped. |
| Stored XSS via file-derived text | Every file/server/model-derived free-text rendered via `esc()`/`escapeHtml` in the web app (CodeQL `js/xss-through-dom` + the hand-audit checklist enforce it). |
| Path traversal on storage keys | Storage keys are server-composed (`{pid}/…`), never client paths. |

### 4. API abuse
| Threat | Control |
|---|---|
| Endpoint flooding | Per-endpoint throttles (`throttle.py`); heavy analysis endpoints bounded (model-count caps, e.g. the 12-model benchmark cap; result `truncated` flags). |
| Stored-data amplification (editor stores → viewer GETs evaluate) | Count/size caps at save (`rule_library.MAX_*`, `schedule_baselines._MAX`, view-template caps, calc-field length/node caps). |
| Expression/DSL injection | `calc_fields.py` is an AST whitelist (no attributes/subscripts/lambdas/`**`/imports; node + length caps); QUERY-DSL is a hand-rolled quote-aware parser with no eval; regexes bounded per the ReDoS discipline (quantifier bounds + input caps). |
| SSRF via connectors/webhooks | The SSRF guard (private-range/scheme validation) on outbound fetch paths (`perf-sec-p0` pattern); connectors are feature-flagged and offline-degrading. |

### 5. Secrets & data protection
| Threat | Control |
|---|---|
| Secrets in repo/images | None stored in-repo (validated by grep-based scan in audits); config via env vars; the massing.cloud shared secret lives ONLY in operator config; `validate_prod_config.py` checks deploy config sanity. |
| Token/PII leakage in logs/errors | `errorlog.py` clips tracebacks, stamps `request_id` not credentials; share-page markers never render the full token. |
| At-rest exposure | Posture: disk/DB-level encryption is the operator's deployment choice (self-hosted); no field-level encryption in the app (gap G-4). TLS in transit at the reverse proxy. |

### 6. Auditability & repudiation
| Threat | Control |
|---|---|
| Untraceable changes | `audit.py` trail on mutating operations (actor/when/what), surfaced in per-topic timelines and feeds; model versions carry review states (`review_status` + who/when); edit recipes are GUID-stable and versioned (undo path). |
| Request untraceability | `X-Request-ID` middleware stamps every request (inbound honored, ≤64 chars), propagated to OTel spans and the error log. |
| Unattributable professional seal | Applying a PE/RA seal requires an authenticated caller and writes an audit row after the seal succeeds, naming the actor, template, seal name, licence number and state. Previously the seal endpoints had no authorisation and no audit row (v0.3.800). |
| Untrusted writes into the audit trail | The e-signature provider webhook is the one anonymous surface that writes audit rows (a provider holds no user credential). It verifies an HMAC over the raw request body when `AEC_ESIGN_WEBHOOK_SECRET` is set, is rate-limited and size-capped, bounds every stored string, and stamps each row with whether the signature was verified — so an unverified entry cannot be read as a verified one. |
| Concurrent-edit clobbering | Optimistic concurrency: `base_source` 409 on stale model edits; per-project mutex on `/edit`; `expected_modified_at` 409 on record updates. |

### 7. Supply chain & CI/CD
| Threat | Control |
|---|---|
| Vulnerable dependencies | CI: pip-audit + bandit (medium+) + npm audit (prod deps) in `security.yml`; Trivy image scans in `ci.yml` (CRITICAL gate); Dependabot; lockfiles committed (npm + Cargo); CVE'd transitives pinned via `overrides`/requirements pins. |
| Malicious code introduction | CodeQL on every push (standing directive: 0 open alerts; HIGHs fixed immediately); branch is release-gated by the full backend suite (344) + web typecheck/lint/vitest/build. |
| MCP tool poisoning | `supply_chain.mcp_tool_audit()` scans the MCP catalog for poisoning shapes (invisible unicode, injection phrasing, base64 blobs, outbound URLs) — CLI `mcp-audit --gate` + a report-only CI step. |
| Arbitrary code via the Blender bridge | Bonsai-MCP `execute_blender_code` is gated, save-first, chunked (project instruction); not reachable from the web product. |
| Schema drift hiding failures | `db-migrations.yml` walks the Alembic chain against real Postgres (the drift guard that caught the FTS index failure); a static guard enforces the per-migration FTS-index rule. |

## Verification matrix (control → evidence)

| Control | Evidence |
|---|---|
| Route authz coverage | `test_route_authz` (suite-gated) |
| Global-route authz (no `{pid}`) | `test_global_mutating_authz` (23 checks, RBAC-on, mutation-verified) + `test_global_authz` ratchet |
| Webhook signature + payload bounding | `test_esign` (valid signature replayed onto a different payload is refused) |
| Login lockout / throttles | `routers/auth.py` + `throttle.py` tests |
| Token revocation | session-revocation tests (`token_epoch`) |
| Upload cap | `main.py` middleware + test |
| XSS discipline | CodeQL 0 open + `esc()` hand-audit checklist |
| Expression-eval safety | `test_calc_fields` security rails block |
| Public-token hardening | `test_portal_txn` (caps, revocation, whitelists) |
| Dependency hygiene | `security.yml` + Trivy runs, green |
| CodeQL | code-scanning API: 0 open alerts |
| Migration drift | `db-migrations.yml` green on real Postgres |
| Backups/DR | `scripts/backup.sh` + [ops-dr.md](../ops-dr.md) drill checklist |
| Audit trail | `audit.py` + timeline tests |

## Gap backlog (prioritized; honest)

1. **G-1 (M) Secret scanning in CI** — no gitleaks/trufflehog step (REL-6 tail); audits use ad-hoc
   grep. Add when tooling is approved.
2. ✅ **G-2 SBOM artifact** — *closed in-sprint:* the Dependency-scan workflow now publishes an
   SPDX SBOM artifact per run (`security.yml` sbom job).
3. **G-3 (S) Formal access-review cadence** — SCIM handles deprovisioning; a quarterly operator
   access-review procedure is documented in the SOC 2 matrix but not tool-enforced.
4. **G-4 (L, posture) Field-level encryption** — at-rest encryption is delegated to the deployment
   (disk/DB). App-level field encryption + KMS is P3 (cloud-infra gated), documented as posture.
5. ✅ **G-5 Password deny-list** — *closed in-sprint:* `auth.weak_password_reason()` (common-password
   deny-list with case/suffix normalization, distinct-char floor, password≠username) enforced on
   register / change / admin create / admin reset / token reset; `test_password_policy`.
6. **G-7 (M) Seal identity is not bound to the account** — sealing now requires an authenticated
   caller and is audited, but the seal's name/licence/state still come from the request, so an
   authenticated user can seal under another person's licence. Binding the seal to the signed-in
   user needs a per-user licence record (product decision, deliberately not changed in the
   security pass).
7. **G-8 (S) `_PROTECTED_PREFIXES` is hand-maintained** — the RBAC middleware's prefix list covers
   8 of 66 top-level prefixes, so a new prefix opts out of the safety net silently. The risk that
   matters is ratcheted (`test_global_authz` freezes unguarded global mutating routes, currently
   29 and falling), but a completeness gate forcing every new prefix to be declared
   protected-or-reviewed-public would close the class instead of the instances.
8. **G-6 (M) Pen test** — no third-party penetration test on record; recommended before the first
   enterprise deployment. Operator action.

*Exclusions per the review doctrine: DoS/resource-exhaustion beyond the shipped caps, rate-limit
tuning, log-spoofing, path-only SSRF, client-side authz, and outdated-dep advisories (handled by the
scanners) are tracked operationally, not as vulnerabilities.*
