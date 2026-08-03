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
                "work_order",
                # R41-CLOSEOUT-OPERATE, 2026-08-02 — these three were the one clause R30 left filed
                # by who PRODUCES a record instead of who USES it. An as-built is the drawing an
                # operator works from for the life of the building; a completion certificate is what
                # the building is handed over with. Reversing it deliberately, with the reasoning in
                # rooms.py next to the table.
                "completion_certificate", "as_built", "lessons_learned"],
    # Schedule is the PLANNER's room: the CPM, the crews, the controls, the closeout. R41-WORK-FIELD
    # took the field registers out of it — it held 38 modules, the most of any room, and this file's
    # own R31 note had already called that "the next thing to fix".
    # the schedule lives in the Schedule room *and* the Schedule section (it did not)
    "schedule": ["schedule_activity", "resource_assignment", "staffing", "risk"],
    # R41-WORK-FIELD, 2026-08-02 — the superintendent's room. Work held ZERO registers before this:
    # no section mapped to it, so it was a tab containing one cross-cutting queue panel and nothing
    # else, which reads to a user as a broken product rather than as a design.
    #
    # Quality moves here on the argument rooms.py ALREADY made when it took Quality out of Design —
    # "an ITP hold point is released by a field engineer standing at the pour, and an NCR is written
    # by a superintendent". That is an argument about the field, and it had been half-applied: the
    # modules landed in Schedule, one room short of the people the reasoning names.
    "work": ["compliance_evidence", "deficiency", "inspection", "itp", "ncr", "test_record",
             "punchlist", "checklist",
             # the safety programme — a field concern, and the user's own call
             "incident", "jha", "toolbox_talk", "safety_violation", "pretask_plan",
             # the day, what got built, and what arrived
             "daily_report", "manpower_log", "timesheet", "progress_actual", "delivery"],
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
            "docs/internal/archive/module-room-audit.md; if it is being changed, change it here too and say why."
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
assert rooms.room_of({"section": "Billing"}) == "cost"
assert rooms.room_of({}) is None
assert rooms.unmapped_sections({"Billing", "Ghost"}) == ["Ghost"]

# a module whose section is unknown is REPORTED, never quietly filed somewhere
odd = rooms.allocate([{"key": "mystery", "section": "Nowhere"}])
assert odd["unplaced_count"] == 1 and odd["unplaced"][0]["key"] == "mystery", odd
assert odd["placed"] == 0

# ---- R31-DESIGN-GROUPS: the room's second level ---------------------------------------------------
# The groups a room is read in ARE its sections. That is the whole design: one table decides the room
# and refines into the sub-rooms, so the two can never disagree. These assertions exist because the
# cheap alternative — a parallel GROUP_OF_SECTION table — would pass a naive test just as well and
# drift within a release.
for r in alloc["rooms"]:
    gs = r["groups"]
    flat = [k for g in gs for k in g["modules"]]
    assert sorted(flat) == sorted(r["modules"]), (
        f"{r['id']}: groups must PARTITION the room — every module in exactly one group. "
        f"missing={sorted(set(r['modules']) - set(flat))} extra={sorted(set(flat) - set(r['modules']))}")
    assert len(flat) == len(set(flat)), f"{r['id']}: a module appears in two groups"
    assert all(g["count"] == len(g["modules"]) for g in gs), f"{r['id']}: a group's count lies"
    # largest first, name as the tie-break — so the heading most likely to be wanted is at the top
    assert gs == sorted(gs, key=lambda g: (-g["count"], g["section"])),         f"{r['id']}: groups out of order: {[g['section'] for g in gs]}"
    assert all(g["section"] for g in gs), f"{r['id']}: a group with no section name"

# THE JUNK DRAWER. `Engineering` held nine Design modules and described none of them — drawings, RFIs,
# submittals, MEP equipment, selections. Harmless while nothing grouped by section; the moment the rail
# rendered "Engineering · 9" as a heading it became a confident label for a filing accident.
#
# Asserted by NAME rather than by a size rule, because size is not the defect: `Field` legitimately
# holds 14 and `Preconstruction` 12. What made these four wrong is that they named nothing a user
# would go looking for — and `Design`, as a section INSIDE the Design room, named nothing at all.
# A SECTION THAT RESTATES ITS ROOM CARRIES NO INFORMATION. Every room had one:
#
#     Design   > Design           Planning > Preconstruction
#     Schedule > Field   ("run the field" is the room's own job line)
#     Schedule > Schedule         Cost     > Cost           Operate > Facilities
#
# The last three were found by THIS assertion, in rooms being edited at the time — the eye slides
# straight past a heading that repeats the tab above it.
#
# Only the literal case is mechanically checkable, and it is checked here. The synonym cases are not,
# and a hand-maintained synonym table is deliberately NOT the answer: it would be another list to
# keep in step, and the term nobody added would be the one that mattered. Those are pinned by name
# below instead, which at least fails loudly if one comes back.
for r in alloc["rooms"]:
    for g in r["groups"]:
        assert g["section"] != r["label"], (
            f"{r['label']} > {g['section']}: a section repeating its room's name tells the user "
            "nothing they did not already know from clicking the room")

for dead in ("Engineering", "BIM", "Design", "Programming", "Field", "Preconstruction", "Facilities"):
    assert dead not in rooms.ROOM_OF_SECTION, (
        f"{dead!r} is back in ROOM_OF_SECTION. It was retired because it was where a module went when "
        "nobody decided, and a section like that is invisible until something groups by it.")

# ---- R32: the cap is a RATCHET over every room, not a Design special case ------------------------
# 8 is not a style rule. It is the size at which a heading stops narrowing anything: `Field` held 14
# and `Preconstruction` 12, and opening either put you back in front of the wall the spine exists to
# replace. A ratchet rather than an allowlist — a new module may join any group, but the moment one
# passes 8 somebody has to decide where the seam is, which is the decision that kept being skipped.
SECTION_MAX = 8
for r in alloc["rooms"]:
    for g in r["groups"]:
        assert g["count"] <= SECTION_MAX, (
            f"{r['label']} > {g['section']} holds {g['count']} modules. Past {SECTION_MAX} a heading "
            f"stops narrowing anything - split it on the seam (what JOB differs), not on the count.")

# Split on the seam, not the size. Cost's change chain was ten and the seam was WHO ACTS: an
# architect issues a change, a contractor prices it. A purely numeric split would have cut the chain
# in a meaningless place.
by_sec = {g["section"]: g for r in alloc["rooms"] for g in r["groups"]}
assert set(by_sec["Change Instruments"]["modules"]) == {"asi", "bulletin", "sketch", "directive"},     by_sec["Change Instruments"]["modules"]
assert "change_event" in by_sec["Change Management"]["modules"], (
    "change_event is the FIRST link of the change chain and was filed under Cost, apart from the "
    "rest of the chain it starts")

design = next(r for r in alloc["rooms"] if r["id"] == "design")
assert design["count"] == 32, design["count"]
biggest = design["groups"][0]
assert biggest["count"] <= SECTION_MAX, f"Design's largest is {biggest['section']} at {biggest['count']}"
assert {g["section"] for g in design["groups"]} == {
    "Model", "Drawings", "Specifications", "Design Phases", "Coordination",
    "Information Management", "Sustainability", "Resilience"}, [g["section"] for g in design["groups"]]

# the modules that moved, by name, so a later bulk edit cannot quietly undo the reasoning
for key, sec in [("drawing", "Drawings"), ("drawing_set", "Drawings"), ("transmittal", "Drawings"),
                 ("rfi", "Coordination"), ("submittal", "Coordination"), ("clash_run", "Coordination"),
                 ("envelope_assembly", "Model"), ("mep_equipment", "Model"), ("space_program", "Model"),
                 ("selection", "Specifications"), ("design_standard", "Specifications"),
                 ("design_review", "Design Phases"), ("concept_render", "Design Phases")]:
    got = next(m["section"] for m in mods if m["key"] == key)
    assert got == sec, f"{key} is sectioned {got!r}, expected {sec!r}"

# the R32 moves, by name — the reasoning is in rooms.py; this is what stops a bulk edit undoing it
for key, sec in [("timesheet", "Daily Log"), ("photo", "Daily Log"), ("daily_report", "Daily Log"),
                 ("progress_actual", "Progress"), ("field_verification", "Progress"),
                 ("delivery", "Logistics"), ("prefab_kit", "Logistics"),
                 ("punchlist", "Quality"), ("checklist", "Quality"),
                 ("bid_package", "Bidding"), ("estimate", "Estimating"),
                 ("responsibility", "Project Governance"), ("decision", "Project Governance"),
                 ("change_event", "Change Management"), ("asi", "Change Instruments"),
                 ("schedule_activity", "Sequencing"), ("staffing", "Resourcing"),
                 ("sov", "Billing"), ("owner_invoice", "Billing"), ("budget", "Budget & Actuals"),
                 ("work_order", "Maintenance"), ("meter", "Performance"),
                 ("fca_element", "Condition & Capital")]:
    got = next(m["section"] for m in mods if m["key"] == key)
    assert got == sec, f"{key} is sectioned {got!r}, expected {sec!r}"

# `punchlist` moving to Quality is a promise rooms.py ALREADY made and did not keep: its own note
# calls deficiency and ncr "near-twins of punchlist". A stated reason nothing acts on is how twins
# come to live in different sections.
for twin in ("deficiency", "ncr", "punchlist"):
    assert next(m["section"] for m in mods if m["key"] == twin) == "Quality", twin

# ---- no test may pin a module's SECTION -----------------------------------------------------------
# R32 renamed five sections and broke `test_pm_close`, which asserted
# `REGISTRY["project_charter"]["section"] == "Preconstruction"`. That assertion was standing in for
# REACHABILITY — "this module is filed somewhere a user can get to" — and said it by naming an
# implementation detail, so it failed in CI having tested nothing that actually changed.
#
# I found it the expensive way. My scan for `section` consumers covered `services/api/src` and
# `apps/web/src` and **not `test_*.py`**, which is where the only stale one lived. A search that
# excludes the test tree will keep missing exactly this.
#
# The room is the durable claim; the section is free to move. This forbids the proxy so the next
# rename cannot cost a CI cycle. `spec_section`, code sections and steel sections are entirely
# different meanings of the word and are not matched — that ambiguity is itself a live hazard here.
import re  # noqa: E402
from pathlib import Path  # noqa: E402

_PIN = re.compile(r'REGISTRY\[[^\]]+\]\[.section.\]\s*==')
for _t in sorted(Path(".").glob("test_*.py")):
    if _t.name == "test_module_rooms.py":
        continue
    _hit = _PIN.search(_t.read_text(encoding="utf-8"))
    assert not _hit, (
        f"{_t.name} pins a module's `section` ({_hit.group(0)}). A section is an implementation "
        "detail and renaming one must not break a distant suite — assert `rooms.room_of(mod)` "
        "instead, which is the reachability claim the pin was standing in for.")

# ---- the FIFTH taxonomy: report categories ------------------------------------------------------
# The redesign's premise was that seven workspaces carried four left-rail taxonomies. `reports.py`
# carries a fifth, invisible because it renders in a different panel — and three of its categories
# named sections that had been retired (`Preconstruction`, `Field`, `Engineering`), so eleven reports
# were filed under places the product no longer has.
#
# NOT forced into full agreement: `Executive`, `Logs`, `Health`, `Capital` and `Disposition` group by
# AUDIENCE and purpose, a legitimately different axis from where a register lives. The rule is only
# that a category may not name a place that does not exist.
from aec_api import reports  # noqa: E402

PURPOSE_CATEGORIES = {"Logs", "Executive", "Health", "Capital", "Disposition"}
live_vocab = set(rooms.ROOM_OF_SECTION) | {r["label"] for r in rooms.ROOMS} | PURPOSE_CATEGORIES
stale = sorted({c for _, c in reports.REPORTS.values()} - live_vocab)
assert not stale, (
    f"report categories naming neither a live section, a room, nor a purpose: {stale}. A report filed "
    "under a retired section is a heading the user cannot reach from anywhere else.")

# A room the rail will subgroup (>= SUBGROUP_MIN, the web constant) must have groups worth reading.
# `schedule` holds 38 in six sections and is the next room to look at; this asserts the mechanism
# reaches it rather than being a one-room special case.
for r in alloc["rooms"]:
    if r["count"] >= 8:
        assert len(r["groups"]) > 1, f"{r['id']} has {r['count']} modules in a single group"

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
