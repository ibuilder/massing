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

### The timing argument — **CHECKED, and wrong as I stated it**

I wrote that `R38-PLAN-TRANSFORM` (v0.3.928) had unblocked a plan-linked walkthrough, on the guess
that their registration would consume a transform of the shape we now publish. **It does not.**

Read: `probe/plan.py` summarises DXF/PDF/DWG — sheet size, stated drawing scale, vector-vs-scan.
`adapters/plan.py` renders a PDF page and returns `points_per_pixel`, described in its own comment as
*"the exact link between pixel and sheet. Without it the image is a picture of a drawing; with it, a
stated scale like 1:100 gives metres per pixel."* Nothing there reads attributes off a plan we
generated.

They solve the same problem **from the opposite end**: recovering a pixel↔world mapping that
rasterisation destroyed in an *imported* drawing, where we publish a mapping we already knew for a
plan we *generated*.

**The real relationship is better than the one I guessed, and it changes step 1.** Both sides now
express the same concept — metres-per-unit plus an origin. That is an argument for defining that
representation ONCE and having both produce it, so a capture position pinned to an imported PDF and
one pinned to a generated plan are the same kind of thing. It is not an argument about adoption
timing, and the sequence below is ordered accordingly.

### Dependencies: the `dependencies = []` headline is true and misleading

Verified by reading imports, not the manifest:

- **`probe/` (all 11 modules) is genuinely stdlib-only.** e57, las, ply, mesh, splat, image, plan,
  structured, text, media, bim — every one. This is the part that is free to take.
- **`adapters/` is not.** Each useful adapter sits behind a real extra: `crs = pyproj>=3.6`
  (imported unconditionally — `from pyproj import CRS, Transformer`, no guard), `drone = pymavlink`,
  `plan = pypdfium2 + pillow`, `pointcloud = open3d`, `mesh = trimesh + numpy + pillow`,
  `media = opencv-python`.

**We do not currently declare pyproj.** So `adapters/crs.py` and `adapters/drone.py` are not a vendor
decision, they are a **new-dependency decision, and those need explicit sign-off.** That is the same
caveat massingplan's VENDOR.md makes in reverse: read the directory, not the project manifest.
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

1. **Agree one plan-calibration shape** — metres-per-unit + origin — that both a generated plan and
   an imported PDF/DXF can produce. This replaces the "verify the transform fit" step, which was
   answered above: there is no fit to verify, there is a representation to unify. Ours already ships
   as `data-plan-*` on the SVG root; theirs comes out of `adapters/plan.render_page`.
2. **Vendor `probe/` — and only `probe/`.** Stdlib-only, verified per module. Purely additive: we
   gain content-first identification of E57, LAS, PLY, mesh, splat, image, structured text and BIM
   files, and it touches nothing we ship. `e57.py` stays ours until a parity gate says otherwise.
3. **`ingest/session.py` + `telemetry.py`** — capture sessions, which is what makes session-vs-session
   compare possible. This is the actual product value and the reason to do any of this.
4. **`adapters/*` — a dependency decision, not a vendoring one.** pyproj, pymavlink, pypdfium2 and
   open3d are all new to us. Each needs explicit approval before any code moves, and coordinate
   frames additionally want parity work against real georeferenced data, because a wrong frame is
   confident and invisible.

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
