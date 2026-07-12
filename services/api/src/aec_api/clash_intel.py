"""Clash coordination intelligence — the management layer on top of geometric clash detection.

Detection (`aec_data.clash`) yields *thousands* of raw intersections; a coordinator can only act on
*coordination issues* — one real-world problem, assigned and tracked. This is the bridge, the pattern
every leading tool (Navisworks · Autodesk Model Coordination · Solibri · Revizto) uses:

  raw Clash rows (ephemeral, regenerated every run)  ──group──▶  Issue = one BCF Topic (persistent)

What this engine adds:
  • **Grouping** — greedy by-element set-cover: a duct crossing 12 joists becomes ONE issue
    ("relocate this duct"), not 12 clashes. Order-of-magnitude reduction, keyed on the dominant element.
  • **Severity** — a discipline clash matrix (structural pairs rank highest) × penetration volume ×
    group size → a 0-100 score and a Low/Medium/High/Critical band.
  • **Stable identity** — a `group_hash` (dominant GUID + the other discipline) that survives re-runs,
    so a coordinated federation cycle can auto-mark issues *resolved* (gone) or auto-*reopen* them
    (reappeared) without losing the comment history.
  • **Reconciliation** — diff a new run against the coordination issues on record: new / active /
    resolved / reappeared — and persist a `clash_run` snapshot for burn-down metrics.
  • **KPIs** — open/closed, by discipline pair, by severity, aging, reappearance rate.

Issues are created as `coordination_issue` records (already BCF-native + pinnable + GUID-anchored), so
everything round-trips with any BIM tool. Pure functions + a DB writer; no new dependency.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from . import classification
from . import modules as me

# Building elements that make a clash matter more (moving structure is expensive / needs an engineer).
STRUCTURAL_CLASSES = {
    "ifcbeam", "ifccolumn", "ifcslab", "ifcwall", "ifcwallstandardcase", "ifcfooting",
    "ifcmember", "ifcpile", "ifcplate", "ifcramp", "ifcstair",
}
_SNAP_M = 0.25          # grid-snap for the point in the clash hash (survives geometry jitter)
_SEV_BANDS = ((75, "Critical"), (50, "High"), (25, "Medium"), (0, "Low"))


def _disc(model: str | None, ifc_class: str) -> str:
    """Discipline label: the federated model/discipline name if present, else classify by IFC class."""
    if model:
        return str(model)
    return classification.discipline_name(classification.discipline_of_ifc_class(ifc_class or "")) or "General"


def _is_structural(*classes: str) -> bool:
    return any((c or "").lower() in STRUCTURAL_CLASSES for c in classes)


def clash_hash(guid_a: str, guid_b: str, point: dict) -> str:
    """Stable identity for a single raw clash — order-independent GUID pair + snapped point."""
    a, b = sorted([guid_a or "", guid_b or ""])
    px, py, pz = (round(float(point.get(k, 0.0)) / _SNAP_M) for k in ("x", "y", "z"))
    return hashlib.sha1(f"{a}|{b}|{px}|{py}|{pz}".encode()).hexdigest()[:16]


def _group_hash(key_guid: str, other_disc: str) -> str:
    """Identity for a coordination ISSUE — the dominant element + the discipline it conflicts with.
    Survives re-runs even as individual clash points shift, so reappearance is detectable."""
    return hashlib.sha1(f"{key_guid}|{other_disc}".encode()).hexdigest()[:16]


def _severity(disc_pair_structural: bool, max_volume: float, count: int) -> tuple[str, int]:
    """0-100 severity: base (structural pairs weigh more) + penetration volume + group size."""
    base = 55 if disc_pair_structural else 30
    vol = min(30, 30 * (max_volume / (max_volume + 0.05)))   # saturating; 0.05 m³ ≈ half weight
    grp = min(15, 3 * (count - 1))                            # a systemic routing problem clashes a lot
    score = int(round(base + vol + grp))
    score = max(0, min(100, score))
    label = next(lbl for lo, lbl in _SEV_BANDS if score >= lo)
    return label, score


def analyze(clashes: list[dict]) -> dict[str, Any]:
    """Group raw clashes into coordination issues + score them. Pure — no DB. Returns the groups and
    the run summary (reduction ratio, distribution by discipline pair and severity)."""
    clashes = [c for c in clashes if c.get("a_guid") and c.get("b_guid")]
    n = len(clashes)
    if not n:
        return {"clash_count": 0, "group_count": 0, "reduction": 0.0, "groups": [],
                "by_discipline": {}, "by_severity": {}}

    # element frequency → pick the "dominant" element of each clash (appears in the most clashes).
    freq: Counter = Counter()
    for c in clashes:
        freq[c["a_guid"]] += 1
        freq[c["b_guid"]] += 1

    groups: dict[tuple[str, str], dict] = {}
    for c in clashes:
        ag, bg = c["a_guid"], c["b_guid"]
        a_struct, b_struct = _is_structural(c.get("a_class", "")), _is_structural(c.get("b_class", ""))
        # dominant = higher-frequency element; tie-break to the structural one (anchor on what won't move)
        a_key = (freq[ag], a_struct)
        b_key = (freq[bg], b_struct)
        if b_key > a_key:
            key_g, key_c, key_n, key_m = bg, c.get("b_class", ""), c.get("b_name", ""), c.get("b_model")
            oth_g, oth_c, oth_m = ag, c.get("a_class", ""), c.get("a_model")
        else:
            key_g, key_c, key_n, key_m = ag, c.get("a_class", ""), c.get("a_name", ""), c.get("a_model")
            oth_g, oth_c, oth_m = bg, c.get("b_class", ""), c.get("b_model")
        other_disc = _disc(oth_m, oth_c)
        gid = (key_g, other_disc)
        g = groups.get(gid)
        if g is None:
            g = groups[gid] = {
                "key_guid": key_g, "key_class": key_c, "key_name": key_n,
                "key_disc": _disc(key_m, key_c), "other_disc": other_disc,
                "other_guids": [], "count": 0, "max_volume": 0.0, "point": c.get("point", {}),
                "_structural": False, "member_hashes": [],
            }
        g["other_guids"].append(oth_g)
        g["count"] += 1
        g["member_hashes"].append(clash_hash(ag, bg, c.get("point", {})))
        vol = float(c.get("volume", 0.0) or 0.0)
        if vol >= g["max_volume"]:
            g["max_volume"] = vol
            g["point"] = c.get("point", {})
        g["_structural"] = g["_structural"] or a_struct or b_struct

    out_groups = []
    by_disc: Counter = Counter()
    by_sev: Counter = Counter()
    for g in groups.values():
        label, score = _severity(g["_structural"], g["max_volume"], g["count"])
        disc_pair = " × ".join(sorted({g["key_disc"], g["other_disc"]}))
        p = g["point"] or {}
        loc = f"~({p.get('x', 0):.1f}, {p.get('y', 0):.1f}, {p.get('z', 0):.1f}) m" if p else ""
        ident = g["key_name"] or (g["key_guid"][:8] if g["key_guid"] else "?")
        subject = f"{g['key_class'] or 'Element'} {ident} × {g['other_disc']}" + (f" ({g['count']})" if g["count"] > 1 else "")
        gh = _group_hash(g["key_guid"], g["other_disc"])
        out_groups.append({
            "group_hash": gh, "subject": subject, "disc_pair": disc_pair,
            "severity_label": label, "severity_score": score, "count": g["count"],
            "key_guid": g["key_guid"], "other_guids": list(dict.fromkeys(g["other_guids"])),
            "location": loc, "point": p, "max_volume": round(g["max_volume"], 4),
            "description": (f"{g['count']} clash(es) between {g['key_class']} {ident} and {g['other_disc']} "
                            f"elements. Largest penetration {g['max_volume']:.3f} m³. Coordinate and resolve."),
        })
        by_disc[disc_pair] += 1
        by_sev[label] += 1
    out_groups.sort(key=lambda x: x["severity_score"], reverse=True)
    return {
        "clash_count": n, "group_count": len(out_groups),
        "reduction": round(n / len(out_groups), 1) if out_groups else 0.0,
        "groups": out_groups, "by_discipline": dict(by_disc), "by_severity": dict(by_sev),
    }


def coordinate(db: Session, pid: str, clashes: list[dict], actor: str, party: str | None = "GC",
               label: str | None = None) -> dict[str, Any]:
    """Turn a raw clash result set into tracked coordination issues, reconciled against the prior run.

    New group  → create a `coordination_issue` (open). Existing + still clashing → active (fields refreshed).
    Existing that was resolved/closed but reappears → **auto-reopen** (comment records the run). A
    previously-tracked issue absent from this run → **auto-resolve**. A `clash_run` snapshot is stored."""
    if "coordination_issue" not in me.TABLES:
        return {"error": "coordination_issue module not installed"}
    an = analyze(clashes)
    groups = an["groups"]
    new_hashes = {g["group_hash"] for g in groups}
    run_label = label or f"Run {str(me._now())[:16]}"

    existing: dict[str, dict] = {}
    for r in me.list_records(db, "coordination_issue", pid, limit=100_000):
        h = (r.get("data") or {}).get("clash_hash")
        if h:
            existing[h] = r

    tally = {"new": 0, "active": 0, "resolved": 0, "reappeared": 0}
    for g in groups:
        h = g["group_hash"]
        data = {
            "subject": g["subject"], "discipline": g["disc_pair"], "description": g["description"],
            "priority": g["severity_label"], "location": g["location"],
            "clash_hash": h, "clash_count": g["count"], "severity_score": g["severity_score"],
        }
        guids = [g["key_guid"], *g["other_guids"]]
        rec = existing.get(h)
        if rec is None:
            me.create_record(db, "coordination_issue", pid,
                             {"data": data, "element_guids": guids}, actor, party)
            tally["new"] += 1
            continue
        me.update_record(db, "coordination_issue", pid, rec["id"], data, actor, party)
        if rec.get("workflow_state") in ("resolved", "closed"):
            me.transition(db, "coordination_issue", pid, rec["id"], "reopen", actor, party,
                          note=f"Reappeared in {run_label}")
            tally["reappeared"] += 1
        else:
            tally["active"] += 1

    for h, rec in existing.items():
        if h not in new_hashes and rec.get("workflow_state") in ("open", "assigned"):
            me.transition(db, "coordination_issue", pid, rec["id"], "resolve", actor, party,
                          note=f"Not present in {run_label} — auto-resolved")
            tally["resolved"] += 1

    if "clash_run" in me.TABLES:
        me.create_record(db, "clash_run", pid, {"data": {
            "label": run_label, "clash_count": an["clash_count"], "group_count": an["group_count"],
            "reduction": an["reduction"], "new_count": tally["new"], "active_count": tally["active"],
            "resolved_count": tally["resolved"], "reappeared_count": tally["reappeared"],
            "disciplines": ", ".join(sorted(an["by_discipline"])),
        }}, actor, party)

    return {"run": run_label, **tally, "clash_count": an["clash_count"], "group_count": an["group_count"],
            "reduction": an["reduction"], "by_discipline": an["by_discipline"],
            "by_severity": an["by_severity"],
            "note": "Raw clashes grouped into tracked coordination issues (BCF-native), reconciled "
                    "against the prior run: new / active / resolved / reappeared."}


def _age_days(created) -> float:
    try:
        return round((me._now() - created).total_seconds() / 86400.0, 1)
    except Exception:
        return 0.0


def metrics(db: Session, pid: str) -> dict[str, Any]:
    """Coordination KPIs over the clash-managed issues + run history: status mix, by discipline pair,
    by severity, aging buckets, reappearance rate, and a per-run burn-down series."""
    issues = [r for r in me.list_records(db, "coordination_issue", pid, limit=100_000)
              if (r.get("data") or {}).get("clash_hash")] if "coordination_issue" in me.TABLES else []
    by_status: Counter = Counter()
    by_disc: Counter = Counter()
    by_sev: Counter = Counter()
    ages = {"0-7": 0, "8-14": 0, "15-30": 0, "30+": 0}
    open_states = {"open", "assigned"}
    open_n = 0
    for r in issues:
        st = r.get("workflow_state") or "open"
        by_status[st] += 1
        d = r.get("data") or {}
        by_disc[d.get("discipline") or "—"] += 1
        by_sev[d.get("priority") or "—"] += 1
        if st in open_states:
            open_n += 1
            a = _age_days(r.get("created_at"))
            b = "0-7" if a <= 7 else "8-14" if a <= 14 else "15-30" if a <= 30 else "30+"
            ages[b] += 1
    total = len(issues)
    closed_n = by_status.get("closed", 0) + by_status.get("resolved", 0)

    runs = me.list_records(db, "clash_run", pid, limit=1000) if "clash_run" in me.TABLES else []
    runs = sorted(runs, key=lambda r: r.get("created_at") or me._now())
    burn = [{"run": (r.get("data") or {}).get("label") or r.get("ref"),
             "new": (r.get("data") or {}).get("new_count", 0),
             "resolved": (r.get("data") or {}).get("resolved_count", 0),
             "reappeared": (r.get("data") or {}).get("reappeared_count", 0),
             "issues": (r.get("data") or {}).get("group_count", 0)} for r in runs]
    reappeared_total = sum(b["reappeared"] for b in burn)
    resolved_total = sum(b["resolved"] for b in burn)

    return {
        "total_issues": total, "open": open_n, "closed": closed_n,
        "resolution_rate": round(100 * closed_n / total, 1) if total else 0.0,
        "by_status": dict(by_status), "by_discipline": dict(by_disc), "by_severity": dict(by_sev),
        "aging": ages, "runs": len(burn), "burn_down": burn,
        "reappearance_rate": round(100 * reappeared_total / (resolved_total + reappeared_total), 1)
        if (resolved_total + reappeared_total) else 0.0,
        "note": "Clash coordination KPIs — issue status mix, worst-coordinating discipline pairs, severity "
                "distribution, aging of open issues, and a per-run burn-down with reappearance rate.",
    }
