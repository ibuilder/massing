"""MOD-BACKFILL — populate the additive text+reference pairs from the text already stored.

The field sweep found 74 text fields naming a concept that already had its own register (`vendor`,
`location`, `spec_section`, `system`, `inspector`), and added 54 reference fields **beside** them
rather than converting in place — because a converted field's legacy string would have rendered as a
clickable link labelled with its first eight characters, across 56 modules, with every gate green.

That left the references empty. This fills them in, and the whole design is about **which matches it
refuses to make**.

**A WRONG AUTO-LINK IS WORSE THAN AN EMPTY ONE**, and not by a little. An empty reference is visibly
empty: somebody sees a blank and fills it. A wrong one is a link that resolves, opens a real record,
and shows a plausible name — so it is never questioned, and it silently attributes an RFI to the wrong
subcontractor or a defect to the wrong room. Nothing downstream can tell the difference, because the
value is structurally perfect. This is the same asymmetry as every other defect this codebase has
chased: the dangerous output is the plausible one, not the missing one.

So the matcher is deliberately timid:

* **Exact, after normalisation only.** Case, surrounding whitespace, internal whitespace runs and a
  trailing legal suffix (`Inc`, `LLC`, `Ltd`, `Co`, `Corp`) are normalised away. Nothing else — no
  fuzzy distance, no token overlap, no prefix matching. "Acme Electrical" and "Acme Electric" are
  different companies and this will not pretend otherwise.
* **Unique or nothing.** Two candidate records matching one string is not a 50/50 guess to be broken
  by `created_at` or by id order; it is a question for a human. Ambiguity is reported, never resolved.
* **Never overwrite.** A reference that already has a value is left alone even if it disagrees with the
  text, because somebody may have set it by hand and the hand-set one is the better evidence.
* **Dry run by default.** `apply=False` returns exactly what it would do and changes nothing, so the
  report can be read before anything is written.

The counterpart to timidity is that every skip is REPORTED with its reason. A backfill that silently
does 60% of the work and says "done" leaves the other 40% invisible, which is worse than one that
does 60% and names the rest.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from .modules_query import list_records
from .modules_registry import REGISTRY

#: The suffixes the sweep used when adding a reference beside its text twin.
PAIR_SUFFIXES = ("_company", "_loc", "_spec", "_system", "_contact", "_package")

#: Trailing company-form tokens that carry no identity — "Acme Inc" and "Acme" are one firm.
_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|co|co\.|corp|corp\.|corporation|company|"
    r"plc|lp|llp|pllc|gmbh|pty|sa|nv|bv)$", re.I)


def normalize(s: Any) -> str:
    """The one normalisation both sides go through. Anything this does not fold is a real difference.

    Deliberately shallow: lowercase, collapse whitespace, drop a single trailing legal suffix, strip
    surrounding punctuation. It does NOT strip internal punctuation ("J&J" vs "J and J"), expand
    abbreviations ("Bldg" vs "Building") or do edit-distance — each of those turns a refusal into a
    guess, and a guess here produces a link that looks right.
    """
    t = re.sub(r"\s+", " ", str(s or "")).strip().strip(".,;:-–—").strip()
    if not t:
        return ""
    prev = None
    while prev != t:                       # "Acme Co., Inc." -> "Acme"
        prev = t
        t = _LEGAL_SUFFIX.sub("", t).strip().strip(".,;:-–—").strip()
    return t.lower()


def pairs_for(module_key: str) -> list[tuple[str, str, str]]:
    """[(text_field, reference_field, target_module)] for one module, from its declared fields."""
    mod = REGISTRY.get(module_key) or {}
    by = {f.get("name"): f for f in mod.get("fields", []) if f.get("name")}
    out: list[tuple[str, str, str]] = []
    for name, f in by.items():
        if f.get("type") != "reference" or not f.get("module"):
            continue
        for suf in PAIR_SUFFIXES:
            if name.endswith(suf):
                stem = name[: -len(suf)]
                twin = by.get(stem)
                if twin and twin.get("type") in ("text", "textarea"):
                    out.append((stem, name, f["module"]))
                break
    return sorted(out)


def _index(db: Session, project_id: str, target: str) -> tuple[dict[str, list[str]], int]:
    """normalised title -> [record ids] for a target module, plus how many records were indexed.

    A LIST, not a single id: collisions are the thing this exists to detect, and a dict keyed by title
    would silently keep the last one — which is exactly the quiet wrong answer the whole module is
    written to avoid.
    """
    mod = REGISTRY.get(target) or {}
    tf = mod.get("title_field")
    idx: dict[str, list[str]] = {}
    rows = list_records(db, target, project_id, limit=5000)
    for r in rows:
        data = r.get("data") or {}
        for candidate in (data.get(tf) if tf else None, r.get("ref")):
            key = normalize(candidate)
            if key:
                idx.setdefault(key, []).append(r["id"])
    return idx, len(rows)


def backfill(db: Session, project_id: str, *, module_keys: list[str] | None = None,
             apply: bool = False) -> dict[str, Any]:
    """Fill empty reference fields from their text twins. Returns a full report either way.

    `apply=False` (the default) changes nothing — the report is identical to what an apply would do,
    so it can be read first. Nothing is ever overwritten and no ambiguous match is ever resolved.
    """
    from . import modules as me  # local: the engine imports this module's peers

    keys = module_keys or sorted(REGISTRY)
    linked: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    indexes: dict[str, tuple[dict[str, list[str]], int]] = {}
    scanned = 0

    for key in keys:
        prs = pairs_for(key)
        if not prs:
            continue
        records = list_records(db, key, project_id, limit=5000)
        scanned += len(records)
        for text_field, ref_field, target in prs:
            if target not in indexes:
                indexes[target] = _index(db, project_id, target)
            idx, target_n = indexes[target]
            for r in records:
                data = r.get("data") or {}
                raw = data.get(text_field)
                if data.get(ref_field):
                    continue                          # never overwrite a hand-set link
                norm = normalize(raw)
                if not norm:
                    continue                          # nothing to match on; not a skip worth reporting
                hits = idx.get(norm) or []
                base = {"module": key, "record": r["id"], "ref": r.get("ref") or "",
                        "field": ref_field, "text": str(raw), "target": target}
                if len(hits) == 1:
                    linked.append({**base, "linked_to": hits[0]})
                    if apply:
                        # `party=None`: a backfill is not a workflow actor. It writes one reference
                        # field and must not be able to advance a state or satisfy a party gate —
                        # the actor string keeps it identifiable in the audit trail.
                        me.update_record(db, key, project_id, r["id"], {ref_field: hits[0]},
                                         "system:backfill", None)
                elif len(hits) > 1:
                    # Two records answer to one name. Breaking the tie by id or date would be a coin
                    # flip wearing a suit — it is a question for a human, so it is reported as one.
                    skipped.append({**base, "reason": "ambiguous",
                                    "detail": f"{len(hits)} records in {target} share this name"})
                else:
                    skipped.append({**base, "reason": "no match",
                                    "detail": f"no {target} record is named this "
                                              f"({target_n} indexed)"})
    return {
        "applied": bool(apply),
        "records_scanned": scanned,
        "linked": linked,
        "skipped": skipped,
        "summary": {"linked": len(linked),
                    "ambiguous": sum(1 for s in skipped if s["reason"] == "ambiguous"),
                    "no_match": sum(1 for s in skipped if s["reason"] == "no match")},
        "note": ("Exact match after normalisation only, unique matches only, existing values never "
                 "overwritten. A wrong link resolves, opens a real record and shows a plausible name, "
                 "so it is never questioned — an empty reference is visibly empty and gets filled. "
                 "Every skip is listed with its reason rather than left as a silent shortfall."),
    }
