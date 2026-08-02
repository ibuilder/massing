"""R22-PIPELINE — the acquisition funnel, and the numbers it refuses to invent.

Acquisition is a funnel, not a project: a site is sourced, screened, underwritten, put under LOI,
diligenced and either closed or dropped. Most of it dies. The portfolio dashboards
(`/portfolio/executive`, `/portfolio/construction`) already answer "how are the deals we *won*
doing?" — this answers the question upstream of that one, which nothing did.

**The headline number here is the most dangerous one in the product.** A weighted pipeline value —
Σ(deal value × stage probability) — goes straight into board decks, capital calls and hiring plans.
The industry convention is to multiply by a textbook ladder (10/25/50/75/90%), and that ladder is a
guess about *somebody else's* firm. Dressed in a currency symbol and summed over thirty deals it
stops reading as a guess at all. So:

1. **stage probabilities are DERIVED from this firm's own closed deals, never defaulted.** A stage
   with too little closed history reports `insufficient_history` and its deals are **excluded from
   the weighted total and counted**, rather than silently multiplied by an invented rate. An
   excluded number is visibly incomplete; a defaulted one is invisibly wrong;
2. **conversion needs a denominator that includes the losses.** If dead deals get deleted rather
   than marked, the win rate climbs toward 100% — the most flattering possible artefact of missing
   data. A clean sheet is reported as a data-quality warning, not as a perfect record;
3. **cycle time is right-censored.** Deals still open have no close date, and slow deals are exactly
   the ones still open, so averaging only closed deals understates the truth. Closed cycle time and
   open age are reported side by side and never blended into one "average";
4. **a deal with no value is not a zero-value deal.** It is excluded and counted, because summing it
   as zero quietly shrinks the pipeline.

There is deliberately **no per-deal probability field** on the module. Offering one would collapse
this straight back into the thing it exists to avoid: a number somebody typed, summed as though it
were measured.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: In-flight stages, in order. Index is used for "how far did this deal get?".
STAGES: list[str] = ["sourced", "screening", "underwriting", "loi", "due_diligence", "closing"]
WON, LOST, DEAD = "won", "lost", "dead"
TERMINAL: set[str] = {WON, LOST, DEAD}

#: Closed deals a stage needs before its conversion rate is reported at all. Below this a rate is
#: noise wearing a percentage sign — three deals, two won, is not a 67% stage.
MIN_CLOSED_SAMPLES = 5

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_history"


def _num(v: Any) -> float | None:
    """A number, or None. Never 0.0 for absent — that is the whole point of refusal 4."""
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _d(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _stage_index(state: str) -> int:
    try:
        return STAGES.index(state)
    except ValueError:
        return -1


def furthest_stage(deal: dict, transitions: list[dict] | None = None) -> str | None:
    """The furthest in-flight stage this deal ever reached.

    A closed deal's `workflow_state` is `won`/`lost`/`dead`, which destroys the fact that decides
    everything here — *where* it died. A deal that died in screening and one that died in closing
    are the same row afterwards, and averaging them is how a funnel lies. The transition log keeps
    the history (`transition:*` entries carry `{"from","to"}`), so we recover it from there and fall
    back to the current state only for deals still in flight.
    """
    best = _stage_index(str(deal.get("workflow_state") or ""))
    for t in transitions or []:
        for key in ("to", "from"):
            best = max(best, _stage_index(str((t or {}).get(key) or "")))
    return STAGES[best] if best >= 0 else None


def stage_conversion(deals: list[dict], history: dict[str, list[dict]] | None = None,
                     min_samples: int = MIN_CLOSED_SAMPLES) -> dict[str, Any]:
    """Per-stage probability of eventually closing, derived from this firm's own closed deals.

    For stage S: of the deals that *reached at least* S and have since resolved, what fraction were
    won? Reaching-at-least is the right population — a deal now in closing did pass through
    screening, and pretending otherwise would make late stages look rarer than they are.

    A stage under `min_samples` gets no rate at all. It is the single most important line in this
    module: the alternative is a number computed from two deals that reads exactly like one computed
    from two hundred.
    """
    history = history or {}
    resolved = [d for d in deals if str(d.get("workflow_state") or "") in TERMINAL]
    out: dict[str, Any] = {}
    for i, stage in enumerate(STAGES):
        reached = [d for d in resolved
                   if _stage_index(furthest_stage(d, history.get(str(d.get("id")))) or "") >= i]
        won = [d for d in reached if d.get("workflow_state") == WON]
        n = len(reached)
        if n < min_samples:
            out[stage] = {"status": STATUS_INSUFFICIENT, "closed_samples": n,
                          "needed": min_samples - n, "probability": None,
                          "note": (f"{n} closed deal(s) ever reached {stage}; "
                                   f"{min_samples - n} more needed before a rate means anything. "
                                   "No default is substituted — deals in this stage are excluded "
                                   "from the weighted value and counted separately.")}
        else:
            out[stage] = {"status": STATUS_OK, "closed_samples": n, "won": len(won),
                          "probability": round(len(won) / n, 4), "needed": 0,
                          "note": f"derived from {n} closed deal(s) that reached {stage}"}
    return out


def weighted_value(deals: list[dict], conversion: dict[str, Any],
                   value_field: str = "purchase_price") -> dict[str, Any]:
    """Probability-weighted pipeline value — with everything it could not weight named.

    Two exclusions, both counted rather than absorbed: a stage with no derived rate, and a deal with
    no value. `coverage` is the fraction of in-flight deals that actually made it into the number,
    so a reader can see at a glance whether the headline covers the book or a corner of it.
    """
    weighted = 0.0
    counted = 0
    excluded: list[dict[str, Any]] = []
    in_flight = [d for d in deals if str(d.get("workflow_state") or "") in set(STAGES)]
    for d in in_flight:
        stage = str(d.get("workflow_state"))
        val = _num((d.get("data") or {}).get(value_field))
        conv = conversion.get(stage) or {}
        p = conv.get("probability")
        if val is None:
            excluded.append({"id": d.get("id"), "ref": d.get("ref"), "stage": stage,
                             "reason": "no_value",
                             "note": f"no {value_field}; counting it as 0 would shrink the pipeline "
                                     "silently"})
        elif p is None:
            excluded.append({"id": d.get("id"), "ref": d.get("ref"), "stage": stage,
                             "value": val, "reason": STATUS_INSUFFICIENT,
                             "note": conv.get("note", f"no derived rate for {stage}")})
        else:
            weighted += val * p
            counted += 1
    n = len(in_flight)
    return {"weighted_value": round(weighted, 2), "deals_weighted": counted,
            "deals_in_flight": n,
            "coverage": round(counted / n, 4) if n else None,
            "excluded_count": len(excluded), "excluded": excluded,
            "excluded_value": round(sum(e.get("value") or 0.0 for e in excluded), 2),
            "note": ("weighted value covers only the deals whose stage has enough closed history to "
                     "derive a rate; the rest are listed in `excluded` rather than weighted by a "
                     "default. A partial number that says so beats a complete one that guessed.")}


def cycle_times(deals: list[dict], as_of: date | None = None) -> dict[str, Any]:
    """Days-to-close for resolved deals, and current age for live ones — reported separately.

    Blending them is tempting and wrong in a specific direction: the deals still open are
    disproportionately the slow ones, so a closed-only mean is biased *low* exactly when somebody is
    using it to promise a closing date. This is right-censoring, and the honest handling is to show
    both populations rather than to average across a boundary that means something.
    """
    as_of = as_of or date.today()
    closed_days: list[float] = []
    open_days: list[float] = []
    for d in deals:
        data = d.get("data") or {}
        start = _d(data.get("sourced_on")) or _d(d.get("created_at"))
        if not start:
            continue
        state = str(d.get("workflow_state") or "")
        if state in TERMINAL:
            end = _d(data.get("closed_on"))
            if end:
                closed_days.append((end - start).days)
        elif state in set(STAGES):
            open_days.append((as_of - start).days)

    def _stat(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"count": 0, "median_days": None, "mean_days": None}
        s = sorted(xs)
        mid = len(s) // 2
        med = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
        return {"count": len(s), "median_days": round(med, 1),
                "mean_days": round(sum(s) / len(s), 1)}

    return {"closed": _stat(closed_days), "open_age": _stat(open_days),
            "blended": None,
            "note": ("closed cycle time and open age are NOT combined. Deals still open are the slow "
                     "ones, so a closed-only average understates how long a deal really takes — the "
                     "open population is shown beside it rather than folded into it.")}


def data_quality(deals: list[dict], min_samples: int = MIN_CLOSED_SAMPLES) -> list[dict[str, Any]]:
    """The tells that a funnel is measuring its own record-keeping rather than the market."""
    warnings: list[dict[str, Any]] = []
    resolved = [d for d in deals if str(d.get("workflow_state") or "") in TERMINAL]
    lost = [d for d in resolved if d.get("workflow_state") in (LOST, DEAD)]
    if len(resolved) >= min_samples and not lost:
        warnings.append({
            "code": "no_losses_recorded", "closed": len(resolved),
            "note": (f"all {len(resolved)} resolved deals are marked won and none lost or passed. A "
                     "100% win rate is nearly always deals being deleted instead of marked — which "
                     "inflates every conversion rate here. Treat the rates as unverified until a "
                     "loss is recorded.")})
    missing_value = [d for d in deals
                     if str(d.get("workflow_state") or "") in set(STAGES)
                     and _num((d.get("data") or {}).get("purchase_price")) is None]
    if missing_value:
        warnings.append({
            "code": "deals_without_value", "count": len(missing_value),
            "refs": [d.get("ref") for d in missing_value][:20],
            "note": ("these in-flight deals carry no purchase price, so they cannot enter the "
                     "weighted value. They are excluded, not counted as zero.")})
    no_dates = [d for d in deals if not (_d((d.get("data") or {}).get("sourced_on"))
                                         or _d(d.get("created_at")))]
    if no_dates:
        warnings.append({
            "code": "deals_without_start_date", "count": len(no_dates),
            "note": "no sourced-on or created-at date; these contribute to no cycle-time figure."})
    return warnings


def from_projects(db, project_ids: set[str] | None = None,
                  as_of: date | None = None) -> dict[str, Any]:
    """The funnel across the caller's projects — the only impure function here.

    `project_ids=None` means no restriction (RBAC off / admin); otherwise the roll-up is
    tenant-scoped exactly as `fca.portfolio` and `benchmarking` are, so a portfolio aggregation
    never reaches another tenant's deals.

    The transition log is fetched in **one** query for the whole set and grouped in Python rather
    than per deal — a funnel is read across a whole book, and a per-deal query would make this a
    page that gets slower the better the firm does.
    """
    from sqlalchemy import select

    from . import modules as me
    from .models import RecordActivity

    t = me.TABLES.get("deal")
    if t is None:                       # module not registered (e.g. a trimmed deployment)
        return funnel([], {}, as_of)

    stmt = select(t.c.id, t.c.ref, t.c.data, t.c.created_at, t.c.workflow_state)
    if project_ids is not None:
        stmt = stmt.where(t.c.project_id.in_(project_ids))
    deals = [{"id": i, "ref": r, "data": d or {}, "created_at": c, "workflow_state": s}
             for i, r, d, c, s in db.execute(stmt).all()]

    hq = select(RecordActivity.record_id, RecordActivity.detail).where(
        RecordActivity.module == "deal", RecordActivity.action.like("transition:%"))
    if project_ids is not None:
        hq = hq.where(RecordActivity.project_id.in_(project_ids))
    history: dict[str, list[dict]] = {}
    for rid, detail in db.execute(hq).all():
        history.setdefault(rid, []).append(detail or {})
    return funnel(deals, history, as_of)


def funnel(deals: list[dict], history: dict[str, list[dict]] | None = None,
           as_of: date | None = None, min_samples: int = MIN_CLOSED_SAMPLES) -> dict[str, Any]:
    """The whole funnel: stage counts and value, derived conversion, weighted value, cycle time.

    `history` maps a deal id to its `transition:*` log entries, which is what makes a *derived*
    conversion rate possible at all — see `furthest_stage`.
    """
    as_of = as_of or date.today()
    by_stage: dict[str, dict[str, Any]] = {}
    for stage in STAGES + [WON, LOST, DEAD]:
        rows = [d for d in deals if str(d.get("workflow_state") or "") == stage]
        vals = [v for v in (_num((d.get("data") or {}).get("purchase_price")) for d in rows)
                if v is not None]
        by_stage[stage] = {"count": len(rows), "value": round(sum(vals), 2),
                           "deals_with_value": len(vals)}
    conv = stage_conversion(deals, history, min_samples)
    return {"as_of": as_of.isoformat(), "deal_count": len(deals),
            "stages": STAGES, "terminal_states": sorted(TERMINAL),
            "by_stage": by_stage, "conversion": conv,
            "weighted": weighted_value(deals, conv),
            "cycle_time": cycle_times(deals, as_of),
            "warnings": data_quality(deals, min_samples),
            "min_closed_samples": min_samples}
