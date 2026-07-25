"""R26-MODULE-HOME / R26-V-REACH — every module has exactly one canonical room, and none is lost.

The redesign's first finding: seven workspaces carry four different left-rail taxonomies, so nothing
learned in one transfers to the next, and modules land in more than one — Facility Condition appears
twice in the Developer rail alone, Climate Resilience in three workspaces, Model Health three times on
a single screen.

The fix is one spine of five rooms with a single canonical home per module. **The risk that fix
introduces is losing a module**: an IA restructure is most likely to make something silently
unreachable, and least likely to notice. This test is the gate that makes that impossible — it reads
the modules on disk, not a hand-maintained list, so a new module cannot be added without a room.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_rooms.py
"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_module_rooms.db"
os.environ["STORAGE_DIR"] = "./test_storage_module_rooms"
if os.path.exists("./test_module_rooms.db"):
    os.remove("./test_module_rooms.db")

from aec_api import rooms  # noqa: E402

MODULES_DIR = os.path.join(os.path.dirname(__file__), "modules")

# ---- read the modules from DISK, so the gate cannot drift from reality ---------------------------
mods = []
for name in sorted(os.listdir(MODULES_DIR)):
    p = os.path.join(MODULES_DIR, name, "module.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        mods.append({"key": d.get("key") or name, "section": d.get("section") or "",
                     "name": d.get("name") or name})

assert len(mods) >= 130, f"expected the full module set, read {len(mods)}"

# ---- THE GATE: every section maps to a room, and every module lands in exactly one ---------------
sections = {m["section"] for m in mods}
missing = rooms.unmapped_sections(sections)
assert not missing, (
    f"{len(missing)} section(s) have no room: {missing}. A section with no room means every module in "
    "it is unreachable from the spine — add it to ROOM_OF_SECTION deliberately rather than letting it "
    "default, because a default hides exactly this."
)

alloc = rooms.allocate(mods)
assert alloc["unplaced_count"] == 0, alloc["unplaced"]
assert alloc["placed"] == len(mods), (alloc["placed"], len(mods))

# every module appears in exactly ONE room — the duplication the audit found must be impossible
seen: dict[str, str] = {}
for r in alloc["rooms"]:
    for key in r["modules"]:
        assert key not in seen, f"{key} is in both {seen[key]} and {r['id']} — one canonical home only"
        seen[key] = r["id"]
assert len(seen) == len(mods), (len(seen), len(mods))

# ---- the spine itself ----------------------------------------------------------------------------
assert [r["id"] for r in rooms.ROOMS] == ["model", "cost", "schedule", "deal", "work"]
# professional terms are primary — this was an explicit decision, and a rename should break the test
assert [r["label"] for r in rooms.ROOMS] == ["Model", "Cost", "Schedule", "Deal", "Work"]
for r in rooms.ROOMS:
    assert len(r["job"]) > 25, f"{r['id']} needs a plain statement of what it is for"

# no room may be empty except Work, which holds records rather than modules — a room nobody can fill
# is a tab that always disappoints
for r in alloc["rooms"]:
    if r["id"] != "work":
        assert r["count"] > 0, f"room {r['id']} has no modules"

# ---- unmapped sections are a FAILURE, not a default ----------------------------------------------
assert rooms.room_of_section("Not A Real Section") is None
assert rooms.room_of_section("") is None
assert rooms.room_of({"section": "Cost"}) == "cost"
assert rooms.room_of({}) is None
assert rooms.unmapped_sections({"Cost", "Ghost"}) == ["Ghost"]

# a module whose section is unknown is REPORTED, never quietly filed somewhere
odd = rooms.allocate([{"key": "mystery", "section": "Nowhere"}])
assert odd["unplaced_count"] == 1 and odd["unplaced"][0]["key"] == "mystery", odd
assert odd["placed"] == 0

counts = {r["id"]: r["count"] for r in alloc["rooms"]}
print(f"R26-MODULE-HOME OK - all {len(mods)} modules resolve to exactly one canonical room "
      f"({counts}), read from the module.json files on disk rather than a hand-maintained list, so a "
      "new module cannot be added without deciding where it lives. This is the gate that makes the IA "
      "restructure safe: the redesign found the same module listed in several rails at once - Facility "
      "Condition twice in the Developer rail alone, Climate Resilience in three workspaces - and the "
      "opposite failure, a module that becomes silently unreachable, is what a restructure is most "
      "likely to cause and least likely to notice. The room is derived from the SECTION rather than "
      "stored per module, so one readable table decides the allocation and an editing slip cannot put "
      "a module in two rooms. A section with no room is a hard failure rather than a default, because "
      "defaulting is precisely what would hide an unreachable module.")
