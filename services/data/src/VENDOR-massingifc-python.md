# Vendored: `massingifc_scene` + `massingifc_ifc`

`MassingCloud/massingifc` at commit `8135d07c7c6dda9138478c4558b853dd57437a18` (2026-08-01), copied
**verbatim** from `python/`. **MIT** — see `apps/web/src/vendor/massingifc/LICENSE`, same upstream repo.

| Package | What it is | Dependencies |
|---|---|---|
| `massingifc_scene` | The scene-package format: reader, writer, validator, importer | **none — stdlib only** |
| `massingifc_ifc` | IFC → scene package, server-side | `ifcopenshell` (already a dependency here) |

**No new dependency.** That is the whole reason these could be taken without asking: the reader half
imports nothing outside the standard library, and the converter half needs only the `ifcopenshell` this
service already runs.

## Why here, and why the import name is not rewritten

`services/data/src` is a PYTHONPATH root (alongside `aec_data`), so these resolve as `massingifc_scene`
and `massingifc_ifc` — **exactly their upstream names**. Nothing was renamed and no import was rewritten,
which is what keeps a re-sync a straight overwrite rather than a merge. A vendored copy with local
patches forks silently; anything wrong here goes upstream as an issue and comes back on the next sync.

## Local deviations from upstream — NONE

Upstream's own `python/tests/` are **not** copied. They are run in that repo, against its fixtures, and
include a TypeScript conformance step (`verify.mjs`) that needs its build. Our coverage of this
integration is `services/api/test_scene_package.py`, which asks a different and more useful question:
does a model **this** codebase authors survive the round trip, read back by `SceneImporter` — a reader
we did not write. A round trip over your own writer and your own reader passes on the wrong format.

## Re-syncing

```
git clone https://github.com/MassingCloud/massingifc      # or fetch an existing clone
cp -r massingifc/python/massingifc_scene services/data/src/
cp -r massingifc/python/massingifc_ifc   services/data/src/
```
then update the SHA above and run `test_scene_package` plus the full backend suite.

## What the format is for, and what it is not for

It carries the **semantic** half of a model — GlobalId-keyed nodes, property sets, typed relationships,
and precomputed by-class / by-level indexes — with geometry referenced by id and hash rather than
inlined. Geometry travels as **Fragments**, not re-encoded to glTF: re-encoding would mean decoding
geometry the engine decodes better and discarding the per-element addressing Fragments already carries.

**It does not speed up this application.** Our web client already receives IFC class and storey per
element from `/elements`, and `.frag` is still one blob per project. The value is every consumer that is
*not* our web client — an engine importer, a Blender addon, a CI check, a native viewer — whose only
alternative today is parsing the IFC themselves, which is the one thing this platform tells people not
to do. Recorded plainly here because a new endpoint that sounds like a performance feature is exactly
the kind of claim that gets repeated until someone measures it.

## One behaviour worth knowing before you debug it

The converter walks the **spatial hierarchy**. Products that hang outside it are reported through
`on_warning` and are not in the package. That is correct, and it means our tracked
`services/data/families/*.ifc` — which are TYPE libraries with no containment — convert to a package
holding nothing but the `IfcProject`. If a package looks empty, check the model has a
site/building/storey spine before suspecting the converter.
