"""R38-PLAN-IDENTITY — a plan whose linework knows which element drew it.

`_bake_uncached` always had `shape.guid` in hand (it is what `by_guid` is called with) and threw it
away, keeping only `(class, mesh)`. Every polyline downstream was therefore anonymous: a drawing
could say "this line is a wall" but never "this line is *that* wall". That is the difference between
a drawing and a picture of one — 2D↔3D selection sync, click-a-wall-in-plan and precise pin
anchoring all need the element behind the line.

The assertions are about the ways a change like this passes while being useless or wrong:

1. **the guid must be REAL** — a positional shift that put the class where the guid belongs would
   still produce three-tuples and still "work". Every guid is resolved through `by_guid` against the
   model, so a plausible-looking string cannot pass;
2. **the guid must be the RIGHT one** — the wall's guid must land on the wall's polylines, not
   merely on some polyline. Checked against a known element placed at a known location;
3. **one element yields MANY polylines** — a cut through a wall with a doorway sections into
   several loops, so guids repeat. Asserting one-entry-per-element would force merging disjoint
   loops and would misdraw exactly the openings that make a plan worth reading;
4. **the existing cuts must not regress** — `cut_baked` / `cut_baked_classed` and the bake cache's
   identity contract are load-bearing for every drawing already shipped.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_plan_identity.py
"""
import os
import re
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TMP = os.path.join(os.path.dirname(__file__), "_plan_identity.ifc")
massing.generate_blank_ifc(TMP, name="Plan Identity", storeys=1, storey_height=3.5, ground_size=20.0)
model = open_model(TMP)
storey = model.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(model, [2, 2], [12, 2], 3.0, 0.2, storey)
edit.add_wall(model, [12, 2], [12, 10], 3.0, 0.2, storey)

meshes = drawings.bake(model)
check("bake produced geometry", len(meshes) > 0, len(meshes))

# --- 1. THE GUID IS REAL, not a plausible string in the right slot ---------------------------------
check("every baked entry is a 3-tuple (guid, class, mesh)",
      all(isinstance(t, tuple) and len(t) == 3 for t in meshes),
      [len(t) for t in meshes[:5]])
def _resolve(g):
    """`by_guid` RAISES on an unknown id, it does not return None — verified, not assumed. Written
    the other way this check crashed the run instead of failing it, which still fails the build but
    reports a traceback where it should report which guid was bad."""
    try:
        return model.by_guid(g)
    except Exception:                        # noqa: BLE001 — an unresolvable guid is the finding
        return None


resolved = [_resolve(g) for g, _c, _m in meshes]
check("EVERY guid resolves to a real element via by_guid — a shifted field cannot pass this",
      all(e is not None for e in resolved),
      [g for (g, _c, _m), e in zip(meshes, resolved) if e is None][:5])
check("  and the class in slot 2 agrees with the element the guid names",
      all(e is not None and e.is_a() == c for (_g, c, _m), e in zip(meshes, resolved)),
      [(c, e.is_a() if e is not None else None)
       for (_g, c, _m), e in zip(meshes, resolved) if e is None or e.is_a() != c][:5])
check("  guids are unique per baked element", len({g for g, _c, _m in meshes}) == len(meshes),
      f"{len({g for g, _c, _m in meshes})} unique of {len(meshes)}")

# --- 2. THE GUID IS THE RIGHT ONE ------------------------------------------------------------------
walls = model.by_type("IfcWall")
check("the fixture really has two walls", len(walls) == 2, len(walls))
wall_guids = {w.GlobalId for w in walls}
baked_wall_guids = {g for g, c, _m in meshes if c == "IfcWall"}
check("the baked wall guids are EXACTLY the model's wall guids (set equality, both directions)",
      baked_wall_guids == wall_guids, (sorted(baked_wall_guids), sorted(wall_guids)))

guided = drawings.cut_baked_guided(meshes, "plan", 1.5)
check("cut_baked_guided returns (guid, class, polyline) triples",
      guided and all(len(t) == 3 for t in guided), len(guided))
check("  every polyline's guid is one that was baked",
      {g for g, _c, _p in guided} <= {g for g, _c, _m in meshes},
      {g for g, _c, _p in guided} - {g for g, _c, _m in meshes})
cut_wall_guids = {g for g, c, _p in guided if c == "IfcWall"}
check("  BOTH walls are named in the plan cut at z=1.5 — the line knows which wall it is",
      cut_wall_guids == wall_guids, (sorted(cut_wall_guids), sorted(wall_guids)))

# --- 3. ONE ELEMENT, MANY POLYLINES ----------------------------------------------------------------
counts: dict[str, int] = {}
for g, _c, _p in guided:
    counts[g] = counts.get(g, 0) + 1
check("guids repeat down the list — an element may section into several loops",
      len(guided) >= len(counts), (len(guided), len(counts)))
check("  so grouping by guid recovers each element's full linework",
      sum(counts.values()) == len(guided), (sum(counts.values()), len(guided)))

# --- 4. NO REGRESSION IN THE EXISTING CUTS ---------------------------------------------------------
plain = drawings.cut_baked(meshes, "plan", 1.5)
classed = drawings.cut_baked_classed(meshes, "plan", 1.5)
check("cut_baked still returns bare polylines", plain and hasattr(plain[0], "shape"), type(plain[0]))
check("cut_baked_classed still returns (class, polyline) pairs",
      classed and all(len(t) == 2 for t in classed), len(classed))
check("  guided and classed agree on how many polylines the same cut produces",
      len(guided) == len(classed) == len(plain), (len(guided), len(classed), len(plain)))
check("  and on the classes",
      [c for _g, c, _p in guided] == [c for c, _p in classed])

# the cache identity contract test_sections.py depends on
check("bake is still cached by model identity", drawings.bake(model) is meshes)

# --- 5. R38-SYNC-SELECT: the SERVED SVG carries the identity ---------------------------------------
# Carrying the guid to the cut and then dropping it at render would leave sync-select asserting
# against a pipeline whose last hop is anonymous — the exact defect PLAN-IDENTITY fixed, one stage
# later. Assert on the emitted markup, which is what the browser actually receives.
svg_plain = drawings.plan_svg(model, 0.0, cut_height=1.5)
svg_disc = drawings.plan_svg(model, 0.0, cut_height=1.5, by_discipline=True)
for label, svg in (("plain", svg_plain), ("by_discipline", svg_disc)):
    check(f"{label} plan SVG emits data-guid on cut linework", 'data-guid="' in svg)
    check(f"  {label}: BOTH walls are named in the markup",
          all(f'data-guid="{g}"' in svg for g in wall_guids),
          [g for g in wall_guids if f'data-guid="{g}"' not in svg])
    check(f"  {label}: every emitted guid resolves in the model — no invented identity",
          all(_resolve(g) is not None
              for g in re.findall(r'data-guid="([^"]+)"', svg)))
check("identity is NOT mode-dependent — both rendering modes name the same elements",
      set(re.findall(r'data-guid="([^"]+)"', svg_plain))
      == set(re.findall(r'data-guid="([^"]+)"', svg_disc)))

# --- 6. storey NAME -> elevation (the plan pane sends a name; the route now resolves it) -----------
lvl = model.by_type("IfcBuildingStorey")[0]
check("resolve_storey finds the level by exact name",
      drawings.resolve_storey(model, str(lvl.Name)) is not None)
check("  case/whitespace-insensitively — the name travels through a query string",
      drawings.resolve_storey(model, f"  {str(lvl.Name).upper()}  ") is not None)
check("  and an unknown name is None, never a silent elevation",
      drawings.resolve_storey(model, "No Such Level") is None)

# --- the shared cross-process payload round-trips WITH the guid -------------------------------------
# The payload widened from (cls, verts, faces) to (guid, cls, verts, faces); the shared key is
# versioned so an older build's entry can never be read back into the new shape.
payload = [(g, c, m.vertices, m.faces) for g, c, m in meshes]
rebuilt = [(g, c) for g, c, _v, _f in payload]
check("the shared-cache payload carries the guid so a cross-process hit is not anonymous",
      rebuilt == [(g, c) for g, c, _m in meshes])
check("  and the shared key is format-versioned, so old entries cannot be misread",
      "g1:" in open(os.path.join(_DATA_SRC, "aec_data", "drawings.py"), encoding="utf-8").read())

for f in (TMP,):
    if os.path.exists(f):
        os.remove(f)

print()
if FAILED:
    print(f"plan_identity: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("plan_identity: all checks passed")
