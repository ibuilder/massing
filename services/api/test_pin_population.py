"""PIN-POPULATION — the pin engine reads every register the product calls pinnable.

`pins.spatial_modules()` decides which registers `resolve_pins` looks in, and `resolve_pins` is what
`GET /projects/{pid}/pins/all` returns and what `routers/drawings._plan_pins` prints on a plan sheet.
**A predicate that decides what to LOOK at hides its own misses**, so this file asks the two
questions that predicate cannot ask about itself:

1. does every name it produces resolve to a register that exists, and
2. does it reach every register the product marks `pinnable`?

### What it would have caught

`SPATIAL_MODULES` was a hand-written tuple of eleven names. **Six named nothing** -- `clash`,
`defect`, `snag`, `quality_issue`, `safety_observation`, `field_report` are the *words* for those
ideas, not module keys; the registers holding those records are `coordination_issue`, `ncr`,
`deficiency` and `incident`. So the engine reached five registers out of thirty-seven, and the
headline case in `pins.py`'s own module docstring -- a clash bound to a wall -- was one of the misses,
because every imported clash becomes a `coordination_issue` (see `clash_intel.py`).

Nothing went red. `test_pins_unified` asserted `"rfi" in SPATIAL_MODULES` and
`"submittal" not in SPATIAL_MODULES`: one hand-written list checked against a hand-written
expectation, which cannot see a name that matches nothing on either side. `test_pin_empty` compared
the migration's list to the same tuple and agreed, because both copies carried the same six ghosts.
**Two green gates, both measuring list-against-list.**

### The behavioural half is not optional

Asserting the derivation's *output* is the same mistake one layer up: a `spatial_modules()` that
returned every key in the registry would satisfy every set assertion here and still return no pins,
because `_record_tables` intersects it with `TABLES`. So this also drives real records through
`resolve_pins` and asserts the engine SEES them -- including a `coordination_issue`, the exact
register the old list missed.

Run: `PYTHONPATH=src:../data/src python test_pin_population.py`
"""
from __future__ import annotations

import os
import sys
import tempfile

# **Assignment, not `setdefault`** — the rule `test_db_url_isolation.py` exists to enforce. This file
# boots the app through `TestClient`, whose lifespan calls `create_all`, so a `setdefault` that
# yielded to an exported `DATABASE_URL` would build this schema in whatever database that names.
# That gate cannot currently see this file (it looks for a literal `create_all`, and a lifespan boot
# has none) — which is DB-URL-BOOT in the roadmap, not a licence to be the offender it would catch.
_d = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_d}/pinpop.db"
os.environ["STORAGE_DIR"] = _d

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    # Detail prints on FAILURE only. The sibling pin tests print it either way, and a passing line
    # that ends in "— the record showed in no surface at all" reads exactly like a failure.
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(f"{label} — {detail}" if detail else label)


from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_registry  # noqa: E402
from aec_api import pins as pin_engine  # noqa: E402
from aec_api.main import app  # noqa: E402

modules_registry.load_registry()
REGISTRY = modules_registry.REGISTRY
POP = pin_engine.spatial_modules()

# --- 1. every name resolves to a register that exists ------------------------------------------
# This is the assertion whose absence cost six registers. It is cheap, and it is the only one that
# can see a name that is a WORD rather than a key.
ghosts = [k for k in POP if k not in REGISTRY]
check("every name the pin engine produces is a real module",
      not ghosts,
      f"names nothing: {ghosts} — a key that matches no module silently contributes no pins")

# --- 2. it reaches every register the product marks pinnable -------------------------------------
# `pinnable` is the flag `module.json` declares. Three other readers already honour it:
# `modules.project_pins` (what `GET /module-pins` draws in the 3D viewer), `traceability.for_element`
# and the reverse deep-link in `routers/cost.py`. A fourth answer to the same question is how the
# sheet and the viewer came to disagree.
declared = {k for k, m in REGISTRY.items() if m.get("pinnable")}
check("the registry declares a non-trivial pinnable set",
      len(declared) > 10,
      f"only {len(declared)} pinnable modules — every set comparison below would be near-vacuous")
check("the pin engine reads every pinnable register",
      set(POP) == declared,
      f"pinnable but unread: {sorted(declared - set(POP))}; "
      f"read but not pinnable: {sorted(set(POP) - declared)}")

# --- 3. the derivation is DERIVED, not a list that happens to agree today -------------------------
# Flipping one module's flag must move the population. Without this, a re-hardcoded tuple that
# matches the registry on the day it is written passes everything above.
#
# **The precondition is load-bearing, and its absence was caught by mutation.** The first draft took
# `sorted(declared)[0]` and asserted only that the probe was ABSENT after the flip. Against the old
# hard-coded tuple that probe (`asi`) was absent to begin with, so the assertion passed while
# measuring nothing -- a vacuous pass in the one check whose whole job is to prove the population is
# read rather than written down. Assert presence first; only then does absence mean anything.
_probe = sorted(set(declared) & set(POP))[0] if set(declared) & set(POP) else None
check("a probe module exists in both the registry and the population",
      _probe is not None,
      "nothing to flip — the derivation check below would be vacuous")
if _probe is not None:
    _saved = REGISTRY[_probe].get("pinnable")
    check(f"the probe {_probe!r} is in the population BEFORE the flip",
          _probe in pin_engine.spatial_modules(),
          "without this, 'absent after the flip' is satisfied by never having been there")
    try:
        REGISTRY[_probe]["pinnable"] = False
        check("turning a module's pinnable flag off removes it from the population",
              _probe not in pin_engine.spatial_modules(),
              f"{_probe!r} survived — the population is not actually read from the registry")
    finally:
        REGISTRY[_probe]["pinnable"] = _saved
    check("...and restoring the flag restores the whole population",
          set(pin_engine.spatial_modules()) == set(POP),
          "the probe left the registry mutated, so every assertion after this one is suspect")

# --- 4. THE BEHAVIOURAL HALF: records the old list missed reach the engine ------------------------
# A set assertion cannot tell a population that is right from one that is right and unreachable:
# `_record_tables` intersects the population with `TABLES`, so a name present in both the registry
# and the tuple and absent from `TABLES` still yields nothing. Drive real records through.
GUID = "1WrzGm1SD2ev45B_OWQ39B"

#: One register the old tuple reached, and four it did not. `coordination_issue` is the one that
#: matters most: `clash_intel` creates every imported clash as one, and the old tuple said "clash".
PROBE = ("rfi", "coordination_issue", "ncr", "deficiency", "incident")
OLD_TUPLE = ("rfi", "punchlist", "observation", "clash", "inspection", "snag", "defect",
             "safety_observation", "quality_issue", "field_report", "photo")


def _payload(key: str) -> dict:
    """A record valid for this module's required fields, tied to one element by GlobalId."""
    data: dict = {}
    for f in REGISTRY[key].get("fields", []):
        if not f.get("required"):
            continue
        t = f.get("type")
        if t in ("number", "currency", "integer", "percent"):
            data[f["name"]] = 1
        elif t == "date":
            data[f["name"]] = "2026-01-01"
        elif t == "bool":
            data[f["name"]] = True
        elif t == "enum":
            data[f["name"]] = (f.get("options") or ["x"])[0]
        else:
            data[f["name"]] = "x"
    return {"title": f"{key} on the wall", "element_guids": [GUID], "data": data}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "PIN-POPULATION"}).json()["id"]
    created = {}
    for key in PROBE:
        r = c.post(f"/projects/{pid}/modules/{key}", json=_payload(key))
        created[key] = r.status_code
    check("every probe record was created",
          all(s in (200, 201) for s in created.values()),
          f"{created} — a probe that fails to save proves nothing about the engine")

    # The route is exercised so the wiring is proven, but its `pins` list holds only the LOCATED
    # ones and no IFC model is loaded here — so the SOURCES are read from the engine envelope the
    # route derives from. Asserting on the route's list alone would be asserting that
    # `located()` filters, which is a different question and already has its own test.
    env = c.get(f"/projects/{pid}/pins/all")
    check("the route the viewer and the sheet share responds", env.status_code == 200,
          f"{env.status_code}: {env.text[:200]}")

    from aec_api.db import SessionLocal  # noqa: E402

    with SessionLocal() as db:
        raw = pin_engine.resolve_pins(db, pid)
    seen = {p["source"] for p in raw["pins"]}

    check("an RFI tied to a wall is a pin (the case that already worked)", "rfi" in seen)
    check("a coordination issue tied to a wall is a pin",
          "coordination_issue" in seen,
          "every imported clash becomes one of these; the old tuple said 'clash', which is a "
          "Topic.type, not a module key")
    for key in ("ncr", "deficiency", "incident"):
        check(f"a {key} tied to a wall is a pin", key in seen,
              f"{key} is pinnable and was unreachable — the record showed in no surface at all")

    check("the engine now sees every probe record",
          seen >= set(PROBE),
          f"missing: {sorted(set(PROBE) - seen)}")

    # The honest negative: a record with no anchor and no element GUID is an issue, not a pin.
    r = c.post(f"/projects/{pid}/modules/rfi", json={**_payload("rfi"), "element_guids": []})
    check("an unattached record was created for the negative case", r.status_code in (200, 201))
    with SessionLocal() as db:
        raw2 = pin_engine.resolve_pins(db, pid)
    check("an RFI attached to nothing is NOT a pin",
          len(raw2["pins"]) == len(raw["pins"]),
          f"{len(raw2['pins'])} vs {len(raw['pins'])} — widening the population must not turn "
          f"every register row into a pin")

# --- 5. the six ghosts, recorded so the correction cannot be undone quietly ------------------------
_ghosts_then = sorted(k for k in OLD_TUPLE if k not in REGISTRY)
check("the six names the old tuple invented are still not modules",
      _ghosts_then == ["clash", "defect", "field_report", "quality_issue", "safety_observation",
                       "snag"],
      f"{_ghosts_then} — if one of these becomes a real module the record above needs rewriting, "
      f"not silently agreeing")

if FAILED:
    print("FAIL test_pin_population")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_pin_population OK  ({len(POP)} pinnable registers read, was 5 of 11 names of which 6 "
      f"were not modules; {len(PROBE)} registers driven through the engine end-to-end)")
