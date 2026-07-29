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
# v0.3.766 renamed Model -> Design and split Planning out of Cost. Both were deliberate, and both
# broke this line first, which is what it is here for: "Model" named one *output* of that room, so
# drawings and specifications read as though they lived elsewhere — and specifications actually did,
# filed under Preconstruction and therefore under Cost. Planning split for the mirror-image reason:
# taking off and buying out are preconstruction work, and sharing a room with the general ledger put
# a quantity surveyor and an accounts clerk behind the same tab.
#
# R30 added **Operate** as the seventh, between Schedule and Deal. Facilities management had been
# sectioned "Operations" and therefore filed under Deal, so the registers that accrue the most records
# over an asset's life lived in a room whose stated job is underwriting and disposition.
#
# The ORDER is the user's, set 2026-07-29: the deal first because it authorizes everything after it,
# the finished asset last because operating it is the longest phase. It is the *unweighted* order —
# `orderRooms()` promotes a workspace's own room to the front, so a Construction user still opens on
# Schedule. `roomNames.test.ts` asserts this same sequence with toEqual across the language boundary.
assert [r["id"] for r in rooms.ROOMS] == ["deal", "design", "planning", "schedule", "cost",
                                          "work", "operate"]
# professional terms are primary — this was an explicit decision, and a rename should break the test
assert [r["label"] for r in rooms.ROOMS] == ["Deal", "Design", "Planning", "Schedule", "Cost",
                                             "Work", "Operate"]
for r in rooms.ROOMS:
    assert len(r["job"]) > 25, f"{r['id']} needs a plain statement of what it is for"

# ---- THE ALLOCATION ITSELF, not just its wellformedness ------------------------------------------
# The gate above proves every module has *a* room. It cannot tell you the module has the *right* one,
# and that is the failure the audit actually found: `work_order` was reachable the whole time, from
# Deal, and being reachable is what made it invisible as a defect. So the specific placements that
# were argued for are asserted by name. Moving one of these is then a deliberate edit to a test with
# the reasoning next to it, rather than a section string changed in passing.
ROOM_OF_MODULE = {
    # Operate exists for these. If one drifts back to Deal or Schedule, say so loudly.
    "operate": ["asset_register", "building_system", "capital_plan", "commissioning", "fca_element",
                "meter", "meter_reading", "om_manual", "pm_schedule", "poe", "warranty",
                "work_order"],
    # Quality is executed in the field, not drawn in the design room.
    "schedule": ["compliance_evidence", "deficiency", "inspection", "itp", "ncr", "test_record",
                 # the schedule lives in the Schedule room *and* the Schedule section (it did not)
                 "schedule_activity", "resource_assignment", "staffing", "risk"],
    # One approvals spine; rate libraries and the vendor book feed estimating, not sequencing.
    "planning": ["permit", "entitlement", "cost_code", "labor_rate", "material_rate",
                 "equipment_rate", "price_observation", "company", "contact"],
    # Equity is a deal, not a ledger entry.
    "deal": ["investor", "lease", "cam_expense"],
}
for room_id, keys in ROOM_OF_MODULE.items():
    for key in keys:
        assert seen.get(key) == room_id, (
            f"{key} is in {seen.get(key)!r}, expected {room_id!r}. This placement was argued for in "
            "docs/module-room-audit.md; if it is being changed, change it here too and say why."
        )

# Sections that were retired, and must not come back by copy-paste. Each had exactly one problem:
# "Resources" sounded like resource loading and held a rate library; "Capital" was a one-module
# section whose module belonged to Deal.
for dead in ("Resources", "Capital"):
    assert dead not in rooms.ROOM_OF_SECTION, f"{dead!r} was retired in R30 — see the audit"
    assert dead not in sections, f"a module is still sectioned {dead!r}"

# Every mapped section is actually used. A section→room entry with no modules is a decision nobody
# can see the effect of, and it is how the table silently accumulates fiction.
unused = sorted(set(rooms.ROOM_OF_SECTION) - sections)
assert not unused, f"ROOM_OF_SECTION maps {unused}, which no module uses"

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
