"""Every export the tier table SELLS must have something that delivers it.

`licensing.state()` returns every tier's features and the Settings panel renders them as a
plan-comparison table, so a format named in `TIER_FEATURES` is a promise to a paying customer. Two
were promises nothing kept, found 2026-08-29 by checking each declared format for a delivery path
rather than by reading the list:

  * **`nwd`** (Enterprise) — Navisworks' document format is a closed Autodesk binary. `routers/convert.py`
    already states the position for its siblings: *".rvt/.dwg/.nwc are closed Autodesk formats with NO
    open-source reader"*. This was not a gap to close; it cannot be written offline at all.
  * **`obj`** (Home) — `viewer/referenceLoader.ts` reads `.obj`. Nothing writes it. **Import is not
    export**, and a tier table that says "exports" is not offering to read the format.

Both were delisted. `png` was kept and is the reason this file checks *delivery* rather than *a route*:
it is genuinely produced, client-side, by the viewer's canvas capture. A rule of "every export needs an
API route" would have deleted a working feature — which is the failure mode of a check whose population
is right and whose property is wrong.

**The check runs against the live FastAPI route table, not against `EXPORT_DELIVERY`.** Asserting that
a registry agrees with the list it was written from is the tautology cut from `test_r37_contract.py`
one release earlier: the derivation reads the same data, so it cannot fail. Resolving each declared
path in `app.routes` is evidence from outside the declaration, and it fails the moment a route is
renamed or removed while the tier table keeps selling it.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

os.environ["DATABASE_URL"] = "sqlite:///./test_export_promises.db"
os.environ["STORAGE_DIR"] = "./test_storage_export_promises"
os.environ["AEC_LOCAL_MODE"] = "1"
for _f in ("./test_export_promises.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import licensing  # noqa: E402
from aec_api.main import app  # noqa: E402

checks = 0


def check(cond, msg):
    """Assert `cond`, counting it, so the summary reports how much was actually verified."""
    global checks
    assert cond, msg
    checks += 1


# The app's own path list — the outside evidence this file is built on. Taken from the OpenAPI
# schema rather than `app.routes`: this FastAPI version keeps included routers nested in
# `_IncludedRouter` wrappers, so `app.routes` reports 74 entries of which only 12 carry a `.path`,
# and a membership test against it would pass vacuously for everything. The schema is also the
# version-independent answer to "what does this service actually serve".
ROUTES = set(app.openapi()["paths"])
check(len(ROUTES) > 200, f"expected a populated path list, got {len(ROUTES)}")

declared = {f for feats in licensing.TIER_FEATURES.values() for f in feats["exports"]}
check(declared, "the tier table must declare some exports, or this file proves nothing")

for fmt in sorted(declared):
    where = licensing.EXPORT_DELIVERY.get(fmt)
    check(where is not None, f"{fmt!r} is sold in the tier table with no recorded delivery path")
    if where == licensing.CLIENT_DELIVERED:
        continue                       # produced in the browser; no route to resolve
    check(where in ROUTES, f"{fmt!r} is sold as {where!r}, which is not a route in this app")

# The registry must not carry entries for formats nobody sells — that is the other direction of the
# same drift, and it is how a delisted format leaves a plausible-looking trace behind.
for fmt in licensing.EXPORT_DELIVERY:
    check(fmt in declared, f"{fmt!r} has a delivery path but no tier sells it — stale registry entry")

# The two delistings, pinned by name so a later edit re-adding them has to confront the reason.
check("nwd" not in declared, "nwd cannot be written without the paid Autodesk SDK — do not re-list it")
check("obj" not in declared, "obj is import-only (viewer/referenceLoader.ts); nothing exports it")
check("png" in declared and licensing.EXPORT_DELIVERY["png"] == licensing.CLIENT_DELIVERED,
      "png is a real export, delivered client-side — the reason this file checks delivery, not routes")

# Every declared export still resolves to a nameable plan, and every boolean entitlement too. This is
# the rendered-message property from test_r37_contract, held over the CHANGED list.
for fmt in sorted(declared):
    check(licensing.min_tier_for_export(fmt) is not None, f"{fmt} names no plan in its 402")

# --- the navisworks entitlement now gates the capability that IS navisworks-specific ---------------
bim_src = (Path(__file__).parent / "src/aec_api/routers/bim.py").read_text()
xml_route = bim_src.split("/coordination/import-xml")[1]
check('licensing.require("navisworks"' in xml_route.split("@router")[0],
      "the native Navisworks XML import must require the navisworks entitlement")
# ...and the tabular sibling stays open: it reads Solibri and any spreadsheet, so it is not the
# Navisworks capability the tier table sells. Gating it would refuse Solibri users an Enterprise plan.
xlsx_route = bim_src.split("/coordination/import-xlsx")[1].split("@router")[0]
check("licensing.require" not in xlsx_route,
      "the generic tabular clash import must NOT be gated on navisworks — it is not Navisworks-only")
check(licensing.TIER_FEATURES["enterprise"]["navisworks"] is True
      and licensing.TIER_FEATURES["commercial"]["navisworks"] is False,
      "navisworks stays an Enterprise differentiator — it is real, it just was not enforced")

print(f"EXPORT-PROMISES OK — {checks} checks. Every format the tier table sells resolves to a real "
      "delivery path, verified against the live route table rather than against the registry that "
      "declares it. nwd (closed Autodesk binary) and obj (import-only) are delisted; png is kept "
      "because it ships client-side. The navisworks entitlement now gates native Navisworks XML "
      "import, and does not gate the generic tabular importer.")
