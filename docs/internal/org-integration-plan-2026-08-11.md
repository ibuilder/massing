# MassingCloud org — what to pull in, 2026-08-11

Internal. A survey of all ten org repos and a recommendation. Everything below was checked against
the repos rather than taken from their descriptions; where it wasn't, it says so.

## Licences: all eight code repos are MIT — and the API says otherwise

`gh repo list --json licenseInfo` returns **`NO-LICENSE` for all ten**, including massingbill, whose
`LICENSE` file plainly reads `MIT License`. GitHub's licence detection is not populated here.

**Read the LICENSE file. Not the API field, not the README badge, not the repo description.** Verified
directly: massingplan, massingbill, massing-pdf, MassingViewer, massingifc, massingcapture,
massingviser, massing-families — all MIT. The two WordPress repos (massing-cloud, massing-pro) are
storefront/PHP and are not code we would consume.

## Activity since 2026-08-01

| repo | commits | our state |
|---|---:|---|
| MassingViewer | 94 | ready; blocked on **our** conformance run (#512) |
| massingbill | 39 | core exists; scope open, "pure addition" claim was false |
| massingplan | 28 | **synced** to `b703dca4` at v0.3.932 |
| massing-pdf | 18 | integrated once (#488); delta **not yet assessed** |
| massingviser | 16 | not adopted as a viewer; server-side reuse only |
| massingifc | 11 | conventions accepted; nothing pending |
| massingcapture | 7 | **never assessed — this document's main finding** |
| massing-families | 0 | integrated (#489); stable |

Activity is not value. The lowest-commit repo is the one worth the most here.

## The recommendation: massingcapture, and the reason is timing

**Reality capture is the one capability gap the user named explicitly** — drone imagery, 3D camera,
digital-twin layering — and it is the only repo we have never assessed.

It meets the adoption bar on its own terms: `dependencies = []`, with `ifcopenshell`, `pye57` and
`laspy` as *optional* extras. The core parses the E57 XML index and the LAS public header without
them. That is the vendorable-core standard applied to a whole package rather than a `core/` subtree.

### What we already have

`services/api/src/aec_api/`: `e57.py` (E57 → XYZ), `photo_cv.py` + `photo_detect.py` (R22-PHOTO-CV
Tiers 1–2), `scan_deviation.py`, `license_cloud.py`. `services/data/`: `step_scan.py`.

### What they have that we do not

`adapters/drone.py`, `adapters/crs.py` (declared-frame coordinate math), `ingest/telemetry.py`,
`ingest/session.py` (capture **sessions** — the thing that makes session-vs-session compare
possible), `probe/splat.py` (Gaussian splats), `probe/ply.py`, `probe/mesh.py`, `probe/las.py`,
`probe/plan.py` (plan registration), `bridge/scene.py` (BIM + mesh + cloud + splat in one scene).

### The timing argument — **stated as a hypothesis, not a finding**

`R38-PLAN-TRANSFORM` shipped three commits ago (v0.3.928). Our plan SVG now publishes the six terms
of its own world↔pixel transform, so a client holding a world position can find its pixel. That is
*precisely* the primitive a plan-linked walkthrough needs in order to place capture positions on a
drawing — and until v0.3.928 we could not have built it without the back-solving hack that entry
explicitly refuses.

**I have inferred this fit from module names and the README, not from reading `probe/plan.py`.**
Confirming it is step 1 below, and if it does not hold the rest of the sequencing changes.

## Why this one is a PARTIAL vendor, unlike massingplan

massingplan was a `core/` subtree, so we took the whole tree — a partial copy is how two
implementations start, and their drift check watches both directions.

massingcapture is different: it is a **whole application**, including `server/api.py` (31 KB) and
`bridge/massingviser.py` — a bridge to the platform we explicitly did **not** adopt. Vendoring it
whole would import a second web server and a dependency on a rejected platform.

So the unit here is `adapters/` + `probe/` + `ingest/`, and the drift story must be written down
before the copy rather than after, because "we took part of it" is exactly the condition their drift
check will flag forever otherwise.

## Sequence

1. **Verify the plan-transform fit.** Read `probe/plan.py` and `adapters/crs.py`. Does their
   registration consume a transform of the shape we now publish? One session, no code.
2. **Vendor `probe/` only**, as a read-only capability: content-first format detection for E57, LAS,
   PLY, mesh, splat, image, structured text. This is additive — we gain formats we cannot currently
   identify — and touches nothing we already ship. `e57.py` stays ours until a parity gate says
   otherwise.
3. **Then `ingest/session.py` + `telemetry.py`**, which is what unlocks capture sessions and
   therefore session-vs-session compare (verified progress). This is the actual product value.
4. **`adapters/drone.py` + `crs.py`** last — coordinate frames are where a wrong answer is confident
   and invisible, so they want their own parity work against real georeferenced data.

Do **not** take `server/`, `demo.py`, or `bridge/massingviser.py`.

## Still unassessed, and honestly so

- **massing-pdf**: 18 commits since our #488 integration. Delta not read. Likely cheap and likely
  worth it, but that is a guess until someone diffs it.
- **massingbill**: unchanged from the v0.3.931 finding — their "pure addition" claim did not survive
  checking (we have retainage math in `payapp.py:49` and G702 across six files), so the requisition
  half is a potential duality. Recommendation stands at money-module-only with the existing G702
  suite as a parity gate.
- **MassingViewer**: 94 commits, and the blocker is ours, not theirs — #512, which needs `:8093` up
  with a real project.

## The method note that applies to all of this

Two claims from sibling agents were checked this week and **both were right while my first check was
wrong**: a non-recursive glob that undercounted a directory 6×, and a CRLF-blind diff that reported
7 changed files where there was 1. When a check contradicts a specific, confident claim from someone
closer to the work, suspect the check first. Recorded in session memory as "a-recheck-must-be-as-careful-as-the-original" — deliberately not
linked, since that path lives outside the repo and a link that cannot resolve is worse than a name.
