"""A saved view's `config` is a schema, and the alert feed counts what the view actually shows.

## Two defects, one cause

`SavedView.config` was `mapped_column(JSON, default=dict)` and `save_view` took `config: dict =
Body(...)` and stored it verbatim. "filter/sort/column config" was true only in the docstring, so:

1. **A saved view was whatever a client happened to POST.** A schema change broke views silently
   with no migration path, and `{"filtres": [...]}` was indistinguishable from a feature.
2. **The alert feed ignored the filters it was storing.** `count_records` has taken `filters` since
   MOD-FILTER, and its docstring names this caller — *"a count that ignores a filter the list applied
   reports a total the page cannot account for, and a total is exactly the number a user trusts
   without checking."* `view_alerts` passed only `state` and `q`.

Measured before the fix, on two RFIs differing by one declared field, with a view saved as
`{"filters": [["discipline","eq","Structural"]]}` — which the write route accepted, because nothing
validated a config::

    alert feed total = 2        the view itself shows = 1

The shipped web register only ever saved `{q, state, sort}`, so **no browser produced this** — but the
API accepted filters from any other client, and item 3's schema now positively invites them. Fixing
the count is what makes storing them safe: the schema and the miscount had to land together, because
either alone makes the other worse.

## Why validation is by RESOLUTION rather than by shape

Every field name goes through `_resolve_field` and every operator through `FILTER_OPS` — the same two
the list route uses. `_json_text` interpolates a field name into a JSON path, so an unvalidated name
is an injection site rather than a typo, and a second validator would be a second answer to "what is
a field". That is the rule `aggregate`'s docstring states; this is the third caller to follow it.

**Unknown keys are refused, not ignored**, which is what gives the schema a migration path: the key
set is the contract, and changing it is a visible act rather than a silent divergence between what
clients write and what the server reads.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_view_config.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_view_config.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_view_config")
for _f in ("./_view_config.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import HTTPException  # noqa: E402

from aec_api import modules as mod  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, SavedView  # noqa: E402
from aec_api.modules_query import (  # noqa: E402
    MAX_FILTERS,
    VIEW_CONFIG_KEYS,
    count_records,
    validate_view_config,
)
from aec_api.modules_registry import REGISTRY, load_registry  # noqa: E402

load_registry()
Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def refused(key: str, cfg: dict) -> str | None:
    """The 422 detail for a config that must be refused, or None if it was wrongly accepted."""
    try:
        validate_view_config(key, cfg)
    except HTTPException as e:
        return str(e.detail)
    return None


KEY = "rfi"
MOD = REGISTRY.get(KEY) or {}
DECLARED = [f["name"] for f in MOD.get("fields", []) if f.get("name")]

# Anti-vacuity: every assertion below resolves names against this module's declared fields. If the
# module stopped declaring any, "unknown field is refused" would pass for the wrong reason.
check("the module under test declares fields to resolve against", len(DECLARED) >= 3,
      f"{len(DECLARED)} declared, e.g. {DECLARED[:4]}")
check("...including the one the filter cases use", "discipline" in DECLARED)

# ---- what a valid config is ---------------------------------------------------------------------
ok = validate_view_config(KEY, {"q": "beam", "state": "open", "sort": "discipline",
                                "sort_dir": "DESC",
                                "filters": [["discipline", "eq", "Structural"]]})
check("a valid config survives validation", ok.get("q") == "beam" and ok.get("state") == "open")
check("...and sort_dir is normalised to lower case", ok.get("sort_dir") == "desc", f"{ok.get('sort_dir')!r}")
check("...and filters come back as [field, op, value]",
      ok.get("filters") == [["discipline", "eq", "Structural"]], f"{ok.get('filters')!r}")
check("an empty config is valid and empty", validate_view_config(KEY, {}) == {})
check("None is valid and empty", validate_view_config(KEY, None) == {})

# ---- what it is not: every refusal names what was wrong ------------------------------------------
REFUSALS = [
    ("an unknown config key", {"filtres": []}, "unknown view config key"),
    ("an undeclared sort field", {"sort": "nope_not_a_field"}, "unknown filter/sort field"),
    ("an undeclared filter field", {"filters": [["nope", "eq", "x"]]}, "unknown filter/sort field"),
    ("an unknown filter operator", {"filters": [["discipline", "regex", "x"]]}, "unknown filter operator"),
    ("a malformed filter triple", {"filters": [["discipline", "eq"]]}, "[field, op, value]"),
    ("filters that are not a list", {"filters": "discipline=x"}, "must be a list"),
    ("an undeclared column", {"columns": ["nope"]}, "unknown filter/sort field"),
    ("a bad sort_dir", {"sort_dir": "sideways"}, "sort_dir must be"),
    ("an unknown aggregate", {"agg": "median"}, "unknown aggregate"),
    ("a non-string q", {"q": {"$ne": None}}, "must be a string"),
    ("too many filters", {"filters": [["discipline", "eq", str(i)] for i in range(MAX_FILTERS + 1)]},
     "too many filters"),
]
for label, cfg, expect in REFUSALS:
    detail = refused(KEY, cfg)
    check(f"refuses {label}", detail is not None and expect in detail,
          "ACCEPTED" if detail is None else f"said {detail!r}")

# The inverse: refusing everything would satisfy all eleven cases above.
# Every declared key at once. `join` names a declared reference field, so this case is also what
# keeps VIEW_CONFIG_KEYS honest: adding a key to the set without teaching the validator to accept it
# fails here rather than shipping a key the schema advertises and refuses.
#
# The detail string used to print `len(VIEW_CONFIG_KEYS)` — the CONSTANT, not what actually round
# -tripped — so when `join` was added to the set and not to this config, the failure reported
# "10 keys round-tripped" while 9 had. A message that reads back the expectation instead of the
# result describes a test that cannot tell you what went wrong.
_every = validate_view_config(KEY, {
    "q": "x", "state": "open", "sort": "discipline", "sort_dir": "asc",
    "filters": [["discipline", "eq", "Structural"]], "columns": ["discipline"],
    "group_by": "discipline", "agg": "count", "agg_field": "discipline",
    "join": "location",
})
check("...while still accepting a config that uses every declared key",
      set(_every) == VIEW_CONFIG_KEYS,
      f"{len(_every)} of {len(VIEW_CONFIG_KEYS)} round-tripped"
      + (f"; missing {sorted(VIEW_CONFIG_KEYS - set(_every))}" if set(_every) != VIEW_CONFIG_KEYS else ""))

# ---- a saved view must be REPLAYABLE, not merely well-formed --------------------------------------
# `aggregate` refuses two things beyond "is `agg` a known function": a non-`count` aggregate needs an
# `agg_field`, and `sum`/`avg` need a NUMERIC one (it refuses rather than returning SQLite's confident
# `0` for summed text). This validator's docstring promises a view is validated exactly as the query
# it replays would be — and until R22 follow-up that promise was kept only for field NAMES, so all
# three configs below saved at 200 and then 400'd when the report was run. A view that cannot be
# replayed is worse than one that was refused: the refusal happens while the user is still looking at
# the form.
#
# `rfi` declares no numeric field, so the ACCEPTANCE half cannot be expressed there — and refusals
# alone would be satisfied by a validator that refuses every aggregate. Both halves are needed, so
# the numeric case resolves against whichever module declares a numeric field.
_NUMERIC = {"number", "currency", "percent"}
NUMKEY = NUMF = NUMTXT = None
for _k in sorted(REGISTRY):
    _types = {f.get("name"): f.get("type") for f in REGISTRY[_k].get("fields", []) if f.get("name")}
    _nums = sorted(n for n, t in _types.items() if t in _NUMERIC)
    _txts = sorted(n for n, t in _types.items() if t == "text")
    if _nums and _txts:
        NUMKEY, NUMF, NUMTXT = _k, _nums[0], _txts[0]
        break
check("a module declaring both a numeric and a text field exists to test aggregates against",
      NUMKEY is not None, f"{NUMKEY}: numeric={NUMF!r} text={NUMTXT!r}")

if NUMKEY:
    AGG_REFUSALS = [
        ("a numeric aggregate with no agg_field", {"group_by": NUMTXT, "agg": "sum"},
         "needs a field to aggregate"),
        ("sum over a non-numeric field", {"group_by": NUMTXT, "agg": "sum", "agg_field": NUMTXT},
         "needs a numeric field"),
        ("avg over a non-numeric field", {"group_by": NUMTXT, "agg": "avg", "agg_field": NUMTXT},
         "needs a numeric field"),
    ]
    for label, cfg, expect in AGG_REFUSALS:
        detail = refused(NUMKEY, cfg)
        check(f"refuses {label} at SAVE time, not at replay time",
              detail is not None and expect in detail,
              "ACCEPTED — it will 400 when the report runs" if detail is None else f"said {detail!r}")

    # The inverse. Refusing every aggregate would satisfy all three cases above.
    AGG_ACCEPTED = [
        ("count needs no field at all", {"group_by": NUMTXT, "agg": "count"}),
        ("sum over a declared numeric field", {"group_by": NUMTXT, "agg": "sum", "agg_field": NUMF}),
        ("min/max are meaningful on text", {"group_by": NUMTXT, "agg": "max", "agg_field": NUMTXT}),
    ]
    for label, cfg in AGG_ACCEPTED:
        detail = refused(NUMKEY, cfg)
        # The detail is built only when it is true. Passing it unconditionally is how this file's
        # earlier "10 of 10 round-tripped" lie happened: a message that describes the failure case
        # prints on the success case too, and then reads as a failure that passed.
        check(f"...while still accepting {label}", detail is None,
              "" if detail is None else f"REGRESSION: refused with {detail!r}")

# ---- the alert miscount, as state rather than as assertion ---------------------------------------
db = SessionLocal()
try:
    PID = "P-view-config"
    for disc in ("Structural", "Mechanical"):
        mod.create_record(db, KEY, PID,
                          {"data": {"subject": f"{disc} RFI", "question": "q?", "discipline": disc}},
                          "u1", None)
    db.commit()

    filters = [("discipline", "eq", "Structural")]
    unfiltered = count_records(db, KEY, PID)
    filtered = count_records(db, KEY, PID, filters=filters)
    check("the fixture distinguishes filtered from unfiltered", unfiltered == 2 and filtered == 1,
          f"unfiltered={unfiltered} filtered={filtered}")

    db.add(SavedView(project_id=PID, module=KEY, user="u1", name="Structural RFIs",
                     config={"filters": [["discipline", "eq", "Structural"]]}))
    db.commit()

    alert = next(a for a in mod.view_alerts(db, PID, "u1") if a["name"] == "Structural RFIs")
    check("the alert feed counts what the view SHOWS, not the whole module",
          alert["total"] == filtered,
          f"feed says {alert['total']}, the view shows {filtered}"
          + (" — the pre-fix value was the unfiltered 2" if alert["total"] == unfiltered else ""))

    # A row written before validation existed must not take the feed down, and must not be counted
    # wrong either — it is reported as uncountable with a reason.
    db.add(SavedView(project_id=PID, module=KEY, user="u1", name="Legacy",
                     config={"filters": "this was never validated"}))
    db.commit()
    legacy = next(a for a in mod.view_alerts(db, PID, "u1") if a["name"] == "Legacy")
    check("a pre-validation config is reported as uncountable, not counted wrong",
          legacy["total"] is None and "re-save" in (legacy.get("error") or ""),
          f"total={legacy['total']} error={legacy.get('error')!r}")
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"VIEW CONFIG OK - {len(VIEW_CONFIG_KEYS)} declared keys, {len(REFUSALS)} refusals each naming "
    "its cause, and the saved-view alert feed now counts through the view's own filters instead of "
    "reporting the whole module."
)
