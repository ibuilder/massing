"""Bid leveling — normalize competing subcontractor bids into an apples-to-apples comparison grid.

The `bid_submission` module already stores structured bids (base_bid, alternates, unit_prices,
inclusions, exclusions, qualifications, bond), so the core comparison is deterministic and works fully
offline: base-bid stats + outliers, a scope matrix (who includes/excludes each scope item), scope-gap
detection, and an apparent-low + scope-adjusted recommendation. When ANTHROPIC_API_KEY is set, an
optional AI pass canonicalizes the free-text inclusion/exclusion phrases so near-duplicates line up in
one row — otherwise raw phrases are used verbatim (never fabricated). This is the Belidor "bid
leveling" capability, grounded in bids you already captured."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import settings_store
from .ai import ai_enabled

_log = logging.getLogger("aec.bidlevel")


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def _as_list(v: Any) -> list[str]:
    """inclusions/exclusions may be a list, or a newline/semicolon/comma string."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if not v:
        return []
    return [p.strip() for p in re.split(r"[\n;]+", str(v)) if p.strip()]


def _canon(phrase: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", phrase.lower()).strip()


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    s = sorted(values)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    avg = sum(s) / n
    lo, hi = s[0], s[-1]
    spread_pct = round((hi - lo) / lo * 100, 1) if lo else 0.0
    return {"count": n, "low": lo, "high": hi, "median": median, "average": round(avg, 2),
            "spread_pct": spread_pct}


def _outliers(bids: list[dict]) -> list[str]:
    """Bidders whose base is >25% off the median (either way) — worth a second look (missing scope /
    error / buy-out)."""
    vals = [(b["bidder"], b["base"]) for b in bids if b["base"] is not None]
    if len(vals) < 3:
        return []
    s = sorted(v for _, v in vals)
    median = s[len(s) // 2]
    if not median:
        return []
    return [name for name, v in vals if abs(v - median) / median > 0.25]


def _normalize(bid: dict) -> dict:
    d = bid.get("data", {}) if "data" in bid else bid
    base = _num(d.get("base_bid")) if d.get("base_bid") not in (None, "") else _num(d.get("amount"))
    return {
        "bidder": d.get("bidder") or bid.get("title") or "(unnamed)",
        "ref": bid.get("ref"),
        "base": base,
        "alternates": _as_list(d.get("alternates")),
        "inclusions": _as_list(d.get("inclusions")),
        "exclusions": _as_list(d.get("exclusions")),
        "qualifications": _as_list(d.get("qualifications")),
        "bond": bool(d.get("bond_provided")),
    }


def _ai_canon_map(phrases: list[str]) -> dict[str, str]:
    """Optional: map each raw phrase -> a canonical scope-item label so near-duplicates merge into one
    grid row. Returns {} on any failure (caller falls back to raw canonicalization)."""
    uniq = sorted({p for p in phrases if p})
    if not uniq or not ai_enabled():
        return {}
    schema = {"type": "object", "additionalProperties": False, "required": ["items"],
              "properties": {"items": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False, "required": ["phrase", "canonical"],
                  "properties": {"phrase": {"type": "string"}, "canonical": {"type": "string"}}}}}}
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"), timeout=60.0, max_retries=1)
        resp = client.messages.create(
            model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=4096,
            system=("You normalize subcontractor bid scope phrases. Map each raw phrase to a short "
                    "canonical scope-item label so equivalent items from different bidders share the "
                    "same label (e.g. 'furnish & install ductwork' and 'provide all duct' -> 'Ductwork'). "
                    "Keep labels 1-4 words. Do not merge genuinely different items."),
            messages=[{"role": "user", "content": json.dumps(uniq)}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"})
        out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return {i["phrase"]: i["canonical"] for i in json.loads(out).get("items", [])}
    except Exception as e:                                    # noqa: BLE001
        _log.warning("AI scope normalization failed (%s) — using raw phrases", e)
        return {}


def level(bids: list[dict]) -> dict[str, Any]:
    """Level a list of bid_submission records (or raw {bidder,base_bid,inclusions,...} dicts)."""
    norm = [_normalize(b) for b in bids]
    norm = [b for b in norm if b["bidder"] != "(unnamed)" or b["base"] is not None]
    if not norm:
        return {"vendors": [], "message": "No bids to level — capture bid submissions for this package first."}

    base_stats = _stats([b["base"] for b in norm if b["base"] is not None])
    outliers = set(_outliers(norm))

    # Build a canonical label for every inclusion/exclusion phrase (AI when available, else raw).
    all_phrases = [p for b in norm for p in (b["inclusions"] + b["exclusions"])]
    ai_map = _ai_canon_map(all_phrases)

    def label(p: str) -> str:
        return ai_map.get(p) or (_canon(p)[:48] or p[:48])

    # scope matrix: canonical item -> {vendor: 'included'|'excluded'} (+ example phrase)
    matrix: dict[str, dict[str, str]] = {}
    examples: dict[str, str] = {}
    for b in norm:
        for p in b["inclusions"]:
            lab = label(p)
            matrix.setdefault(lab, {})[b["bidder"]] = "included"
            examples.setdefault(lab, p)
        for p in b["exclusions"]:
            lab = label(p)
            matrix.setdefault(lab, {}).setdefault(b["bidder"], "excluded")
            examples.setdefault(lab, p)

    vendors = [b["bidder"] for b in norm]
    rows = []
    gaps = []
    for lab, per in sorted(matrix.items()):
        included = [v for v in vendors if per.get(v) == "included"]
        excluded = [v for v in vendors if per.get(v) == "excluded"]
        # a gap = some bidders include it, others exclude it or are silent on it
        is_gap = bool(included) and len(included) < len(vendors)
        rows.append({"item": lab, "example": examples.get(lab, lab),
                     "included_by": included, "excluded_by": excluded, "gap": is_gap})
        if is_gap:
            silent = [v for v in vendors if v not in included and v not in excluded]
            gaps.append({"item": lab, "included_by": included,
                         "excluded_or_silent": excluded + silent})

    # recommendation: apparent low, flagged if it's an outlier or misses scope others carry
    apparent_low = min((b for b in norm if b["base"] is not None),
                       key=lambda b: b["base"], default=None)
    rec = None
    if apparent_low:
        missing = [g["item"] for g in gaps if apparent_low["bidder"] in g["excluded_or_silent"]]
        rec = {"apparent_low": apparent_low["bidder"], "base": apparent_low["base"],
               "is_outlier": apparent_low["bidder"] in outliers,
               "missing_scope": missing,
               "note": ("Lowest base bid." if not missing else
                        "Lowest base, but does not clearly include scope other bidders carry — "
                        "level for these before award.")}

    return {"vendors": vendors, "base_stats": base_stats, "outliers": sorted(outliers),
            "scope_rows": rows, "gaps": gaps, "recommendation": rec,
            "bids": [{"bidder": b["bidder"], "ref": b["ref"], "base": b["base"],
                      "alternates": b["alternates"], "bond": b["bond"],
                      "qualifications": b["qualifications"]} for b in norm],
            "source": "claude+rules" if ai_map else "rules"}
