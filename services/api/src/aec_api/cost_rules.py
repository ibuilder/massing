"""ESTIMATE-DARK — the cost rule set a rules-based estimate needs, stored so a firm can author it.

`POST /projects/{pid}/cost/estimate` and `POST /projects/{pid}/cost/sov` have been computable since
R25 and callable by nobody, and the blocker was not a missing screen. Both take a `rules` body —
`fived.validate_rules` wants `{selector, code, basis, unit_cost | rate_from: "vintage"}` — and
**nothing in this product stored a cost rule set**, so a card would have had to invent one. *An
estimate computed from rules the user never chose is a number with no author*, which is why the
roadmap entry refused to ship a default in place of a store.

`rule_library` is the deliberate NON-candidate and the shape to copy. It stores model-CHECK rules,
`{scope, require, severity}` — two QUERY-DSL selectors and a severity, answering *does the model
comply*. These answer *what does the model cost*. Both are "rules", both are QUERY-DSL, and they are
different vocabularies: **adjacent names are adjacent in nothing else.** So this is a sibling store
with the same mechanics (one JSON blob per project, validate-all-before-write, a bounded size, a
starter set) and its own vocabulary, rather than a field bolted onto that one.

VALIDATION IS NOT DUPLICATED. `save()` calls `fived.validate_rules`, the same function the estimate
runs, so a rule set that stores is a rule set that prices. Re-implementing the checks here would let
the two drift, and the drift would surface as a 422 at estimate time on a rule the editor accepted —
the error furthest from the person who can fix it.
"""
from __future__ import annotations

import json
from typing import Any

from . import fived, storage
from .query_dsl import QueryError

_KEY = "{pid}/cost_rules.json"

#: Bounded for the same reason `rule_library.MAX_RULES` is: a stored rule set is evaluated
#: O(rules × predicates × elements) by every `/cost/estimate`, which makes it an editor-authored
#: input driving an expensive POST.
#:
#: DERIVED from `fived.MAX_RULES` rather than restated, so the save bound and the estimate bound
#: cannot drift apart. Restating it is how a project comes to hold a set the estimate then refuses —
#: a 422 arriving at the far end of the one path the store exists to keep clear.
MAX_RULES = fived.MAX_RULES

#: Seeded when a project has never saved a set — real, editable defaults rather than an empty box.
#:
#: **Every one carries a QUOTED rate, and not `rate_from: "vintage"`, deliberately.** A vintage rule
#: prices off the project's pinned cost database and lands in `no_rate` when there is not one — so a
#: starter set built on vintage rates would hand a brand-new project an estimate of zero lines and a
#: `no_rate_count` equal to its whole model. Technically honest, and useless as a starting point.
#:
#: The numbers are order-of-magnitude placeholders in 2026 USD and say so in `description`, because
#: **a starter rate that looks authored is worse than one that looks provisional** — and `seeded`
#: travels with them so a screen can refuse to present the total as the firm's own.
STARTER_RULES: list[dict[str, Any]] = [
    {"selector": "IfcWall", "code": "03 30 00", "basis": "area", "unit_cost": 28.0,
     "rate_from": "quoted", "description": "Walls, per ft² (PLACEHOLDER rate — edit me)"},
    {"selector": "IfcSlab", "code": "03 30 53", "basis": "area", "unit_cost": 16.0,
     "rate_from": "quoted", "description": "Slabs, per ft² (PLACEHOLDER rate — edit me)"},
    {"selector": "IfcColumn", "code": "05 12 00", "basis": "volume", "unit_cost": 520.0,
     "rate_from": "quoted", "description": "Columns, per ft³ (PLACEHOLDER rate — edit me)"},
    {"selector": "IfcDoor", "code": "08 11 00", "basis": "count", "unit_cost": 1450.0,
     "rate_from": "quoted", "description": "Doors, each (PLACEHOLDER rate — edit me)"},
    {"selector": "IfcWindow", "code": "08 50 00", "basis": "count", "unit_cost": 980.0,
     "rate_from": "quoted", "description": "Windows, each (PLACEHOLDER rate — edit me)"},
]


def load(pid: str) -> list[dict]:
    """The project's saved cost rules ([] if none saved yet — callers fall back to STARTER_RULES)."""
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("rules", [])
    except Exception:                                 # noqa: BLE001 — no blob yet / unreadable
        return []


def save(pid: str, rules: list[dict]) -> list[dict]:
    """Validate + persist the set. Raises QueryError on any bad rule, and nothing is written.

    ATOMIC on purpose, exactly as the rule library is: a partially-saved cost rule set would price
    part of the model at rates the author did not finish choosing, and the half that stored would
    look as deliberate as the half that did not.
    """
    if len(rules or []) > MAX_RULES:
        raise QueryError(f"too many rules ({len(rules)}) — max {MAX_RULES}")
    clean = fived.validate_rules(list(rules or []))   # validate ALL before persisting
    storage.put(_KEY.format(pid=pid), json.dumps({"rules": clean}).encode("utf-8"))
    return clean


def effective(pid: str) -> tuple[list[dict], bool]:
    """`(rules, seeded)` — the set an estimate should run, and whether it is the starter set.

    Returned as a pair rather than letting each caller write `load(pid) or STARTER_RULES`, because
    there are two callers (`/cost/estimate` and `/cost/sov`) that MUST agree on the rule set or the
    schedule of values is billed against a different estimate than the one the estimate endpoint
    returns — the exact split `_run_estimate` exists to prevent one layer up. And `seeded` has to
    travel with them: an estimate priced from placeholder rates nobody chose is not the same claim as
    one priced from the firm's own, and a total that cannot say which is a number with no author.
    """
    stored = load(pid)
    return (stored or [dict(r) for r in STARTER_RULES], not stored)
