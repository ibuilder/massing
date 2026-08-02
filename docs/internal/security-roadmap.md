# Security roadmap — the work queue

**Status: live.** Unlike most files in `docs/internal/`, this one is not a superseded snapshot. It is
the standing queue of security work: what is closed and what proves it, what is open and who decides.

**Scope split, so this does not drift from its neighbour.**
[`docs/security/threat-model.md`](../security/threat-model.md) is the *controls* document — STRIDE by
surface, and the verification matrix mapping each control to the test that enforces it. This file is
the *queue*: priority, ownership, and what "done" looks like. When an item closes, the control moves
to the threat model and the row here says so. Do not restate control detail in both.

**Disclosure rule, and it applies here despite the fence.** `docs/internal/` is excluded from the
published Pages site but is **tracked in a public repository** — anyone can read it on GitHub. So this
file records *what* is open and *why it matters*, never *how to exploit it*. That is the same rule the
operator set for the audit write-ups: push the code, trim the detail. Reproduction steps live in the
unredacted private notes outside the repo.

Reference standard: **OWASP ASVS 5.0.0** (May 2025). Massing's tooling is broadly aligned — CodeQL,
Trivy, pip-audit, bandit, npm audit, SPDX SBOM, and an ORM that parameterises by default. The gaps
below are mostly *posture and process*, not missing scanners.

---

## P0 — one decision, not a task

### SEC-BRANCH — `main` protection does not bind the accounts that push to it

`main` has protection, and it is real as far as it goes: force-pushes blocked, deletion blocked, one
approving review required. But:

| setting | state |
|---|---|
| `enforce_admins` | **false** |
| required status checks | **not enabled** |

`enforce_admins: false` is GitHub's default, and it means *"the restrictions of a branch protection
rule don't apply to people with admin permissions"*. Every agent session pushes with an admin
identity, so the review requirement has never applied to any commit any of them made. With no required
checks, nothing blocks a red CI either.

**This is the control that would have prevented the two documented near-misses**, and it is the only
open item with a real incident behind it:

- 2026-07-31: main went red at 06:12 from an unindexed `docs/internal/` file. The gate fired correctly
  within three minutes. Three further commits landed on top over the next hour — **including a cut and
  tagged release** — because every session verified its own work and none asked about the build.
- 2026-08-01: `v0.3.813` was prepared, then three commits landed behind it in four minutes, two of them
  money fixes. Tagging either end would have shipped something nobody verified.

**Not an engineering task — an operator decision**, because the options trade differently:

| option | effect | cost |
|---|---|---|
| `enforce_admins` only | the existing 1-review requirement becomes real | every change needs a human approval; an agent cannot approve its own PR, so the operator becomes the bottleneck |
| + required checks, reviews → 0 | CI must be green to merge, no human gate | ends direct-to-main pushing; the API test gate is 17–40 min, so that becomes the floor per change |
| rulesets with a bypass list | per-actor exemption, more surgical than all-or-nothing `enforce_admins` | whoever is exempted is back to today's posture |
| local pre-push hook | catches the authz gates in ~1–2 min at the point of creation | per-clone, protects a machine rather than the repo |

Interim mitigation already shipped: `.claude/skills/ship-release` now requires a green-main check
before tagging, and that the tagged commit still be the tip of main. Both are prose disciplines a
required status check would enforce mechanically.

---

## P1 — worth doing, no decision needed

### SEC-G1 — no secret scanning in CI

Confirmed absent: no gitleaks / trufflehog / secret-scan step in any workflow. Audits have used ad-hoc
grep, which finds what it is asked for and nothing else. `security.yml` is the natural home; it already
runs pip-audit, bandit and npm audit.

Note the shape this shares with everything else in this file: a scanner that is not run is
indistinguishable from a scanner that found nothing.

### SEC-OPS — three operator defaults that are safe for on-prem and wrong for hosted

Each is a one-line config change, and each is currently the *permissive* default:

1. **`AEC_WEBHOOK_ALLOW_PRIVATE` defaults to `1`** (`webhooks.py`) — webhook targets resolving to
   private/loopback addresses are allowed. Correct for a LAN listener, wrong for multi-tenant hosting,
   where it is the standard cloud-metadata and intranet-probing surface. `SECURITY.md` documents
   setting it to `0`; nothing enforces it.
2. **`AEC_AUTH_SECRET` signs two different things** — auth tokens *and* signed download URLs. No
   collision is currently possible (the two message formats cannot overlap), but that is a property of
   today's formats rather than a structural guarantee. Deriving two subkeys with distinct labels makes
   it structural.
3. **Container memory limits are present but commented out** in `docker-compose.prod.yml` (6 commented
   resource directives). The sandbox has a CPU bound; a memory bound is delegated to a limit nobody
   has enabled, so an allocation raises `MemoryError` in the best case and OOM-kills the worker in the
   realistic one.

---

## P2 — posture, cloud-gated, or operator-scheduled

- **SEC-G3 — access-review cadence.** SCIM handles deprovisioning; a quarterly operator access review
  is documented in the SOC 2 matrix but not tool-enforced.
- **SEC-G4 — field-level encryption.** At-rest encryption is delegated to the deployment (disk/DB).
  App-level field encryption + KMS is cloud-infra gated; documented as posture, not a gap to close
  unilaterally.
- **SEC-G6 — third-party penetration test.** None on record. Recommended before the first enterprise
  deployment. Operator action.
- **SEC-SEAL-2 — seal identity is bound, licence *verification* is not.** A licence row is written by a
  platform admin and carries `verified_by`/`verified_at`, but nothing checks the number against a state
  board. That is an integration, not a defect, and the audit trail is honest about which human asserted
  it — recorded so nobody later reads "verified" as "verified against the issuer".

---

## Reviewed and deliberately not changed

Recording these stops the next audit re-deriving them, and stops a future reader assuming they were
missed.

- **bandit medium findings** — `B102 exec` is the documented IFC sandbox; the `B310 urlopen` sites
  carry `# noqa: S310` with fixed hosts behind the SSRF guard; of the two `B608` string-SQL sites one
  is a false positive (a vendor's HTTP query language with internal literals, not SQL against our DB)
  and the other is a deliberate read-only SQL console over a user's *own* connected database, behind
  `/connections`, with `SELECT`/`WITH` only, no semicolons, an int-coerced `LIMIT`, a read-only
  transaction on Postgres, and a denylist that also blocks data-modifying CTEs.
- **`_PROTECTED_PREFIXES` covers 8 of 67 top-level prefixes.** That is a posture choice, not the bug —
  most routes carry their own dependency. The bug was that a 68th could appear unnoticed, and that is
  now gated.

## External analysis tools — what is usable

- **Repowise** — the index is current (freshness proved by resolving a symbol hours old). Its
  **history-derived** layers are sound and worth reading: `get_risk` in PR-review mode correctly caught
  a change that had not updated the CHANGELOG or version. Its **static-analysis** layers are
  systematically confounded here and must not be actioned — see the roadmap's external-tools section
  for the three verified reasons. Its security layer (CVEs, secrets, SBOM) is **Pro-gated** and returns
  `upgrade_required`: unavailable, not clean.
- **Specula** — evaluated and rejected for this repo. It is a TLA+ formal-verification tool for
  concurrent and distributed systems (consensus protocols); Massing has no replicated state machine,
  and the cost is disproportionate to its narrow concurrency surface.

## Standing gates — what is already enforced, so nobody re-litigates it

| gate | what it makes impossible |
|---|---|
| `test_global_authz` | a new global mutating route with no authorising dependency (frozen count, down-only) |
| `test_global_mutating_authz` | **no global route may take a caller-supplied `pid`** — asserted against the OpenAPI schema, so it catches the next one rather than listing known-bad routes |
| `test_protected_prefix_coverage` | a new top-level prefix silently leaving the RBAC middleware; a read-only prefix growing its first mutating route; a frozen entry losing its referent |
| `test_seal_identity` · `test_stepup_race` | sealing without a verified licence **and** a single-use human step-up; a replayed assertion sealing twice |
| `test_invisible_unicode` | the tool-poisoning detector missing a bidi control; any source file carrying one (Trojan Source) |
| `test_no_comparative_names` | comparative competitor naming — **now including source**, not only docs |
| `innerHtmlGuard` · `hrefGuard` | new unescaped `innerHTML` interpolation; a URL attribute from an unguarded external field |
| `test_import_cycles` · `test_claude_md_gates` | top-level import cycles; a backticked path in the docs that resolves to nothing |

Every one is mutation-verified: the check was deliberately broken and confirmed to fail. A gate that
has never been seen to fail is a claim, not a control.

---

## How to work this list

1. **Take the P0 decision first** — it is the only item where the answer changes what everyone else
   should do, and it is not ours to make.
2. **One item per branch, PR it.** Three sessions share this checkout; the shared-tree failure modes
   are documented and have bitten repeatedly.
3. **Write the gate before closing the row.** Every closed item above has a test that fails when the
   defect is reintroduced. "Fixed" without one is a row that reopens silently.
4. **When an item closes, move the control to the threat model** and leave a one-line pointer here.
   Two documents describing the same control will disagree within a month.
