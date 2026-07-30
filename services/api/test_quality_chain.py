"""R22-ITP-NCR ② — the per-element quality chain, and the one thing it must never say.

The registers were built; the reach was zero. What is pinned here is mostly the REFUSAL: an element
with no quality record is `unrecorded`, never `clear`. A closeout report saying "0 open NCRs" across a
building nobody inspected is literally true and completely misleading, and it is the single most
dangerous sentence this subsystem could emit.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_quality_chain.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import quality_chain as qc  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


G1, G2, G3 = "1a2b3c4d5e6f7g8h9i0jkl", "2b3c4d5e6f7g8h9i0jklmn", "3c4d5e6f7g8h9i0jklmnop"


def row(rid, state, guids=(), **data):
    return {"id": rid, "ref": rid.upper(), "workflow_state": state,
            "element_guids": list(guids), "data": data}


def gathered(itp=(), ncr=(), inspection=()):
    """Build what `gather()` would return, without a database."""
    out = {}
    for key, rows in (("itp", itp), ("ncr", ncr), ("inspection", inspection)):
        out[key] = [{"id": r["id"], "ref": r["ref"], "state": r["workflow_state"],
                     "open": qc._is_open(key, r), "guids": qc._guids(r), "data": r["data"]}
                    for r in rows]
    return out


# --- 1. the three statuses, and that they are distinguishable -------------------------------------------
g = gathered(itp=[row("i1", "verified", [G1])], inspection=[row("n1", "passed", [G1])])
e = qc.element_evidence(g, G1)
check("an element with resolved evidence is CLEAR", e["status"] == qc.STATUS_CLEAR, e["status"])
check("  and its records are counted", e["record_count"] == 2, e["record_count"])

g2 = gathered(itp=[row("i1", "verified", [G1])], ncr=[row("n2", "open", [G1])])
e2 = qc.element_evidence(g2, G1)
check("an open NCR makes the element OUTSTANDING", e2["status"] == qc.STATUS_OUTSTANDING, e2["status"])
check("  and the open item is named, not just counted",
      [x["module"] for x in e2["open_items"]] == ["ncr"], e2["open_items"])

# --- 2. THE RULE: absence is not compliance -------------------------------------------------------------
e3 = qc.element_evidence(g, G3)
check("an element with NO quality record is UNRECORDED, not clear",
      e3["status"] == qc.STATUS_UNRECORDED, e3["status"])
check("  its status note says absence is not evidence of conformance",
      "not evidence of conformance" in e3["status_note"], e3["status_note"])
check("  and it reports zero records rather than zero problems",
      e3["record_count"] == 0 and e3["open_count"] == 0)
check("unrecorded is a DIFFERENT status from clear — they must never collapse",
      qc.STATUS_UNRECORDED != qc.STATUS_CLEAR)

# --- 3. a dispositioned-but-not-closed NCR is still open -------------------------------------------------
# The lifecycle is open -> dispositioned -> closed. Only `closed` resolves it; treating "dispositioned"
# as done would mark an element clear while the corrective action is still outstanding.
for state, expect_open in (("open", True), ("dispositioned", True), ("closed", False)):
    gg = gathered(ncr=[row("n", state, [G1])])
    check(f"an NCR in '{state}' leaves the element "
          f"{'outstanding' if expect_open else 'clear'}",
          (qc.element_evidence(gg, G1)["status"] == qc.STATUS_OUTSTANDING) is expect_open)

# --- 4. an unverified hold point is named specifically ---------------------------------------------------
# Skipping a hold point is the exact failure an ITP exists to prevent, so it is surfaced rather than
# folded into a count.
gh = gathered(itp=[row("i9", "active", [G1], point_type="Hold", acceptance_criteria="ACI 318")])
eh = qc.element_evidence(gh, G1)
check("an unverified hold point is listed by name",
      [x["point_type"] for x in eh["unverified_hold_points"]] == ["Hold"],
      eh["unverified_hold_points"])
check("  a VERIFIED hold point is not listed as unverified",
      qc.element_evidence(gathered(itp=[row("i9", "verified", [G1], point_type="Hold")]),
                          G1)["unverified_hold_points"] == [])

# --- 5. attachment reads element_guids AND the legacy data.guid ------------------------------------------
check("records attach through element_guids (the platform column)",
      qc._guids(row("x", "open", [G1, G2])) == [G1, G2])
check("  and data.guid is honoured too, as element_facts._claims already does",
      qc._guids(row("x", "open", [], guid=G3)) == [G3])
check("  a record naming both does not double-count the same element",
      qc._guids(row("x", "open", [G1], guid=G1)) == [G1])


# --- 6. the project-wide capability guard ----------------------------------------------------------------
# If nothing is attached anywhere, every element reads `unrecorded` — a fact about the PROCESS, not
# about the building. Reporting that as a building finding is the mistake.
class _FakeDB:
    pass


def _run(itp=(), ncr=(), inspection=(), guids=None):
    _orig, _tab = qc.me.list_records, qc.me.TABLES
    data = {"itp": list(itp), "ncr": list(ncr), "inspection": list(inspection)}
    qc.me.list_records = lambda db, key, pid, limit=0: data.get(key, [])
    qc.me.TABLES = {k: object() for k in qc.QUALITY_MODULES}
    try:
        return qc.chain(_FakeDB(), "p1", guids), qc.turnover_readiness(_FakeDB(), "p1", guids)
    finally:
        qc.me.list_records, qc.me.TABLES = _orig, _tab


c_none, t_none = _run(ncr=[row("n1", "open")])          # a record exists but names no element
check("records that name no element are counted, not silently ignored",
      c_none["records_without_element"]["ncr"] == 1, c_none["records_without_element"])
check("  any_attached is False when nothing is linked", c_none["any_attached"] is False)
check("  and the message says how to attach them",
      "/elements" in (c_none["message"] or ""), c_none["message"])
check("  turnover is NOT ready when no evidence is attached", t_none["ready"] is False)

c_ok, t_ok = _run(itp=[row("i1", "verified", [G1])], inspection=[row("s1", "passed", [G1])])
check("with everything resolved and attached, turnover is ready", t_ok["ready"] is True, t_ok)
check("  coverage is 100% when every reported element carries evidence",
      c_ok["coverage_pct"] == 100.0, c_ok["coverage_pct"])

# The decisive case: ask about an element nobody recorded, alongside one that is clean.
c_mix, t_mix = _run(itp=[row("i1", "verified", [G1])], guids=[G1, G2])
check("an explicitly-requested element with no evidence counts AGAINST readiness",
      t_mix["ready"] is False and t_mix["unrecorded_count"] == 1, t_mix)
check("  it is named so it can be chased", t_mix["unrecorded_elements"] == [G2],
      t_mix["unrecorded_elements"])
check("  and the clean one is not dragged down with it",
      c_mix["counts"][qc.STATUS_CLEAR] == 1, c_mix["counts"])
check("  coverage is 50%, not 100%", c_mix["coverage_pct"] == 50.0, c_mix["coverage_pct"])
check("the readiness basis states why absence counts against it",
      "reads as perfectly clean" in t_mix["basis"])

# --- 7. an outstanding element blocks, and says what is open ---------------------------------------------
c_out, t_out = _run(ncr=[row("n1", "open", [G1])])
check("an element with an open NCR blocks readiness", t_out["ready"] is False)
check("  and the open item travels with the block, not just a count",
      t_out["outstanding_elements"][0]["open_items"][0]["module"] == "ncr",
      t_out["outstanding_elements"])

# --- 8. no module.json change was needed — this is a reach seam ------------------------------------------
# Asserted so a future reader does not "helpfully" add an `element` field alongside the platform's own
# attachment column and create a second convention.
import json  # noqa: E402
import os  # noqa: E402

for k in qc.QUALITY_MODULES:
    fields = [f["name"] for f in json.load(open(os.path.join("modules", k, "module.json"),
                                                encoding="utf-8"))["fields"]]
    check(f"{k}/module.json still declares no bespoke element field",
          "element" not in fields and "guid" not in fields, fields)

print()
if FAILED:
    print(f"quality_chain: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("quality_chain: all checks passed")
