"""R22-ENTITLEMENT ① — conditions of approval as tracked items, not a paragraph.

Premise-checked, and three of the ring entry's four clauses were already built: jurisdiction
submittal packages (`jurisdiction_packs.validate`), review cycles (the `entitlement` register's
draft→submitted→hearing→approved/denied/appealed workflow, plus `permit_timeline`), and comment
responses (`submittals.py`). The entry's claim that "nothing spans approval" is stale.

The fourth clause — **conditions of approval carried into the model as constraints** — is genuinely
missing, and it starts one step earlier than the entry assumes. `entitlement.conditions` is a single
**textarea**. An approval carrying fourteen conditions is one paragraph, so nobody can say which have
been discharged, and no constraint can be derived from prose nobody has separated.

This splits that paragraph into individually tracked conditions. It does **not** claim to check them
against the model — that is the next slice, and claiming it here would be the overreach the whole
ring is meant to prevent.

Three refusals, and the first is the one that matters:

1. **a condition this cannot interpret is `unparsed`, never satisfied.** An approval condition
   silently treated as met is a building constructed out of compliance while the report said it was
   fine. Nothing here marks anything satisfied on its own — discharge is a human act, recorded;
2. **an extracted quantity carries the sentence it came from.** Parsing an agency's prose is
   extraction, not authority: a reading of "45" that came from "45 dwelling units" and got filed as
   a height limit would become a silent constraint nobody chose. Every quantity is reported beside
   its source text so a human can check the reading;
3. **an approved entitlement with an EMPTY conditions field is `unrecorded`, not unconditioned.**
   Approvals almost always carry conditions; a blank field far more often means nobody typed them
   than that the agency imposed none. Same distinction as `no_data` vs `not_captured` in
   `provenance_report` — absence of evidence, reported as absence of evidence.
"""
from __future__ import annotations

import re
from typing import Any

STATUS_OPEN = "open"
STATUS_DISCHARGED = "discharged"
STATUS_UNPARSED = "unparsed"

#: An entitlement that reached a terminal approval but records no conditions text.
STATUS_UNRECORDED = "unrecorded"

#: Approval states in the `entitlement` register that mean conditions should exist.
APPROVED_STATES = ("approved",)

#: Leading enumerators an agency uses: "1.", "1)", "(1)", "a.", "Condition 3:", "•", "-".
_ENUM = re.compile(
    r"^\s*(?:\(?\d{1,3}[.)]|\(?[a-z][.)]|condition\s+\d{1,3}\s*[:.]?|[•\-–—])\s+",
    re.I)

#: Quantities worth surfacing, with the unit kept as written. Deliberately narrow: a pattern that
#: matches everything produces confident readings of sentences it did not understand.
_QTY = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ft|feet|foot|m|metres|meters|stor(?:e|ie)ys?|stories|"
    r"spaces?|units?|percent|%)\b", re.I)

_KEYWORDS = {
    "height": ("height", "storey", "story", "stories", "storeys"),
    "setback": ("setback", "set-back", "yard"),
    "parking": ("parking", "stall", "space"),
    "landscape": ("landscap", "tree", "planting", "buffer"),
    "traffic": ("traffic", "trip", "access", "driveway"),
    "affordable": ("affordable", "inclusionary", "workforce"),
    "fee": ("fee", "contribution", "exaction", "in-lieu"),
    "utility": ("sewer", "water", "storm", "utility", "drainage"),
}


def _topic(text: str) -> str | None:
    """Topic by WHOLE-WORD match, not substring.

    Substring matching tagged "a landscape buffer shall be in-STALL-ed" as *parking*, because
    "stall" sits inside "installed". A keyword list matched loosely does not mis-tag rarely — it
    mis-tags exactly the conditions whose wording is most ordinary.
    """
    low = text.lower()
    for topic, words in _KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(w), low) for w in words):
            return topic
    return None


def split_conditions(text: str) -> list[str]:
    """Split an agency's conditions blob into individual conditions.

    Enumerated lines win; failing any enumerator, blank-line-separated paragraphs are used. A blob
    with neither is returned as ONE condition rather than guessed at by sentence — splitting prose on
    full stops turns a single condition containing "Fig. 3" into two, and a condition that was
    invented is worse than one that stayed long.
    """
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    lines = raw.split("\n")
    if any(_ENUM.match(ln) for ln in lines):
        out, cur = [], ""
        for ln in lines:
            if _ENUM.match(ln):
                if cur.strip():
                    out.append(cur.strip())
                cur = _ENUM.sub("", ln)
            else:
                cur += " " + ln.strip()
        if cur.strip():
            out.append(cur.strip())
        return [c for c in (s.strip() for s in out) if c]
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return paras or [raw]


def parse(text: str) -> list[dict[str, Any]]:
    """Conditions as tracked items, each carrying the sentence it came from."""
    out: list[dict[str, Any]] = []
    for i, body in enumerate(split_conditions(text), start=1):
        quantities = [{"value": float(m.group("value")), "unit": m.group("unit").lower(),
                       "source_text": body[max(0, m.start() - 60):m.end() + 20].strip()}
                      for m in _QTY.finditer(body)]
        topic = _topic(body)
        out.append({
            "seq": i, "text": body, "topic": topic, "quantities": quantities,
            # Nothing is ever `discharged` by this function. Discharge is a human act; see refusal 1.
            "status": STATUS_OPEN if topic or quantities else STATUS_UNPARSED,
            "note": ("" if (topic or quantities) else
                     "no topic or quantity could be read from this condition — it is tracked as "
                     "UNPARSED and must be reviewed by a person. It is NOT satisfied, and nothing "
                     "here will mark it so"),
        })
    return out


def assess(entitlement: dict[str, Any], discharged_seqs: set[int] | None = None) -> dict[str, Any]:
    """Condition tracking for one `entitlement` record.

    `discharged_seqs` is what a person has signed off. Nothing is discharged automatically — a
    condition marked met by a parser is a compliance claim nobody made.
    """
    discharged = discharged_seqs or set()
    state = str(entitlement.get("workflow_state") or "")
    data = entitlement.get("data") or {}
    text = data.get("conditions") or ""
    items = parse(text)
    for it in items:
        if it["seq"] in discharged and it["status"] != STATUS_UNPARSED:
            it["status"] = STATUS_DISCHARGED

    approved = state in APPROVED_STATES
    if approved and not items:
        return {"entitlement_id": entitlement.get("id"), "ref": entitlement.get("ref"),
                "workflow_state": state, "status": STATUS_UNRECORDED,
                "conditions": [], "counts": {}, "open_count": 0, "unparsed_count": 0,
                "note": ("this entitlement is APPROVED and records no conditions text. Approvals "
                         "almost always carry conditions, so a blank field far more often means "
                         "nobody typed them than that the agency imposed none. Reported as "
                         "unrecorded — absence of evidence, not evidence of absence")}

    counts: dict[str, int] = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    unparsed = counts.get(STATUS_UNPARSED, 0)
    return {
        "entitlement_id": entitlement.get("id"), "ref": entitlement.get("ref"),
        "workflow_state": state, "status": "tracked" if items else "no_conditions",
        "conditions": items, "counts": counts,
        "open_count": counts.get(STATUS_OPEN, 0),
        "unparsed_count": unparsed,
        "discharged_count": counts.get(STATUS_DISCHARGED, 0),
        "fully_discharged": bool(items) and counts.get(STATUS_DISCHARGED, 0) == len(items),
        "note": (f"{unparsed} condition(s) could not be read and are tracked as UNPARSED. They are "
                 "NOT satisfied — an approval condition silently treated as met is a building put "
                 "up out of compliance while the report said it was fine."
                 if unparsed else
                 ("every condition is discharged" if items and counts.get(STATUS_DISCHARGED) == len(items)
                  else "conditions are tracked; discharge is recorded by a person, never inferred")),
    }


def for_project(db, project_id: str) -> dict[str, Any]:
    """Condition tracking across a project's entitlements."""
    from . import modules as me

    try:
        rows = me.list_records(db, "entitlement", project_id, limit=10_000)
    except Exception:                            # noqa: BLE001 — register absent in a trimmed deploy
        return {"project_id": project_id, "entitlements": [], "unrecorded": [],
                "note": "the entitlement register is not installed here"}
    out = [assess(r) for r in rows]
    return {
        "project_id": project_id,
        "entitlements": out,
        "entitlement_count": len(out),
        "unrecorded": [x["ref"] or x["entitlement_id"] for x in out
                       if x["status"] == STATUS_UNRECORDED],
        "total_open": sum(x.get("open_count") or 0 for x in out),
        "total_unparsed": sum(x.get("unparsed_count") or 0 for x in out),
        "note": ("conditions are tracked, never auto-satisfied. An UNPARSED condition is one nobody "
                 "has read yet, and an APPROVED entitlement with no conditions recorded is reported "
                 "as unrecorded rather than as clean."),
    }
