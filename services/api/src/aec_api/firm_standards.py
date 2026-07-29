"""R27-FIRM-MEMORY — standards that outlive a project.

`rule_library` is scoped per project (`load(pid)` / `save(pid)`), and so are `design_standards` and
`standards_expert`. But a firm's actual standards are precisely the thing that does *not* change per
project — "every L1 door needs a fire rating" is true on the next job too. Today that gets re-authored
or copy-pasted, which means the firm's standards quietly become forty slightly different sets of rules
and nobody can say which one is the standard.

**Deliberately not an AI feature.** The products selling "institutional memory" reduce to clean
extraction plus safe write-back. We already have both; what was missing was somewhere for a rule to
live that is not a project.

**The scope question, answered honestly.** This codebase has no `Organization` entity — what
`test_tenant_scoping` calls a tenant is RBAC over project membership, not a firm. Rather than invent a
multi-tenant model nobody asked for, "firm" here means **the deployment**: a self-hosted install is one
firm's install. That is a real limitation and it is stated rather than hidden — if organisations arrive
later, `FIRM_SCOPE` becomes an org id and the inheritance logic below does not change.

Persistence reuses `rule_library`'s own blob path under a reserved scope key, so there is exactly one
storage implementation and one validator. `FIRM_SCOPE` cannot collide with a project: project ids are
UUIDs and this is not one.

**The override is the interesting part.** A firm rule that a project silently replaces is how a firm's
standards stop being standards — the project still passes its checks, so nothing ever complains. Every
effective rule therefore carries where it came from, and a project rule that displaces a firm rule says
which one it displaced.
"""
from __future__ import annotations

from typing import Any

from . import rule_library

#: Reserved storage scope for firm-level rules. Not a project id (project ids are UUIDs).
FIRM_SCOPE = "_firm"


def load_rules() -> list[dict]:
    """The firm's standard rules ([] when none have been authored)."""
    return rule_library.load(FIRM_SCOPE)


def save_rules(rules: list[dict]) -> list[dict]:
    """Validate + persist the firm library. Same validator as a project's — a rule that would be
    rejected on a project must not be accepted merely because it was authored at the firm level."""
    return rule_library.save(FIRM_SCOPE, rules)


def effective_rules(pid: str) -> dict[str, Any]:
    """The rules that actually apply to `pid`: the firm's, with the project's layered over them.

    A project rule overrides a firm rule when it carries the **same id** — matching on name would make
    a rename look like a new rule and silently reinstate the firm's version alongside the project's,
    which is worse than either outcome alone.

    Every rule reports its `source`, and an overriding rule names the firm rule it displaced. An
    override is a legitimate act — a job with a client standard that differs from the firm's is normal
    — but it has to be *visible*, because the failure mode here is not a wrong answer, it is a firm
    discovering its standards were quietly optional.
    """
    firm = load_rules()
    own = rule_library.load(pid)
    by_id = {r["id"]: r for r in firm}

    out: list[dict] = []
    overridden: list[dict] = []
    for r in own:
        base = by_id.get(r["id"])
        rule = dict(r, source="project", overrides=None)
        if base:
            rule["overrides"] = {"id": base["id"], "name": base["name"],
                                 "scope": base["scope"], "require": base["require"],
                                 "severity": base["severity"]}
            overridden.append({"id": base["id"], "name": base["name"],
                               "firm_require": base["require"], "project_require": r["require"]})
        out.append(rule)

    own_ids = {r["id"] for r in own}
    inherited = [dict(r, source="firm", overrides=None) for r in firm if r["id"] not in own_ids]
    out.extend(inherited)

    return {
        "rules": out,
        "count": len(out),
        "firm_count": len(firm),
        "inherited_count": len(inherited),
        "overridden_count": len(overridden),
        "project_only_count": len(own) - len(overridden),
        "overridden": overridden,
        "note": ("Firm standards with the project's rules layered over them, matched by rule id. "
                 "`source` says where each rule came from; a project rule that displaces a firm rule "
                 "carries the firm version it replaced under `overrides`, so an override is visible "
                 "as an override rather than looking like the standard. With no firm rules authored "
                 "this returns exactly the project's own library, so inheriting costs nothing."),
    }
