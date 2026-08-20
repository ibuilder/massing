# Library performance & security review — 2026-08-19

**Grade: research + proposal, measured against this tree.** Live pins checked on
`origin/main` at v0.3.986, then v0.3.987 ships the one actionable web bump in the
same change. Not a shopping list. New packages still need an explicit operator OK
(roadmap-directions). Version bumps of existing deps are routine when they fix a
published advisory or sit at the current upstream without a pairing hazard.

Sources: npm/PyPI latest versions, GitHub/OSV advisories (CVE-2026-16633,
CVE-2026-54283, PYSEC-2026-2447), this repo's `requirements.lock`,
`package-lock.json`, `apps/web/package.json`, `docs/internal/dependency-advisories.md`,
and the RT-BVH / RT-NODE-LANE gated items in `docs/roadmap.md`.

---

## Verdict

**Do not add a new rendering, caching, or security library.** The expensive work
is already in the right packages (Fragments, ifcopenshell, orjson, diskcache when
opted in). Performance that a user will feel is **incremental fragment reload after
an edit**, which is application work, not an npm install.

**Do tighten one existing web pin and both pdf.js call sites** (this PR). The Python
lock is already on the patched FastAPI / Starlette / pypdf / cryptography /
python-multipart / Pillow floors. Regenerating that lock on a laptop is forbidden;
raise floors only via `lockfile.yml`.

---

## What we run today vs upstream (2026-08-19)

### Web (must stay a compatible set)

| Package | Manifest | Lock / resolved | Latest seen | Action |
|---|---|---|---|---|
| `@thatopen/components` | **3.4.8** (exact) | 3.4.8 | **3.4.8** (npm, updated 2026-07-26) | Hold. Pair with fragments. |
| `@thatopen/fragments` | **3.4.7** (exact) | 3.4.7 | **3.4.7** | Hold. |
| `@thatopen/components-front` | 3.4.4 | — | still 3.4.x line | Hold with the pair. |
| `web-ifc` | **0.0.77** (exact) | 0.0.77 | 0.0.77 (That Open peer) | Hold. A drift mis-parses geometry. |
| `three` | **0.185.1** (exact) | 0.185.1 | **r185** is current on GitHub | Hold. That Open peers `>=0.182`. Do not jump r186 until the pair does. |
| `vite` | **8.2.1** | 8.2.1 | **8.2.1** (2026-08-06) | Hold. Dev-server CVEs in 8.0.x are already behind us. |
| `pdfjs-dist` | was `^6.0.227` | already **6.2.108** | **6.2.108** | **Pin 6.2.108.** Range `^6.0.227` still *allows* the vulnerable 6.0–6.2.107 line. CVE-2026-16633 (HIGH): PDF-embedded JS in the hosting origin when `enableScripting` defaults true. |
| `pdf-lib` | ^1.17.1 | — | 1.17.x | Hold (write path, not the viewer). |
| `camera-controls` | 3.1.2 | — | matches That Open peer `>=3.1.2` | Hold. |

### Python (API image installs the hashed lock)

| Package | Lock | Latest on PyPI | Action |
|---|---|---|---|
| `fastapi` | 0.141.1 | **0.141.1** | Hold. |
| `starlette` | **1.3.1** | 1.6.0 | Hold. 1.3.1 **is** the CVE-2026-54283 fix. A 1.6 bump is a FastAPI-coupled lock regen, not a security floor. |
| `python-multipart` | **0.0.32** | **0.0.32** | Hold. |
| `pypdf` | **6.15.0** | (6.15 line is the 71852/71870 floor) | Hold. |
| `cryptography` | **50.0.0** | 50.x | Hold unless `audit_lock_gate.py` fires. |
| `pillow` | **12.3.0** | floor already in `services/data/requirements.txt` | Hold. |
| `diskcache` | **5.6.3** | still 5.6.3; **no upstream fix** | Carry. See dependency-advisories. Do **not** add `mapped-diskcache` (temporary fork, new package). |
| `orjson` | present | — | Hold. Already the JSON hot path. |
| `defusedxml` | present | — | Hold. XXE path. |

---

## Security — libraries vs our own code

1. **pdf.js scripting (this PR).** Lock was already on 6.2.108; the manifest range was not.
   Two `getDocument` sites (`vendor/massingpdf/core/document.ts`, `drawings/drawings.ts`)
   did not set `enableScripting: false`. Pin + flag. Apache-2.0, existing dep.

2. **diskcache pickle.** Unchanged. Off unless `AEC_BAKE_SHARE_DIR` is set. A HMAC fork
   (`mapped-diskcache`) is a *new* dependency and an unmaintained-upstream bet. If the
   shared cache is ever on-by-default, prefer configuring `JSONDisk` *inside* diskcache
   (no new package) if the cached values are JSON-safe; geometry buffers may not be.
   Re-review 2026-11-09 as already written.

3. **Do not add.** `gitleaks` / TruffleHog remain REL-6 (tooling when a permitted scanner
   exists in CI). Not an application library. `three-mesh-bvh` is **already transitive**
   and MIT; promoting it to a direct dep is RT-BVH and is gated on a picking benchmark
   that asserts `hits > 0` (roadmap). Adding it now would not make Place faster.

4. **Do not swap.** React, Reflex, Redis-as-required-cache, PyMuPDF (AGPL). Closed.

---

## Performance — what a library will not buy

The round-trip that hurts is **recipe → IFC write → convert → full `.frag` reload**.
No BVH, Draco, or mesh-opt package on the client fixes that. Fragments + server convert
already are the architecture. Next performance work is delta/optimistic geometry, then
`PERF-WORKERS` / `AEC_GEOM_WORKERS` for clash/drawings — existing knobs.

Vite 8 / Rolldown: already on Vite 8.2.1. Roadmap's "defer Vite 8" line is stale;
do not treat it as a pending upgrade.

WebGPU via `three/webgpu`: MassingViewer extraction will make viewport creation async
(WebGPU first). Do not dual-track a Three WebGPU renderer here ahead of that swap.

---

## New libraries evaluated and **refused** (this pass)

| Candidate | Licence | Why not |
|---|---|---|
| `mapped-diskcache` | (fork of Apache diskcache) | New package; upstream diskcache still 5.6.3; advisory already accepted with a re-review date. |
| Direct `three-mesh-bvh` | MIT | Transitive already. RT-BVH wants a measured miss/hit split first. |
| Extra Redis / msgpack cache | — | Breaks offline/$0 default. diskcache is the cross-worker path. |
| Another PDF engine | often AGPL (PyMuPDF) | Forbidden. pdf-lib + pdf.js is the permitted pair. |

---

## Operator decisions still open

- Promote `three-mesh-bvh` to a **direct** dep after a picking benchmark (RT-BVH).
- `JSONDisk` vs pickle **if** bake-share is turned on in prod.
- Starlette 1.3.1 → 1.6.0 only with a FastAPI-compatible lock regen on `lockfile.yml`.

---

## What shipped in v0.3.987 from this review

- Pin `pdfjs-dist` to **6.2.108** (no caret).
- `enableScripting: false` on both `getDocument` sites; `PDFJS_LOAD` constant; gate in
  `apps/web/src/drawings/pdfjsScripting.test.ts`.
