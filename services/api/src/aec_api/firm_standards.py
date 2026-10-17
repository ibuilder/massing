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


def applicable_rules(pid: str) -> dict[str, Any]:
    """What `pid` must actually be CHECKED against, and where each rule came from.

    `effective_rules` answers *what applies here*. This answers *what to run*, and the two differ in
    exactly one place: when neither the firm nor the project has authored anything, the evaluators
    fall back to `rule_library.STARTER_RULES` — three sample rules shipped as a starting point. The
    fallback is legitimate (an empty library would report a vacuous pass over nothing), but those
    three are **not a standard anybody adopted**, so they are labelled `source="starter"` and
    `using_starter` says so, rather than being mixed in silently.

    **This function exists because three callers were each answering the question for themselves and
    two of them got it wrong.** `GET /projects/{pid}/rules` returns `seeded: not stored`, so the
    LISTING has always been honest about the sample fallback. `/projects/{pid}/rules/run` and
    `model_ci.rule_summary` both did `rule_library.load(pid) or STARTER_RULES`, which has two
    consequences nothing reported:

      * **A firm rule the project inherits was never evaluated.** `effective_rules` existed, said in
        its own docstring that the failure mode is *"a firm discovering its standards were quietly
        optional"*, and had exactly one consumer — its own route, which no screen reached. So the
        firm authored standards, every project showed them as inherited on a page nobody opened, and
        the only two things that actually check a model ignored them.
      * **A project with no library of its own was checked against the samples**, and the pass was
        reported with no indication the rules were examples. `model_ci` stores that as the project's
        quality badge.

    Returned as a dict rather than a tuple so a caller cannot silently take the rules and drop the
    provenance — which is the shape of the defect this replaces.
    """
    eff = effective_rules(pid)
    rules = eff["rules"]
    using_starter = not rules
    if using_starter:
        rules = [dict(r, source="starter", overrides=None) for r in rule_library.STARTER_RULES]
    return {
        "rules": rules,
        "provenance": {
            "using_starter": using_starter,
            "firm_count": eff["firm_count"],
            "inherited_count": eff["inherited_count"],
            "overridden_count": eff["overridden_count"],
            "project_only_count": eff["project_only_count"],
            "overridden": eff["overridden"],
            "note": ("No rules have been authored for this project or for the firm, so these are the "
                     "three SAMPLE rules — a pass here is a pass against examples, not against a "
                     "standard. Author a firm library (Standards → Firm standards) or a project one."
                     if using_starter else
                     f"{eff['count']} rule(s) apply: {eff['inherited_count']} inherited from the "
                     f"firm, {eff['project_only_count']} this project's own, "
                     f"{eff['overridden_count']} overriding a firm standard. Every row says which."),
        },
    }


def attach_provenance(result: dict, rules: list[dict]) -> dict:
    """Carry each rule's `source` / `overrides` onto its result row, matched by **id**.

    By id and not by position: `rule_library.run` happens to preserve order 1:1 today, and a result
    row that silently inherited the wrong rule's provenance would attribute a firm standard's failure
    to the project, or the reverse — a wrong answer about who owns a breach, which is worse than no
    answer. A row whose id matches nothing is left with `source: None` rather than guessed at.
    """
    by_id = {r.get("id"): r for r in rules}
    for row in result.get("rules") or []:
        src = by_id.get(row.get("id")) or {}
        row["source"] = src.get("source")
        row["overrides"] = src.get("overrides")
    return result
