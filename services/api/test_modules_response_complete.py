"""MOD-COMPLETE — `GET /modules` must not silently drop a declared module key.

The handler is a hand-written projection: ~15 explicit `m.get("...")` lines. A key added to
`module.json` and not added *there* is simply absent from the response, with nothing failing anywhere.
That is how `tools:` shipped invisible for a full release — declared by the modules, consumed by
nothing, and found only by curling a running server.

**This is a completeness check, not a longer allowlist.** Adding the missing key to the projection
fixes today's instance and guarantees the next one repeats it verbatim. The check instead asserts a
relationship: *every top-level key any module declares is either served, or explicitly recorded as
deliberately withheld with a reason.* A new key then fails **the day it is declared**, and the fix is a
decision rather than a memory.

Two design points that make it a real check rather than a second list:

1. **The served set is read from the handler's actual output**, never re-declared here. A hardcoded
   copy of the projection would pass while the response was wrong — the check would be asserting
   against itself, which is the exact failure it exists to catch.
2. **`NOT_SERVED` requires a reason string.** A bare name is an allowlist; a name plus a justification
   is a decision someone can review and reverse.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_modules_response_complete.py
"""
import glob
import json
import sys

sys.path.insert(0, "src")

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


#: Keys deliberately NOT sent to the client, each with the reason. Server-only concerns belong here;
#: anything a client must know to render or predict behaviour does not.
NOT_SERVED: dict[str, str] = {}


def declared_keys() -> dict[str, int]:
    """Every top-level key across every module.json, with how many modules declare it.

    Read from disk rather than from the registry so a key is counted even if the loader drops it —
    the loader is one of the layers this check is meant to see past."""
    seen: dict[str, int] = {}
    files = glob.glob("modules/*/module.json")
    assert files, "no module.json found — running from the wrong directory"
    for p in files:
        # Explicit UTF-8: the default on this box is cp1252 and several module.json files contain
        # characters it cannot decode. A per-file reader that swallows that error reports a short
        # answer that looks complete, which is the failure this whole check is about.
        with open(p, encoding="utf-8") as fh:
            for k in json.load(fh):
                seen[k] = seen.get(k, 0) + 1
    return seen


def served_keys() -> set[str]:
    """The keys `GET /modules` actually returns — read from the handler, never re-declared here."""
    # The registry is populated at app startup, not at import — an empty REGISTRY would make this
    # check pass vacuously by finding no keys to compare, which is the shape it exists to catch.
    from aec_api.modules_registry import REGISTRY, load_registry
    from aec_api.routers.modules import list_modules

    if not REGISTRY:
        load_registry()
    assert REGISTRY, "module registry is empty — the check would pass vacuously"

    rows = list_modules()
    assert rows, "GET /modules returned nothing"
    out: set[str] = set()
    for r in rows:
        out |= set(r)
    return out


declared = declared_keys()
served = served_keys()

print(f"  {len(declared)} distinct top-level keys across {len(glob.glob('modules/*/module.json'))} "
      f"modules · {len(served)} keys in the response\n")

dropped = {k: n for k, n in declared.items() if k not in served and k not in NOT_SERVED}
check("no declared module key is silently dropped from GET /modules",
      not dropped,
      "dropped: " + ", ".join(f"{k} ({n} modules)" for k, n in sorted(dropped.items())))

# The reverse direction: a NOT_SERVED entry for a key nobody declares any more is stale, and a stale
# exemption is how a list rots into a place where things are parked and forgotten.
stale = [k for k in NOT_SERVED if k not in declared]
check("no NOT_SERVED entry is stale — every exemption names a key that still exists",
      not stale, stale)

# --- MOD-COMPLETE ③: served → declared, the direction this gate was structurally blind to ------------
#
# The check above asks "is every DECLARED key served?". Nothing asked the mirror: "is every SERVED key
# actually declared by something?" A key can be emitted by the handler that no module.json declares,
# no schema defines and no loader populates — so it is sent to every client as a constant empty value,
# forever, and this gate stayed green the whole time.
#
# That is not hypothetical. `relations` was exactly this from Modules Phase 1 until 2026-08-01: served
# as `[]` to every client, declared by 0 of 133 modules, absent from `module_schema.py`, read by
# nothing in the web app. It was removed rather than wired, because the capability already ships as
# `"type": "reference"` FIELDS (85 modules use them). **A field that is always empty teaches every
# client to ignore it, which is how a real value later goes unnoticed.**
#
# This is the third sighting in this repo of "a check that runs one way only" — the lane gate searched
# the region it was validating, and the doc-citation gate never asked whether an index entry named a
# real file. Directionality is the recurring blind spot, not any one list.
#
#: Keys the RESPONSE adds that no `module.json` declares — each with the reason it is legitimate.
#: A computed or renamed key belongs here; a key that is simply dead does not, it belongs deleted.
SERVED_WITHOUT_DECLARATION: dict[str, str] = {
    "room": (
        "COMPUTED, not declared. `rooms.room_of(m)` derives it from the module's `section`, so no "
        "module.json declares it and none should — the room spine is single-sourced in rooms.py "
        "precisely so a module cannot invent its own taxonomy. Found by this check on its first run, "
        "which is the distinction the list exists to make: `room` is derived and correct, `relations` "
        "was dead and got deleted. Both look identical from the declared-keys side."
    ),
}

undeclared = sorted(k for k in served
                    if k not in declared and k not in SERVED_WITHOUT_DECLARATION)
check("no key is served that nothing declares — an always-empty field is worse than an absent one",
      not undeclared,
      "served but undeclared: " + ", ".join(undeclared) if undeclared else
      f"{len(served)} served keys, all declared by at least one module")

check("every SERVED_WITHOUT_DECLARATION entry carries a real reason",
      all(isinstance(v, str) and len(v.strip()) > 20 for v in SERVED_WITHOUT_DECLARATION.values()),
      {k: v for k, v in SERVED_WITHOUT_DECLARATION.items()
       if not (isinstance(v, str) and len(v.strip()) > 20)})

check("no SERVED_WITHOUT_DECLARATION entry is stale — every exemption names a key still served",
      not [k for k in SERVED_WITHOUT_DECLARATION if k not in served],
      [k for k in SERVED_WITHOUT_DECLARATION if k not in served])

check("`relations` is gone from the response — removed, not re-added as an empty list",
      "relations" not in served)

check("every NOT_SERVED entry carries a non-empty reason, so an exemption is a decision not a name",
      all(isinstance(v, str) and len(v.strip()) > 20 for v in NOT_SERVED.values()),
      {k: v for k, v in NOT_SERVED.items() if not (isinstance(v, str) and len(v.strip()) > 20)})

# --- the specific regressions this was written for -------------------------------------------------
check("`tools` is served — the R30 key that shipped invisible for a full release",
      "tools" in served)
check("`room` is served — the shell must not invent its own taxonomy", "room" in served)
check("`close_requires_attachment` is served — it is ENFORCED at modules.py, so a client that "
      "cannot see it cannot warn before the transition is rejected",
      "close_requires_attachment" in served)

print()
if FAILED:
    print(f"modules_response_complete: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("modules_response_complete: all checks passed")
