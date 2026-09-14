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
| Privilege escalation via side doors | The audited lesson (HARDEN-2): stricter endpoints must not be reachable through generic gates — job queue kinds carry `_KIND_MIN_ROLE`, MCP dispatch gates writes per-operation. **No longer hand-audited:** `test_dispatcher_privilege_coverage` enumerates both registries and fails on an operation classified nowhere, on a frozen entry with no referent, and — read from `_MUTATING_KINDS`, which is derived from the code — on a kind that *starts* mutating behind an unchanged name. Both tables were correct when it was written; what was missing was a reason the next entry has to be. |
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
| SSRF / local-file read via a settable outbound URL | `net.safe_urlopen` validates scheme, host and — because `urlopen` follows 3xx — **every redirect hop**, not just the URL it was handed. Adoption is no longer a matter of remembering: `test_outbound_fetch_guard` enumerates every raw `urlopen` in the package and fails unless the fetch is either routed through the guard or has its scheme+host pinned as a literal, so exemption is a property of the code rather than a name on a list. Connectors stay feature-flagged and offline-degrading. |

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
| Unattributable or misattributed professional seal | A seal is a personal legal attestation of responsible charge, not an authorisation, so it requires an authenticated caller **plus** a fresh step-up assertion a stored token cannot satisfy, and the identity is derived from the caller's own admin-verified licence rather than from the request. The audit row records the actor, the licence **row id**, `via` (verified licence vs legacy free text) and that a step-up was required — so a human act and an automated one are distinguishable after the fact. Previously the seal endpoints had no authorisation and no audit row at all (v0.3.800). |
| Untrusted writes into the audit trail | The e-signature provider webhook is the one anonymous surface that writes audit rows (a provider holds no user credential). It verifies an HMAC over the raw request body when `AEC_ESIGN_WEBHOOK_SECRET` is set, is rate-limited and size-capped, bounds every stored string, and stamps each row with whether the signature was verified — so an unverified entry cannot be read as a verified one. |
| Concurrent-edit clobbering | Optimistic concurrency: `base_source` 409 on stale model edits; per-project mutex on `/edit`. On record updates there are **two** controls, and the entry previously named only the opt-in one. `expected_modified_at` returns 409 when the record moved since the caller loaded it — but it is opt-in, and one of five web call sites passes it, so the register's inline cell editors had nothing. Every read-modify-write on a record row now also carries an in-SQL compare-and-swap on `modified_at` (`modules._cas_row_edit`): a write derived from a stale read matches no row. What happens next depends on who owns the transaction — a caller that owns it RE-READS and re-applies (up to four rounds), so a concurrent edit to a different field is no longer erased; a caller that does not (`update_record(commit=False)`, used for multi-row edits) gets ONE attempt and a 409, because retrying would roll back the rows it had already staged and then report a partial edit as whole. The stamp is advanced through `modules._next_stamp`, which is strictly monotonic per row: a bare `datetime.now()` can repeat inside one microsecond, and a token that repeats leaves the predicate reusable by the very writer it is meant to exclude. Gated by `services/api/test_rmw_sweep.py`, which fails the build on a register-row write that derives its value from a read it does not swap on. **Twelve** sites remain open and are named in that gate's ledgers rather than left unstated: six IFC-authoring routes that derive a new model version outside the per-project lock the other six take (gap G-11), one JSON collection on a table with no `modified_at` (gap G-10), and five more read-modify-writes on tables that likewise carry no concurrency token — `drawingset.revise_sheet`, `connections.put_mappings`, `connections.update_connection`, `proforma.sync_gmp_to_hard` and `proforma.sync_model_to_hard` (gap G-12). **The count went UP on 2026-09-14, and that is the sweep working rather than failing**: the gate's ledgers were keyed by `(path, function)`, so one status and one sentence covered every read-modify-write in a function — and six functions write more than one. Re-keying by `(path, function, attribute)` took the derived population from 32 to 41 and found `update_connection`'s `config` merge sitting EXEMPT on the strength of a sentence about `body.name or c.name`, a different line of the same function. The count is **derived from a structured status field** in those ledgers, not by searching their prose: it read thirteen until 2026-09-14 because one entry spelled its status "Open" and the tally matched "OPEN". The pair that writes `Project.dev_property` — `proforma.put_property` and `realestate.save_appraisal` — was closed the same day with `pid_lock.mutating(pid)` rather than a swap, because that table has no token to swap on; **both** writers take it, since a lock one side does not take protects nothing, and the gate verifies the pair lexically rather than accepting the claim. |

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
| Seal identity + human step-up | `test_seal_identity` (26 checks, RBAC-on, mutation-verified) |
| RBAC middleware prefix coverage | `test_protected_prefix_coverage` (ratchet; 3 failure modes, mutation-verified) |
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
| Outbound-fetch guard adoption | `test_outbound_fetch_guard` (derived from the package, not a list) |

## Gap backlog (prioritized; honest)

1. ✅ **G-1 Secret scanning in CI** — *closed.* `security.yml` runs gitleaks over the **full git
   history** (`fetch-depth: 0` — a shallow clone would scan one commit and report "clean over the
   full history"), redacted so a public Actions log cannot itself leak the finding, and **findings
   now fail the build**. The baseline it waited for is `.gitleaksignore`: five fingerprints, each
   carrying its reason, all triaged as false positives with nothing to rotate — a fabricated licence
   key, the published RFC 6238 TOTP test vector, two fixtures, and a source *comment* whose `key:`
   prefix matched. Fingerprints pin **commits, not files**, which is the property worth knowing: the
   comment was reworded and its historical commit still matches, because history is exactly what
   this scans. The documented fix for a real finding is therefore **rotate first, then purge from
   history** — never a new line in the ignore file, which silences the report and leaves the
   credential in the objects.
2. ✅ **G-2 SBOM artifact** — *closed in-sprint:* the Dependency-scan workflow now publishes an
   SPDX SBOM artifact per run (`security.yml` sbom job).
3. **G-3 (S) Formal access-review cadence** — SCIM handles deprovisioning; a quarterly operator
   access-review procedure is documented in the SOC 2 matrix but not tool-enforced.
4. **G-4 (L, posture) Field-level encryption** — at-rest encryption is delegated to the deployment
   (disk/DB). App-level field encryption + KMS is P3 (cloud-infra gated), documented as posture.
5. ✅ **G-5 Password deny-list** — *closed in-sprint:* `auth.weak_password_reason()` (common-password
   deny-list with case/suffix normalization, distinct-char floor, password≠username) enforced on
   register / change / admin create / admin reset / token reset; `test_password_policy`.
6. ✅ **G-7 Seal identity bound to a verified licence + a human step-up** — *closed in-sprint.*
   The seal text is now derived server-side from a `professional_licenses` row that belongs to the
   caller and was recorded by a platform admin (`verified_by`/`verified_at`), never self-served; an
   expired licence refuses with 409. The free-text `profile` field is refused by default
   (`AEC_SEAL_ALLOW_PROFILE=1` re-opens it, audited as `via: profile:legacy`).
   **The account-binding alone was not sufficient, and that is the part worth remembering:** a
   bearer token identifies a session, not a person, so any process holding one — including an
   automation driving this API — could still emit sealed documents in the licensee's name, and the
   audit row would faithfully record a human act that never happened. Sealing therefore also
   requires a fresh single-action step-up assertion (`POST /auth/step-up`, **single-use**
   via a `jti` spent in `stepup_spent`, 5-minute TTL, bound to
   the password hash so a password change invalidates it, rejected as a bearer token by
   `verify_token_claims`), and the `api-key` machine identity is refused outright. Single-operator
   mode (RBAC off / `LOCAL_MODE`) is exempt by design: it has no accounts and no passwords, so a
   step-up there would be theatre in front of an app that is unauthenticated by design.
   `test_seal_identity` (26 checks, mutation-verified).
7. ✅ **G-8 `_PROTECTED_PREFIXES` completeness gate** — *closed in-sprint.* The RBAC middleware's
   prefix list still covers only 8 of 67 top-level prefixes — that is a posture choice, not the bug.
   The bug was that a **68th could appear and nothing would fail**, which is how /pdf (the
   unauthenticated PE-seal forgery), /templates, /samples and /firm all got in: each was also
   defective in its own gate, but the middleware would have caught all four and never got the chance.
   `test_protected_prefix_coverage` freezes the current sets and fails on three things — an
   unclassified new prefix; a frozen **read-only** prefix that has gained its first mutating route
   (plain set membership would wave that through, and it is the likeliest real regression); and a
   frozen entry with no referent, which would otherwise pre-authorise whatever reuses the name. A
   ratchet rather than an allowlist-with-reasons: the sets record "this existed and was looked at",
   never "this is safe", because a stale justification reads exactly like a live one. All three modes
   mutation-verified. Complements `test_global_authz` (individual unguarded global mutating routes,
   29) — that measures routes, this measures the middleware's blast radius.
8. ✅ **G-9 Outbound-fetch guard adoption made derived, not listed** — *closed in-sprint.* The shared
   guard existed and five modules used it; five did not, and two of those were live defects — an ERP
   connector whose operator-set `base_url` reached `urlopen` unvalidated (so a `file://` value was
   read as the ERP payload), and a bridge that validated its URL and then let `urlopen` follow
   redirects, clearing hop zero and nothing after it. **A scheme/host check is a property of a hop,
   not of a URL.** The prior check asserted the five *adopters* still used the guard, so a module
   that never adopted was outside what it could see; `test_outbound_fetch_guard` derives the set
   instead — every raw `urlopen` must be guarded or literal-hosted. Reported six call sites against
   the pre-fix tree, so it is known to fail on the real bugs and not only on synthetic ones.
9. **G-6 (M) Pen test** — no third-party penetration test on record; recommended before the first
   enterprise deployment. Operator action.
10. **G-11 (M) Six IFC-authoring routes derive a new model version outside the project lock** —
   `bake_layers`, `import_families`, `import_family_pack`, `place_family`, `content_import` and
   `_restore_version` in `services/api/src/aec_api/routers/authoring.py` each read
   `Project.source_ifc`, produce a NEW IFC version from it, and write the pointer back. Six sibling
   routes doing the identical thing (`edit`, `edit_graph`, `edit_batch`, `macros_run`,
   `option_activate`, and `mcp_tools._run_recipe`) wrap that region in `pid_lock.mutating(pid)`,
   one of them commented *"same RMW race as /edit — serialize per project"* — so the control exists,
   is documented in the row above, and is applied to half the population. Two concurrent placements
   lose one, silently, with both callers answered 200. **Found by widening `test_rmw_sweep.py`'s ORM
   derivation, not by anyone reading the routes**, and the split is now asserted there in both
   directions: a site the ledger calls locked must be lexically under the lock, and a site it calls
   open must still be open, so closing one cannot leave a stale gap recorded. Deliberately NOT fixed
   in the pull request that found it — wrapping six routes that do long IFC I/O is a different blast
   radius from the register-row change, and is its own item (roadmap: RMW-LOCKGAP).
   `upload_source_ifc` and `import_rvt` are excluded on purpose: they write uploaded bytes to a
   fixed path, derived from nothing they read, so last-writer-wins is an upload's specified
   behaviour.

11. **G-12 (S) Five more read-modify-writes on tables with no concurrency token** —
   `drawingset.revise_sheet`, `connections.put_mappings`, `connections.update_connection`,
   `proforma.sync_gmp_to_hard` and `proforma.sync_model_to_hard`. The two `connections` entries are
   a **pair on one blob**: `put_mappings` merges `mappings` into `Connection.config` while
   `update_connection` merges the body's keys into the same column, keeping a stored secret where
   the form sent it blank. One admin saving connection settings while another saves field mappings
   loses a write, and whatever concurrency control `connections` eventually gets has to cover both
   — *a lock one side does not take protects nothing*, which is what the `dev_property` pair cost to
   learn. (`proforma.put_property` was one of the original six and is now
   **closed** under the per-project lock — see the `dev_property` note in the concurrent-edit row
   above. `bim.promote_markup` was another and is **closed** too: it claimed the back-link with a
   plain assignment after a `topic_id` check, so two concurrent promotes minted two RFI Topics for
   one markup and orphaned the first, and it now uses the conditional UPDATE
   `modules.promote_comment` had been given one module over. *An already-solved defect living on
   elsewhere is the cheapest kind to close and the easiest to never look for.*) Each reads a column and writes back a value derived from it on a
   table that carries no `modified_at`, so the register row's compare-and-swap is unavailable
   exactly as in G-10. Surfaced by widening `services/api/test_rmw_sweep.py`'s ORM derivation to
   propagate taint through one local — before that, hoisting a read into a variable removed a site
   from the inventory. Frozen in that gate's ledger with a structured status, so a new instance reds
   the build. The four that remain are deliberately **not** ranked here. The first draft of this
   sentence ranked them and was wrong on the facts within a minute of being written — it called
   `drawingset.revise_sheet` a lost *sheet revision* with a single writer, when the read-modify-write
   is actually `m.data = d2` on each **markup** it tags `carried_from`, a blob the markup save and
   bulk-replace routes also write. *A priority claim is a factual claim about blast radius, and this
   file has now carried two wrong ones about this same list.* Rank them by reading the sites.

12. **G-10 (S) One JSON collection still loses a concurrent write** — `Scenario.shared_with` (a
   share grant). It reads a JSON collection and writes back what it derived, and that table carries
   no `modified_at`, so the compare-and-swap the record row uses does not exist for it; JSON
   equality is not a swap that behaves the same on SQLite and Postgres, which is why the same fix
   was not simply copied. `Project.dev_property` (the appraisal-override merge) was the second and
   is now **closed** under the per-project lock. It is
   listed in `services/api/test_rmw_sweep.py`'s `BAND_2` ledger, so the set is frozen and cannot
   grow silently — a new instance reds the build. Closing it means giving those tables a concurrency
   token, which is a migration (roadmap: RMW-TOKEN). Severity is small: the loss needs two grants or
   two appraisal saves inside one request window, and neither is a privilege boundary.

*Exclusions per the review doctrine: DoS/resource-exhaustion beyond the shipped caps, rate-limit
tuning, log-spoofing, path-only SSRF, client-side authz, and outdated-dep advisories (handled by the
scanners) are tracked operationally, not as vulnerabilities.*
