"""
The sample library.

"Load a sample" used to mean one of three bare `.frag` files — geometry and nothing else, so the
sample demonstrated the viewer and hid every number the platform exists to produce. A `.mass`
container already carries the whole project, so the library is the container we ship, packaged.

Two things are worth asserting and one is worth asserting hard:

- the catalog describes a container from **its own manifest**, so the description cannot drift from
  the contents the way a hand-maintained catalog file would;
- a sample opens through `bundle.import_bundle`, the same path a user's own file takes;
- and an id from a request **never becomes a path**. That last one is why `read()` selects from the
  directory listing instead of joining. The tests below include the traversal strings not because
  they are expected to work, but because a future refactor to `os.path.join(dir, sample_id)` would
  look harmless in review and would be caught here.
"""
import io
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def fresh(d):
    """Re-import against a chosen directory — the catalog memoises deliberately.

    `importlib.reload`, not `sys.modules.pop`: the parent package holds an attribute pointing at the
    old module object, so a plain re-import hands back the stale one and every assertion afterwards
    measures the previous directory.
    """
    import importlib

    os.environ["AEC_SAMPLES_DIR"] = d
    from aec_api import samples
    return importlib.reload(samples)


def write_mass(path, name, tables, with_geometry=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({
            "format": "massing.project", "version": 2,
            "project": {"name": name}, "tables": tables,
        }))
        z.writestr("README.txt", "a self-describing container")
        if with_geometry:
            z.writestr("model.frag", b"\x00" * 64)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())


with tempfile.TemporaryDirectory() as d:
    write_mass(os.path.join(d, "riverside_house.mass"), "Riverside House",
               {"element": 42, "topic": 6, "estimate_line": 118, "module_record": 0})
    write_mass(os.path.join(d, "civic_tower.mass"), "Civic Tower",
               {"element": 3100, "topic": 44})
    # a decoy: not a .mass, must never be listed or served
    with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("not a sample")
    # a .mass that is not a zip — the library must survive one broken file
    with open(os.path.join(d, "corrupt.mass"), "wb") as fh:
        fh.write(b"this is not a zip")

    s = fresh(d)
    cat = s.catalog()
    by_id = {c["id"]: c for c in cat}

    check("the library lists only .mass files", set(by_id) ==
          {"riverside_house.mass", "civic_tower.mass", "corrupt.mass"},
          f"got {sorted(by_id)}")
    check("a non-.mass file is not a sample", "notes.txt" not in by_id)

    house = by_id["riverside_house.mass"]
    check("the name comes from the manifest, not the filename", house["name"] == "Riverside House",
          f"got {house['name']!r} — a filename-derived name drifts the moment a file is renamed")
    check("the container is readable", house["readable"] is True)
    check("row counts are reported", house["elements"] == 42, f"got {house['elements']}")
    check("empty tables are omitted from contents", "module_record" not in house["contents"],
          "listing a table with 0 rows makes an empty sample look populated")
    check("a populated table survives", house["contents"].get("estimate_line") == 118)
    check("geometry is detected", house["has_geometry"] is True)
    check("size is reported", house["bytes"] > 0)

    # --- one broken file must not take the library down --------------------------------------------
    bad = by_id["corrupt.mass"]
    check("a corrupt container is still listed", bad["id"] == "corrupt.mass")
    check("...but is honestly marked unreadable", bad["readable"] is False,
          "silently hiding it would make a packaging mistake invisible")
    check("...and claims no contents", bad["contents"] == {} and bad["elements"] == 0)

    # --- reading -----------------------------------------------------------------------------------
    data = s.read("riverside_house.mass")
    check("a sample's bytes come back", data is not None and data.startswith(b"PK"))
    check("...and are a real zip", zipfile.ZipFile(io.BytesIO(data)).namelist() != [])

    # --- the id is never a path ---------------------------------------------------------------------
    # Each of these would resolve to something real under os.path.join(dir, id). Under enumeration
    # they are simply absent from the listing, so there is nothing to escape.
    for probe in ("../notes.txt", "..\\notes.txt", "../../etc/passwd",
                  os.path.join(d, "notes.txt"), "/etc/passwd", "notes.txt",
                  "riverside_house.mass/../notes.txt", ""):
        check(f"a traversal id resolves to nothing: {probe!r}", s.read(probe) is None)

    check("an unknown id is a clean miss, not an error", s.read("nope.mass") is None)

    # --- the SHAPE, not just the behaviour ------------------------------------------------------
    # v0.3.744 checked membership and then opened `os.path.join(samples_dir(), sample_id)`. Every
    # behavioural test above passed, because the membership check does make it safe. CodeQL flagged
    # it anyway (`py/path-injection`) and was right to: dataflow cannot see a guard several lines
    # away, and neither can the next person to edit this. Safety that lives in a check somewhere
    # else is safety a later edit can remove without noticing.
    #
    # So assert the shape. `read()` must select a path the filesystem produced, never compose one
    # from the argument — if this ever fails, the behavioural tests will still be green and the
    # regression will be invisible without it.
    # Parsed with `ast`, not grepped. The first version of this check stripped lines by prefix and
    # then searched the whole source — which flagged the *docstring*, where `os.path.join` appears
    # while explaining why it is no longer used. A shape test that reads prose measures prose.
    import ast
    import inspect

    fn = ast.parse(inspect.getsource(s.read).lstrip()).body[0]
    stmts = fn.body[1:] if (isinstance(fn.body[0], ast.Expr)
                            and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    code = "\n".join(ast.dump(st) for st in stmts)
    check("read() does not join caller input onto a root", "'join'" not in code,
          "a guard the scanner cannot see is a guard the next editor cannot see either")
    check("read() selects from the listing instead", "_entry_paths" in code)

    # --- the catalog re-reads when the library changes ----------------------------------------------
    write_mass(os.path.join(d, "third.mass"), "Third", {"element": 1})
    check("a newly packaged sample appears without a restart",
          any(c["id"] == "third.mass" for c in s.catalog()),
          "a cache keyed on the directory alone would miss this on Windows")

# --- an absent library is a valid state, not a failure ----------------------------------------------
s = fresh(os.path.join(tempfile.gettempdir(), "definitely-not-a-samples-dir-92f1"))
check("a missing library lists empty rather than raising", s.catalog() == [])
check("...and reading from it is a clean miss", s.read("anything.mass") is None)

os.environ.pop("AEC_SAMPLES_DIR", None)

# --- the DEFAULT directory, which no test had ever exercised ------------------------------------
#
# Every check above sets AEC_SAMPLES_DIR, so `_DEFAULT_DIR` was never measured. It was wrong: four
# `dirname` hops from `services/api/src/aec_api/samples.py` reach `services/`, not the repo root, so
# the default pointed at `<repo>/services/samples` — a directory that has never existed. The library
# returned `[]` with the containers sitting in `<repo>/samples`, and I recorded that empty list as
# correct behaviour.
#
# The lesson generalises past this bug: a test that configures the thing it is testing never tests
# the configuration's default, and defaults are what actually ship.
import os.path as _p  # noqa: E402

from aec_api import samples as _s  # noqa: E402

_root = _s._REPO_ROOT
check("the repo root is the repo root", _p.isdir(_p.join(_root, "services")) and _p.isdir(_p.join(_root, "apps")),
      f"got {_root!r} — must contain services/ and apps/")
check("the default library is <repo>/samples", _p.basename(_s._DEFAULT_DIR) == "samples"
      and _p.dirname(_s._DEFAULT_DIR) == _root, f"got {_s._DEFAULT_DIR!r}")
check("...and it is NOT services/samples", "services" not in _p.relpath(_s._DEFAULT_DIR, _root),
      "four dirname hops instead of five is exactly the bug this guards")
check("the shipped library directory exists on disk", _p.isdir(_s._DEFAULT_DIR),
      "samples/ is committed; if this fails the default has drifted again")

# --- the routes are actually reachable ---------------------------------------------------------
#
# Not optional. Seven engines once shipped here with no route to them, because every gate measured
# the module and none measured the path to it.
#
# It must be checked through a STARTED app. This codebase includes routers lazily — until the
# lifespan runs, `app.router.routes` holds 55 `_IncludedRouter` placeholders with no `.path`, so
# inspecting routes at import time reports every endpoint in the product as missing. I read exactly
# that and spent a while concluding the router was unwired before noticing the app had never been
# started. `TestClient` as a context manager runs the lifespan; a bare `TestClient(app)` does not.
import warnings  # noqa: E402

warnings.simplefilter("ignore")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as _c:
    r = _c.get("/samples")
    check("GET /samples is routed", r.status_code == 200, f"got {r.status_code}")
    check("...and returns a list", isinstance(r.json().get("samples"), list))

    r = _c.post("/samples/nope.mass/open")
    check("an unknown sample is 404, not 500", r.status_code == 404, f"got {r.status_code}")

    for probe in ("..%2F..%2Fetc%2Fpasswd", "..%5C..%5Cwindows%5Cwin.ini"):
        r = _c.post(f"/samples/{probe}/open")
        check(f"a traversal id is refused over HTTP: {probe}", r.status_code == 404,
              f"got {r.status_code}")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_samples OK")
