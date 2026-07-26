# Family content — the type library and the external pack shelf

Massing places **types** (`IfcTypeProduct`), not meshes. A family is an IFC type carrying a mapped
representation; `place_type` instances occurrences that share that representation, which is why a
type edit propagates to every placed occurrence at once and stays GUID-stable.

There are three sources of family content, in increasing order of richness.

| Source | Where | What it gives you |
|---|---|---|
| **Generated catalog** | `aec_data/families.py` `CATALOG` | The built-in parametric families (furniture, sanitary, appliances, lighting, MEP). Box geometry, sized on demand. |
| **Generated library** | `services/data/families/library.ifc` | The same catalog written out as importable openBIM. |
| **External pack shelf** | `services/data/families/external/*.ifc` | Discipline-scoped packs of data-rich content — real sections, psets, classification, materials, quantities. |

## The shelf

Any IFC4 file of `IfcTypeProduct` entities dropped in `services/data/families/external/` is a pack.

```
GET  /families/library                        → catalog + generated library + shelf listing
POST /projects/{pid}/families/import-pack     → import a shelf pack into the project's source IFC
POST /projects/{pid}/families/import          → import an IFC the caller uploads
```

`import-pack` takes a **plain file name**, never a path — separators, parent references and
non-`.ifc` suffixes are refused, and the resolved path is re-checked against the shelf root so a
symlink cannot walk out of it either. The audit record carries the pack's **sha256**, so an import
can be tied back to exact content later.

### manifest.json

Drop a `manifest.json` beside the packs and the shelf listing gains real metadata:

```json
{"licensing": {"content": "CC0-1.0", "code": "MIT", "attribution": "…", "url": "…", "notice": "…"},
 "packs": [{"file": "structural-steel-w.ifc", "discipline": "structural-steel-w",
            "families": 3, "types": 403, "licenses": ["CC0-1.0"], "tiers": ["L300"]}]}
```

Two honesty rules hold here:

- A pack the manifest does **not** describe is still listed and importable, marked
  `described: false`. It claims nothing rather than inheriting a neighbour's metadata.
- If a manifest declares more types than actually arrive, the import response says so. A count that
  silently disagrees with its own manifest is the kind of thing that later reads as fact.

**Licence.** A licence may be stated on the pack row or once for the whole library, and either
spelling — `licence`/`license` for a single expression, `licences`/`licenses` for a list. A list is
read as *alternatives* and reported joined with SPDX `OR`; a pack that states nothing inherits the
library's declaration and is marked `licence_source: "library"` so an inherited claim is never
mistaken for the pack's own. Whatever applies travels with the content into the import audit record.
The shipped packs are **content CC0-1.0, code MIT** — the same terms as the rest of the platform.

### Getting packs

```bash
python scripts/fetch_families.py --list
```

Build/ops-time only — never a runtime dependency; the platform reads whatever is already on the
shelf and runs fully offline. Each pack's sha256 is checked against the release manifest, which
detects a corrupted download but **not** a compromised release (manifest and asset come from the
same place). Treat a pack like any third-party content you choose to trust.

The [`massing-families`](https://github.com/MassingCloud/massing-families) generator produces
CC0 packs from a YAML catalog. Until it publishes a tagged release, build them from a checkout —
`fetch_families.py` prints the exact commands.

## Can the shelf build a building?

Pack and family counts say how much content is on the shelf, not whether it is *enough*. A modeller's
question is "can I build a hospital with this", and `GET /families/coverage` answers that one.

```
GET /families/coverage                 → every typology
GET /families/coverage?typology=hotel  → one
```

Coverage checks the installed shelf against the IFC **type classes** each building system needs.
Class-level rather than family-level on purpose: a shelf holding some `IfcPumpType` provably *can*
place a pump, whereas asserting on family keys would only prove that some catalog happened to name
something `fire_pump`. Nine base systems apply to every building — structure, envelope, openings,
circulation, HVAC, plumbing, electrical, fire protection, site — and each typology
(residential · commercial · hotel · hospital · industrial · airport) adds the systems that
distinguish it.

A system is **satisfied only when every required class is present**. An HVAC package with terminals
and no duct is not half an HVAC package; it is one that cannot be issued. So a short system lists its
missing classes rather than reporting a comfortable percentage, and an unknown typology raises rather
than returning an empty report that would read as a pass.

```json
{ "buildable": ["airport", "commercial", "hospital", "hotel", "industrial", "residential"],
  "not_buildable": [], "shelf_classes": 72 }
```

This check is why `structural-foundations` exists. Before it, 413 families across 56 packs contained
**zero `IfcFootingType`** — W-shapes, HSS, precast, timber, rebar and post-tensioning, and nothing to
stand any of it on. Every typology was unbuildable for the same reason, and the shelf's size had
hidden it. `test_family_coverage` keeps it that way.

> The shelf directory can be relocated with `AEC_FAMILY_SHELF`. Tests that write packs use it so they
> never mutate the shipped content directory — two that did raced under the parallel runner.

## What the platform reads from a type

`type_detail` reports a type's bounding `[w, d, h]` in metres from its swept solid. This works for
**any** section we can measure, not just boxes:

- 13 parameterised IFC4 profiles — rectangle (incl. hollow and rounded), I-shape (incl. asymmetric,
  bounded by the *wider* flange), T, U, C, Z, L (equal-leg omits `Width` → falls back to `Depth`),
  circle (incl. hollow), ellipse, trapezium.
- `IfcArbitraryClosedProfileDef` — measured from the bounding box of its outer polyline.

A profile we genuinely cannot measure reports `dims: null`. That is the correct answer, not a
placeholder.

## Resizing a type — and what it costs

`edit_type_params(dims=…)` has two paths:

- **A plain rectangle is mutated in place.** The same solid entity is edited, so the change flows to
  every occurrence at once. This is the GUID-stable propagation path.
- **Anything else is replaced.** A `[w, d, h]` resize cannot express a W-shape or a hollow tube, so
  the existing representation is cleared and a box assigned. The response reports what was discarded:

```json
{"dims": [0.5, 0.5, 3.0], "geometry_replaced": ["IfcRectangleHollowProfileDef"]}
```

Two things this deliberately does **not** do, both of which it used to:

- It does not *append* the box beside the original section. That rendered both solids and made every
  downstream take-off count both.
- It does not treat a hollow section as an editable box. `is_a("IfcRectangleProfileDef")` is true for
  `IfcRectangleHollowProfileDef`, so an `HSS24X12X3/4` could be rewritten to 500×500 — keeping its
  wall thickness and its catalog name, describing a section that exists in no steel catalog.

If you need a resized *section* rather than a box, generate the type at the size you want instead of
editing an existing one. Renaming is the caller's job: a replaced type keeps whatever name it had.

## Type names follow the project's units

The type name is what appears in schedules, the picker and drawings, so it is formatted from the
model's `IfcUnitAssignment`:

| Project unit | Name |
|---|---|
| foot / inch | `Door 3'-0" × 0'-2" × 7'-0"` (to the nearest 1/16", fraction reduced) |
| millimetre | `Door 914.4×50.8×2133.6 mm` |
| metre (default) | `Desk 1.4×0.7×0.75 m` |

Geometry is unaffected — lengths always convert through `IfcUnitAssignment`. Only the label changes.

## Authoring a parametric shape (W10-2)

`create_type(..., shape={…})` builds a real section instead of a box. Fourteen profiles are
available — the same set the reader measures, asserted symmetric by the test suite:

`rectangle` · `rect_hollow` · `rounded_rect` · `ishape` · `asym_ishape` · `tshape` · `ushape` ·
`cshape` · `zshape` · `lshape` · `circle` · `circle_hollow` · `ellipse` · `trapezium`

```python
create_type(model, "IfcBeamType", "W16x40", shape={
    "profile": "ishape", "overall_width": 0.178, "overall_depth": 0.407,
    "web_thickness": 0.0079, "flange_thickness": 0.0131,
    "length": 6.0,                       # the SWEEP — see the trap below
})
```

**`length` is the sweep; `depth` is a profile parameter.** On the T/U/C/Z/L sections `depth` is the
*section* depth. If you pass the sweep as `depth` on a tee you get a member as long as its own web —
geometry that parses and is simply wrong. The builder refuses an extrusion with no `length`.

- **Revolve** instead of extruding with `{"revolve_angle": 360, "axis_x": 0.05}`. Angles outside
  (0, 360] are refused, and a *partial* revolve reports no bounding box rather than one it would
  overstate.
- **Cut holes** with `{"holes": [{"shape": "cylinder", "radius": .011, "height": .05, "at": [x,y,z]}]}`
  — `box` cutters too, capped at 32. A boolean result is written with `RepresentationType: "CSG"`;
  labelling it `SweptSolid` makes conformance checkers and some viewers drop the geometry.
- **`family_shapes.area(spec)`** gives the cross-sectional area only where it is exact. Sections that
  would need approximating return `None` — an approximate area silently feeds an inaccurate take-off.
- Every parameter must be positive. A zero web thickness produces a profile that parses, renders as
  nothing, and takes off as zero, so it is refused at build time.

**Meshes are deliberately not supported here.** A mesh can't be resized, scheduled by section, or
read back as dimensions — parametric authoring dies at that boundary. Content that genuinely needs
one belongs in an imported pack, above.

## Authoring a pack

Nominal size does not survive unit conversion: a 3'-0" door is 0.9144 m, and 0.9 m is 2'-11 7/16",
which is not a door anyone builds. Author in the units the product is specified in and store the
exact metric equivalent.

Keep packs **discipline-scoped**. `import_types_from_ifc` imports *every* type in the file it is
given, so a monolithic library floods a project with types nobody asked for.

See also: [authoring-matrix.md](authoring-matrix.md) for the recipes that place these types.
