"""A route that takes a client-supplied list must bound it.

The threat model claims this under §4 "stored-data amplification (editor stores → viewer GETs
evaluate)", with the control given as "count/size caps at save (`rule_library.MAX_*`,
`schedule_baselines._MAX`, view-template caps, calc-field length/node caps)". Those caps are real —
`rule_library`, `smart_views`, `view_templates`, `macros`, `jurisdiction_packs`, `clause_playbook`,
`deal_authority`, `shared_params` and `workflow_config` all enforce one. The claim was never that no
store had a cap; it was that *stores have caps*, and nothing decided which stores the sentence covered.

`codecheck.put_code_amendments` did not. It accepted `amendments: list[dict] = Body(...)`, validated
each ENTRY (family known, edition published) and stored the LIST, unbounded, with `section`/`note`
free text also unbounded. That distinction is the threat: a write is paid once, but the amendment
overlay is re-read and evaluated by every code check, so an unbounded list is paid on every read for
as long as it is stored. Per-entry validation reads as thorough while leaving the amplifying dimension
open — the entries were all individually valid.

**Deriving the population is what made this findable.** The obvious query — "every `storage.put` must
reference a cap" — returns 50 call sites across 33 modules, most of which legitimately write ONE
artifact (a model, a hero image, an export) where the upload middleware is the bound. That gate would
have shipped ~30 false positives on day one, and a gate whose first real encounter is a false positive
is one people learn to route around. Narrowing to *a route that takes a `list[...]` from `Body()` and
persists* yields exactly two, both of which are now capped, so the check needs no exemption list at
all — the honest version of "derive the population, don't list it".

A second measurement trap sits behind the first: asking whether the *saving function* mentions a cap
reports `clause_playbook.save`, `deal_authority.save`, `shared_params.save` and `workflow_config.save`
as uncapped. All four are fine — they cap in a validation helper called before the save. The check has
to look at the module's whole reachable path, not the one function whose name matched.

Rules asserted here:

  1. every route taking `list[...] = Body(...)` and persisting must apply a cap
  2. the derived population must be non-empty — a query that silently matches nothing passes forever
  3. `codes.validate_amendments` bounds count and both free-text fields (the specific fix, behavioural)

Pure AST plus a direct call to the validator: no DB, no TestClient, no network.
"""
import ast
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).parent / "src" / "aec_api"
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "data" / "src"))
CAP = re.compile(r"MAX[_A-Z]*")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _fn_sources(sources: dict) -> dict:
    """function name -> its source, across EVERY module in the corpus.

    Cross-module resolution is load-bearing, not thoroughness for its own sake. Restricted to the
    route's own module this check calls `put_code_amendments` and `macros_put` uncapped, because
    their caps live in `aec_data.codes.validate_amendments` and `aec_api.macros.save` — imported, not
    local. Both would have been false positives, in the exact place the docstring above warns that a
    first-encounter false positive teaches people to route around the gate.
    """
    out = {}
    for src in sources.values():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            out.setdefault(fn.name, []).append(ast.unparse(fn))
    return out


def list_body_routes(sources: dict | None = None) -> list:
    """(module, function, params, capped) for every route taking a client list AND persisting it."""
    if sources is None:
        sources = {p.stem: p.read_text(encoding="utf-8", errors="replace")
                   for p in sorted(SRC.rglob("*.py"))}
        data_src = pathlib.Path(__file__).parent.parent / "data" / "src" / "aec_data"
        if data_src.is_dir():
            sources.update({f"aec_data.{p.stem}": p.read_text(encoding="utf-8", errors="replace")
                            for p in sorted(data_src.rglob("*.py"))})
    fn_src = _fn_sources(sources)
    out = []
    for mod, src in sources.items():
        if "Body(" not in src or "storage.put(" not in src:
            continue
        tree = ast.parse(src)
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            defaults = fn.args.defaults
            if not defaults:
                continue
            listy = []
            for a, d in zip(fn.args.args[-len(defaults):], defaults):
                ann = ast.unparse(a.annotation) if a.annotation else ""
                if ann.startswith("list") and "Body(" in ast.unparse(d):
                    listy.append(f"{a.arg}: {ann}")
            if not listy:
                continue
            body = ast.unparse(fn)
            if "storage.put(" not in body and ".put(" not in body:
                continue
            # a cap named in the route, or reached through anything it calls — in this module or
            # another. `macros_put` caps in aec_api.macros.save; `put_code_amendments` in
            # aec_data.codes.validate_amendments.
            called = {c.func.attr if isinstance(c.func, ast.Attribute) else
                      getattr(c.func, "id", "") for c in ast.walk(fn) if isinstance(c, ast.Call)}
            reachable = body + "".join(
                "".join(fn_src.get(name, [])) for name in called if name)
            out.append((mod, fn.name, listy, bool(CAP.search(reachable))))
    return out


routes = list_body_routes()
uncapped = [(m, f, p) for m, f, p, c in routes if not c]

check("the derived population is non-empty — a query matching nothing would pass forever",
      len(routes) >= 2, f"{len(routes)} route(s): " + ", ".join(f"{m}.{f}" for m, f, _, _ in routes))
check("every route taking a client list and persisting it applies a cap", not uncapped,
      "; ".join(f"{m}.{f} {p}" for m, f, p in uncapped))

# --- the detector must be able to go red --------------------------------------------
UNCAPPED_SRC = ('from fastapi import Body\n'
                'from .. import storage\n'
                'def put_things(pid: str, things: list[dict] = Body(...)):\n'
                '    storage.put(f"{pid}/things", b"x")\n')
CAPPED_SRC = UNCAPPED_SRC.replace('    storage.put',
                                  '    if len(things) > MAX_THINGS: raise ValueError("too many")\n'
                                  '    storage.put')
check("fires on a route that persists a client list with no cap",
      len(list_body_routes({"m": UNCAPPED_SRC})) == 1
      and not list_body_routes({"m": UNCAPPED_SRC})[0][3])
check("passes once the cap is applied", list_body_routes({"m": CAPPED_SRC})[0][3])

VIA_HELPER = ('from fastapi import Body\n'
              'from .. import storage\n'
              'def _validate(things):\n'
              '    if len(things) > MAX_THINGS: raise ValueError("too many")\n'
              'def put_things(pid: str, things: list[dict] = Body(...)):\n'
              '    _validate(things)\n'
              '    storage.put(f"{pid}/things", b"x")\n')
check("a cap applied in a helper the route calls counts — the clause_playbook/deal_authority shape",
      list_body_routes({"m": VIA_HELPER})[0][3])

# --- the specific fix, asserted behaviourally not by grep ----------------------------
from aec_data import codes  # noqa: E402

over = [{"family": "IBC", "edition": 2021} for _ in range(codes.MAX_AMENDMENTS + 1)]
check("validate_amendments refuses a list over the cap", bool(codes.validate_amendments(over)),
      f"cap={codes.MAX_AMENDMENTS}")
check("and a list at the cap is still accepted — the bound is not off by one",
      codes.validate_amendments(over[:-1]) == [])
check("refuses an over-long section",
      bool(codes.validate_amendments([{"family": "IBC", "section": "x" * (codes.MAX_SECTION_LEN + 1)}])))
check("refuses an over-long note",
      bool(codes.validate_amendments([{"family": "IBC", "note": "x" * (codes.MAX_NOTE_LEN + 1)}])))
check("still accepts an ordinary amendment", codes.validate_amendments(
    [{"family": "IBC", "edition": 2021, "section": "1004.5", "note": "local amendment"}]) == [])

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"stored_collection_caps OK — {len(routes)} derived route(s), all capped; "
      f"detector driven red; amendment bounds verified at the boundary")
