"""R26-MODULE-HOME — one canonical room per module.

The redesign's first finding is that seven workspaces carry **four different left-rail taxonomies**,
so nothing a user learns in one transfers to the next — and modules land in more than one of them
(Facility Condition appears twice in the Developer rail alone). The fix is one constant spine of five
rooms, with every module having exactly **one** canonical home and being referenced, never re-listed,
anywhere else.

**Why the mapping lives here rather than in 132 `module.json` files.** `module_schema` is the single
source of truth for a module's shape, and every module already declares a `section`. A room is a
property of the *section*, not of each module, so deriving it from one table means a new module
inherits a room automatically and cannot be added to two rooms by an editing slip. It also means the
allocation can be reviewed as a single readable list instead of by grepping a hundred files.

**A section with no room fails the gate rather than defaulting.** A default would make a
mis-sectioned module silently unreachable — which is exactly the failure an IA restructure is most
likely to cause and least likely to notice. Same rule the rest of the codebase follows: the absence
of an answer is not an answer.

**ROOM-NAMING — settled 2026-07-29: professional terms, not plain language.** The prototype named
these Building · Budget · Timeline · Money · My to-do. We ship **Deal · Design · Planning · Schedule
· Cost · Work · Operate**, and this is now a decision rather than an open question.

The reason is not formality. *These are the words the work already has*: an architect issues a
**design**, a contractor runs a **schedule** and reports **cost**, a developer works a **deal**.
Plain labels read as friendlier right until someone has to decide whether "Money" means the budget,
the commitment, the pay application or the equity draw — at which point the friendly word is a second
vocabulary layered on the real one. A tool for professionals that renames their own domain is harder
to use in exactly the moments that matter.

The labels are duplicated in `apps/web/src/shell/spine.ts` (`FALLBACK_ROOMS`), which is what renders
when `/rooms` fails — load-bearing since the classic shell was deleted in v0.3.779. Two tables
encoding one decision drift, so `roomNames.test.ts` reads THIS file and asserts they agree on **id,
label AND `job`**, in order, and that no prototype name has crept back.

The `job` half was added on 2026-07-29 after it drifted within a day of the labels being guarded:
Approvals moved into Planning, this file widened Planning's job to "…and get it approved", and the
fallback still said "…buy it out and contract it" — green the whole time. A gate measures what it was
written for and stays silent about the thing beside it, so the fix is to widen the gate rather than to
remember harder.

**R30-OPERATE — the seventh room, added 2026-07-29.** Facilities management was filed under
`Operations` and therefore under **Deal**, so a technician logging a work order opened a room labelled
*"Underwrite it, fund it, lease it and dispose of it"*. Eight registers — `work_order`, `pm_schedule`,
`meter`, `meter_reading`, `building_system`, `fca_element`, `poe`, `capital_plan` — were doing a job
the room they lived in did not describe, and they are the registers that accrue the most records over
an asset's life. The platform already serves that job deeply (`cmms.py`, `fca.py`, `reserve.py`,
`twin.py`, `energy.py`), so the room was the only thing missing.

The same change reunites the **handover package** with its consumer. `asset_register`, `om_manual`,
`warranty` and `commissioning` were filed under `Closeout` — the end of the construction sequence,
which is where they are *produced* — while every system that reads them sits in operations. That is
the COBie chain (assets, warranties, spares, PM schedules moving into the CMMS on day one) cut in half
by a room boundary. They move to a `Handover` section in **operate**; what genuinely belongs to the
end of construction — `completion_certificate`, `as_built`, `lessons_learned` — stays in `Closeout`.

**R41 (2026-08-02) reversed that last clause**, and the reversal is instructive because R30 made the
right argument and then stopped one step short of it. R30 saw that filing the handover package by
*when it is produced* severed it from *who consumes it* — and left `Closeout` filed by exactly that
rule. `Closeout` is now **operate** too; see the note on the section itself. The same change gave
**work** its contents: it had none at all.
"""
from __future__ import annotations

from typing import Any

#: The seven rooms. Professional terms are primary — the users are builders, developers, architects
#: and engineers who already own the vocabulary; there is deliberately no second string table.
#:
#: **Order is the user's, set 2026-07-29**: the deal comes first because it is what authorizes
#: everything after it, and the finished asset comes last because operating it is the longest and
#: final phase. This is the *unweighted* order — `orderRooms()` promotes a workspace's own room to
#: the front, so a Construction user still sees Schedule first. That is the spine weighting working,
#: not a bug.
ROOMS: list[dict[str, str]] = [
    {"id": "deal", "label": "Deal",
     "job": "Underwrite it, fund it, lease it and dispose of it"},
    {"id": "design", "label": "Design",
     "job": "Model it, draw it, specify it — the architect's and engineer's room"},
    {"id": "planning", "label": "Planning",
     "job": "Take it off, estimate it, bid it, buy it out, contract it and get it approved"},
    {"id": "schedule", "label": "Schedule",
     "job": "Sequence it, resource it and control it — the plan for time"},
    {"id": "cost", "label": "Cost",
     "job": "Budget it, change it, bill it and account for it"},
    {"id": "work", "label": "Work",
     "job": "Run the field — your court today, the log, safety, progress and the punch"},
    {"id": "operate", "label": "Operate",
     "job": "Hand it over, maintain it, meter it and plan its renewal"},
]
ROOM_IDS = {r["id"] for r in ROOMS}

#: section → room. Every section present in `services/api/modules/*/module.json` must appear here;
#: `test_module_rooms` fails the build if one is missing, so a new section is a deliberate decision
#: rather than an accident.
ROOM_OF_SECTION: dict[str, str] = {
    # ── Design: the building and everything that describes it ───────────────────────────────────
    # Named for the *discipline*, not the artifact. "Model" described one output of this room and
    # left drawings and specifications looking like they belonged somewhere else — which is exactly
    # where specifications had ended up (filed under Preconstruction, and therefore under Cost).
    # An architect or engineer does all of it here: model, draw, specify, analyse.
    #
    # R31-DESIGN-GROUPS (2026-07-31): the sections BELOW are also the groups Design is read in, so the
    # list is short and each entry names something an architect or engineer would recognise as a place
    # to go. Four sections were retired to get there, and the reason is worth keeping:
    #
    # **"Engineering" held nine modules and described none of them** — `drawing`, `drawing_set` and
    # `drawing_issuance` (documents), `rfi` and `submittal` (coordination), `design_review` and
    # `selection` (design process), `envelope_assembly` and `mep_equipment` (model content). It was
    # not a section, it was the place a module went when nobody decided. `Design`, `BIM` and
    # `Programming` were the same failure at smaller scale: `Design`, inside the Design room, carried
    # no information at all.
    #
    # A junk-drawer section is invisible while nothing groups by it. The moment the room rail started
    # rendering groups, "Engineering (9)" became a heading a user would open expecting engineering.
    "Model": "design",               # the building as modelled, and the space program it satisfies
    "Drawings": "design",            # the drawn documents and their issue record
    "Specifications": "design",      # the written half of the documents; the drawings are the other
    "Design Phases": "design",       # options, reviews, renders — the design as it develops
    "Coordination": "design",        # RFIs, submittals, clashes — raised AGAINST the documents, so
                                     # they sit beside the documents
    "Information Management": "design",   # LOD, information requirements, the CDE — ISO 19650 work
    "Sustainability": "design",
    "Resilience": "design",
    # ── Planning: turning a design into a bought, contracted, approved scope ────────────────────
    # Split out of Cost. Estimating, taking off and buying out are *planning* work with an outcome
    # in money — filing them under Cost put a quantity surveyor and an accounts clerk in one room,
    # and buried the takeoff a preconstruction lead uses daily under a general ledger they never open.
    # R32 (2026-07-31): "Preconstruction" held twelve and described eight of them. `assumption`,
    # `decision`, `project_charter` and `responsibility` are project GOVERNANCE — they run for the
    # whole job, and calling them a phase of it is what buried a RACI matrix and a decision log under
    # a heading a preconstruction lead owns and a project manager never opens.
    "Bidding": "planning",
    "Estimating": "planning",
    "Project Governance": "planning",
    "Contracts": "planning",
    # Approvals are one spine — zoning, entitlement, permit, certificate of occupancy are successive
    # gates on the same path — and they had been cut in two: `permit` sat under Engineering (design)
    # and `entitlement` under Acquisition (deal), so the two halves of one chase never met.
    "Approvals": "planning",
    # Rate libraries and the vendor book are *reference data* consumed by estimating and buyout. They
    # spent the last revision in Schedule because the section was called "Resources", which sounded
    # like resource loading and is not.
    "Reference Data": "planning",
    "Directory": "planning",
    # ── Cost: money against the building, once the scope is bought ──────────────────────────────
    # R32: `Cost ▸ Cost`, the third one this change's own rule found. The seam is direction of
    # money: what the job is expected and committed to spend, versus what is being billed to the
    # owner and by the subs. `sov` sits with billing because a schedule of values IS the basis of a
    # pay application — see MOD-G702.
    "Budget & Actuals": "cost",
    "Billing": "cost",
    # R32: the change chain held ten under one heading. The seam is who acts: an architect ISSUES a
    # change (ASI, bulletin, sketch, construction change directive), a contractor PRICES it (change
    # event → PCO → proposal → COR, plus the T&M tickets that carry the work). Split on that rather
    # than on the count — a group is worth a heading when it names a different job, not when it gets
    # long.
    "Change Instruments": "cost",
    "Change Management": "cost",
    # ── Schedule: time, the field that consumes it, and the quality of what it produces ─────────
    # R32: `Schedule ▸ Schedule` was caught by this change's OWN new rule — a section repeating its
    # room's name, in the room being edited at the time. The seam is CPM/Last-Planner sequencing
    # versus who is assigned to it: one answers "when", the other "by whom", and they are maintained
    # by different people on different cadences.
    "Sequencing": "schedule",
    "Resourcing": "schedule",
    "Project Controls": "schedule",
    # ── Work: running the field ─────────────────────────────────────────────────────────────────
    # R41-WORK-FIELD (2026-08-02). **Work held NOTHING.** No section mapped to it: it was a room
    # containing one cross-cutting panel (the ball-in-your-court queue) and zero registers, so a user
    # who opened it saw an empty room and reasonably concluded the product was broken.
    #
    # The cause was that "Work" is ambiguous and the code took the narrower reading — *"my work"*, a
    # personal inbox ("Whatever is in your court right now") — while every user reads the tab as
    # *"the work"*: the field, the jobsite, what the crews are doing. The second reading is the one
    # worth having, because it also answers a defect this file had already recorded about itself:
    # Schedule held **38 modules**, the most of any room, and the R31 note below says in as many
    # words that "the sections there are the next thing to fix".
    #
    # The seam is who maintains the record, and it is the sharpest one in the product: **Schedule is
    # the planner's room** (the CPM, the crews, the controls, the closeout), **Work is the
    # superintendent's** (today's log, the safety programme, what got built, what arrived, the
    # punch). A scheduler and a superintendent are different people on different cadences, and until
    # now they shared one 38-item rail.
    #
    # The queue is not lost — it stays as Work's HOME panel (`ROOM_HOME.work = "__workqueue__"`),
    # which is exactly right: open the field room and see your plate before the registers.
    "Daily Log": "work",             # what happened today — reports, manpower, equipment, hours, photos
    "Progress": "work",              # what got BUILT, and whether it is verifiably where it should be
    "Logistics": "work",             # material and fabrication arriving on site
    "Safety": "work",                # the field safety programme — JHAs, toolbox talks, incidents
    # Quality follows the argument this file ALREADY made when it moved Quality out of Design: "an
    # ITP hold point is released by a field engineer standing at the pour, and an NCR is written by a
    # superintendent". That is an argument about the FIELD, and it was half-applied — the modules
    # landed in Schedule, one room short of the people the reasoning names.
    "Quality": "work",
    # ── Operate: the asset in service, which is most of its life ────────────────────────────────
    "Handover": "operate",           # what operations *receives*; see the R30 note above
    # R41-CLOSEOUT-OPERATE (2026-08-02) — **this reverses the R30 note above, deliberately.** That
    # note kept `completion_certificate`, `as_built` and `lessons_learned` in Closeout under
    # Schedule, reasoning that they are what construction *finishes*. True of who PRODUCES them and
    # false of who USES them, which is the same half-applied argument R30 itself caught with the
    # handover package: an as-built is the drawing an operator works from for thirty years, and a
    # completion certificate is the legal artifact the building is handed over WITH. Filing them by
    # the moment they are produced put the whole turnover set one room away from everyone who reads
    # it — and left the COBie chain cut in the same place R30 had just repaired it.
    #
    # Schedule keeps sequencing, resourcing and controls: the plan for time, not its end artifacts.
    "Closeout": "operate",
    # R32: "Facilities" is an honest name for eight modules doing three jobs — fixing things,
    # tracking their condition and the capital to renew them, and measuring how the building
    # performs. `work_order` is the highest-volume register in the product over an asset's life, and
    # it was one of eight bullets under a heading naming the department rather than the work.
    "Maintenance": "operate",
    "Condition & Capital": "operate",
    "Performance": "operate",
    # ── Deal: the asset as an investment ────────────────────────────────────────────────────────
    "Acquisition": "deal",
    "Feasibility": "deal",
    "Finance": "deal",
    "Market & Sales": "deal",
    "Operations": "deal",            # leasing and recoveries — the landlord's half of owning it
}


def room_of_section(section: str) -> str | None:
    """The room a section belongs to, or None when the section is unmapped (which is a failure)."""
    return ROOM_OF_SECTION.get(str(section or "").strip())


def room_of(module: dict[str, Any]) -> str | None:
    return room_of_section(str((module or {}).get("section") or ""))


def unmapped_sections(sections: set[str]) -> list[str]:
    """Sections with no room. A non-empty result must fail a build, not warn."""
    return sorted(s for s in sections if s and s not in ROOM_OF_SECTION)


#: R31-DESIGN-GROUPS — a room's second level of navigation.
#:
#: Design held 32 modules as ONE flat alphabetical list, from `action_item` to `waste_diversion`. A
#: list that long is not navigation, it is a search box you have to read. (`schedule` holds 38 and has
#: the same problem; this ships the mechanism, and the sections there are the next thing to fix.)
#:
#: **The group IS the section — there is no second table.** The obvious move was a new
#: `GROUP_OF_SECTION` mapping, and it was the wrong one: this file's own argument for deriving rooms
#: from sections is that one table cannot disagree with itself, and adding a parallel table to slice
#: the same modules a second way gives up exactly that. So where a section was too vague to be a
#: heading, the SECTION was fixed rather than papered over with a group name.
#:
#: Ordered largest-first with a stable tie-break on the name. Not alphabetical: the heading a user is
#: most likely to want should not sit below one holding three modules because it starts with a later
#: letter. Not hand-ordered either — a hand-ordered list is a fourth place to keep in step.
def _groups(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [{"section": sec, "count": len(keys), "modules": keys}
            for sec, keys in sorted(sections.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def allocate(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """Group modules into rooms, and report anything that could not be placed.

    `unplaced` is the number an IA restructure lives or dies on: a module with no room is a module a
    user can no longer reach, and it would otherwise be invisible until someone went looking for it.
    """
    by_room: dict[str, list[str]] = {r["id"]: [] for r in ROOMS}
    by_group: dict[str, dict[str, list[str]]] = {r["id"]: {} for r in ROOMS}
    unplaced: list[dict[str, str]] = []
    for m in modules or []:
        key = str(m.get("key") or m.get("name") or "?")
        room = room_of(m)
        if room in by_room:
            by_room[room].append(key)
            by_group[room].setdefault(str(m.get("section") or ""), []).append(key)
        else:
            unplaced.append({"key": key, "section": str(m.get("section") or "")})
    for k in by_room:
        by_room[k].sort()
        for g in by_group[k].values():
            g.sort()
    return {
        "rooms": [{**r, "count": len(by_room[r["id"]]), "modules": by_room[r["id"]],
                   "groups": _groups(by_group[r["id"]])} for r in ROOMS],
        "placed": sum(len(v) for v in by_room.values()),
        "unplaced": sorted(unplaced, key=lambda u: u["key"]),
        "unplaced_count": len(unplaced),
        "note": ("Every module has exactly one canonical room; it may be REFERENCED from elsewhere "
                 "but is never re-listed under a second heading. An unmapped section is a failure, "
                 "not a default — a silently unreachable module is the defect an IA change is most "
                 "likely to cause and least likely to notice."),
    }
