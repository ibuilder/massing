"""R22-PROVENANCE — one admissibility verdict across all three provenance legs.

Premise-checked before writing, and two thirds of this ring was already built:

* **agent answers** — `cited_answer.py`: `cite_doc(document_id, revision, sheet, page, …)`,
  coverage, conflict detection, a stale-revision penalty;
* **estimate lines** — `boe_ledger.py`: `source` / `quote_ref` / `basis_date` per line, with the
  undocumented lines surfaced;
* **proforma assumptions** — `assumption_provenance.py`, which closed the third leg.

What did **not** exist is the join. Each leg answers for itself and provenance is exposed only on the
proforma path, so nothing answers the question the ring is actually for: *is this deal's output
admissible in an IC memo or a claim?* A reader had to open three endpoints and reconcile them.

**Admissibility is not a score, and this module refuses to produce one.** The tempting join is a
single 0–100 "provenance score"; it is also the thing that makes an uncited estimate invisible behind
a well-cited proforma. A memo is not admissible because it scored 82. So the verdict is per-leg,
the blockers are **named**, and there is no blended number anywhere.

**An empty leg is `no_data`, never coverage — and the two legs prove why.** They disagree about what
zero means, in opposite directions:

    boe_ledger.ledger([])            -> pct_documented 1.0    "perfectly documented"
    assumption_provenance.provenance({}) -> coverage_pct 0.0  "nothing cited"

Both describe *the same absence*. Averaging them would be arithmetic over two different claims, and
either one alone would mislead: a project with no estimate lines is not a project with a perfectly
documented estimate. So an empty leg reports `no_data` with what is missing, and is excluded from
the verdict rather than counted as pass or fail.
"""
from __future__ import annotations

from typing import Any

STATUS_OK = "cited"
STATUS_GAPS = "has_uncited"
STATUS_NO_DATA = "no_data"

#: Distinct from `no_data`, and the distinction is the point. `no_data` means a source exists and is
#: empty — the user can fix that by filling it in. `not_captured` means **this system has nowhere to
#: put the evidence**: the `estimate` register's `line_items` columns are code/description/qty/unit/
#: unit_cost/amount, with no `source`, `quote_ref` or `basis_date`, so a basis-of-estimate ledger can
#: only ever be built from lines posted in a request body. Reporting that as "no data" would send
#: somebody looking for a field to fill that does not exist.
STATUS_NOT_CAPTURED = "not_captured"

VERDICT_ADMISSIBLE = "admissible"
VERDICT_BLOCKED = "blocked"
VERDICT_INCOMPLETE = "incomplete"

#: How many named blockers to carry per leg. The count is always exact; the list is capped so a
#: pathological deal cannot turn a verdict into a payload.
MAX_NAMED = 25


def _leg_assumptions(prov: dict | None) -> dict[str, Any]:
    if not prov:
        return {"status": STATUS_NO_DATA, "leg": "assumptions", "counted": 0,
                "note": "no proforma assumptions were supplied — not an assumption set with nothing "
                        "to cite"}
    material = int(prov.get("material_count") or 0)
    uncited = list(prov.get("uncited") or [])
    if not material:
        return {"status": STATUS_NO_DATA, "leg": "assumptions", "counted": 0,
                "note": ("the scenario declares no MATERIAL assumptions. `coverage_pct` reads 0.0 "
                         "here, which means 'nothing to cite', not 'nothing cited' — reporting it "
                         "as 0% coverage would invent a failure")}
    return {"status": STATUS_OK if not uncited else STATUS_GAPS, "leg": "assumptions",
            "counted": material, "uncited_count": len(uncited),
            "uncited": [str(u) for u in uncited[:MAX_NAMED]],
            "note": "material assumptions with no cited source" if uncited else ""}


def _leg_estimate(led: dict | None) -> dict[str, Any]:
    if not led:
        return {"status": STATUS_NO_DATA, "leg": "estimate", "counted": 0,
                "note": "no basis-of-estimate ledger was supplied"}
    lines = int(led.get("line_count") or 0)
    undoc = list(led.get("undocumented") or [])
    if not lines:
        return {"status": STATUS_NO_DATA, "leg": "estimate", "counted": 0,
                "note": ("the ledger holds no lines. `pct_documented` reads 1.0 for an empty ledger, "
                         "which would report a project with NO estimate as having a perfectly "
                         "documented one — the opposite error to the assumptions leg, from the same "
                         "absence")}
    return {"status": STATUS_OK if not undoc else STATUS_GAPS, "leg": "estimate",
            "counted": lines, "uncited_count": len(undoc),
            "uncited": [f"{u.get('key')}: missing {', '.join(u.get('missing') or [])}"
                        for u in undoc[:MAX_NAMED]],
            "note": "estimate lines with an undocumented basis" if undoc else ""}


def _leg_answers(answers: list[dict] | None) -> dict[str, Any]:
    rows = [a for a in (answers or []) if isinstance(a, dict)]
    if not rows:
        return {"status": STATUS_NO_DATA, "leg": "answers", "counted": 0,
                "note": "no agent answers were supplied — an unanswered deal is not an uncited one"}
    uncited = [str(a.get("text") or a.get("target") or "answer")[:120]
               for a in rows if not (a.get("citations") or [])]
    return {"status": STATUS_OK if not uncited else STATUS_GAPS, "leg": "answers",
            "counted": len(rows), "uncited_count": len(uncited),
            "uncited": uncited[:MAX_NAMED],
            "note": "agent answers carrying no citation" if uncited else ""}


#: What each un-gatherable leg would need before a project-scoped verdict could include it. Named
#: rather than described, so the follow-up is a schema change somebody can action, not a sentiment.
NOT_CAPTURED_REASON: dict[str, str] = {
    "answers": ("agent answers are not persisted at all. `cited_answer` is an in-flight contract "
                "consumed by decision_gate / persona_answer / rfi_qa; no store keeps the answers or "
                "their citations after the response is returned. A store of answered claims is what "
                "would make this leg gatherable"),
}


#: The `estimate` register and `boe_ledger` name two of the same things differently: the register's
#: table columns are `code` and `amount`, the ledger reads `cost_code` and `total`. Handing the rows
#: over unmapped is not a crash — it is worse. `_key()` falls through to `description`, so every line
#: still gets a key, `cost_code` comes back None on every row, and `total` silently drops to None for
#: any line priced as a lump sum rather than qty x unit_cost. The result is a full, plausible,
#: quietly-wrong ledger. So the mapping is written down in one place, and asserted in
#: `test_provenance_estimate_leg.py` against `boe_ledger`'s real output rather than against a
#: fixture written to match it.
ESTIMATE_TO_BOE: dict[str, str] = {"code": "cost_code", "amount": "total"}


def estimate_lines(records: list[dict] | None) -> list[dict[str, Any]]:
    """Every line item across a project's estimate records, in the shape `boe_ledger` reads.

    Pass-through for anything already named the ledger's way, so a record that carries `cost_code`
    outright is not clobbered by an absent `code`.
    """
    out: list[dict[str, Any]] = []
    for rec in records or []:
        data = (rec.get("data") or rec) if isinstance(rec, dict) else {}
        for ln in (data.get("line_items") or []):
            if not isinstance(ln, dict):
                continue
            row = dict(ln)
            for src, dst in ESTIMATE_TO_BOE.items():
                if row.get(dst) in (None, "") and ln.get(src) not in (None, ""):
                    row[dst] = ln[src]
            out.append(row)
    return out


def answer_rows(records: list[dict] | None) -> list[dict[str, Any]]:
    """`answer_record` rows in the shape `_leg_answers` reads.

    The mapping is written down here for the same reason `ESTIMATE_TO_BOE` is: the register stores
    `answer`, `citations` is a table field of rows, and the leg reads `text` and a list of citation
    dicts. Handing the rows over unmapped would not raise — every row would simply look uncited, and
    a report claiming every answer lacks a citation is a confident, plausible, wrong verdict.
    """
    out: list[dict[str, Any]] = []
    for rec in (records or []):
        data = (rec.get("data") or {}) if isinstance(rec, dict) else {}
        cites = [c for c in (data.get("citations") or []) if isinstance(c, dict)]
        out.append({
            "text": data.get("answer") or rec.get("title") or "",
            "target": data.get("target") or data.get("source_document") or "",
            "citations": cites,
            "ref": rec.get("ref"),
            "engine": data.get("engine"),
        })
    return out


#: Every citation key the `answer_record` citations table declares. Written here rather than derived,
#: because the WRITE side is where an unknown key silently vanishes: a module `table` field keeps the
#: columns it knows and drops the rest, so a citation carrying `page` under some other name would
#: store as a row with no page and read back as a citation nobody can open.
_CITATION_COLUMNS = ("source_type", "document_id", "sheet", "page", "revision")

#: `cited_answer` builds citations with keys that do not all match the register's columns — it emits
#: `guid` for an IFC cite and `rule_id` for a rule. Both are the thing a reader would open, so both
#: map onto `document_id` rather than being dropped. The direction is the mirror of `answer_rows`,
#: and both live here for the reason `ESTIMATE_TO_BOE` does: a mapping split across two files is a
#: mapping that will disagree with itself.
_CITE_ALIASES = {"guid": "document_id", "rule_id": "document_id", "doc": "document_id",
                 "module": "document_type", "id": "document_id"}


def citation_row(cite: dict) -> dict[str, Any]:
    """One `cited_answer` citation as a row of the register's citations table."""
    row: dict[str, Any] = {}
    for key, val in (cite or {}).items():
        col = _CITE_ALIASES.get(key, key)
        if col in _CITATION_COLUMNS and val not in (None, "") and col not in row:
            row[col] = val
    return row


def record_answer(db, project_id: str, question: str, cited: dict | None, *,
                  engine: str = "rfi_qa", target: str = "", asked_by: str = "",
                  actor: str = "system") -> dict[str, Any]:
    """Persist an answered claim so the ANSWERS leg has something to gather. Never raises.

    **Recording must not be able to break answering.** A question that was answered correctly and
    failed to file is a worse outcome than one that filed and returned nothing, so every failure here
    is reported *as data* on the response — `recorded: False` with a composed reason — and none of it
    reaches the caller as an exception. The reason is composed rather than relayed: `str(exc)` on a
    response path is the v0.3.962 defect and CodeQL flags it.

    An answer with **no** citations is still recorded. That is the point: `_leg_answers` counts it and
    names it as uncited, and dropping it here would quietly improve every provenance report by hiding
    the answers that most need looking at.
    """
    from . import modules as me
    if "answer_record" not in me.TABLES:
        return {"recorded": False,
                "reason": "the answer_record register is not present in this deployment"}
    claims = [c for c in ((cited or {}).get("claims") or []) if isinstance(c, dict)]
    if not claims:
        return {"recorded": False,
                "reason": "the answer carried no claims, so there is nothing to file"}

    rows = []
    for claim in claims:
        cites = [citation_row(c) for c in (claim.get("citations") or []) if isinstance(c, dict)]
        rows.append({
            "question": question or "",
            "answer": str(claim.get("text") or ""),
            "target": str(claim.get("target") or target or ""),
            "engine": engine,
            "asked_by": asked_by,
            "answered_at": _today(),
            "confidence": claim.get("confidence"),
            "citations": [c for c in cites if c],
        })

    filed = 0
    try:
        for data in rows:
            # `create_record` reads the field map out of `body["data"]` — only the POST-create shape
            # wraps; PATCH takes the map flat. Passing it flat here does not raise, it inserts a
            # record with every field empty, which would file an answer nobody can read.
            me.create_record(db, "answer_record", project_id, {"data": data}, actor, None)
            filed += 1
    except Exception:  # noqa: BLE001 — see the docstring: a filing failure must not lose the answer
        return {"recorded": False, "filed": filed, "of": len(rows),
                "reason": "the answer was produced but could not be filed to the answer_record "
                          "register; the answer itself is unaffected and is returned above"}
    return {"recorded": True, "filed": filed, "of": len(rows)}


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def from_project(db, project_id: str, scenario_id: str | None = None) -> dict[str, Any]:
    """The admissibility verdict for a project, from what this system actually persists.

    **Only one of the three legs is gatherable, and saying so precisely is the point.** The
    assumptions leg comes from the project's own scenarios. The other two report `not_captured` with
    the schema change each would need — because "you have not filled this in" and "this system has
    nowhere to put it" send a reader to completely different places, and a verdict that conflates
    them wastes the time of whoever acts on it.

    Pass `scenario_id` to judge one scenario; otherwise the project's most recent is used, since that
    is the one an IC memo is written from.
    """
    from .models import Scenario

    q = db.query(Scenario).filter(Scenario.project_id == project_id)
    scen = (q.filter(Scenario.id == scenario_id).first() if scenario_id
            else q.order_by(Scenario.created_at.desc()).first())

    ap = None
    if scen is not None:
        from . import assumption_provenance
        ap = assumption_provenance.scenario_provenance(scen)

    from . import boe_ledger
    from . import modules as me

    lines = estimate_lines(
        me.list_records(db, "estimate", project_id, limit=100000) if "estimate" in me.TABLES else [])
    led = boe_ledger.ledger(lines) if lines else None

    # R22-PROVENANCE, v0.3.975: the ANSWERS leg is gatherable. `answer_record` is the store the
    # `NOT_CAPTURED_REASON` below asked for by name — "a store of answered claims is what would make
    # this leg gatherable". The reason text is kept, past-tense, because a closed gap that leaves no
    # trace reads as though it was never there.
    answers = (answer_rows(me.list_records(db, "answer_record", project_id, limit=100000))
               if "answer_record" in me.TABLES else None)

    out = report(ap, led, answers)
    # A register that exists but is absent from THIS deployment is still `not_captured` — an engine
    # cannot gather what the schema does not hold, and that is a different sentence from "nobody
    # filled it in". Derived from the registry rather than hardcoded, so removing the module
    # restores the honest refusal instead of silently reporting `no_data`.
    for name in ("answers",):
        if name == "answers" and "answer_record" in me.TABLES:
            continue
        lg = next(x for x in out["legs"] if x["leg"] == name)
        lg["status"] = STATUS_NOT_CAPTURED
        lg["note"] = NOT_CAPTURED_REASON[name]
    out["legs_absent"] = [x["leg"] for x in out["legs"] if x["status"] == STATUS_NO_DATA]
    out["legs_not_captured"] = [x["leg"] for x in out["legs"]
                                if x["status"] == STATUS_NOT_CAPTURED]
    out["project_id"] = project_id
    out["scenario_id"] = getattr(scen, "id", None)
    # The verdict is no longer forced down. Until v0.3.975 it was, and correctly: one leg could not
    # be satisfied by ANY project, so `admissible` was unreachable and pretending otherwise would
    # have been the worst kind of green. Now that the leg is gatherable, a project that cites its
    # assumptions, its estimate AND its answers can genuinely read `admissible` — and one that does
    # not still cannot, on the leg's own evidence rather than on a schema gap.
    if "answer_record" not in me.TABLES:
        out["verdict"] = VERDICT_INCOMPLETE if out["verdict"] == VERDICT_ADMISSIBLE else out["verdict"]
    out["note"] = (
        "the ANSWERS leg is gatherable since v0.3.975: `answer_record` persists an answer, what it "
        "was about and the citations behind it, so a verdict can now read `admissible` on evidence "
        "rather than being held down by a schema gap. An answers leg reading `no_data` means nobody "
        "recorded an answer, which is a different problem from having nowhere to put one — the two "
        "are still reported differently. The "
        "estimate leg IS now gathered from the `estimate` register, whose line items carry `source`, "
        "`quote_ref` and `basis_date`; an estimate leg reading `no_data` means nobody filled them in, "
        "which is a different problem from having nowhere to put them, and the two are reported "
        "differently on purpose. Nothing here is hidden by scoring only the leg that happens to "
        "work. " + out["note"])
    return out


def report(assumptions_provenance: dict | None = None, estimate_ledger: dict | None = None,
           agent_answers: list[dict] | None = None) -> dict[str, Any]:
    """One admissibility verdict across the three legs — per-leg, never blended.

    Every input is the OUTPUT of the leg that owns it (`assumption_provenance.provenance`,
    `boe_ledger.ledger`, a list of `cited_answer.claim` results), so this module re-derives nothing
    and cannot disagree with the engine it summarises.
    """
    legs = [_leg_assumptions(assumptions_provenance), _leg_estimate(estimate_ledger),
            _leg_answers(agent_answers)]
    present = [x for x in legs if x["status"] != STATUS_NO_DATA]
    blocking = [x for x in present if x["status"] == STATUS_GAPS]
    absent = [x["leg"] for x in legs if x["status"] == STATUS_NO_DATA]

    if not present:
        verdict, why = VERDICT_INCOMPLETE, (
            "no leg carried any data. This is not an admissible deal with nothing to cite — it is a "
            "deal with nothing in it, and the two must not read alike.")
    elif blocking:
        verdict, why = VERDICT_BLOCKED, (
            f"{sum(x['uncited_count'] for x in blocking)} item(s) across "
            f"{len(blocking)} leg(s) carry no source. They are named below rather than counted: a "
            "count gets quoted in a memo, a list gets fixed.")
    elif absent:
        verdict, why = VERDICT_INCOMPLETE, (
            f"every leg that HAS data is fully cited, but {len(absent)} leg(s) — {', '.join(absent)} "
            "— hold nothing at all. An absent leg is not a clean one, and calling this admissible "
            "would let an empty estimate pass as a documented one.")
    else:
        verdict, why = VERDICT_ADMISSIBLE, (
            "every leg carries data and every material item names a source.")

    return {"verdict": verdict, "reason": why, "legs": legs,
            "legs_with_data": [x["leg"] for x in present], "legs_absent": absent,
            "blocking_legs": [x["leg"] for x in blocking],
            "uncited_total": sum(x.get("uncited_count") or 0 for x in present),
            "note": ("there is deliberately NO blended provenance score. A single percentage lets a "
                     "well-cited proforma hide an uncited estimate, and a memo is not admissible "
                     "because it scored well — each leg answers for itself."),
            }
