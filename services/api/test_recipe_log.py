"""R23-RECIPE-ARTIFACT — the log has to record the INPUTS, and refuse when it cannot reproduce them.

The ring entry says the edit-recipe log "already IS a CAD operation timeline" and needs formalising.
It was not one. `edit_history.json` is a stack of file paths for undo; the audit log records an
edit's *outputs* (`/edit`) or just the recipe *names* (`/edit/batch`). The **parameters were nowhere**,
and every capability the item asks for — replay, diff, export — depends on them.

So the tests below are about the inputs: that they are kept, that an over-large one is elided rather
than truncated, and that a replay of an elided entry is **refused** rather than attempted with the
descriptor. That last one is the whole discipline: a replay must either reproduce the edit or say it
cannot, never quietly call the recipe with something that resembles the original argument.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_recipe_log.py
"""
import json
import os
import shutil
import sys

os.environ.setdefault("STORAGE_DIR", "./test_storage_recipe_log")
sys.path.insert(0, "src")

from aec_api import recipe_log as rl  # noqa: E402
from aec_api import storage  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. an entry keeps what a replay would need ---------------------------------------------------
e = rl.entry("add_wall", {"start": [0, 0], "end": [6, 0], "height": 3.0},
             actor="ana@x", source_in="/srv/ifc/p1/model.ifc",
             source_out="/srv/ifc/p1/model_20260729.ifc", outputs={"guid": "abc"})
check("the recipe is kept", e["recipe"] == "add_wall")
check("the PARAMETERS are kept — the half that did not exist before",
      e["params"] == {"start": [0, 0], "end": [6, 0], "height": 3.0}, e["params"])
check("the actor is kept", e["actor"] == "ana@x")
check("the outputs are kept alongside, not instead", e["outputs"] == {"guid": "abc"})
check("it is timestamped", e["at"].startswith("20"))
check("paths are reduced to basenames — a server layout is not the reader's business",
      e["source_in"] == "model.ifc" and e["source_out"] == "model_20260729.ifc", e["source_in"])
check("nothing is elided for an ordinary recipe", e["params_elided"] is False)

# --- 2. a large value is elided, and the elision is legible ----------------------------------------
big = {"verts": [float(i) for i in range(5000)], "name": "Mesh"}
be = rl.entry("add_mesh_representation", big, actor="ana@x", source_in="a.ifc", source_out="b.ifc")
check("an over-large value is elided", be["params_elided"] is True)
check("  the small sibling parameter survives", be["params"]["name"] == "Mesh")
d = be["params"]["verts"]
check("  the elided value becomes a descriptor", d.get("__elided__") is True, d)
check("  carrying its type, size and a hash", d["type"] == "list" and d["bytes"] > 8192 and d["hash"])
check("  and its element count", d["length"] == 5000)
check("  it is NOT a truncation — half a vertex array looks like a vertex array",
      not isinstance(d, list))

unserializable = rl.entry("weird", {"obj": object(), "ok": 1}, actor="a", source_in="a", source_out="b")
check("a non-JSON-serializable value elides rather than raising",
      unserializable["params"]["obj"].get("__elided__") is True
      and unserializable["params_elided"] is True, unserializable["params"])
check("  with the reason stated", unserializable["params"]["obj"]["reason"] == "not JSON-serializable")
# The invariant that makes the elision worth doing: whatever `entry` returns must survive the trip
# through storage. If a value slipped past `_shrink`, `_save` would raise, `append_safe` would
# swallow it, and the WHOLE entry would vanish — a worse failure than eliding one parameter.
import json as _json  # noqa: E402

for label, ent in (("an ordinary entry", e), ("an elided entry", be),
                   ("an unserializable-param entry", unserializable)):
    try:
        _json.dumps(ent)
        check(f"{label} is JSON-serializable end to end", True)
    except (TypeError, ValueError) as ex:
        check(f"{label} is JSON-serializable end to end", False, ex)

# --- 3. replay refuses what it cannot reproduce -----------------------------------------------------
good = [rl.entry("add_wall", {"start": [0, 0], "end": [6, 0]}, actor="a", source_in="a", source_out="b"),
        rl.entry("add_column", {"point": [2, 2]}, actor="a", source_in="b", source_out="c")]
plan = rl.replay_plan(good)
check("a clean log replays", plan["count"] == 2)
check("  as ordered {recipe, params} steps",
      [s["recipe"] for s in plan["steps"]] == ["add_wall", "add_column"])
check("  with the original parameters", plan["steps"][0]["params"]["end"] == [6, 0])
check("  and it is a PLAN, not an execution", "does not execute" in plan["note"])

sel = rl.replay_plan(good, indices=[1])
check("a subset can be selected", sel["count"] == 1 and sel["steps"][0]["recipe"] == "add_column")

for label, arg, entries in (("an elided entry", None, good + [be]),
                            ("an out-of-range index", [9], good),
                            ("an empty selection", [], good)):
    try:
        rl.replay_plan(entries, indices=arg)
        check(f"replay refuses {label}", False, "no exception")
    except rl.ReplayError as ex:
        check(f"replay refuses {label}", True)
        if label == "an elided entry":
            check("  naming the entry that cannot be reproduced",
                  "add_mesh_representation" in str(ex), str(ex)[:100])
            check("  and saying why the descriptor must not be substituted",
                  "resembles the original" in str(ex), str(ex)[:160])

# --- 4. diff compares like with like ------------------------------------------------------------------
w1 = rl.entry("add_wall", {"start": [0, 0], "end": [6, 0], "height": 3.0}, actor="a",
              source_in="a", source_out="b")
w2 = rl.entry("add_wall", {"start": [0, 0], "end": [8, 0], "height": 3.0}, actor="a",
              source_in="b", source_out="c")
df = rl.diff(w1, w2)
check("two runs of the same recipe are comparable", df["comparable"] is True)
check("  only the changed parameter is reported",
      [c["param"] for c in df["changed"]] == ["end"], df["changed"])
check("  with before and after", df["changed"][0]["before"] == [6, 0]
      and df["changed"][0]["after"] == [8, 0])
check("  and the unchanged ones are named too", set(df["unchanged"]) == {"start", "height"})
check("identical entries diff as identical", rl.diff(w1, w1)["identical"] is True)

cross = rl.diff(w1, rl.entry("set_pset", {"guid": "g"}, actor="a", source_in="a", source_out="b"))
check("two DIFFERENT recipes are not comparable", cross["comparable"] is False)
check("  and it says why rather than reporting every field as changed",
      "not the same vocabulary" in cross["reason"], cross["reason"])

edf = rl.diff(be, be)
check("a diff touching an elided entry warns about what the comparison means",
      edf["elided"] is True and "compares by hash" in edf["elided_warning"])

# --- 5. a corrupt log is NEVER silently replaced ------------------------------------------------------
# Found by the security-audit session, reproduced here before fixing: `_load` caught bare Exception
# and returned an empty log, so a file that existed but did not parse read as "no history". The next
# `record()` then appended to that emptiness and `_save()` overwrote the file — 120 entries gone,
# with `record` reporting SUCCESS and `append_safe` never firing. For a provenance artifact that is
# the worst available failure: it does not break, it quietly becomes a shorter history.
PID = "corrupt-test"
shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)
rl.record(PID, [rl.entry("add_wall", {"i": i}, actor="a", source_in="a", source_out="b")
                for i in range(120)])
check("a log with 120 entries loads", len(rl._load(PID)["entries"]) == 120)

storage.put(rl._key(PID), b"{ this is not valid json")
try:
    rl._load(PID)
    check("a corrupt log RAISES rather than reading as empty", False, "no exception")
except rl.LogUnreadable as e:
    check("a corrupt log RAISES rather than reading as empty", True)
    check("  and says the file was not overwritten", "NOT been overwritten" in str(e), str(e)[:120])

# The behaviour that matters: an append must not be able to destroy it.
rl.append_safe(PID, [rl.entry("add_column", {"p": 1}, actor="a", source_in="a", source_out="b")])
check("append_safe on a corrupt log does not overwrite it",
      storage.get(rl._key(PID)) == b"{ this is not valid json")
check("  the edit still succeeds — append_safe swallows it, as designed", True)

# An absent log is still an empty log, not an error. Absent and unreadable must stay distinguishable.
shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)
check("an ABSENT log is empty, not an error", rl._load("never-written")["entries"] == [])

# A file that parses but is not a log document is also refused.
rl.record("shape-test", [rl.entry("x", {}, actor="a", source_in="a", source_out="b")])
storage.put(rl._key("shape-test"), b'{"version": 1, "entries": "not a list"}')
try:
    rl._load("shape-test")
    check("a parseable non-log document is refused", False, "no exception")
except rl.LogUnreadable:
    check("a parseable non-log document is refused", True)

# --- 6. the ENTRY is bounded, not just each value ------------------------------------------------------
# Also from the security audit: `_MAX_VALUE` bounds one value and therefore bounds nothing. `params`
# comes off the request body (capped at AEC_MAX_UPLOAD_MB, 1 GB by default), so 300 individually
# small values is a 1.2 MB entry that passes every per-value check — and `_load` re-parses the whole
# sidecar on every edit, so the cost lands on every subsequent edit, permanently.
many = {f"k{i}": "x" * 4000 for i in range(300)}       # each value 4 KB, all under _MAX_VALUE
me = rl.entry("mesh", many, actor="a", source_in="a", source_out="b")
size = len(json.dumps(me).encode("utf-8"))
check("an entry of many small values is capped", size <= rl._MAX_ENTRY, f"{size:,} bytes")
check("  and is marked elided", me["params_elided"] is True)
check("  largest-first, so the fewest parameters are lost",
      sum(1 for v in me["params"].values() if isinstance(v, dict) and v.get("__elided__")) < 300)
check("  survivors are kept verbatim",
      any(v == "x" * 4000 for v in me["params"].values()))
check("  and the cap reason is stated on the elided ones",
      any(isinstance(v, dict) and str(v.get("reason", "")).startswith("entry exceeded")
          for v in me["params"].values()))
check("a small entry is untouched by the cap", rl.entry(
    "add_wall", {"start": [0, 0]}, actor="a", source_in="a", source_out="b")["params_elided"] is False)

# --- 7. credential-looking parameters never reach the exportable log --------------------------------------
sec = rl.entry("connect", {"api_key": "sk-live-123", "auth_token": "t", "PASSWORD": "p",
                           "licence_key": "L", "host": "example.com"},
               actor="a", source_in="a", source_out="b")
for k in ("api_key", "auth_token", "PASSWORD", "licence_key"):
    check(f"{k} is elided by name", sec["params"][k].get("__elided__") is True, sec["params"][k])
check("  with the reason", "credential" in sec["params"]["api_key"]["reason"])
check("  and the value is nowhere in the serialized entry",
      "sk-live-123" not in json.dumps(sec))
check("an ordinary parameter beside them is untouched", sec["params"]["host"] == "example.com")

shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)

print()
if FAILED:
    print(f"recipe_log: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("recipe_log: all checks passed")
