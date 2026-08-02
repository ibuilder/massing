"""R38-ARRAY-LIVE — an array you can still edit after you place it, and the deletion it refuses.

`array_element` used to be a one-shot: it produced independent GUID-stable copies and stored
**nothing** — no group, no pset, no definition — so there was nothing to re-edit and changing a count
meant deleting copies by hand. The definition now lives in IFC itself (a group pset carrying
nx/ny/pitch, and a cell index on each member), so it survives a round-trip through any IFC tool
rather than sitting in a sidecar this application would be the only reader of.

The assertions are about the one genuinely dangerous operation here:

1. **shrinking an array DELETES elements.** A member somebody has moved is no longer a generated
   copy — it is authored work — and deleting it is unrecoverable from the definition. Refused by
   default, named with its offset, `force=True` to override. The dangerous default is the plausible
   one: an array editor that silently drops edited members looks exactly like one that works;
2. **re-pitching must not snap a hand-placed member back**, which would discard the placement just
   as surely as deleting it;
3. **an element that merely LOOKS arrayed has no definition.** Three walls in a row somebody drew by
   hand must not acquire one, or a later count change would delete elements nobody arrayed;
4. **the source is never deleted** — cell (0,0) is the user's original element, not a copy.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_array_live.py
"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, groups, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED: list[str] = []


def _exists(guid) -> bool:
    """`by_guid` RAISES on a missing id rather than returning None (verified in R38-PLAN-IDENTITY —
    written the other way this crashes the run instead of failing it)."""
    try:
        m.by_guid(guid)
        return True
    except Exception:                        # noqa: BLE001 — absence is the answer, not an error
        return False


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TMP = os.path.join(os.path.dirname(__file__), "_array_live.ifc")
massing.generate_blank_ifc(TMP, name="Array Live", storeys=1, storey_height=3.0, ground_size=60.0)
m = open_model(TMP)
storey = m.by_type("IfcBuildingStorey")[0].Name
src = edit.add_wall(m, [0, 0], [4, 0], 3.0, 0.2, storey)

# --- 1. THE DEFINITION IS PERSISTED ----------------------------------------------------------------
r = groups.array_element(m, src, nx=3, ny=1, dx=5.0)
check("array_element still returns its copies", r["count"] == 2, r)
check("  and now reports the group it stored the definition in", bool(r.get("group")), r)

info = groups.array_params(m, src)["array"]
check("the array is READABLE BACK from the model", info is not None)
check("  with its parameters", (info["nx"], info["ny"], info["dx"]) == (3, 1, 5.0), info)
check("  and the source named", info["source"] == src, info)
check("  every cell is a member, source included", info["member_count"] == 3, info)
check("  each member knows its cell", sorted((x["i"], x["j"]) for x in info["members"])
      == [(0, 0), (1, 0), (2, 0)], info["members"])

# it must survive a save/reload — a definition only this process can see is not persisted
m.write(TMP)
m2 = open_model(TMP)
check("THE DEFINITION SURVIVES A ROUND-TRIP THROUGH THE FILE",
      (groups.array_params(m2, src)["array"] or {}).get("nx") == 3,
      groups.array_params(m2, src)["array"])

# --- 3. AN ELEMENT THAT ONLY LOOKS ARRAYED HAS NO DEFINITION ----------------------------------------
lone = edit.add_wall(m, [0, 30], [4, 30], 3.0, 0.2, storey)
check("a hand-drawn element is NOT reported as an array",
      groups.array_params(m, lone)["array"] is None)
check("  and says so rather than returning an empty array",
      "not part of a stored array" in groups.array_params(m, lone)["note"])
check("  changing its params is refused as not_an_array",
      groups.set_array_params(m, lone, nx=5)["status"] == "not_an_array")

# --- GROWING ----------------------------------------------------------------------------------------
grow = groups.set_array_params(m, src, nx=5)
check("growing to nx=5 adds exactly the two new cells", len(grow["added"]) == 2, grow["added"])
check("  and removes nothing", grow["removed"] == [], grow["removed"])
check("  the stored definition is updated", groups.array_params(m, src)["array"]["nx"] == 5)
check("  new members land on the pitch",
      [a["i"] for a in grow["added"]] == [3, 4], grow["added"])
xs = sorted(groups._origin_of(m.by_guid(x["guid"]))[0] for x in grow["added"])
check("  at the right world positions (base + 5·i)",
      all(abs(x - (groups._origin_of(m.by_guid(src))[0] + 5.0 * i)) < 1e-6
          for x, i in zip(xs, (3, 4))), xs)

# --- SHRINKING, THE UNMODIFIED CASE ------------------------------------------------------------------
shrink = groups.set_array_params(m, src, nx=3)
check("shrinking to nx=3 deletes the two outer members", len(shrink["removed"]) == 2, shrink)
check("  and they are really gone from the model, not merely unlinked",
      all(not _exists(g) for g in shrink["removed"]), shrink["removed"])

# --- 2 + THE REFUSAL: A MOVED MEMBER IS AUTHORED WORK -------------------------------------------------
info = groups.array_params(m, src)["array"]
outer = max((x for x in info["members"] if not x["is_source"]), key=lambda x: x["i"])
edit.move_element(m, outer["guid"], 0.0, 7.0, 0.0)          # somebody repositioned it by hand

refuse = groups.set_array_params(m, src, nx=1)
check("SHRINKING PAST A MOVED MEMBER IS REFUSED",
      refuse["status"] == "would_delete_authored" and refuse["changed"] is False, refuse["status"])
check("  nothing was deleted", groups.array_params(m, src)["array"]["member_count"] == 3,
      groups.array_params(m, src)["array"]["member_count"])
_auth = refuse.get("authored_members") or []          # absent entirely if the refusal is removed
check("  the authored member is NAMED, with how far it moved",
      bool(_auth) and _auth[0]["guid"] == outer["guid"] and _auth[0]["offset_m"] >= 7.0, _auth)
check("  and the refusal explains why silence would be worse",
      "looks exactly like one that is working" in (refuse.get("note") or ""), refuse.get("note"))

# an UNMOVED member in the same shrink is not protected — the refusal is about authored work only
check("  the count of would-be deletions is reported alongside",
      (refuse.get("would_delete") or 0) >= len(_auth) and bool(_auth), refuse)

forced = groups.set_array_params(m, src, nx=1, force=True)
check("force=True carries out the deletion the caller was warned about",
      forced["status"] == "ok" and outer["guid"] in forced["removed"], forced)
check("  and records that it was forced", forced["forced"] is True, forced)

# --- 4. THE SOURCE IS NEVER DELETED --------------------------------------------------------------------
check("shrinking to nx=1 leaves ONLY the source",
      groups.array_params(m, src)["array"]["member_count"] == 1,
      groups.array_params(m, src)["array"]["member_count"])
check("  and the source element itself still exists — cell (0,0) is the user's own element",
      _exists(src))

# --- 2. RE-PITCHING LEAVES A HAND-PLACED MEMBER WHERE IT IS ----------------------------------------------
groups.set_array_params(m, src, nx=3, dx=5.0)
info = groups.array_params(m, src)["array"]
mid = next(x for x in info["members"] if (x["i"], x["j"]) == (1, 0))
edit.move_element(m, mid["guid"], 0.0, 9.0, 0.0)
before = groups._origin_of(m.by_guid(mid["guid"]))
rep = groups.set_array_params(m, src, dx=8.0)
after = groups._origin_of(m.by_guid(mid["guid"]))
check("re-pitching does NOT snap a hand-placed member back to the grid", before == after,
      (before, after))
check("  it is reported as kept_moved rather than silently skipped",
      any(x["guid"] == mid["guid"] for x in rep["kept_moved"]), rep["kept_moved"])
check("  with the reason stated", "left where it is" in rep["kept_moved"][0]["note"],
      rep["kept_moved"])
check("  and the new pitch is stored", groups.array_params(m, src)["array"]["dx"] == 8.0)

for f in (TMP,):
    if os.path.exists(f):
        os.remove(f)

print()
if FAILED:
    print(f"array_live: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("array_live: all checks passed")
