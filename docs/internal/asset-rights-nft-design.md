# Asset-rights / NFT-backed `.mass` releases — repository integration study

**Status: steps 1–3 of §5 BUILT (chain-independent core), and sealing is an OPT-IN chosen when the
`.mass` is created. No chain, no wallet, no contract, no new dependency.** The user chose this scope
after reading the mismatches below. What exists now: `services/api/src/aec_api/asset_rights.py`, a
stable `projects.asset_id` that survives a `.mass` round-trip, an `asset_rights.json` release
manifest written into the container only when asked for, and `services/api/test_asset_rights.py`
(69 checks, mutation-tested four ways). Everything from step 4 on — provider abstraction, contract,
testnet, wallet proof — remains unbuilt and gated on the decisions in §4.

**Why opt-in at creation rather than always-on.** A release manifest attests to the bytes of one
particular export, so it cannot be added to a container afterwards without producing a different
file — the choice only exists at the moment the file is written. Making it a choice also removed a
wart from the first cut: `asset_id` was previously minted on *every* export, which both opted
everyone in silently and made a `viewer`-role GET write to the database. Now a default save is
byte-for-byte the container this format has always produced, mints nothing, and writes nothing.

This document began as step 6 of the incoming brief's "First: Inspect the Repository", and it
exercises that brief's own closing instruction: *"Stop and report any mismatch between this brief and
the repository's architecture instead of building a duplicate subsystem."*

There are five material mismatches. Two of them change what the feature *is*, not merely how it is
built. They are recorded here before any code is written, because each one is cheap now and expensive
after a schema and a contract exist.

> **Placement note.** The brief asks for this file at "docs/architecture/asset-rights-nft-design.md".
> `docs/` is this repository's **public web root** (`docs/CNAME` → massing.build) and there is no
> `docs/architecture/` directory. Design notes for unshipped work live in `docs/internal/`, alongside
> "r36-viewer-subapp-design.md" and "security-roadmap.md". Publishing an architecture for an unbuilt,
> counsel-gated rights system on the public marketing site is a disclosure decision, not a filing
> convention, so this follows repository convention instead. Trivially movable if you want it public.

---

## 1. The five mismatches

### ① `.mass` is a ZIP container, not a JSON document

The brief's schema section adds a top-level `assetRights` key beside `schemaVersion` and `project`,
and speaks of "the `.mass` file" as one JSON object with a whole-file hash.

`.mass` is **a plain ZIP archive** — format id `massing.project`, version 2 — holding `manifest.json`,
`README.txt`, `project.json`, `data/<table>.json`, `geometry/*.ifc` + `model.frag`, and `blobs/`.
See `docs/mass-format.md` and `services/api/src/aec_api/bundle.py`.

There is no document to add a top-level field to. The equivalent move is a new archive entry
("asset_rights.json") plus an inventory row in `manifest.json`. This is a **better** fit than the
brief's shape — the container already carries a per-entry inventory and an explicit `excluded` list —
but every sentence in the brief about optional-vs-null semantics, unknown-field preservation and
serializer round-tripping is written against a JSON document model that does not exist here.

### ② A deterministic content hash already exists — building `massCoreHash` would duplicate it

Deliverable 2 asks for a canonical-JSON, SHA-256, determinism-tested release hash, with fixtures
proving the same semantic release hashes identically.

That is **R23-DIGEST**, shipped: `services/data/src/aec_data/model_digest.py` is a deterministic,
Merkle-shaped, multi-scale digest (project → storey → class → element). Its test file
`services/api/test_model_digest.py` already makes exactly the brief's determinism claims falsifiable —
it digests the same file from two separate opens and asserts byte-identical JSON, and has named tests
for each thing that silently breaks determinism: timestamps, paths, filesystem stats, `id()`, STEP
entity ids, iteration order, and IEEE float noise. It rounds floats *before* hashing, sorts every
mapping, and records its own configuration so a diff refuses to compare digests measured differently.

Writing an RFC-8785 `massCoreHash` beside this is the duplicate subsystem the brief warns against.
The correct move is to make the release manifest *cite* the existing digest.

**One real gap:** the digest covers the IFC model. A release manifest also wants hashes over
`exports/` and `blobs/`. Those are ordinary file hashes and are new work — but small, and not a
second hashing philosophy.

### ③ Import mints a fresh project id — so `assetId` cannot bind to a project id

The brief binds `assetId: urn:massing:asset:<project-id>` and expects it to identify the asset.

`import_bundle` in `services/api/src/aec_api/bundle.py` **mints a new project id on every import**
(`new_pid = uuid.uuid4().hex`) and regenerates row primary keys, deliberately, so a container can be
cloned into the same database or moved between machines without collisions.

Consequence: export a `.mass`, re-import it, and the project id is different — so a token minted
against the old id no longer names anything in the new database. Provenance that dies on a
round-trip is not provenance. `assetId` must be a **new, stable, container-carried identity** that
survives import, explicitly preserved by the import path — which is a change to import semantics,
not an additive field.

### ④ `model.frag` is derived and regenerable — do not hash it into release identity

The container carries `geometry/model.frag`, documented in `docs/mass-format.md` as *derived and
regenerable* from the IFC. The brief's manifest lists "scene/model.glb" as a hashed export.

Hashing a regenerable artifact into release identity means a re-conversion — a tessellator upgrade, a
different build — changes the release hash without the building changing. That is the exact false
positive `model_digest.py` was designed to avoid. Derived artifacts must either be excluded from the
identity hash or hashed in a clearly separate, non-identity section.

### ⑤ There is a prior recorded decision on tokenization, and it points the other way

`docs/roadmap-completed.md` carries an explicit, revised **DECISION** under "Compliant syndication /
investor-management depth — cap-table-first, token-last (strategic, legal-gated)":

> *"We will **not** build the securities/compliance stack ourselves (KYC/accreditation, transfer-agent
> recordkeeping, Reg-D compliance engine, escrow, the token) — that is licensed, counsel-gated,
> multi-year work and outside our risk appetite."*

with the posture "Postgres is the legal source of truth, the token an optional mirror", and Massing
staying the origination front-end that hands regulated pieces to a licensed partner.

**In fairness, that decision is adjacent, not identical.** It is about *securities* tokens —
fractional ownership of a deal, Reg-D, transfer agents. This brief is about *provenance and license
entitlement* for a design release, which is not a security and does not move money. It is genuinely a
different question and the prior decision does not automatically settle it.

But the posture it establishes — token last, Postgres is the source of truth, legal-gated, stay out
of the regulated path — is the house position on this class of work, and this brief proposes the
opposite sequencing. That is a decision for the user, not for me.

---

## 2. What already exists that this feature would use (verified)

| Need | Exists as | Note |
|---|---|---|
| Release / version concept | `ModelVersion` in `services/api/src/aec_api/models.py` | Snapshot per publish: guids, element_count, per-element fingerprints |
| Release **state machine** | `ModelVersion.review_status` | `draft → in_review → approved`, with reviewed_by / reviewed_at / review_note |
| Deterministic content hash | `services/data/src/aec_data/model_digest.py` | See ② |
| Version diff | `services/api/src/aec_api/versions.py` | Per-element fingerprint diff |
| Audit log | `audit.record(...)` in `services/api/src/aec_api/audit.py` | `action / actor / method / path / topic_id / detail` |
| **Revocable scoped entitlement** | `ShareToken` in `services/api/src/aec_api/models.py` | See below — this is the important one |
| Auth, step-up, token signing | `services/api/src/aec_api/auth.py` | Includes `create_stepup_token` / `verify_stepup_claims` |
| Migrations | Alembic, 25 revisions, single-head test | A new table needs a revision |
| Container round-trip | `services/api/src/aec_api/bundle.py` | Export / import / preview |

### The finding that most changes the framing: `ShareToken`

`ShareToken` (with `services/api/src/aec_api/client_portal.py`) is already a **revocable, auditable,
per-capability opt-in entitlement system**: a strong random credential scoped to one project, soft-
revocable with immediate effect, view-counted, with capabilities defaulting to **off** and granted
one at a time (`show_payments`, `show_model`). Its docstring draws precisely the distinction the
brief's metadata section cares about — serving converted geometry is a different disclosure from
serving `source.ifc`, which carries every property set, classification and GlobalId in the model.

So "grant a named party a revocable, scoped, audited right to a specific release, and prove it later"
is **substantially already built, without a blockchain**. What a token would add over `ShareToken` is
narrow and should be stated honestly before building: transferability without the issuer, and
third-party verifiability of that transfer. Everything else in the brief's entitlement model —
revocation, scoping, audit, project-permission-AND-entitlement — the existing system already does,
and does with the property the brief itself concedes a chain cannot have (revocation that actually
takes effect).

---

## 3. Already satisfied, and one thing that is not

- **"Never persist secrets to `.mass`"** — there is a gate: `services/api/test_no_secrets.py`.
- **Dependency licensing** — the repository rule is permissive-only (MIT/BSD/Apache; AGPL explicitly
  refused, see `docs/ATTRIBUTIONS.md`). OpenZeppelin (MIT) and the usual EVM client libraries (MIT)
  would pass that rule. Note the prior decision above observed that the T-REX security-token
  reference is GPL-3.0 and therefore unusable here.
- **Threat model location** — `docs/security/threat-model.md` already exists and is public, so a
  sibling threat model there is consistent with convention (unlike the architecture doc, ①'s note).
- **Not satisfied: there is no feature-flag mechanism.** The brief requires the whole capability be
  flag-gated and disabled by default. There is an `AppSetting` table and various env-read helpers,
  but no general flag service. `NFT_ENABLED` would have to be built as env config plus a per-project
  setting — a small piece of new infrastructure the brief assumes is already there.

---

## 4. Decisions required before any implementation

These are the user's, not mine. None has been pre-empted.

1. **Does the prior "token-last, integrate-don't-build" decision (⑤) govern this?** If yes, this stops
   here. If no — because provenance/licensing is not securities — say so and it proceeds.
2. **Given `ShareToken` already delivers revocable scoped entitlement, is the goal transferability
   and third-party verification specifically?** If the actual goal is "prove this release is
   authentic and unaltered", that is achievable today with the existing digest plus a signature, with
   **no chain, no wallet, and no new dependency** — and would be my recommendation as step one
   regardless, since the brief's own manifest/signature layer is chain-independent.
3. **Is `assetId` allowed to change import semantics (③)?** Provenance requires a stable identity
   that survives export/import; today nothing does.
4. **Solidity in this repository.** There is no JS/TS contract toolchain here and CI does not run
   one. Adding Hardhat/Foundry plus contract tests to CI is a real, separate infrastructure change.
5. **Public-repo disclosure.** This repository is public. Decide what of this design is published.

## 5. Recommended sequencing if it proceeds

Chain-independent value first, so nothing is wasted if the chain question is answered "no":

1. ✅ **Stable asset identity** surviving a `.mass` round-trip (③) — prerequisite to everything else.
2. ✅ **Release manifest** citing the existing digest rather than re-implementing it (②) and
   excluding derived artifacts (④).
3. ✅ **Sign and verify** the manifest. *Stopped here, as planned.* Steps 1–3 deliver authenticity,
   provenance and tamper-evidence with no chain, no wallet, no new dependency, and no legal gate.
4. Provider abstraction + mock provider — still no chain. **Not built.**
5. Contract, testnet, wallet proof — only after decisions 1, 4 and 5 above are answered. **Not built.**

## 6. What was built, and the decisions inside it

`services/api/src/aec_api/asset_rights.py` — canonicalisation, manifest construction, two hashes,
Ed25519 signing and verification. `services/api/test_asset_rights.py` covers it.

Four choices in it are worth knowing about, because each went against the brief's literal text for a
reason:

- **Two hashes, not one.** `content_hash` is release *identity* and excludes every volatile value
  (timestamps, release id, signature, derived artifacts) so the same semantic release hashes
  identically anywhere. `manifest_hash` covers the whole statement and is what the signature is
  over. Collapsing them would have meant a release's identity changed every time it was re-attested.
- **Floats are refused outright.** The brief asks for RFC 8785, which mandates ECMAScript number
  formatting that Python's float repr does not always match. Rather than rest a determinism claim on
  that agreement holding, `canonical_bytes` raises on any float; every manifest value is a string or
  an int, so the divergence cannot arise.
- **Ed25519, not an HMAC.** `auth.py` already has HMAC signing over a shared secret, which was the
  cheaper route. It is a MAC: it proves a release to whoever already holds the secret, which is not
  what provenance means. `cryptography` was already in the lock, so asymmetric signing cost zero new
  packages — but it did make the "nothing here is imported by our code" note in
  `services/api/requirements.in` false, which is corrected there rather than left to drift.
- **`verify_release` reports findings, not a boolean.** `trusted_key` is False when a signature
  verified only against the public key carried *in the same document* — self-consistent, and
  worthless against an attacker who rewrote the manifest and re-signed it. A single true/false would
  have hidden exactly that case.

**Where the option surfaces.** `GET /projects/{pid}/bundle?asset_rights=true` (default false), and in
the web app's *Save project* flow, which asks only where the deployment can honour it —
`GET /asset-rights/status` reports whether the capability is on and whether a signing key exists, so
the UI can distinguish "signed and attributable" from "tamper-evident but anonymous" instead of
implying the stronger one. Dismissing that dialog saves **unsealed**: the fallback of a cancelled
prompt should be the plainer artifact, never the one that mints an identity and applies a signature.
The status route deliberately uses plain authentication rather than `require_role`, which resolves
its `pid` from the query string and so is unsafe on a route with no `{pid}`.

`projects.asset_id` is nullable, **not unique**, and **not backfilled** — cloning a container into
one database legitimately yields two rows of the same lineage, and an id invented by a migration
would differ on every installation while looking authoritative. The reasoning is on the model and in
the migration.

## 7. Explicitly not done

No contract deployed, no funds spent, no mainnet configuration, no new dependency, no `.mass`
format-version bump (the container gained a field; v2 readers ignore it and a container without it
still imports — both tested). Per the brief: *"Do not begin contract deployment or mainnet
integration during the initial implementation."*
