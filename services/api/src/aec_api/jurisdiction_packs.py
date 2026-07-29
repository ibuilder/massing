"""R23-JURISDICTION-PACKS — data requirements that belong to an authority, not to a project.

The ring entry: *"jurisdiction-scoped data-requirement rule packs (a regulator defines a pset spec a
submitted model must satisfy). `query_dsl` + `rule_library` + IDS already carry this shape; turnover
data requirements are the same problem."*

Checked before building, and the shape is there while the scoping is not:

* `rule_library` rules are **per project** (`{pid}/rule_library.json`) and hand-authored. Two projects
  in the same city write the same rules twice and drift apart.
* `ids_authoring` builds an IDS from a **use case**, not from a place.
* `Project.jurisdiction` exists and already resolves the IBC edition for code-checking — so the field
  is there and nothing reads it for *data* requirements.

So this adds one thing: a pack is a **named, versioned, attributed** set of requirements keyed to a
jurisdiction, adopted by a project rather than retyped into it. Each requirement is
`rule_library`-shaped (`scope` + `require` selectors) and is evaluated by `rule_library.evaluate()` —
the same evaluator, not a second one. A rule that means something different depending on which engine
ran it is worse than no rule.

**This module ships no regulatory claims, and that is deliberate.** A table asserting "Texas requires
X" would be an invention wearing a citation unless someone had actually read the ordinance, and a
fabricated requirement is worse than a missing one: it fails a model for a rule nobody imposed, and
the person it fails has no way to check. So the built-in library contains exactly one pack, `example`,
labelled as an example and attributed to nobody. Real packs are **imported** — from an authority, by
someone who can point at the document.

That is enforced rather than documented. `validate()` refuses a pack without an `authority`, an
`edition` and a `source` — because a data requirement with no citation is a house rule wearing a
regulator's name, and the whole value of the pack is that a submitting party can look up why.

**Adoption is explicit.** `resolve()` returns the packs whose jurisdiction matches, and a project with
no jurisdiction set gets an empty list and a reason — never a default pack. Same argument as the
contract family in `notice_clock`: a requirement set from the wrong authority is not a conservative
approximation of the right one, it is a different answer that looks exactly like it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import rule_library, storage

#: One global document rather than a per-project sidecar — the point of a pack is that it is shared.
_KEY = "jurisdiction_packs.json"

MAX_PACKS = 100
MAX_REQUIREMENTS = 200

#: Fields a pack must carry to be storable. `authority`/`edition`/`source` are required because a
#: requirement nobody can trace is indistinguishable from one somebody made up.
REQUIRED = ("id", "jurisdiction", "authority", "name", "edition", "source")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

#: `Pset_Foo.Bar` — a property path written with a dot instead of the `::` the resolver uses.
#: It PARSES (as a bare-field existence test), resolves to `e.get("Pset_Foo.Bar")`, and matches
#: nothing, so the requirement reads as satisfied on every model. Parse-validation cannot catch this,
#: which is the point: the grammar is fine and the meaning is wrong.
_DOTTED_PSET = re.compile(r"\b(Pset_|Qto_)[A-Za-z0-9_]*\.[A-Za-z0-9_]+")


def _looks_like_dotted_pset(selector: str) -> str | None:
    m = _DOTTED_PSET.search(selector or "")
    return m.group(0) if m else None


class PackError(ValueError):
    """A pack cannot be stored or applied as given."""


#: The only built-in. Attributed to nobody on purpose: it demonstrates the shape and asserts nothing
#: about any real jurisdiction. Real packs arrive through `import_pack`.
EXAMPLE_PACK: dict[str, Any] = {
    "id": "example",
    "jurisdiction": "EXAMPLE",
    "authority": "(example — not a real authority)",
    "name": "Example data requirements",
    "edition": "0",
    "source": "built-in demonstration pack; replace with a pack from your authority",
    "is_example": True,
    "requirements": [
        # `Pset::Prop`, with TWO colons. `Pset_WallCommon.FireRating` parses cleanly as a bare-field
        # existence test, resolves to `e.get("Pset_WallCommon.FireRating")`, and therefore never
        # matches anything — a requirement that looks enforced and enforces nothing. This pack
        # shipped with exactly that mistake until a test caught it; see `_looks_like_dotted_pset`.
        {"id": "walls-fire-rating", "name": "Walls declare a fire rating",
         "scope": "IfcWall", "require": "Pset_WallCommon::FireRating", "severity": "high"},
        {"id": "doors-fire-rating", "name": "Doors declare a fire rating",
         "scope": "IfcDoor", "require": "Pset_DoorCommon::FireRating", "severity": "high"},
        {"id": "spaces-named", "name": "Spaces are named", "scope": "IfcSpace",
         "require": "name", "severity": "medium"},
    ],
}


def _norm_jurisdiction(j: Any) -> str:
    """Upper-cased and trimmed. Jurisdiction codes are compared, not parsed — `tx`, `TX ` and `Tx`
    are the same place, and treating them as three is how a project silently adopts nothing."""
    return re.sub(r"\s+", " ", str(j or "")).strip().upper()


def validate(pack: dict[str, Any]) -> dict[str, Any]:
    """A normalised pack, or `PackError` naming what is missing.

    The citation fields are not bureaucracy: this module's whole claim is that a requirement belongs
    to an authority. A pack that cannot say whose requirement it is has no standing to fail anyone's
    model, and the person it fails cannot go and read the rule.
    """
    if not isinstance(pack, dict):
        raise PackError("a pack must be an object")
    missing = [f for f in REQUIRED if not str(pack.get(f) or "").strip()]
    if missing:
        raise PackError(
            f"a pack must carry {', '.join(missing)} — a data requirement with no authority, edition "
            "or source is a house rule wearing a regulator's name, and the submitting party has no "
            "way to look up why their model failed")
    pid = str(pack["id"]).strip().lower()
    if not _ID_RE.match(pid):
        raise PackError(f"pack id {pack['id']!r} must be lower-case alphanumeric with . _ - (max 64)")

    reqs = pack.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        raise PackError("a pack must carry at least one requirement")
    if len(reqs) > MAX_REQUIREMENTS:
        raise PackError(f"a pack may carry at most {MAX_REQUIREMENTS} requirements, got {len(reqs)}")

    seen: set[str] = set()
    norm_reqs = []
    for i, r in enumerate(reqs):
        if not isinstance(r, dict):
            raise PackError(f"requirement {i} must be an object")
        for field in ("scope", "require"):
            if not str(r.get(field) or "").strip():
                raise PackError(f"requirement {i} is missing {field!r}")
        # Validated with the SAME parser that will evaluate it. A selector that stores fine and then
        # never matches is a silent pass — the rule looks enforced and enforces nothing.
        for field in ("scope", "require"):
            try:
                rule_library.query_dsl.parse(r[field])
            except rule_library.query_dsl.QueryError as e:
                raise PackError(f"requirement {i} has an unparseable {field}: {e}") from e
            # Parsing is necessary and not sufficient. `Pset_WallCommon.FireRating` is valid grammar
            # — a bare-field existence test — and resolves to a key no element has, so the
            # requirement passes on every model forever. A rule that cannot fail is worse than a
            # missing one: the authority believes it is enforced.
            dotted = _looks_like_dotted_pset(r[field])
            if dotted:
                raise PackError(
                    f"requirement {i}'s {field} contains {dotted!r} — property paths use TWO colons "
                    f"({dotted.replace('.', '::')}). Written with a dot it parses as a bare field "
                    "name, matches nothing, and the requirement silently passes on every model.")
        rid = str(r.get("id") or f"r{i}").strip().lower()
        if rid in seen:
            raise PackError(f"duplicate requirement id {rid!r} — results are keyed on it")
        seen.add(rid)
        sev = str(r.get("severity") or "medium").lower()
        if sev not in rule_library.SEVERITIES:
            raise PackError(f"requirement {rid!r} has unknown severity {sev!r}; "
                            f"known: {', '.join(rule_library.SEVERITIES)}")
        norm_reqs.append({"id": rid, "name": str(r.get("name") or rid), "scope": str(r["scope"]),
                          "require": str(r["require"]), "severity": sev})

    return {
        "id": pid,
        "jurisdiction": _norm_jurisdiction(pack["jurisdiction"]),
        "authority": str(pack["authority"]).strip(),
        "name": str(pack["name"]).strip(),
        "edition": str(pack["edition"]).strip(),
        "source": str(pack["source"]).strip(),
        "is_example": bool(pack.get("is_example")),
        "requirements": norm_reqs,
    }


def _load() -> list[dict[str, Any]]:
    try:
        raw = storage.get(_KEY)
    except Exception:  # noqa: BLE001 — nothing imported yet
        return []
    try:
        d = json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        # Same reasoning as recipe_log: an unreadable store is NOT an empty one, and treating it as
        # empty means the next import overwrites every pack anyone has imported.
        raise PackError(f"the jurisdiction-pack store exists but could not be read ({e}). "
                        "It has NOT been overwritten.") from e
    packs = d.get("packs") if isinstance(d, dict) else None
    if not isinstance(packs, list):
        raise PackError("the jurisdiction-pack store is not a pack document. It has NOT been overwritten.")
    return packs


def library() -> list[dict[str, Any]]:
    """Every pack available — the built-in example plus anything imported."""
    return [EXAMPLE_PACK, *_load()]


def import_pack(pack: dict[str, Any]) -> dict[str, Any]:
    """Validate and store a pack, replacing any pack with the same id."""
    norm = validate(pack)
    if norm["id"] == EXAMPLE_PACK["id"]:
        raise PackError(f"{EXAMPLE_PACK['id']!r} is the built-in example pack id; choose another")
    stored = [p for p in _load() if p.get("id") != norm["id"]]
    if len(stored) >= MAX_PACKS:
        raise PackError(f"at most {MAX_PACKS} imported packs")
    stored.append(norm)
    storage.put(_KEY, json.dumps({"packs": stored}).encode("utf-8"))
    return norm


def delete_pack(pack_id: str) -> bool:
    stored = _load()
    keep = [p for p in stored if p.get("id") != str(pack_id).strip().lower()]
    if len(keep) == len(stored):
        return False
    storage.put(_KEY, json.dumps({"packs": keep}).encode("utf-8"))
    return True


def resolve(jurisdiction: str | None) -> dict[str, Any]:
    """The packs that apply to a jurisdiction.

    No jurisdiction → no packs, with a reason. Never a default: a requirement set from the wrong
    authority is not a conservative approximation of the right one, it is a different answer that
    looks exactly like it — and it would fail a model against rules nobody imposed.
    """
    j = _norm_jurisdiction(jurisdiction)
    if not j:
        return {"jurisdiction": None, "packs": [], "adopted": False,
                "why": "this project has no jurisdiction set, and data requirements belong to a "
                       "jurisdiction — set Project.jurisdiction, or apply a pack explicitly by id"}
    packs = [p for p in library() if p.get("jurisdiction") == j]
    return {"jurisdiction": j, "packs": packs, "adopted": bool(packs),
            "why": None if packs else f"no pack has been imported for {j}"}


def check(idx: dict[str, dict] | None, packs: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the packs' requirements against the model index.

    Delegates every requirement to `rule_library.evaluate()`. Reusing the evaluator rather than
    writing a second one is the point: a requirement expressed in the same selector language must
    mean the same thing whether a project author wrote it or a regulator published it.
    """
    if idx is None:
        return {"model_scored": False, "packs": [], "total_requirements": 0,
                "note": "no model index loaded — a data-requirement check needs a model to check"}
    out = []
    total = failing = violations = 0
    for p in packs:
        res = rule_library.run(idx, p.get("requirements") or [])
        total += res.get("total_rules", 0)
        failing += res.get("failing_rules", 0)
        violations += res.get("total_violations", 0)
        out.append({
            "id": p.get("id"), "name": p.get("name"), "authority": p.get("authority"),
            "edition": p.get("edition"), "source": p.get("source"),
            "is_example": bool(p.get("is_example")),
            **res,
        })
    return {
        "model_scored": True, "packs": out,
        "total_requirements": total, "failing_requirements": failing,
        "total_violations": violations,
        "satisfied": failing == 0 and total > 0,
        # Every result carries its authority and edition. A compliance figure detached from whose
        # rules it measured is the kind of number that gets quoted at somebody.
        "attribution": [{"pack": p.get("id"), "authority": p.get("authority"),
                         "edition": p.get("edition"), "is_example": bool(p.get("is_example"))}
                        for p in packs],
    }
