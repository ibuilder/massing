"""Time & Material (eTicket) cost rollup — aggregates `eticket` records (labor/material/equipment)
into a T&M cost summary by status, with billed vs unbilled. Pure over the record dicts."""
from __future__ import annotations

from typing import Any

BILLED = "billed"


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


GC_PARTY = "GC"

#: The GC-accepted states of the SHIPPED `eticket` workflow, for a caller that must answer when the
#: module registry is not loaded. It is DECLARED rather than inferred at import -- the registry
#: populates at startup, so an import-time derivation would silently be `[]` -- and
#: `test_eticket_tm.py` asserts it equals `accepted_states(REGISTRY["eticket"])`, so the declaration
#: cannot drift away from the rule it stands in for. *A constant beside a derivation is a second
#: copy unless something ties them together.*
SHIPPED_ACCEPTED = ("billed", "gc_signed")


def _parties(t: dict) -> set[str]:
    p = t.get("party")
    return {p} if isinstance(p, str) else {str(x) for x in (p or [])}


def accepted_states(mod: dict) -> list[str]:
    """The states whose T&M the **GC has accepted**, derived from the workflow `mod` declares.

    TM-UNBILLED. A state counts as accepted when EVERY transition that reaches it is performable by
    the GC alone. On the shipped `eticket` workflow that is exactly `gc_signed` (via `gc_sign`, party
    `["GC"]`, `requires: ["gc_approved_by"]`) and `billed` (via `bill`, party `["GC"]`) --
    `super_signed` is excluded because `super_sign` is party `["Subcontractor", "GC"]`, i.e. the
    sub's signature, and `draft` is reached by nothing.

    **The derivation is here because the set was hardcoded in two places and could not stay in
    agreement.** `cost.summary` counted T&M as actual cost for `("gc_signed", "billed")`, written out
    by hand; this card inferred acceptance from three state names written out by hand on the client.
    Since WORKFLOW-DARK a project may REPLACE these transitions, at which point both copies are
    quietly wrong -- and the money one is wrong in the direction that understates actual cost. One
    definition, resolved through `workflow_config.effective` by `effective_accepted` so it answers
    for the workflow the project actually runs.

    *That it reproduces the hand-written pair on the shipped module is the argument for the rule, and
    `test_eticket_tm.py` asserts that equality rather than leaving it as a claim here.*
    """
    reached: dict[str, list[dict]] = {}
    for t in (mod.get("workflow") or {}).get("transitions") or []:
        to = t.get("to")
        if to:
            reached.setdefault(str(to), []).append(t)
    return sorted(s for s, ts in reached.items() if all(_parties(t) == {GC_PARTY} for t in ts))


def effective_accepted(pid: str) -> tuple[list[str] | None, bool]:
    """`accepted_states` for the workflow THIS PROJECT runs, and whether it overrode the shipped one.

    The override flag is the half a client cannot derive: the three state names a screen labels are
    the SHIPPED ones, so a project that replaced the transitions makes those labels a guess. Reported
    rather than inferred -- the same reason `occupancy_basis` is on the rent roll.

    **`None`, not `[]`, when the module is not in the registry.** The registry is populated at
    startup, so an unloaded one is a configuration failure rather than a project with no accepted
    states -- and `[]` would have been read downstream as "the GC has accepted nothing", which is a
    plausible-looking answer to a question nobody managed to ask. `cost.summary` would then drop
    every T&M dollar out of `actual`. Measured while writing this: `REGISTRY` is empty on a bare
    import of the package, so the quiet path was reachable from any caller outside a served request.
    """
    from . import modules_registry, workflow_config
    mod = modules_registry.REGISTRY.get("eticket")
    if not mod:
        return None, False
    eff = workflow_config.effective(mod, pid)
    return accepted_states(eff), bool(eff.get("workflow_overridden"))


def summarize(etickets: list[dict], accepted: list[str] | None = None,
              overridden: bool = False) -> dict[str, Any]:
    """Roll `eticket` records up. `accepted` is the GC-accepted state set from `effective_accepted`;
    `None` means nobody resolved it, which is reported as `null` rather than as an empty set --
    "the server did not say" and "nothing is accepted" are different facts and the second one reads
    as a plausible answer."""
    rows, by_status = [], {}
    labor = material = equipment = billed_total = 0.0
    for e in etickets:
        d = e.get("data") or e
        lt, mt, et = _num(d.get("labor_total")), _num(d.get("material_total")), _num(d.get("equipment_total"))
        total = lt + mt + et
        labor += lt; material += mt; equipment += et
        st = e.get("workflow_state") or "draft"
        by_status[st] = by_status.get(st, 0.0) + total
        if st == BILLED:
            billed_total += total
        rows.append({"ref": e.get("ref"), "subject": d.get("subject"), "work_date": d.get("work_date"),
                     "labor": round(lt, 2), "material": round(mt, 2), "equipment": round(et, 2),
                     "total": round(total, 2), "status": st})
    grand = labor + material + equipment
    return {
        "ticket_count": len(rows),
        "labor_total": round(labor, 2), "material_total": round(material, 2),
        "equipment_total": round(equipment, 2), "grand_total": round(grand, 2),
        "billed_total": round(billed_total, 2), "unbilled_total": round(grand - billed_total, 2),
        "by_status": {k: round(v, 2) for k, v in by_status.items()},
        # TM-UNBILLED. `unbilled_total` is everything-not-billed, which on this module's workflow
        # (`draft -> super_signed -> gc_signed -> billed`) spans three states that say different
        # things about who owes what: `draft` is a claim nobody has signed, `super_signed` is signed
        # by the sub and not accepted by the GC, and `gc_signed` IS accepted. Measured: all-draft
        # and all-gc_signed both return `grand_total 90000, unbilled_total 90000`, and the T&M
        # rollup card rendered both as the same sentence.
        #
        # `by_status` always carried the split; what no client could derive is WHICH of those states
        # the GC has accepted -- a project may override the transitions -- so the resolved set and
        # the override flag are stated here instead of being inferred from three state names.
        #
        # NOT the CO-REJECTED shape, and worth saying because it is the first thing to suspect:
        # `eticket` declares NO refusal state, so there is no money-nobody-owes inside this figure.
        # The defect is the flattening of ACCEPTANCE, not contamination.
        "accepted_states": accepted,
        "workflow_overridden": overridden,
        "rows": sorted(rows, key=lambda r: (r.get("work_date") or "")),
    }


def tm_summary(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    ets = me.list_records(db, "eticket", pid, limit=100000) if "eticket" in me.TABLES else []
    accepted, overridden = effective_accepted(pid)
    return summarize(ets, accepted, overridden)


def by_change_event(db, pid: str) -> dict[str, Any]:
    """Roll up eTicket T&M by the change event each ticket is linked to — ties field T&M to the
    change-management → cost chain. eTickets with no link land in an 'unassigned' bucket."""
    from . import modules as me
    ets = me.list_records(db, "eticket", pid, limit=100000) if "eticket" in me.TABLES else []
    ce = {r["id"]: r for r in (me.list_records(db, "change_event", pid, limit=100000)
                               if "change_event" in me.TABLES else [])}
    groups: dict[str, dict] = {}
    for e in ets:
        d = e.get("data") or e
        total = _num(d.get("labor_total")) + _num(d.get("material_total")) + _num(d.get("equipment_total"))
        cid = d.get("change_event")
        rec = ce.get(cid)
        gkey = cid if (cid and rec) else "__unassigned__"
        g = groups.setdefault(gkey, {
            "change_event_id": cid if rec else None,
            "ref": rec.get("ref") if rec else None,
            "subject": ((rec.get("data") or {}).get("subject") if rec else "Unassigned"),
            "ticket_count": 0, "total": 0.0})
        g["ticket_count"] += 1
        g["total"] = round(g["total"] + total, 2)
    rows = sorted(groups.values(), key=lambda r: (r["ref"] is None, r["ref"] or ""))
    return {"groups": rows, "linked_total": round(sum(g["total"] for g in rows if g["change_event_id"]), 2),
            "unassigned_total": round(sum(g["total"] for g in rows if not g["change_event_id"]), 2)}
