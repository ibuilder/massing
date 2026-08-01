# Sibling repositories — what to import, what to leave, and why

*Working note, 2026-08-01. Evaluated `MassingCloud/{massingifc, massingviser, massingcapture, massing-pdf}`
against this codebase with the brief: **server-side efficiency, load speed, general efficiency** — not
feature count.*

All four are **MIT** (GitHub's licence detector reports "none" for all four; the LICENSE files are
present and are MIT — the detector is wrong, not the repos). Nothing here is a licence blocker.

---

## The headline: "we imported an old version" is true of exactly one of them

That was the starting assumption, and it is worth stating precisely because it changes the plan.

| Repo | What we vendor | Vendor point | Drift in the part we use |
|---|---|---|---|
| `massingifc` | `core-kernel`, `plugin-sdk`, `project-schema` | `a581f064` (07-27) | **NONE — byte-identical to upstream HEAD** |
| `massing-pdf` | `src/` as `@massingcloud/pdf-viewer` | `65e90114` (07-27) | **14 commits, 14 source files** |
| `massingviser` | nothing | — | n/a |
| `massingcapture` | nothing | — | n/a |

`massingifc` is 12 commits ahead overall, but **not one of the 43 changed files touches the three
packages we vendor** — verified by comparing directory content hashes at both commits, not by reading
the commit subjects. So the kernel copy is current and needs no re-sync. Everything new there is
capability we never took, which is a different decision from a version bump.

`massing-pdf` is the one that is genuinely behind, and it matters — see the finding below.

---

## Finding: our vendored PDF engine carries an upstream permission bypass

Upstream `bcd636fa` (today) fixes this in `core/store.ts`. Our copy at
`apps/web/src/vendor/massingpdf/core/store.ts:194` has the defective form verbatim:

```ts
const capability = patch.status !== undefined && patch.status !== before.status
  ? "markup:status" as const
  : "markup:edit" as const;
if (!this.o.policy.allows(capability, before)) return undefined;
```

One patch is checked against **one** capability. A patch carrying a status change *and* a text or
geometry change is only ever checked against `markup:status` — so a reviewer granted `markup:status`
but deliberately not `markup:edit` can reword or move a markup by bundling both fields into one
object. The comment two lines above states the exact guarantee the code fails to provide: *"a reviewer
may be allowed to close an issue without being allowed to reword it."*

**Grade for us: not currently exploitable, and I want to be exact about why rather than either
alarming or dismissing.** `pdfTakeoff.ts` imports **only** `PdfDocument` and `configureWorker`. We
never construct a `Viewer`, never build a store, and never pass a `policy` — so the branch is
unreachable in our build. Client-side policy is not our authorisation boundary in any case; ours is
server-side.

It is still worth fixing now, for one reason: `pdfTakeoff.ts:15` records that *"markup and calibrated
takeoff are still ours and move in later."* The day that move happens, this becomes live — and it will
look like new code that was reviewed, not inherited code that was not. Re-syncing costs one overwrite
today and removes a landmine from a planned step.

The same commit also fixes a **false success count**: `addMany` filtered drafts through the `import`
permission but reported the number *attempted*, so a user without `import` saw *"Imported 47 markups."*
over an empty store. That is the house pattern — a confident number where the honest answer was "none
of them" — and worth importing on its own.

---

## Gap analysis against the actual brief

| Capability | Us today | Verdict |
|---|---|---|
| ETag / conditional GET / `immutable` caching of `.frag` | **Built** — `serving.py:36-48`, 304 on revalidate | no action |
| Geometric level of detail (decimation) | **Absent** | **real gap** |
| Server-side spatial index for picking / culling / broad-phase | **Absent** | **real gap** |
| Broad-phase clash | `clash.py` all-pairs AABB, numpy-vectorised | **scaling ceiling** |
| Precomputed class / level indexes shipped with geometry | partial (API-side) | worth adopting |
| Content-addressed geometry identity | via `storage.version` ETag | adequate |

### The LOD false friend — worth flagging explicitly

We already have `services/api/src/aec_api/lod.py`, and it is **not** what massingviser's `geometry/lod.py`
is. Ours is Level of **Development** (LOD 100–500, BIM maturity inferred from LOIN facet completeness).
Theirs is geometric Level of **Detail** (vertex-clustering mesh decimation). A search for "do we have
LOD" returns a confident yes and the wrong answer. We have no geometric LOD at all.

### The clash scaling ceiling

`clash.py:120` builds the candidate set as a full N×M boolean matrix:

```python
overlap = ((mins_a[:, None, :] <= maxs_b[None, :, :]).all(axis=2)
           & (maxs_a[:, None, :] >= mins_b[None, :, :]).all(axis=2))
```

Vectorised and fast at a few thousand elements per side; at 50k × 50k that is 2.5 × 10⁹ booleans
before any narrow phase runs. massingviser's `geometry/bvh.py` is a median-split BVH written
explicitly to move picking, frustum culling and broad-phase clash server-side. This is an
optimisation of something we have, not a new feature — which makes it the easiest to justify and the
easiest to measure.

**Measure before adopting.** The last performance claim in this repo moved from "6.44% of a takeoff"
to "0.92%" once it was measured at a realistic element count, because the small fixture under-sampled
everything the hot path competes with. Any BVH claim must be benchmarked at tower scale (the 30-storey
model), not on a fixture.

---

## What each repo is actually for

**`massingifc`** — framework-agnostic TS kernel and capability contracts, no viewer. We already
depend on its stable third. What is new is `engine-bridge` (engine-neutral scene packages: GlobalId-keyed
nodes, precomputed class/level indexes, geometry as Fragments binary carried by reference) plus **two
new Python packages**: `massingifc_scene` (the scene-package format — reader, writer, validator,
importer; stdlib only) and `massingifc_ifc` (IFC → scene package, server-side, on `ifcopenshell`).

That Python pair is the closest fit to our non-negotiables of anything in the four repos: pre-convert
server-side, address by GlobalId, keep geometry and metadata separate with binary payloads fetched
only when asked. It runs on the `ifcopenshell` we already have.

**`massingviser`** — a complete parallel AEC platform in Python: kernel, fifteen capability families,
content-addressed VCS, server-side geometry. **Do not import this wholesale.** Thirteen of its fifteen
families duplicate `services/api` and would fork the product. Its value to us is three files in
`geometry/` (`lod.py`, `bvh.py`, `payload.py`) and possibly `vcs/`.

**`massingcapture`** — reality capture: content-first format detection across ~30 scanner formats,
declared-frame coordinate maths, plan-linked walkthroughs, zero runtime dependencies. This is a **new
product area**, not an efficiency win, and it should be judged on whether we want reality capture at
all — not folded into a performance sprint.

**`massing-pdf`** — already vendored; needs the re-sync above.

---

## Plan

Four phases, ordered so the cheap certain wins land before the expensive uncertain ones.

### Phase 1 — Re-sync `massing-pdf` *(S, no risk, do first)*
Straight overwrite of `apps/web/src/vendor/massingpdf/` to upstream HEAD; VENDOR.md records "no local
patches", so this is a copy, not a merge. Brings the permission fix, the honest import count, three OCR
fixes and the a11y-label correction. Verify: `ties.test.ts` alias map, `pdfVendor.test.ts` reachability,
typecheck, the drawings suite. Re-assert "no local deviations" by diffing against upstream after the copy.

### Phase 2 — Adopt `massingifc_scene` + `massingifc_ifc` server-side *(M, high value)*
Take the two Python packages into `services/` behind the existing conversion pipeline. Serve the scene
package alongside `.frag` so the browser receives precomputed class/level indexes and an ancestor chain
instead of deriving them, and fetches geometry only for what it draws. The conformance suite upstream
already proves the format round-trips between two independent implementations — which is exactly the
"assert against a reader you didn't write" discipline this repo learned the hard way, so it is worth
keeping their tests rather than writing our own.

**Premise check before building:** confirm what our client currently derives client-side versus receives.
If the API already ships class/level indexes, the win is only the lazy geometry, and the phase shrinks.
Do not build against the assumption.

### Phase 3 — Port `bvh.py` and benchmark broad-phase clash at tower scale *(M)*
Port the BVH into `services/data`, put it behind the existing `clash.py` entry point, and benchmark
against the 30-storey tower — both correctness (same clash set, asserted as a set, not a count) and
time/memory. Ship only if the tower measurement justifies it; record the numbers either way, including
a negative result.

### Phase 4 — Geometric LOD *(M–L, defer until 2 and 3 land)*
`lod.py` vertex-clustering decimation to generate a coarse tier served first. Highest ceiling of
anything here for perceived load speed, and the most work: it needs a serving tier, a client swap, and
a visual-regression check. It also needs a name that cannot be confused with the LOD we already have —
`geometry_lod.py`, or the module renamed on adoption.

**Not planned:** `massingviser`'s kernel and fifteen families (duplicates `services/api`), and
`massingcapture` (separate product decision, not an efficiency question).
