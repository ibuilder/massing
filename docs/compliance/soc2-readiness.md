# SOC 2 readiness — control matrix

*R19 COMPLY-SOC2 (2026-07-24). A Trust-Services-Criteria–organized readiness matrix for enterprise
diligence: each criterion mapped to the shipped control and its evidence source, with the honest gap
list. This is **readiness**, not an audit — a SOC 2 Type I/II engagement is an operator/company
action with a licensed auditor. Cloud-infra-only items (KMS, managed retention, residency) remain
roadmap-gated (P3).*

## Scope

The self-hosted Massing stack (API + Postgres + MinIO + Redis + web/desktop clients) as deployed by
an operator, plus the engineering organization's SDLC. Criteria: Security (common criteria) +
Availability + Confidentiality. Processing Integrity and Privacy can be added when a customer
requires them.

## Control matrix

### CC1/CC2 — control environment & communication
| Criterion | Control | Evidence |
|---|---|---|
| Documented security program | [threat-model.md](../security/threat-model.md) + the `security-monitoring` operating skill (CodeQL-after-every-push directive) | docs in repo; CodeQL history |
| Engineering standards | [backend-standards](../engineering/backend-standards.md) · [web-standards](../engineering/web-standards.md) | docs; CI gates enforcing them |
| Architecture decisions recorded | ADR-LITE (`docs/adr/`) | ADR files |

### CC3/CC4 — risk assessment & monitoring
| Criterion | Control | Evidence |
|---|---|---|
| Threat model maintained | STRIDE threat model with verification matrix | threat-model.md, updated per ring |
| Vulnerability management | CodeQL (0-open policy) · pip-audit · bandit · npm audit · Trivy CRITICAL gate · Dependabot | workflow runs; alert history; fix releases (e.g. v0.3.648 js-yaml) |
| Drift detection | `db-migrations.yml` real-Postgres chain walk; static migration guards | workflow runs; the FTS-index incident fix (v0.3.628–632) |
| Error monitoring | Sentry (`sentry.py`) + the error log (`errorlog.py`, request-id stamped) + OTel traces (`otel.py`) | operator dashboards; `/observability` surfaces |

### CC5 — control activities (change management)
| Criterion | Control | Evidence |
|---|---|---|
| Change gating | Every release: full backend suite (344) + web typecheck/lint/vitest/build + CodeQL; version-numbered tagged releases; CHANGELOG per release | CI runs; git tags; CHANGELOG.md |
| Migration discipline | Alembic chain with autogenerate + hand-added guards; SQLite + real-Postgres verification | migration files; db-migrations runs |
| Rollback | Versioned model edits (undo path); tagged releases; DR restore procedure | [ops-dr.md](../ops-dr.md) |

### CC6 — logical & physical access
| Criterion | Control | Evidence |
|---|---|---|
| Identity & SSO | Local (PBKDF2-SHA256) + OAuth + **SAML SSO**; **SCIM** provisioning/deprovisioning | `saml.py`, `routers/scim.py`; IdP config |
| MFA | TOTP (`totp.py`); or IdP-enforced via SAML | code + tests |
| Session control | JWT `iat` + `token_epoch` revocation watermark ("sign out everywhere") | session-revocation tests |
| Brute-force resistance | Login lockout (sliding window) + endpoint throttles | `routers/auth.py`, `throttle.py` |
| Least privilege | Role-based project membership; `require_role` on every project route (**test-enforced**); privileged job kinds gated (`_KIND_MIN_ROLE`) | `test_route_authz` |
| Tenant isolation | Project-scoped queries; rollups scoped to `member_project_ids`; SEC-TENANT pass | code + tests |
| External sharing | Revocable curated ShareTokens; opt-in financial visibility; hardened public endpoints | `test_portal_txn` |
| Physical access | Operator's data-center/host responsibility (self-hosted) | operator attestation |

### CC7 — system operations
| Criterion | Control | Evidence |
|---|---|---|
| Incident response | [runbooks.md](../ops/runbooks.md) playbooks + SLOs | docs; drill notes |
| Backup & recovery | `scripts/backup.sh`/`restore.sh` (Postgres + MinIO + IFC volumes, one manifest tarball), `BACKUP_KEEP` retention, quarterly restore drill | [ops-dr.md](../ops-dr.md); drill checklist |
| Availability monitoring | health endpoints + OTel + Sentry; SLOs defined in runbooks | operator dashboards |
| Capacity | Scale harness (`seed_scale.py`/`loadtest.py`) + the mega-project fixes | test artifacts |

### CC8 — change management (SDLC)
| Criterion | Control | Evidence |
|---|---|---|
| Code review & static analysis | CodeQL + bandit + ruff/eslint/oxlint; the security-review hand-audit checklist per hardening pass | CI runs; HARDEN release notes |
| Dependency change control | Committed lockfiles (npm, Cargo, requirements.lock); overrides/pins for CVEs; new runtime deps require explicit approval (project rule) | lockfiles; CHANGELOG |
| Supply-chain audits | SBOM/license audit + MCP tool-poisoning self-audit (CI step) | `security.yml` runs |

### A1 — availability
| Criterion | Control | Evidence |
|---|---|---|
| RPO/RTO defined | [ops-dr.md](../ops-dr.md): what-must-survive matrix, RPO/RTO targets | doc |
| Restore verified | Quarterly drill procedure with verification checklist | drill records (operator) |
| Degradation posture | Offline-first: connectors feature-flagged and offline-degrading; viewer fully offline | architecture docs |

### C1 — confidentiality
| Criterion | Control | Evidence |
|---|---|---|
| Transport encryption | TLS at the reverse proxy (deploy standard) | operator config |
| At-rest | Disk/DB-level encryption is the operator's deployment responsibility; documented posture (no app-level field encryption — gap) | threat model G-4 |
| Data segregation | Tenancy controls above; curated external surfaces | CC6 evidence |
| Secrets handling | Env-var config; no secrets in repo; license secret operator-config-only; `validate_prod_config.py` | audits |

## Gap list (what an auditor will ask for that we don't yet have)

1. **Evidence retention automation** — CI runs and audit trails exist but are not exported/retained
   on a defined schedule. Define an evidence-collection cadence (operator).
2. **Access-review procedure** — documented here as quarterly; needs an owner + a record template.
3. **Vendor review** — subprocessor list + review notes (for self-hosted: none required beyond the
   optional connectors; document per-deployment).
4. **Secret scanning in CI** — threat-model G-1 (REL-6 tail).
5. **Published SBOM per release** — threat-model G-2.
6. **Security-awareness / policy docs** — org-level policies (acceptable use, onboarding/offboarding)
   are company documents, out of repo scope.
7. **Pen test report** — threat-model G-6; operator/company action.
8. **KMS / managed retention / residency** — P3 (cloud-infra gated), by design for self-hosted.

*Sequencing recommendation: close 4 and 5 in-repo (cheap), template 1–3 as operator docs, then a
Type I readiness assessment is realistic; Type II follows an observation window.*
