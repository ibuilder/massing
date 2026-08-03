"""R22-ENTITLEMENT ① — conditions of approval as tracked items, and the one it must never satisfy.

Premise-check first: three of the ring entry's four clauses were already built — jurisdiction packs
(`jurisdiction_packs.validate`), review cycles (the `entitlement` register's own workflow plus
`permit_timeline`), and comment responses (`submittals.py`). The entry's "nothing spans approval" is
stale. The fourth clause, conditions carried into the model as constraints, is real — and starts
earlier than the entry assumes, because `entitlement.conditions` is a single **textarea**.

The assertions:

1. **an uninterpretable condition is UNPARSED, never satisfied.** An approval condition silently
   treated as met is a building constructed out of compliance while the report said it was fine.
   Nothing here marks anything discharged on its own;
2. **an extracted quantity carries its source sentence** — parsing an agency's prose is extraction,
   not authority, and a "45" read out of "45 dwelling units" must be checkable by a human;
3. **an APPROVED entitlement with an empty conditions field is `unrecorded`, not unconditioned** —
   absence of evidence reported as absence of evidence;
4. **the twin**: splitting must actually split. A tracker that returns one blob has done nothing.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_approval_conditions.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.approval_conditions import (  # noqa: E402
    STATUS_DISCHARGED,
    STATUS_UNPARSED,
    STATUS_UNRECORDED,
    assess,
    parse,
    split_conditions,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


NUMBERED = """1. Maximum building height shall not exceed 45 feet.
2. Provide a minimum front setback of 20 ft.
3) Applicant shall provide 1.5 parking spaces per unit.
(4) A landscape buffer of 10 feet shall be installed along the north property line.
5. Applicant shall comply with all applicable requirements of the City Engineer."""

# --- 4. THE TWIN: SPLITTING MUST ACTUALLY SPLIT --------------------------------------------------------
parts = split_conditions(NUMBERED)
check("an enumerated blob splits into its conditions", len(parts) == 5, len(parts))
check("  and the enumerator is stripped, leaving the condition text",
      parts[0].startswith("Maximum building height"), parts[0])
check("  mixed enumerator styles (1. / 3) / (4)) all split",
      parts[2].startswith("Applicant shall provide") and parts[3].startswith("A landscape buffer"),
      parts[2:4])
check("blank-line paragraphs split when there are no enumerators",
      len(split_conditions("First condition here.\n\nSecond condition here.")) == 2)
check("a single unenumerated blob stays ONE condition, not guessed apart by sentence",
      len(split_conditions("Applicant shall comply with Fig. 3 of the plan set. No exceptions.")) == 1,
      split_conditions("Applicant shall comply with Fig. 3 of the plan set. No exceptions."))
check("empty text yields no conditions at all", split_conditions("") == [])

# --- 2. QUANTITIES CARRY THEIR SOURCE ------------------------------------------------------------------
items = parse(NUMBERED)
h = items[0]
check("a height quantity is extracted", h["quantities"][0]["value"] == 45.0, h["quantities"])
check("  with the unit as written", h["quantities"][0]["unit"] == "feet", h["quantities"][0])
check("  and the SOURCE TEXT it came from, so a person can check the reading",
      "height" in h["quantities"][0]["source_text"], h["quantities"][0]["source_text"])
check("  the condition is topic-tagged", h["topic"] == "height", h["topic"])
check("a parking condition is tagged parking", items[2]["topic"] == "parking", items[2]["topic"])
check("a landscape condition is tagged landscape", items[3]["topic"] == "landscape", items[3]["topic"])
# Extraction allows ONE descriptive word between the number and its unit. Strict adjacency was the
# first cut and it was too strict for how agencies actually write — "20 parking spaces", "45 dwelling
# units" and "1.5 parking spaces per unit" all extracted NOTHING, so every parking condition came
# back unreadable (found by R22-ENTITLEMENT ②'s checks). Safety is not "refuse to read": it is that
# `topic` must agree with the unit family, and that every quantity carries its source_text — a wrong
# reading is then visible rather than silent.
_far = parse("Project limited to 45 dwelling units.")[0]
check("one descriptive word between number and unit still extracts — real agencies write this way",
      _far["quantities"][0]["value"] == 45.0 and _far["quantities"][0]["unit"] == "units",
      _far["quantities"])
check("  and it is read as UNITS, not as a height — the unit is taken as written",
      _far["quantities"][0]["unit"] == "units")
check("  with the source text, so a wrong reading is visible rather than silent",
      "dwelling" in _far["quantities"][0]["source_text"], _far["quantities"][0]["source_text"])
check("'20 parking spaces' extracts 20 spaces — the phrasing that broke strict adjacency",
      parse("Provide a minimum of 20 parking spaces.")[0]["quantities"][0]["unit"] == "spaces",
      parse("Provide a minimum of 20 parking spaces.")[0]["quantities"])
check("  a landscape condition containing 'installed' is NOT tagged parking (stall/installed)",
      parse("A landscape buffer shall be installed.")[0]["topic"] == "landscape",
      parse("A landscape buffer shall be installed.")[0]["topic"])

# --- 1. NOTHING IS EVER SATISFIED BY THIS CODE ---------------------------------------------------------
check("NO condition is discharged by parsing — discharge is a human act",
      all(i["status"] != STATUS_DISCHARGED for i in items),
      [i["status"] for i in items])
vague = parse("Applicant shall satisfy the Director prior to issuance.")[0]
check("a condition with no topic and no quantity is UNPARSED",
      vague["status"] == STATUS_UNPARSED, vague)
check("  and explicitly NOT satisfied", vague["status"] != STATUS_DISCHARGED)
check("  with a note saying a person must read it",
      "must be reviewed by a person" in vague["note"], vague["note"])

ENT = {"id": "e1", "ref": "ENT-001", "workflow_state": "approved", "data": {"conditions": NUMBERED}}
a = assess(ENT)
check("assess tracks every condition", len(a["conditions"]) == 5, len(a["conditions"]))
check("  the vague one is counted as unparsed", a["unparsed_count"] == 1, a["counts"])
check("  and the report says an unread condition is not a met one",
      "out of compliance" in a["note"], a["note"])
check("  nothing is fully discharged out of the box", a["fully_discharged"] is False)

d = assess(ENT, discharged_seqs={1, 2, 3, 4})
check("a person CAN discharge a parsed condition — the twin of the refusal",
      d["discharged_count"] == 4, d["counts"])
check("  but an UNPARSED condition cannot be discharged even when named",
      assess(ENT, discharged_seqs={1, 2, 3, 4, 5})["counts"].get(STATUS_UNPARSED) == 1,
      assess(ENT, discharged_seqs={1, 2, 3, 4, 5})["counts"])
check("  so an approval with an unreadable condition is never fully discharged",
      assess(ENT, discharged_seqs={1, 2, 3, 4, 5})["fully_discharged"] is False)

allp = {"id": "e2", "ref": "ENT-002", "workflow_state": "approved",
        "data": {"conditions": "1. Maximum height 30 ft.\n2. Provide 10 parking spaces."}}
check("an approval whose every condition IS discharged reports fully_discharged",
      assess(allp, discharged_seqs={1, 2})["fully_discharged"] is True,
      assess(allp, discharged_seqs={1, 2}))

# --- 3. APPROVED WITH NO CONDITIONS RECORDED IS `unrecorded`, NOT CLEAN ---------------------------------
blank = assess({"id": "e3", "ref": "ENT-003", "workflow_state": "approved",
                "data": {"conditions": ""}})
check("an APPROVED entitlement with no conditions text is UNRECORDED",
      blank["status"] == STATUS_UNRECORDED, blank["status"])
check("  and says a blank field usually means nobody typed them",
      "nobody typed them" in blank["note"], blank["note"])
check("  it is NOT reported as having no conditions",
      blank["status"] != "no_conditions", blank["status"])
draft = assess({"id": "e4", "workflow_state": "draft", "data": {"conditions": ""}})
check("a DRAFT with no conditions is not flagged — nothing has been imposed yet",
      draft["status"] == "no_conditions", draft["status"])

print()
if FAILED:
    print(f"approval_conditions: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("approval_conditions: all checks passed")
