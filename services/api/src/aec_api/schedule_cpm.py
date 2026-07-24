"""Critical Path Method (CPM) over the schedule_activity records — the float / critical-path
analysis that Gantt/Line-of-Balance alone don't give (and that Procore's scheduler lacks).

Pure, dependency-free: takes a list of activity dicts, returns each activity's early/late
start/finish, total + free float, and the critical path. Finish-to-Start dependencies (the common
case); duration comes from the `duration` field, else derived from start/finish dates, else 1 day.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _duration(a: dict) -> int:
    d = a.get("duration")
    try:
        if d not in (None, ""):
            return max(0, int(float(d)))
    except (TypeError, ValueError):
        pass
    s, f = a.get("start"), a.get("finish")
    if s and f:
        try:
            return max(0, (date.fromisoformat(str(f)[:10]) - date.fromisoformat(str(s)[:10])).days)
        except ValueError:
            pass
    return 1


def _preds(raw: Any) -> list[str]:
    if not raw:
        return []
    return [tok.strip() for tok in str(raw).replace(";", ",").split(",") if tok.strip()]


def compute(activities: list[dict]) -> dict[str, Any]:
    """activities: dicts with id, ref, data{wbs,duration,predecessors,...}. Returns the CPM result."""
    nodes: dict[str, dict] = {}
    alias: dict[str, str] = {}            # ref / wbs -> id, for resolving predecessor tokens
    for a in activities:
        data = a.get("data") or {}
        nid = a["id"]
        nodes[nid] = {"id": nid, "ref": a.get("ref"), "name": a.get("title") or data.get("name"),
                      "dur": _duration(data), "pred_tokens": _preds(data.get("predecessors")), "preds": []}
        for key in (a.get("ref"), data.get("wbs")):
            if key:
                alias[str(key).strip()] = nid
    # A record id is a legitimate predecessor token — `critical_path` below emits ids whenever an
    # activity has no ref, so refusing to *consume* one would make the engine's output unusable as its
    # own input. setdefault, so an explicit ref/wbs always wins over an id that happens to collide.
    for nid in nodes:
        alias.setdefault(str(nid), nid)
    for n in nodes.values():
        n["preds"] = [alias[t] for t in n["pred_tokens"] if t in alias and alias[t] != n["id"]]
    succ: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, n in nodes.items():
        for p in n["preds"]:
            succ[p].append(nid)

    # topological order (Kahn) — detect cycles
    indeg = {nid: len(n["preds"]) for nid, n in nodes.items()}
    queue = [nid for nid, d in indeg.items() if d == 0]
    order: list[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for s in succ[nid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    cyclic = len(order) != len(nodes)
    if cyclic:                            # break the cycle deterministically so we still return data
        order += [nid for nid in nodes if nid not in order]

    # forward pass: ES/EF (working-day offsets from project start = day 0)
    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    for nid in order:
        n = nodes[nid]
        es[nid] = max((ef[p] for p in n["preds"] if p in ef), default=0)
        ef[nid] = es[nid] + n["dur"]
    project_end = max(ef.values(), default=0)

    # backward pass: LS/LF
    lf: dict[str, int] = {}
    ls: dict[str, int] = {}
    for nid in reversed(order):
        n = nodes[nid]
        lf[nid] = min((ls[s] for s in succ[nid] if s in ls), default=project_end)
        ls[nid] = lf[nid] - n["dur"]

    out = []
    for nid in nodes:
        n = nodes[nid]
        total = ls[nid] - es[nid]
        free = min((es[s] - ef[nid] for s in succ[nid]), default=project_end - ef[nid])
        out.append({"id": nid, "ref": n["ref"], "name": n["name"], "duration": n["dur"],
                    "es": es[nid], "ef": ef[nid], "ls": ls[nid], "lf": lf[nid],
                    "total_float": total, "free_float": max(0, free), "critical": total <= 0,
                    "predecessors": n["preds"]})
    out.sort(key=lambda x: (x["es"], x["ef"]))
    critical_path = [o["ref"] or o["id"] for o in out if o["critical"]]
    return {"project_duration": project_end, "activity_count": len(nodes),
            "critical_count": sum(1 for o in out if o["critical"]),
            "has_cycle": cyclic, "activities": out, "critical_path": critical_path}
