Title: chore(audit): CI, security, migration & plugin-sandbox scaffolding

This PR adds an initial enterprise-grade audit, CI hardening, migration scaffolding, and a plugin sandbox RFC prototype.

Summary of changes
- docs/AUDIT-MASSING-AUDIT.md — Detailed audit, prioritized fixes, and 3-month rollout plan.
- docs/PLUGIN-SANDBOX-RFC.md — RFC describing a sandbox architecture for plugins (IPC contract, signing, resource limits).
- docs/MIGRATION-POLICY.md — Recommended migration policy and Alembic dry-run guidance.
- services/api/alembic/ — Alembic scaffolding and an example revision (0001_add_audit_example).
- services/plugin-sandbox/README.md — Prototype sandbox scaffold.
- .github/workflows/security-ci.yml — CI checks: Node/Python version check, npm/pip audits, lint/typecheck.
- .github/workflows/container-sbom-trivy.yml — Container build and Trivy/SBOM generation.
- .github/workflows/bundle-budget.yml — Enforce apps/web bundle budget on PRs.
- .github/dependabot.yml — Weekly dependency update config (npm + pip).
- .pre-commit-config.yaml — Basic hooks (detect-secrets, large-file guard, ends-of-file).
- scripts/ci/check-node-python.mjs — Runtime check used in CI to validate node/python versions.
- .nvmrc /.python-version — Standardize Node 24 and Python 3.11 for developers.
- docs/nginx.production.conf — Recommended headers, CSP, SRI snippet, cache TTLs.

Why
- Makes supply-chain & runtime checks explicit and enforceable in CI; provides a safer plugin execution path; gives a clear migration path for non-additive DB changes; and lays groundwork for container scanning and SBOM generation.

CI gates
- security-ci.yml will run on PRs and fail if high/critical npm vulnerabilities are found and if Node/Python runtime checks fail.
- bundle-budget.yml will fail PRs that exceed the configured frontend bundle budget.

Requested reviewers
- @ibuilder (you), backend lead, frontend lead and security owner (please add individuals or teams you want as reviewers).

Testing notes
- The PR includes CI workflows; once opened the workflows will execute automatically. The container SBOM/Trivy workflow requires Docker build capability.

Acceptance criteria
- PR should be reviewed by backend (DB/migrations), security, and frontend owners.
- After merge, enable Dependabot and review failing CI alerts for new issues.
