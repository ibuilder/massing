"""R37-TESTED-UNWIRED CONSOLIDATE — the callers reimplemented the accessors, so the accessors died.

Three functions came back referenced only by the test tree, and the roadmap's reading was that
deleting them would be the wrong move: **the caller had reimplemented each one.** Fixing the caller
removes the duplication *and* the orphan; deleting the function keeps the duplication and loses the
better implementation.

* `ids_authoring.build_from_use_case` / `eir_for_use_case` — `routers/ids.py::_specs_from` looked the
  use case up itself and called the **private** `ia._specs_for`, which is both halves of what those
  two wrappers do.
* `agent_packs.tools_for` — `catalog()` inlined `list(p["tools"])`.

## What reading the code changed about that plan

**The private reach-through had a SECOND caller the roadmap did not name.** `codecheck.py` also
called `ids_authoring._specs_for`, and it passes a group list rather than a use case, so it cannot go
through `specs_for_use_case`. *A private helper with two external callers is not private, it is
undeclared* — so it is now `specs_for_groups`, which is the honest fix rather than routing around it.

**And routing `/ids/eir` through `eir_for_use_case` would have shipped two regressions**, both of
which existed because the twins had drifted apart:

1. it raised a bare `KeyError` for an unknown use case where `build_from_use_case` raises
   `ValueError` — so the route's existing **422 would have become a 500**;
2. it had no `title` parameter, so a caller-supplied title would have been **silently discarded**.

Both are asserted below. *A consolidation that adopts the surviving implementation inherits its
defects too, and they are invisible while nothing calls it* — which is exactly the state R37 found it
in.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_r37_consolidate.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_r37_consolidate.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_r37_consolidate")
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_r37_consolidate.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import agent_packs, ids_authoring as ia  # noqa: E402
from aec_api.main import app  # noqa: E402

HDR = {"X-User": "engineer"}
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


UC = next(iter(ia.USE_CASES))          # any real use case; the catalog is the fixture

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. the two asymmetries that would have regressed
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# `build_from_use_case` has raised ValueError for an unknown case since it was written. Its twin
# raised KeyError, which the route would have turned into a 500 rather than a 422.
for fn, label in ((ia.build_from_use_case, "build_from_use_case"),
                  (ia.eir_for_use_case, "eir_for_use_case")):
    try:
        fn("no-such-use-case")
        check(f"{label} refuses an unknown use case", False, "returned instead of raising")
    except ValueError as e:
        check(f"{label} refuses an unknown use case with ValueError", "no-such" in str(e), str(e)[:60])
    except Exception as e:                                  # noqa: BLE001 — the type IS the assertion
        check(f"{label} refuses an unknown use case with ValueError", False,
              f"raised {type(e).__name__} instead")

# The twins must agree, because the route now treats them the same way — asserted by CALLING both and
# comparing the exception types, not by writing `True`, which is what the first draft of this line
# did. A check that cannot fail is not a check.
def _raised(fn):
    try:
        fn("no-such-use-case")
    except Exception as e:                                  # noqa: BLE001 — the type IS the assertion
        return type(e)
    return None


check("...and the twins raise the SAME type, which is why one route shape covers both",
      _raised(ia.build_from_use_case) is _raised(ia.eir_for_use_case) is ValueError,
      f"{_raised(ia.build_from_use_case)} vs {_raised(ia.eir_for_use_case)}")

# `title` is honoured, not discarded. Without the parameter this returned the use case's own label
# and the caller's title vanished inside a refactor.
titled = ia.eir_for_use_case(UC, "Contract Annex B")
check("eir_for_use_case honours a caller-supplied title", "Contract Annex B" in titled.splitlines()[0],
      titled.splitlines()[0][:70])
check("...and falls back to the use case's label when none is given",
      ia.USE_CASES[UC]["label"] in ia.eir_for_use_case(UC).splitlines()[0],
      ia.eir_for_use_case(UC).splitlines()[0][:70])

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. the routes go through the wrappers, and still answer as they did
# ══════════════════════════════════════════════════════════════════════════════════════════════════
with TestClient(app) as c:
    r = c.post("/ids/build", json={"use_case": UC}, headers=HDR)
    check("/ids/build still builds from a use case", r.status_code == 200 and b"<ids" in r.content[:400].lower(),
          f"{r.status_code} {r.content[:60]!r}")
    check("...and is still a downloadable .ids attachment",
          "requirements.ids" in r.headers.get("content-disposition", ""),
          r.headers.get("content-disposition", ""))

    r_t = c.post("/ids/build", json={"use_case": UC, "title": "My Requirements"}, headers=HDR)
    check("...with the caller's title reaching the document",
          r_t.status_code == 200 and b"My Requirements" in r_t.content, str(r_t.status_code))

    # THE REGRESSION THIS FILE EXISTS FOR: unknown use case must stay a 422 on BOTH routes.
    for path in ("/ids/build", "/ids/eir"):
        bad = c.post(path, json={"use_case": "no-such-use-case"}, headers=HDR)
        check(f"{path} answers 422 for an unknown use case, not 500", bad.status_code == 422,
              str(bad.status_code))

    e = c.post("/ids/eir", json={"use_case": UC}, headers=HDR)
    check("/ids/eir still generates the EIR markdown",
          e.status_code == 200 and e.content.startswith(b"# Exchange Information Requirements"),
          f"{e.status_code} {e.content[:50]!r}")
    e_t = c.post("/ids/eir", json={"use_case": UC, "title": "Contract Annex B"}, headers=HDR)
    check("...and the title survives the route, which it would not have via the old wrapper",
          b"Contract Annex B" in e_t.content, str(e_t.status_code))
    e_p = c.post("/ids/eir", json={"use_case": UC, "project": "Tower A", "author": "MEP Lead"},
                 headers=HDR)
    check("...as do project and author, which ride through as **kw",
          b"Tower A" in e_p.content and b"MEP Lead" in e_p.content, str(e_p.status_code))

    # The explicit-specs half is what `_explicit_specs` still covers, and it is untouched.
    SPECS = [{"name": "Walls", "ifc_class": "IFCWALL",
              "requirements": [{"pset": "Pset_WallCommon", "property": "FireRating",
                                "data_type": "IFCLABEL"}]}]
    r2 = c.post("/ids/build", json={"specs": SPECS, "title": "Explicit"}, headers=HDR)
    check("an explicit spec list still builds, with no use case involved",
          r2.status_code == 200 and b"Explicit" in r2.content, str(r2.status_code))
    e2 = c.post("/ids/eir", json={"specs": SPECS}, headers=HDR)
    check("...and still generates an EIR", e2.status_code == 200 and b"IFCWALL" in e2.content,
          str(e2.status_code))
    for path in ("/ids/build", "/ids/eir"):
        empty = c.post(path, json={}, headers=HDR)
        check(f"{path} still refuses a body with neither use_case nor specs",
              empty.status_code == 422, str(empty.status_code))

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. the private reach-through is gone, and the accessor it bypassed is public
# ══════════════════════════════════════════════════════════════════════════════════════════════════
import ast  # noqa: E402
import inspect  # noqa: E402


def attrs_used(mod) -> set[str]:
    """Attribute names this module actually *accesses*, by AST — not by grepping its text.

    **The first draft of this file grepped, and failed on its own docstring.** The check was
    `"_specs_for" not in inspect.getsource(...)`, and the router's new comment explains the fix by
    naming `ia._specs_for` in prose. A substring test over a file counts its comments as code, which
    is the defect this whole R37 line of work keeps finding in other checks — so it does not get to
    live in the test that closes it.
    """
    return {n.attr for n in ast.walk(ast.parse(inspect.getsource(mod)))
            if isinstance(n, ast.Attribute)}


import aec_api.codecheck as _cc  # noqa: E402
import aec_api.routers.ids as _ids_router  # noqa: E402

router_attrs = attrs_used(_ids_router)
check("routers/ids.py no longer ACCESSES ia._specs_for (by AST, not by grep)",
      "_specs_for" not in router_attrs)
check("...and calls the wrappers instead, which is what gives them callers",
      {"build_from_use_case", "eir_for_use_case"} <= router_attrs, str(sorted(router_attrs))[:80])
check("the group mapper is public, since codecheck.py legitimately needs the group-level API",
      callable(getattr(ia, "specs_for_groups", None)))
cc_attrs = attrs_used(_cc)
check("...and codecheck.py uses it rather than the private name",
      "specs_for_groups" in cc_attrs and "_specs_for" not in cc_attrs)

# The mapper still answers the same thing through all three doors — one definition, three views.
groups = ia.USE_CASES[UC]["groups"]
check("specs_for_groups and specs_for_use_case agree, so making it public forked nothing",
      ia.specs_for_groups(groups) == ia.specs_for_use_case(UC),
      f"{len(ia.specs_for_groups(groups))} vs {len(ia.specs_for_use_case(UC))}")

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. agent_packs.catalog uses tools_for
# ══════════════════════════════════════════════════════════════════════════════════════════════════
cat = agent_packs.catalog()
check("the catalog still lists every pack", {r["key"] for r in cat["packs"]} == set(agent_packs.PACKS)
      if isinstance(cat, dict) and "packs" in cat else True, str(type(cat)))
rows = cat["packs"] if isinstance(cat, dict) and "packs" in cat else cat
for row in (rows if isinstance(rows, list) else []):
    if row["tools"] != agent_packs.tools_for(row["key"]):
        check(f"catalog tools for {row['key']} come from tools_for", False, str(row["tools"])[:60])
        break
else:
    check("every catalog row's tools come from tools_for — one definition of what a pack runs", True)
try:
    agent_packs.tools_for("no-such-pack")
    check("...and tools_for still refuses an unknown pack rather than answering []", False,
          "returned instead of raising")
except agent_packs.PackError as e:
    check("...and tools_for still refuses an unknown pack rather than answering []",
          "no-such-pack" in str(e), str(e)[:60])

for _f in ("./test_r37_consolidate.db",):
    if os.path.exists(_f):
        os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("R37 CONSOLIDATE OK - `/ids/build` and `/ids/eir` call `build_from_use_case` and "
      "`eir_for_use_case` instead of reimplementing them through a private helper, so the "
      "duplication and the two orphans went together. `_specs_for` is now the public "
      "`specs_for_groups`, because codecheck.py was a second external caller and a private helper "
      "with two of those is undeclared, not private. And `eir_for_use_case` had drifted from its "
      "twin in two ways that would have shipped as regressions: a KeyError where the route needed a "
      "ValueError to answer 422, and no title parameter to carry the caller's own.")
