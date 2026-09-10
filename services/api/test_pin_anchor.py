"""PIN-ANCHOR — `/pins/all` is the union of both ways a record reaches the model.

There are two ways a register record gets onto the model, and until this change the two readers each
saw exactly one of them:

* `pins.resolve_pins` -- `GET /projects/{pid}/pins/all`, and what `routers/drawings._plan_pins`
  prints on a plan sheet -- selected register rows with `element_guids IS NOT NULL`;
* `modules.project_pins` -- `GET /projects/{pid}/module-pins`, what the 3D viewer overlay draws --
  selects them with `anchor IS NOT NULL`.

**Neither was the union its own route docstring promised.** A record somebody PLACED at a point, with
no element tied to it, was drawn in the viewer and absent from the sheet; a record tied to a wall with
no stored point was on the sheet and absent from the viewer. One issue, two surfaces, two different
answers -- which is exactly what `routers/drawings.py` claims cannot happen.

`pins.pin_fields` was already ONE definition of the exact test, called by both of `resolve_pins`'s
loops. Its SQL counterpart was not: the topic loop asked for `anchor IS NOT NULL OR element_guids IS
NOT NULL` and the register loop asked for half of that. **The half that was shared is the half that
stayed right.** So the SQL half is now `pins.pin_where`, called by both.

### What this asserts, and why each half is here

1. **Behaviour, over all four row shapes.** anchored / attached / both / neither. The anchored-only
   row is the one that was invisible, and it must come back PLACED -- with the coordinates it was
   stored with -- not merely counted.
2. **The superset claim itself, over the whole pinnable population.** Every pin `project_pins`
   returns must appear in `resolve_pins`. That is the claim the roadmap makes and the reason the
   viewer could ever stop calling two routes; asserting it on one register would prove it for one
   register.
3. **The empty-value source.** `POST` with `anchor: {}` used to store `{}`, which is non-NULL: a pin
   CANDIDATE that fails the exact test, so `pin_total` overstates and the sheet prints `~`. Before
   PIN-ANCHOR that cost nothing on a register, because no reader that reported a total looked at a
   register's anchor. Now one does.
4. **That "absent" is stored as absent at all.** SQLAlchemy persists a Python `None` in a `JSON`
   column as the JSON scalar `null`, which is NOT SQL NULL — so `anchor IS NOT NULL` matched every
   row ever written and the SQL half of BOTH predicates selected the whole register.

### The gate could not detect its own defect, and only mutation found that out

Restoring `element_guids.isnot(None)` on the register loop changed nothing here. Removing the anchor
arm from `pin_where` changed nothing here. **Both mutations passed** — the anchored-only record still
came back placed — because point 4 above made the broken and the fixed predicate select the same
rows, and `pin_fields` then sorted it out in Python either way. The behavioural assertions were
correct and were measuring a defect that a third one underneath had made invisible.

That is why the checks at the dialect level are here (`typeof(anchor)`, `IS NULL`, and a candidate
count compared against the register's row count) rather than only through readers that decode a
stored `null` back to `None` before anyone can see it. **A predicate that admits everything looks
exactly like one that works**, from every angle except the one that counts rows.

Run: `PYTHONPATH=src:../data/src python test_pin_anchor.py`
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

# **Assignment, not `setdefault`** — see `test_db_url_isolation.py`. This file boots the app through
# `TestClient`, whose lifespan calls `create_all`.
_d = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_d}/pinanchor.db"
os.environ["STORAGE_DIR"] = _d

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(f"{label} — {detail}" if detail else label)


import sqlalchemy as sa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules as mod_engine  # noqa: E402
from aec_api import modules_registry  # noqa: E402
from aec_api import pins as pin_engine  # noqa: E402
from aec_api.main import app  # noqa: E402

modules_registry.load_registry()
REGISTRY = modules_registry.REGISTRY
POP = pin_engine.spatial_modules()
check("the pinnable population loaded", len(POP) > 10,
      f"only {len(POP)} pinnable registers — every assertion below would be near-vacuous")

#: A well-formed IFC GlobalId. Elements are referenced by GlobalId, never by a viewer id.
GUID = "1WrzGm1SD2ev45B_OWQ39B"
#: Where the anchored-only record was PLACED. Non-zero on every axis so a coordinate that is dropped,
#: zeroed or transposed shows up as a wrong number rather than as a plausible one.
POINT = {"x": 11.5, "y": -3.25, "z": 7.75}

PROBE = "coordination_issue"      # every imported clash becomes one of these; see `clash_intel.py`


def _payload(key: str) -> dict:
    """A record valid for this module's required fields."""
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
    return {"data": data}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "PIN-ANCHOR"}).json()["id"]

    # --- 1. all four row shapes, through the real route -------------------------------------------
    SHAPES = {
        "anchored":  {"anchor": POINT},                                  # THE CASE THAT WAS INVISIBLE
        "attached":  {"element_guids": [GUID]},
        "both":      {"anchor": POINT, "element_guids": [GUID]},
        "neither":   {},                                                 # a record, not a pin
    }
    made: dict[str, dict] = {}
    for name, extra in SHAPES.items():
        r = c.post(f"/projects/{pid}/modules/{PROBE}", json={**_payload(PROBE), "title": name, **extra})
        check(f"the {name!r} record was created", r.status_code in (200, 201),
              f"{r.status_code}: {r.text[:200]}")
        if r.status_code in (200, 201):
            made[name] = r.json()

    from aec_api.db import SessionLocal  # noqa: E402

    with SessionLocal() as db:
        env = pin_engine.resolve_pins(db, pid)
    by_id = {p["id"]: p for p in env["pins"]}

    check("THE ANCHORED-ONLY RECORD IS A PIN — this is the case that reached no sheet at all",
          made["anchored"]["id"] in by_id,
          "a register row with a stored anchor and no element was invisible to `/pins/all`, so a "
          "record the viewer drew did not exist on the printed plan")
    _a = by_id.get(made["anchored"]["id"], {})
    check("...and it comes back PLACED, at the point it was stored with",
          (_a.get("x"), _a.get("y"), _a.get("z")) == (POINT["x"], POINT["y"], POINT["z"]),
          f"got ({_a.get('x')!r}, {_a.get('y')!r}, {_a.get('z')!r}), expected {POINT} — counting a "
          "pin without placing it draws nothing")
    check("...and carries no element_guid, because it has none",
          _a.get("element_guid") is None, f"element_guid={_a.get('element_guid')!r}")

    check("the attached-only record is still a pin (the case that already worked)",
          made["attached"]["id"] in by_id)
    _t = by_id.get(made["attached"]["id"], {})
    check("...and reports itself unplaced rather than pretending, with no model loaded",
          _t.get("x") is None and _t.get("element_guid") == GUID,
          f"x={_t.get('x')!r} element_guid={_t.get('element_guid')!r} — a pin that cannot be located "
          "must say so; silence is the failure mode")

    _b = by_id.get(made["both"]["id"], {})
    check("a record with BOTH is placed by its anchor", made["both"]["id"] in by_id)
    check("...at the anchor, not at the element", (_b.get("x"), _b.get("y")) == (POINT["x"], POINT["y"]),
          f"got ({_b.get('x')!r}, {_b.get('y')!r}) — an explicit placement outranks a derived one")
    check("...and KEEPS the element tie, so the deep-link still works",
          _b.get("element_guid") == GUID, f"element_guid={_b.get('element_guid')!r}")

    check("THE HONEST NEGATIVE — a record with neither is not a pin",
          made["neither"]["id"] not in by_id,
          "widening the predicate must not turn every register row into a pin")
    check("...and the total counts three, not four", env["pin_total"] == 3,
          f"pin_total={env['pin_total']}, pins={len(env['pins'])}")
    BASE_PINS = 3

    # --- 1b. A PARTIAL ANCHOR IS NOT A PLACEMENT, AND MUST NOT BLOCK THE ELEMENT ------------------
    # Nothing validates an anchor's shape on the way in: `create_record` stores `body.get("anchor")`
    # as given. `{"x": 1}` used to take the placement branch — returning `y=None, z=None`, which
    # `located()` rejects — AND keep the row out of `need`, so the model could not place it either.
    # A half-written coordinate made a pin permanently unplaceable while the element beside it would
    # have resolved fine. Found by review of PR #503; `pins.anchor_point` is the fix.
    PARTIAL = {
        "part-xy":   {"x": 1.0, "y": 2.0},          # z missing
        "part-x":    {"x": 1.0},
        "no-coords": {"note": "somewhere"},          # a dict, but not a position
        "bool-x":    {"x": True, "y": 2.0, "z": 3.0},   # bool is an int subclass; not a coordinate
        "str-x":     {"x": "1.0", "y": 2.0, "z": 3.0},  # a string is not a number
    }
    partial_ids = {}
    for name, bad in PARTIAL.items():
        r = c.post(f"/projects/{pid}/modules/{PROBE}",
                   json={**_payload(PROBE), "title": name, "anchor": bad, "element_guids": [GUID]})
        check(f"the {name!r} record was created", r.status_code in (200, 201),
              f"{r.status_code}: {r.text[:160]}")
        if r.status_code in (200, 201):
            partial_ids[name] = r.json()["id"]
    with SessionLocal() as db:
        env_p = pin_engine.resolve_pins(db, pid)
    by_p = {p["id"]: p for p in env_p["pins"]}
    for name, rid in partial_ids.items():
        pin = by_p.get(rid)
        check(f"{name}: still counts as a pin (it IS attached)", pin is not None,
              "a partial anchor is a malformed placement, not an absent one — the row is still a pin")
        if pin:
            check(f"{name}: is NOT placed from the broken anchor",
                  pin.get("x") is None and pin.get("y") is None and pin.get("z") is None,
                  f"got ({pin.get('x')!r}, {pin.get('y')!r}, {pin.get('z')!r}) — a partial anchor "
                  f"reported as a position puts a marker at a coordinate nobody chose")
            check(f"{name}: KEEPS its element, so the model can still place it",
                  pin.get("element_guid") == GUID,
                  f"element_guid={pin.get('element_guid')!r} — this is the half that was lost: the "
                  f"anchor branch dropped the row from `need` and nothing could resolve it")
    # The exact test still calls these pins, and `anchor_point` is what refuses to place them —
    # asserted directly so the two questions cannot be re-merged by accident.
    check("pin_fields still calls a partial anchor a pin",
          pin_engine.pin_fields({"x": 1.0}, [])[0] == {"x": 1.0},
          "being a pin and being placeable are different questions")
    check("...while anchor_point refuses to place it", pin_engine.anchor_point({"x": 1.0}) is None)
    check("A ZERO ANCHOR STILL PLACES — {x:0,y:0,z:0} is the project origin",
          pin_engine.anchor_point({"x": 0, "y": 0, "z": 0}) == (0.0, 0.0, 0.0),
          "testing truthiness instead of presence deletes every pin at the origin")
    check("...and a complete anchor places", pin_engine.anchor_point(POINT) ==
          (POINT["x"], POINT["y"], POINT["z"]))
    check("...and a non-dict places nothing", pin_engine.anchor_point(["x"]) is None
          and pin_engine.anchor_point(None) is None)

    # --- 2. the empty-value source, which is where `{}` came from ---------------------------------
    # A `{}` anchor is non-NULL: it passes the SQL candidate predicate and fails the exact test, so
    # it inflates `pin_total`. `e4a7c2b81f60` backfilled those rows on the premise that both writers
    # in `modules.py` had been normalised. `create_record` had NOT been -- measured here, not assumed.
    r = c.post(f"/projects/{pid}/modules/{PROBE}",
               json={**_payload(PROBE), "title": "empty", "anchor": {}, "element_guids": []})
    check("a record with empty pin values was created", r.status_code in (200, 201),
          f"{r.status_code}: {r.text[:200]}")
    _t_probe = mod_engine.TABLES[PROBE]
    with SessionLocal() as db:
        _row = db.execute(sa.select(_t_probe.c.anchor, _t_probe.c.element_guids)
                          .where(_t_probe.c.id == r.json()["id"])).one()
    check("AN EMPTY ANCHOR IS NORMALISED TO NULL AT THE WRITE SITE",
          _row.anchor is None,
          f"stored {_row.anchor!r} — `{{}}` is non-NULL, so it is a pin CANDIDATE that fails the "
          "exact test: `pin_total` overstates for as long as the row exists, and a backfill behind "
          "a source that still writes them is not a backfill")
    check("...and so is an empty element_guids list", _row.element_guids is None,
          f"stored {_row.element_guids!r}")
    with SessionLocal() as db:
        env2 = pin_engine.resolve_pins(db, pid)
    _expected = BASE_PINS + len(partial_ids)
    check("...so the empty record is neither a pin nor a candidate",
          env2["pin_total"] == _expected and env2["total_counts_candidates"] is False,
          f"pin_total={env2['pin_total']} expected={_expected} "
          f"candidates={env2['total_counts_candidates']}")

    # --- 2b. ABSENT MUST BE STORED AS ABSENT, or the SQL half of the predicate is decoration ------
    # SQLAlchemy persists a Python `None` in a `JSON` column as the JSON scalar `null`, which is NOT
    # SQL NULL. With the default, `anchor IS NOT NULL` was TRUE for every register row ever written,
    # on every dialect — so `pin_where`'s SQL half selected the whole table as pin candidates,
    # `resolve_pins` spent its 2,000-row budget on ordinary records, and `pin_total` counted them.
    # Nothing was ever WRONG, because `pin_fields` rejects a decoded `None` in Python; the pin SET
    # was right and the cap and the count were not. **A predicate that admits everything looks
    # exactly like one that works** — which is why this is asserted at the dialect level, on the
    # stored value, rather than through any reader that would decode it back to None first.
    _plain = c.post(f"/projects/{pid}/modules/{PROBE}", json={**_payload(PROBE), "title": "plain"})
    check("a record with no pin values at all was created", _plain.status_code in (200, 201),
          f"{_plain.status_code}: {_plain.text[:200]}")
    with SessionLocal() as db:
        _null = db.execute(
            sa.select(_t_probe.c.anchor.is_(None), _t_probe.c.element_guids.is_(None))
            .where(_t_probe.c.id == _plain.json()["id"])).one()
    check("AN ABSENT ANCHOR IS SQL NULL, not the JSON scalar `null`", _null[0] is True,
          "stored as JSON `null`: non-NULL to SQL, so `anchor IS NOT NULL` matches every row and "
          "the SQL half of every pin predicate narrows nothing")
    check("...and so is an absent element_guids", _null[1] is True)

    # The consequence, measured rather than argued: the candidate predicate must SELECT FEWER ROWS
    # than the register holds. This is the assertion the JSON-null defect could not fail.
    with SessionLocal() as db:
        _all = db.execute(sa.select(sa.func.count()).select_from(_t_probe)
                          .where(_t_probe.c.project_id == pid)).scalar()
        _cand = db.execute(
            sa.select(sa.func.count()).select_from(_t_probe)
            .where(*pin_engine.pin_where(_t_probe.c.project_id, _t_probe.c.anchor,
                                         _t_probe.c.element_guids, pid))).scalar()
    check("THE SQL CANDIDATE PREDICATE ACTUALLY NARROWS", _cand < _all,
          f"{_cand} candidates out of {_all} rows — a predicate that admits the whole register "
          f"spends the pin budget on records that are not pins and reports them in `pin_total`")
    check("...to exactly the rows that are pins", _cand == BASE_PINS + len(partial_ids),
          f"{_cand} candidates; the register holds {_all} rows, "
          f"{BASE_PINS + len(partial_ids)} of them pins")

    # --- 3. THE SUPERSET CLAIM, over the whole pinnable population --------------------------------
    # `/pins/all` can only replace the viewer's second call if it returns every record `/module-pins`
    # does. Asserting that on one register would prove it for one register, so every pinnable
    # register gets an anchored row -- written through Core rather than the route, because a module
    # whose required fields this file cannot synthesise would otherwise be dropped from the
    # population silently, and a population predicate that hides its own misses is the defect this
    # whole line of work is about.
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    planted: dict[str, str] = {}
    with SessionLocal() as db:
        for key in POP:
            t = mod_engine.TABLES[key]
            rid = str(uuid.uuid4())
            row = {"id": rid, "project_id": pid, "ref": f"{key.upper()[:3]}-900",
                   "title": f"anchored {key}", "workflow_state": "open",
                   "created_at": now, "modified_at": now,
                   "anchor": POINT, "element_guids": None, "links": [], "data": {}}
            cols = {col.name for col in t.columns}
            db.execute(sa.insert(t).values(**{k: v for k, v in row.items() if k in cols}))
            planted[key] = rid
        db.commit()
        wide = pin_engine.resolve_pins(db, pid)
        viewer = mod_engine.project_pins(db, pid)
    check("every pinnable register took an anchored row", len(planted) == len(POP),
          f"{len(planted)} of {len(POP)}")
    check("the viewer route sees them all", len({p["id"] for p in viewer}) >= len(POP),
          f"`project_pins` returned {len(viewer)} — the superset check below is only meaningful if "
          f"the set it is a superset OF is populated")

    _sheet_ids = {p["id"] for p in wide["pins"]}
    _viewer_ids = {p["id"] for p in viewer}
    _only_viewer = sorted(_viewer_ids - _sheet_ids)
    check("EVERY PIN THE 3D VIEWER DRAWS IS ALSO ON THE SHEET — `/pins/all` is the superset",
          not _only_viewer,
          f"{len(_only_viewer)} record(s) reach `/module-pins` and not `/pins/all`: "
          f"{_only_viewer[:5]} — the two surfaces disagree about the same issue")
    check("...and it is a STRICT superset: the sheet also holds element-tied pins the viewer misses",
          bool(_sheet_ids - _viewer_ids),
          "if these were equal, `/module-pins` would not be the narrower half and the roadmap's "
          "claim that the viewer can drop a call would be about nothing")

    # --- 4. the route the sheet and the viewer share still answers --------------------------------
    resp = c.get(f"/projects/{pid}/pins/all")
    check("the shared route responds", resp.status_code == 200, f"{resp.status_code}: {resp.text[:200]}")
    if resp.status_code == 200:
        body = resp.json()
        # The route renames the engine's `pin_total` to `total` and its `pins` to the LOCATED subset
        # (`shown` is the window before that filter). Read the route's own names, not the engine's:
        # asserting `body["pin_total"]` gets `None`, which compares unequal and looks like a
        # disagreement rather than like a test reading the wrong key.
        check("...and its envelope agrees with the engine it derives from",
              body.get("total") == wide["pin_total"] and body.get("shown") == len(wide["pins"]),
              f"route total={body.get('total')} shown={body.get('shown')}; "
              f"engine pin_total={wide['pin_total']} pins={len(wide['pins'])}")
        # The route already applies `located()`, so `pins` holds only what can be DRAWN. With no IFC
        # model loaded, the anchored ones are the only ones that can be — which is the whole
        # user-visible win: before this change not one anchored register record was among them.
        check("...and the anchored register pins are drawable with no model loaded",
              len(body.get("pins", [])) >= len(POP),
              f"{len(body.get('pins', []))} drawable of {body.get('shown')} — an anchored record "
              f"needs no model to be placed, and before this change none reached the sheet")
        check("...while the element-tied ones are DISCLOSED as unlocated, not dropped",
              body.get("unlocated") == body.get("shown", 0) - len(body.get("pins", []))
              and body.get("unlocated", 0) > 0,
              f"unlocated={body.get('unlocated')} — the attached-only probe has no model to resolve "
              f"against, and a list that silently returns fewer pins than exist is the failure this "
              f"envelope exists to end")
        check("...and the route says no model was available, rather than implying one was",
              body.get("model_available") is False, f"model_available={body.get('model_available')!r}")

if FAILED:
    print("FAIL test_pin_anchor")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_pin_anchor OK  (4 row shapes; {len(POP)} pinnable registers planted with an anchor and "
      f"every one of them reaches both surfaces)")
