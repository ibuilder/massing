"""R23-PREFAB-KIT — a prefabrication kit as a join across spines that already exist.

A kit is four things the platform already holds, tied together: a **scope** (a `query_dsl` selector
over the model), a **bill of materials** rolled up from those elements, a **pull-plan task** it
installs under, and a **delivery** that has to land before that task starts. There is no new engine
here; there is a join, and the join is where the value is — nobody can currently answer "is the
level-3 duct kit ready to release, and will it be on site before the crew needs it?" without opening
four screens and doing the comparison by eye.

**The one thing this module exists to prevent.** A kit is fabricated off-site against a scope decided
at a moment in time. A `query_dsl` selector is *live* — it re-evaluates against whatever the model
says today. Those two facts are in direct conflict, and resolving them the convenient way (always
re-run the selector) means a model revision silently changes what the shop is building, after the
steel is cut. So a released kit **freezes its GlobalId list**, the selector becomes the record of how
that list was arrived at rather than the definition of it, and `drift()` reports the difference
between the frozen scope and what the selector matches now. Drift is surfaced, never absorbed: an
element that has left the selector's scope is a design change the shop has not been told about, and
an element that has joined it is work nobody has priced.

That is the same discipline as an issued drawing. The revision cloud is the point.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from . import query_dsl

log = logging.getLogger("aec")

#: Refusals that reach a response, exported as CONSTANTS. The rule they exist for: no text in an HTTP
#: response may derive from a caught exception, because CodeQL's py/stack-trace-exposure taints a
#: caught exception regardless of its class — typing it does not help, only changing the shape does.
#: A router answers with these directly rather than stringifying whatever was raised.
BAD_SELECTOR = ("the selector could not be evaluated — check its syntax against the QUERY-DSL "
                "(the parse error is in the server log)")
FREEZE_NO_MATCH = "the selector matches no elements — there is nothing to release"
FREEZE_TRUNCATED = ("the selector matched more elements than the query limit returns; a frozen scope "
                    "must be the whole set, not the first page of it")
FREEZE_FAILED = "the kit's scope could not be frozen"

#: A kit is only as good as the moment it was frozen, so the states that mean "the shop is working"
#: are named. Before `released` a kit is a proposal and the live selector IS its scope; from
#: `released` on, the frozen list is.
FROZEN_STATES = ("released", "fabricating", "delivered", "installed")

#: Quantities rolled up on a BOM line, in the order an estimator reads them.
_QTY_KEYS = ("count", "length", "area", "volume", "weight")

#: Base-quantity aliases, the same canonical names `qto.py` uses, so a kit's BOM quantity and the
#: estimate's quantity for the same element are the same number rather than two plausible ones.
#: The index stores IFC quantity sets nested under `qtos`, NOT as flat per-element keys — reading
#: them as flat keys yields a BOM of zeroes that looks exactly like a measured result.
_QTO_ALIASES = {
    "length": ("Length", "NetLength", "GrossLength"),
    "area": ("NetArea", "GrossArea", "Area", "NetSideArea", "GrossSideArea"),
    "volume": ("NetVolume", "GrossVolume", "Volume"),
    "weight": ("NetWeight", "GrossWeight", "Weight"),
}


def element_quantities(element: dict[str, Any]) -> dict[str, float]:
    """Declared base quantities for one indexed element, canonicalised.

    **Declared only.** There is no geometry fallback here on purpose: a kit BOM is a document a shop
    fabricates from, and a quantity the model asserts and a quantity we derived by meshing a solid
    are different claims. Elements carrying no `Qto_*` contribute their count and nothing else, and
    `bom()` reports how many of those there were rather than letting them read as measured zeroes."""
    out: dict[str, float] = {}
    for qset in (element.get("qtos") or {}).values():
        if not isinstance(qset, dict):
            continue
        for canonical, keys in _QTO_ALIASES.items():
            if canonical in out:
                continue
            for k in keys:
                v = qset.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[canonical] = float(v)
                    break
    return out


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # NaN is not a quantity


def parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def parse_guids(text: Any) -> list[str]:
    """The frozen list, from a textarea. Newline or comma separated, deduped, order preserved.

    Order-preserving rather than sorted: the list is a shop document as much as a data structure, and
    the order somebody wrote it in is information."""
    if isinstance(text, (list, tuple)):
        raw = [str(t) for t in text]
    else:
        raw = str(text or "").replace(",", "\n").split("\n")
    out, seen = [], set()
    for tok in raw:
        g = tok.strip()
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def resolve(idx: dict[str, dict] | None, selector: str, limit: int = 5000) -> dict[str, Any]:
    """Evaluate a kit's selector against the property index.

    Errors are returned rather than raised: a kit register showing twelve kits should not fail
    wholesale because one of them has a typo in its selector — it should show eleven kits and one
    that says what is wrong with it."""
    if not (selector or "").strip():
        return {"selector": selector or "", "guids": [], "matched": 0, "error": "no selector set"}
    try:
        r = query_dsl.select(idx, selector, limit=limit)
    except query_dsl.QueryError:
        # The exception's text does NOT go into the payload. `resolve()` feeds three response paths
        # (the register, the kit detail, and freeze), so putting a caught exception's message in
        # `error` puts it in three responses — which is what CodeQL alert #108
        # (py/stack-trace-exposure) fired on, at the GET detail route rather than at freeze.
        # Typing the exception does not clear it; a caught exception is tainted whatever its class.
        # The shape has to change: a constant out, the detail to the log where an operator can find
        # it. See memory `codeql-stack-trace-exposure` and the option_score.EMPTY_OPTIONS precedent.
        log.info("prefab kit selector %r did not parse", selector, exc_info=True)
        return {"selector": selector, "guids": [], "matched": 0, "error": BAD_SELECTOR}
    return {"selector": selector, "guids": list(r["guids"]), "matched": r["matched"],
            "truncated": bool(r.get("truncated")),
            "note": r.get("note")}


def bom(idx: dict[str, dict] | None, guids: list[str]) -> dict[str, Any]:
    """Bill of materials for a GUID set: one line per (IFC class, type), with quantities rolled up.

    `unresolved` counts GUIDs that are not in the index. That number matters more than it looks: on a
    released kit it means the frozen scope references elements the current model no longer contains,
    which is exactly the condition a shop needs to hear about and the one a silent `KeyError`-free
    dict lookup would swallow.
    """
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved: list[str] = []
    unquantified = 0
    for g in guids:
        e = (idx or {}).get(g)
        if e is None:
            unresolved.append(g)
            continue
        key = (e.get("ifc_class") or "?", e.get("type_name") or "")
        line = lines.setdefault(key, {"ifc_class": key[0], "type": key[1] or None,
                                      "count": 0, "unquantified": 0, "guids": []})
        line["count"] += 1
        line["guids"].append(g)
        q = element_quantities(e)
        if not q:
            line["unquantified"] += 1
            unquantified += 1
        for name, v in q.items():
            n = _num(v)
            if n is not None:
                line[name] = round(line.get(name, 0.0) + n, 4)
    ordered = sorted(lines.values(), key=lambda ln: (ln["ifc_class"], ln["type"] or ""))
    totals: dict[str, float] = {"count": sum(ln["count"] for ln in ordered)}
    for q in _QTY_KEYS[1:]:
        vals = [ln[q] for ln in ordered if q in ln]
        if vals:
            totals[q] = round(sum(vals), 4)
    return {"lines": ordered, "totals": totals,
            "unresolved": unresolved,
            "unquantified": unquantified,
            "measured": "declared base quantities (Qto_*) only — no geometry fallback",
            "note": (f"{unquantified} of {totals['count']} element(s) carry no base quantities and "
                     "contribute to the count only; their length/area/volume are absent from the "
                     "totals rather than counted as zero")
                    if unquantified else None}


def drift(frozen: list[str], live: list[str]) -> dict[str, Any]:
    """What the selector matches now, against what the shop was given.

    Both directions are defects and they are different defects, so they are reported separately.
    `added` is work nobody priced; `removed` is a design change the shop has not been told about and
    may already have fabricated.
    """
    fz, lv = set(frozen), set(live)
    added, removed = sorted(lv - fz), sorted(fz - lv)
    return {
        "frozen": len(fz), "live": len(lv),
        "added": added, "removed": removed,
        "stable": len(fz & lv),
        "drifted": bool(added or removed),
        "means": None if not (added or removed) else
                 (f"{len(added)} element(s) now in scope that the released kit does not contain"
                  if added else "") +
                 ("; " if added and removed else "") +
                 (f"{len(removed)} element(s) in the released kit that the selector no longer matches"
                  if removed else ""),
    }


def assess(kit: dict[str, Any], idx: dict[str, dict] | None, *,
           pull_task: dict[str, Any] | None = None, delivery: dict[str, Any] | None = None,
           today: Any = None) -> dict[str, Any]:
    """One kit, fully resolved: scope, BOM, drift, the task it installs under, and its blockers.

    `blockers` is the answer to "can this be released / is it going to be there in time", and every
    entry names the thing to fix. A readiness figure with no list of what is holding it back is a
    number people learn to ignore.
    """
    data = kit.get("data") or kit
    state = kit.get("workflow_state") or data.get("workflow_state") or "draft"
    now = parse_date(today) or date.today()

    live = resolve(idx, data.get("selector") or "")
    frozen = parse_guids(data.get("frozen_guids"))
    is_frozen = state in FROZEN_STATES

    # Which list IS the kit: before release the selector defines it, after release the frozen list
    # does. Getting this backwards is the whole failure mode this module exists for.
    scope = frozen if is_frozen else live["guids"]
    scope_source = "frozen" if is_frozen else "selector"

    out: dict[str, Any] = {
        "id": kit.get("id"), "ref": kit.get("ref"),
        "name": data.get("name"), "trade": data.get("trade"),
        "fabricator": data.get("fabricator"),
        "state": state, "scope_source": scope_source,
        "selector": live, "frozen_count": len(frozen),
        "elements": len(scope),
        "bom": bom(idx, scope),
        "as_of": now.isoformat(),
    }
    out["drift"] = drift(frozen, live["guids"]) if (is_frozen and not live.get("error")) else None

    blockers: list[dict[str, str]] = []
    if live.get("error"):
        blockers.append({"code": "selector_error", "detail": live["error"]})
    if idx is None:
        blockers.append({"code": "no_model",
                         "detail": "no model index loaded for this project — a kit's scope cannot be "
                                   "resolved, so neither the BOM nor the drift check means anything"})
    elif not scope:
        blockers.append({"code": "empty_scope",
                         "detail": f"the {scope_source} scope contains no elements"})
    if out["bom"]["unresolved"]:
        blockers.append({"code": "unresolved_elements",
                         "detail": f"{len(out['bom']['unresolved'])} GlobalId(s) in the frozen scope "
                                   "are not in the current model"})
    if out["drift"] and out["drift"]["drifted"]:
        blockers.append({"code": "scope_drift", "detail": out["drift"]["means"]})
    if is_frozen and not frozen:
        blockers.append({"code": "released_without_freezing",
                         "detail": "the kit is released but no frozen scope was recorded, so what the "
                                   "shop is building is not written down anywhere"})

    # --- the schedule tie -------------------------------------------------------------------------
    task_d = (pull_task or {}).get("data") or {}
    if pull_task:
        constraints = task_d.get("constraints") or []
        out["pull_task"] = {
            "id": pull_task.get("id"), "ref": pull_task.get("ref"),
            "task": task_d.get("task"), "planned_week": task_d.get("planned_week"),
            "state": pull_task.get("workflow_state"),
            "constraints": list(constraints),
        }
        if constraints:
            out["pull_task"]["open_constraints"] = len(constraints)
            blockers.append({"code": "task_constrained",
                             "detail": f"the installing task {pull_task.get('ref') or ''} still has "
                                       f"{len(constraints)} make-ready constraint(s): "
                                       f"{', '.join(str(c) for c in constraints)}"})
    else:
        out["pull_task"] = None
        blockers.append({"code": "no_pull_task",
                         "detail": "the kit is not tied to a pull-plan task, so nothing connects its "
                                   "delivery date to the week the crew needs it"})

    need = parse_date(data.get("needed_on_site"))
    del_d = (delivery or {}).get("data") or {}
    del_date = parse_date(del_d.get("date"))
    out["delivery"] = ({"id": delivery.get("id"), "ref": delivery.get("ref"),
                        "date": del_date.isoformat() if del_date else None,
                        "supplier": del_d.get("supplier"), "status": del_d.get("status")}
                       if delivery else None)
    out["needed_on_site"] = need.isoformat() if need else None

    if need and del_date and del_date > need:
        blockers.append({"code": "delivery_late",
                         "detail": f"delivery {del_date.isoformat()} is after the {need.isoformat()} "
                                   f"need-by date — {(del_date - need).days} day(s) late"})
    if need and not del_date:
        blockers.append({"code": "no_delivery_date",
                         "detail": f"needed on site {need.isoformat()} with no delivery date recorded"})
    if need and need < now and state not in ("delivered", "installed"):
        blockers.append({"code": "need_by_passed",
                         "detail": f"the {need.isoformat()} need-by date has passed and the kit is "
                                   f"still {state}"})

    out["blockers"] = blockers
    out["ready"] = not blockers
    return out


#: Sort order for the register. A kit whose scope has drifted outranks one that is merely late,
#: because a late kit is a known problem and a drifted one is an unknown wrong one.
_SEVERITY = {"released_without_freezing": 0, "scope_drift": 1, "unresolved_elements": 2,
             "selector_error": 3, "need_by_passed": 4, "delivery_late": 5, "no_delivery_date": 6,
             "task_constrained": 7, "empty_scope": 8, "no_pull_task": 9, "no_model": 10}


def register(kits: list[dict[str, Any]], idx: dict[str, dict] | None, *,
             tasks_by_id: dict[str, dict] | None = None,
             deliveries_by_id: dict[str, dict] | None = None,
             today: Any = None) -> dict[str, Any]:
    """Every kit on the project, worst first."""
    tasks_by_id = tasks_by_id or {}
    deliveries_by_id = deliveries_by_id or {}
    rows = []
    for k in kits:
        d = k.get("data") or {}
        rows.append(assess(
            k, idx,
            pull_task=tasks_by_id.get(str(d.get("pull_task") or "")),
            delivery=deliveries_by_id.get(str(d.get("delivery") or "")),
            today=today,
        ))
    rows.sort(key=lambda r: (min((_SEVERITY.get(b["code"], 99) for b in r["blockers"]), default=99),
                             r.get("needed_on_site") or "9999-12-31",
                             r.get("ref") or ""))
    counts: dict[str, int] = {}
    for r in rows:
        for b in r["blockers"]:
            counts[b["code"]] = counts.get(b["code"], 0) + 1
    return {
        "kits": rows,
        "total": len(rows),
        "ready": sum(1 for r in rows if r["ready"]),
        "blocked": sum(1 for r in rows if not r["ready"]),
        "blocker_counts": dict(sorted(counts.items())),
        "as_of": (parse_date(today) or date.today()).isoformat(),
        "model_loaded": idx is not None,
    }


def freeze_blocker(kit: dict[str, Any], idx: dict[str, dict] | None) -> str | None:
    """Why this kit cannot be frozen — one of the exported constants — or None if it can.

    Split out from `freeze()` so a router can ask the question and answer with a constant, instead of
    calling `freeze()` and stringifying whatever it raised. That is the difference between a response
    whose text is a fixed literal and one derived from a caught exception, which is what
    py/stack-trace-exposure is about."""
    live = resolve(idx, (kit.get("data") or kit).get("selector") or "")
    if live.get("error"):
        return live["error"]                    # already a constant — see `resolve`
    if not live["guids"]:
        return FREEZE_NO_MATCH
    if live.get("truncated"):
        return FREEZE_TRUNCATED
    return None


def freeze(kit: dict[str, Any], idx: dict[str, dict] | None) -> dict[str, Any]:
    """The GUID list to write onto a kit when it is released.

    Returns the list and what it was resolved from, so the caller writes a recorded decision rather
    than a side effect. Refuses an empty or erroring selector — freezing nothing and calling it a
    released kit is the failure this whole module is built around.
    """
    blocker = freeze_blocker(kit, idx)
    if blocker:
        raise ValueError(blocker)
    live = resolve(idx, (kit.get("data") or kit).get("selector") or "")
    return {"guids": live["guids"], "frozen_guids": "\n".join(live["guids"]),
            "selector": live["selector"], "matched": live["matched"]}
