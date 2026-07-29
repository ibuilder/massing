# Massing — Audit, recommendations & plan

Author: GitHub Copilot (audit)
Repo: https://github.com/ibuilder/massing
Date: 2026-07-29

---
Executive summary
---
I reviewed the repository structure (README, SECURITY.md, top-level manifests), the web app (apps/web package.json, vite config), the API/service layer (services/api directory, requirements files, many focused tests), and CI/compose artifacts. The codebase is large and well-tested (extensive test suite in services/api). The product already includes many good practices (signed URLs, HMAC, RBAC gating, environment flags, tests for rate-limits/OTel/Sentry, non-root container image, pip-audit/npm audit in CI). To reach enterprise-grade production quality for a CAD/BIM authoring product you must tighten security guardrails (plugin sandboxing, supply chain), stabilize and document build/runtime environment, adopt stricter migration practices, enforce continuous dependency & image scanning, harden runtime (rate-limits, sandbox boundaries), and invest in viewer performance, offline integrity and UX affordances (onboarding, progressive disclosure, accessibility).

What I reviewed (evidence)
- README.md (project goals, run instructions, features). (see README.md)
- SECURITY.md (threat model, checklist, built-in protections). (see SECURITY.md)
- package.json (repo workspace engines node >=24). (see package.json)
- apps/web/package.json (dependencies: three 0.184.0, web-ifc 0.0.77, ThatOpen libs pinned, vite 8.1.5, TS 5.9.3). (see apps/web/package.json)
- apps/web/vite.config.ts and scripts (WASM copy, bundling scripts, budget script).
- services/api/requirements.in and requirements.lock, services/api tests (huge test suite), Dockerfiles, docker-compose.yml and docker-compose.prod.yml.
- plugins/README.md — plugin manifest & loader rules (plugin sandbox recommended).
- Many tests around security, rate-limits, SAML/MFA, otel, sentry, file sizes, plugin registry → shows coverage and focus areas (see services/api/test_*.py).

Top-level snapshot
- Languages: Python backend (~74%), TypeScript web (~25%).
- Web stack: Vite + TypeScript, three.js, web-ifc, ThatOpen components (pinned).
- Backend stack: FastAPI + SQLAlchemy on Postgres, ifcopenshell, MinIO, background workers/sidecar patterns.
- CI: GitHub Actions CI badge present; repo runs pip-audit/npm audit in CI per SECURITY.md.

Key findings & risks (concise)
1. Build/runtime engine mismatch risk
   - package.json and apps/web package.json declare "node": ">=24" (package.json line 13–15; apps/web line 6–8). Local environment notes mention Node 20/18 confusion. This is a real risk for contributors and CI if Node version is inconsistent.
2. Dependency & supply-chain
   - Many essential native/crypto/wasm dependencies (web-ifc, three.js, ThatOpen fragments). These are pinned but must be continuously scanned. The repo already runs pip-audit/npm audit (good), but I recommend automating Dependabot/updates and SBOM generation.
3. Migration strategy & schema drift
   - SECURITY.md documents an additive “create_all + _ensure_columns” approach and "no Alembic" by design. For enterprise multi-tenant deployments this is brittle for non-additive schema changes (retypes, renames, NOT NULL backfills).
4. Plugin system & remote code execution
   - Plugins run Python at load and can register recipes (plugins/README.md). Plugin discovery is opt-in, but plugin code execution on the same process is risky. The optional execute_ifc_code and Bonsai/Blender bridges are gated but still potential attack surface.
5. Sandbox/compute limits & DoS
   - Sandbox budget (AEC_IFC_CODE_TIMEOUT) exists; make sure it's enforced and audited. Many heavy ops (geometry tiling, triangulation, Boolean clash narrow-phase) can be DoS vectors.
6. Secrets & environment guidance
   - SECURITY.md gives good env var guidance. But .env.example is present — ensure secrets are never committed and CI enforces secret scanning.
7. Web viewer offline integrity & caching
   - Offline WASM + fragments are core requirements — integrity (SRI), caching, content-security-policy, and upgrade path must be robust.
8. Performance and bundle size
   - Large client dependencies (three.js + ThatOpen components + web-ifc + wasm) can bloat bundle. The repo includes a bundle-budget script but needs automated enforcement and progressive code-splitting/loading strategies.
9. UX complexity risk
   - The product is powerful and complex — without carefully designed progressive disclosure, onboarding and role-tailored defaults, adoption will suffer.

Actionable recommendations (prioritized)
P0 — Urgent / high-risk (should be addressed before production rollouts)
- Environment/engines alignment
  - Pick a supported Node major (Node 20 LTS is a safe, widely-supported baseline today; Node 24 may be in use — choose one and standardize). Update package.json and apps/web/package.json to the same "engines" value and document exact developer setup (nvmrc or .tool-versions).
  - Add an automated version check in CI that fails PRs if the developer Node or Python runtime is different.
- Secrets & manifest shipping
  - Add secret scanning to CI (GitHub secret scanning and pre-commit hooks). Ensure .env.example contains placeholders only and that no secrets are present in history.
- Plugin hardening
  - Move plugin load/run into a sandboxed external process or container. Do NOT execute plugin code in the main API process. Options:
    - Run plugin registration in a dedicated process with a tight seccomp/SELinux profile and limited filesystem/network capability.
    - Or require a signed plugin manifest + binary signature verification + a plugin permit approval workflow.
  - Enforce plugin API whitelisting at manifest-level and limit available functions.
- Rate-limiting & DoS protections
  - Enable/require AEC_RATE_LIMIT_RPM and shared Redis for multi-worker deployments. Ensure Redis protection and fallback behavior is understood.
  - Monitor CPU/memory heavy endpoints (IFC conversion, Boolean ops) and add queueing + worker pool + job concurrency limits.
- Signed WASM & CSP/SRI
  - Serve WASM and fragment assets with Subresource Integrity (SRI) and strict CSP. Harden CSP (currently opt-in) to production-ready policy; consider nonce-based inline script strategy for needed inlines.
- Database migration strategy
  - Adopt explicit, tested migration tooling for non-additive changes. Options:
    - Introduce Alembic for controlled migrations (recommended).
    - Or maintain a separate migration-runner pipeline that records schema version and applies one-off SQL with backups & rollback plans.
  - Add a DB migration acceptance test to CI that runs migrations against a fresh DB container and verifies key endpoints.

P1 — Important (address in coming sprints)
- Image/container security
  - Ensure Dockerfiles are multi-stage, small images, non-root (appuser already present in SECURITY.md), and scanned (Trivy/Clair). Avoid embedding secrets in images or build args.
- Observability & SLOs
  - Enable OpenTelemetry production export (traces + metrics) and structured JSON logging. Add dashboards + alerts for: job queue saturation, high-latency recipe ops, failed plugin loads, signed URL misuse, and auth failure spikes.
  - Set SLOs for conversion latency, preview generation, and signed URL TTL policies.
- Harden web endpoints (CSRF, CORS)
  - Ensure CSRF protections for state-changing endpoints when accessed from browsers (SameSite cookie is used; check form or XSRF tokens for AJAX calls).
  - Lock CORS to whitelisted origins in production (AEC_CORS_ORIGINS).
- Sandboxed authoring & Blender/Bonsai bridge
  - Ensure Bonsai-MCP / Blender run in audited environment with chunked operations, forced-save snapshots and a checkpoint system to abort long-running or failing scripts.
- Auditable plugin & recipe actions
  - Ensure every authoring recipe call (server-side edit) is logged with actor, timestamp, checksum of inputs, and resulting diff/summary for audit/rollback.

P2 — Medium/long-term improvements
- Viewer performance & network
  - Implement streaming fragments with range requests & progressive LOD. Use web workers / WASM threads for geometry parsing/selection and transferable objects to avoid main-thread stalls.
  - Lazy-load rarely-used UI modules. Implement code-splitting and optimize critical render path.
- UX / Product adoption
  - Implement role-based dashboards, guided onboarding, keyboard-first flows and an interactive tutorial/demo project (maple_grove_house.mass exists as a sample).
  - Add in-app help & contextual tips for powerful features (AI command bar, CAD-line commands, plugin recipes).
  - Accessibility: run axe/lighthouse audits and implement ARIA for interactive controls (gizmos, lists, dialogs).
- Testing & automation
  - Add E2E test suite for main authoring flows (desktop/tauri + web) and include heavy-model smoke tests using the samples directory.
  - Add fuzzing tests around IFC parsing and fragment conversion to reduce crash surface.

Detailed technical checks & quick diagnostics
- Local dev quickchecks (recommended)
  - Ensure correct Node: create .nvmrc or .node-version and document:
    - echo "Use Node X (e.g., 20 or 24): nvm use" (pick one). If choosing Node 24, verify local toolchains (CI, Windows builds, native addons).
  - Web build quick run:
    - export PATH="/c/Program Files/nodejs:$PATH"   # per local notes
    - npm ci
    - npm run dev --workspace apps/web
  - Full stack with docker-compose:
    - docker compose --profile full up --build
    - docker compose --profile full --profile seed run --rm seed
- Dependency audits
  - npm audit: npm ci && npm audit --audit-level=moderate
  - pip-audit: pip install pip-audit && pip-audit -r services/api/requirements.lock
  - Add Trivy scan for containers: trivy image <image>
- SBOM & provenance
  - Add `syft` or `cyclonedx` step in CI to produce SBOM.json and attach to release.

Concrete security changes to implement (short checklist)
- [ ] Add pre-commit hook to run secret-scan and block large-file commits.
- [ ] Run Dependabot/renovate for npm and python.
- [ ] CI: fail on critical/pinned CVEs (pip-audit/npm audit).
- [ ] CI: produce SBOM for each release; store it with release artifacts.
- [ ] Plugin runtime isolation: move plugin loading to separate process/container and implement signed manifest verification.
- [ ] Enforce AEC_REQUIRE_SECRET (fail-closed) in production deployment templates and document in deploy/README.
- [ ] Add SRI/CSP enforcement for static assets (WASM/frag).
- [ ] Add explicit migration path (Alembic or guarded migration runner) and create a migration policy in docs.

Database/migration recommendation detail
- Because the repo’s current design intentionally avoids Alembic, adopt one of:
  - Option A (recommended): Adopt Alembic with migrations created for every non-additive DB change, plus a staged deploy plan and DB backup step. Keep the current additive boot sync as a fallback for safe additive changes only.
  - Option B: Keep db-delta approach but introduce a migration-runner for explicit destructive changes with:
    - migration manifests checked into repo,
    - pre-deploy backups,
    - post-migration validation tests.
- Add a DB migration acceptance test to CI that runs migrations against a fresh DB container and verifies key endpoints.

Viewer & geometry performance checklist
- [ ] Use webworkers/WASM threads for geometry parsing (threejs + web-ifc).
- [ ] Ensure the viewer lazily loads large feature modules (curtain-wall, rebar, MEP).
- [ ] Ensure fragment streaming uses cache-control and range requests; implement progressive LOD.
- [ ] Enforce a bundle budget in CI (apps/web/budget script) and fail the build if budget exceeded.
- [ ] Use Brotli/Gzip with proper content-type and caching headers (nginx.conf exists — review for TTL and SRI).
- [ ] Implement offline integrity checks: signed fragments/WASM + integrity verification at startup.

UI/UX and adoption improvements (practical)
- Progressive disclosure:
  - Role-based landing pages: default to the 10 most used workflows for each persona (GC PM, Architect, Estimator).
  - Contextual command palettes — expose advanced features via keyboard or an "Advanced" toggle.
- Onboarding:
  - Guided sample project with checklist "First 10 things to try", tutorial build scripts to auto-create a sample.
- Accessibility:
  - Keyboard-first interactions for orbit/selection/draw; ARIA labels for the model tree and dialogs; color contrast checks for theming.
- Undo/Redo & Safety:
  - Make the undo/redo visible & accessible with timeline + per-action replay for audit.
  - Add "dry-run" option for AI/recipe-driven multi-step changes (preview + accept).

Testing & CI improvements
- Tighten PR gates:
  - Run lint, typecheck, unit tests, security scans, and a "bundle budget" check on PRs.
  - Add a smaller, fast E2E smoke test in CI and an overnight heavy-model full integration run.
- Increase test parallelization and add resource quotas to avoid CI worker OOM from heavy-model tests.

Recommended rollout roadmap (3-month cadence, adjustable)
Sprint 0 (week 0 — discovery & emergency fixes)
- Standardize Node & Python versions; add .nvmrc, .python-version and update README (1–2 days).
- Add secret scanning pre-commit + CI (1–2 days).
- Enforce dependency audit as failing in CI for critical CVEs (1 day).

Sprint 1 (weeks 1–2)
- Implement plugin sandbox prototype:
  - Move plugin load to a separate process (start with a process-per-plugin model, containerize later). Add logging and connection via a tightly-scoped IPC protocol (JSONRPC) (5–10 days).
- Add SRI/CSP for static WASM and fragments, update nginx.conf to use strict caching and security headers (3–5 days).
- Fail build on bundle budget exceedance and add budget enforcement to CI (2–3 days).

Sprint 2 (weeks 3–4)
- Add migration tooling & policy (adopt Alembic or equivalent). Create at least one structured migration and a rollback test (5–8 days).
- Add OTel exporter config to production compose and instrument backend critical paths (3–5 days).

Sprint 3 (weeks 5–8)
- Viewer performance: web workerify parsing & fragment streaming optimization. Add progressive LOD and lazy-load modules (10–15 days).
- Harden Dockerfiles and add Trivy scanning in CI (2–3 days).
- Add SBOM generation to CI (1–2 days).

Ongoing (monthly)
- Dependabot/renovate PR reviews, security patching, and emergency CVE handling.
- Monthly dependency and image scans; quarterly SAST.
- Add user research-driven UX improvements + accessibility fixes.

Concrete next steps I can do for you (pick one)
- A. Draft the initial CI changes (GitHub Actions job files) to add npm/pip-audit, Trivy, SBOM step, and Node-version check. (I can produce a PR.)
- B. Create an RFC doc in repo proposing plugin sandbox architecture and IPC protocol; include migration plan and security controls.
- C. Create an example Alembic migration and CI job to run migrations in a safe "dry run" mode.
- D. Create the file above in the repository as `docs/AUDIT-MASSING-AUDIT.md` and open a PR with the write-up.

Commands & quick checks (copy-paste)
- Local dev (web):
  - export PATH="/c/Program Files/nodejs:$PATH"   # Windows note from repo context
  - npm ci
  - npm run dev --workspace apps/web
- Full stack (docker):
  - docker compose --profile full up --build
  - docker compose --profile full --profile seed run --rm seed
- Dependency scans:
  - npm ci && npm audit --audit-level=moderate
  - pip install pip-audit && pip-audit -r services/api/requirements.lock
- Container scan:
  - docker build -t massing-api services/api && trivy image massing-api

Appendix: files / locations I referenced
- README.md — project overview and quickstart (root).
- SECURITY.md — threat model and checklist (root).
- package.json (root) — engines: node >=24.
- apps/web/package.json — dependencies (three.js 0.184.0, web-ifc 0.0.77, ThatOpen packages pinned), scripts including bundle-budget and copy-wasm.
- apps/web/vite.config.ts — build config; review for service-worker/CSP handling.
- plugins/README.md — plugin manifest & loader rules (plugin sandbox recommended).
- services/api/requirements.in, requirements.lock — Python deps and pins.
- services/api/*tests* — many tests demonstrating coverage and intended behavior: security, otel, sentry, plugin registry, file-size guard.

Notes & rationale
- The site and offline viewer are the product’s unique value — protecting the integrity of the WASM/frag pipeline and ensuring high performance, offline correctness and predictable upgrade paths are critical.
- Enterprise customers will expect clear migration procedures and robust RBAC + plugin governance plus audited logging and SSO/MFA.
- The plugin and recipe system provide incredible power but are the highest residual risk if run in-process.

If you want, I can:
- Create the markdown file in the repo (docs/AUDIT-MASSING-AUDIT.md) and open a PR, and I can also draft the initial CI workflow changes (npm/pip-audit, Trivy, SBOM, Node-version check) in the same PR.
- Draft the CI changes (Action workflow) + pre-commit config for secret scanning and bundle-budget enforcement.
- Draft a plugin-sandbox RFC that defines how to move plugin loads to a separate worker process and the contract/manifest format.

Which of the "next steps" above would you like me to do now?
