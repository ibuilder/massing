"""Typed schema for a `module.json` — the single source of truth for what a valid module looks like.

The module engine (`modules.py`) reads config as plain dicts for speed and flexibility, but "what is a
well-formed module" was previously only encoded in an ad-hoc test. This Pydantic layer formalizes it:
one model that both the config test and the runtime loader validate against, so a malformed module is
caught by the same rules everywhere. Validation is *advisory at load* (a bad community module logs a
warning rather than crashing the API) and *authoritative in the test* (the build fails on any issue).

Kept intentionally permissive (`extra="allow"`) — modules carry many optional presentation keys
(icon, fieldset, workspace, rollup wiring, …) and new ones are added often; this validates the load-
bearing structure without freezing the format."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# Field types the config-driven CRUD UI knows how to render. Keep in sync with the web form renderer.
FIELD_TYPES = {"text", "number", "currency", "date", "textarea", "select", "multiselect",
               "reference", "signature", "rollup", "checkbox", "email", "phone", "percent", "file"}


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    type: str
    label: str | None = None
    required: bool = False
    options: list[str] | None = None
    module: str | None = None                 # reference target
    # rollup wiring (type == "rollup")
    source_module: str | None = None
    source_field: str | None = None
    op: str | None = None

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"unknown field type {v!r}")
        return v


class Transition(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    action: str
    # `party` may be a list or a single party string — `rbac.party_allowed` accepts both, so the
    # schema does too, normalizing to a list.
    party: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)

    @field_validator("party", mode="before")
    @classmethod
    def _party_to_list(cls, v):
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


class Workflow(BaseModel):
    model_config = ConfigDict(extra="allow")
    initial: str | None = None
    states: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class ModuleSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str
    name: str | None = None
    fields: list[FieldDef] = Field(default_factory=list)
    workflow: Workflow | None = None
    title_field: str | None = None
    list_columns: list[str] = Field(default_factory=list)


def validate_module(mod: dict, *, known_modules: set[str] | None = None,
                    folder: str | None = None) -> list[str]:
    """Return a list of human-readable problems with one module dict (empty = valid).

    Combines Pydantic structural validation with the cross-field rules the engine relies on:
    unique field names, reference/select wiring, title_field & list_columns & workflow states/
    transitions all pointing at things that exist. `known_modules` (if given) checks reference
    targets exist; `folder` checks the key matches its directory."""
    errors: list[str] = []
    try:
        m = ModuleSchema.model_validate(mod)
    except ValidationError as e:
        key = mod.get("key", folder or "?")
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            errors.append(f"{key}: {loc}: {err['msg']}")
        return errors                          # structural errors first; cross-field checks need a model

    key = m.key
    if folder is not None and key != folder:
        errors.append(f"{folder}: key {key!r} != folder name")

    names = [f.name for f in m.fields]
    seen: set[str] = set()
    for nm in names:
        if nm in seen:
            errors.append(f"{key}: duplicate field {nm!r}")
        seen.add(nm)

    for f in m.fields:
        if f.type == "reference":
            if not f.module:
                errors.append(f"{key}.{f.name}: reference field has no 'module' target")
            elif known_modules is not None and f.module not in known_modules:
                errors.append(f"{key}.{f.name}: reference target module {f.module!r} does not exist")
        if f.type in ("select", "multiselect") and not f.options:
            errors.append(f"{key}.{f.name}: {f.type} field has no options")

    nameset = set(names)
    if m.title_field and m.title_field not in nameset:
        errors.append(f"{key}: title_field {m.title_field!r} is not a field")
    for c in m.list_columns:
        if c not in nameset:
            errors.append(f"{key}: list_column {c!r} is not a field")

    if m.workflow:
        states = set(m.workflow.states)
        if m.workflow.initial and m.workflow.initial not in states:
            errors.append(f"{key}: workflow.initial {m.workflow.initial!r} not in states")
        for t in m.workflow.transitions:
            for label, s in (("from", t.from_), ("to", t.to)):
                if s and s not in states:
                    errors.append(f"{key}: transition {label} {s!r} not in states")
            for req in t.requires:
                if req not in nameset:
                    errors.append(f"{key}: transition {t.action!r} requires non-existent field {req!r}")
    return errors


_NUMERIC_TYPES = {"number", "currency", "percent"}


def validate_record(mod: dict, data: dict) -> list[str]:
    """Validate a record's field values against the module's field defs (empty = valid).

    Only checks fields actually *present* in `data` (so partial PATCH updates are fine), and only the
    one unambiguous type violation that would silently store garbage the UI can't render: a
    non-numeric value in a numeric field (number/currency/percent). Select `options` are treated as
    *suggestions*, not a closed enum — this system routinely stores free-form values a picklist didn't
    anticipate (e.g. a discipline not on the default list), so membership is deliberately NOT enforced.
    Required-field enforcement lives in the engine (`_validate_fields`); unknown extra keys are allowed
    (title aliases, integrations)."""
    errors: list[str] = []
    by_name = {f.get("name"): f for f in mod.get("fields", []) if f.get("name")}
    for name, value in data.items():
        f = by_name.get(name)
        if f is None or value in (None, "", [], {}):
            continue                          # unknown key or empty -> skip (partial update / clear)
        if f.get("type") in _NUMERIC_TYPES:
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{name}: {value!r} is not a number")
    return errors


def validate_dir(modules_dir: Path) -> dict[str, list[str]]:
    """Validate every modules/*/module.json under a directory. Returns {folder: [errors]} for the
    ones with problems (empty dict = all valid). Reads dicts itself so it's independent of the
    engine's global registry (usable from a test or a CLI)."""
    import json

    folders = {p.parent.name for p in modules_dir.glob("*/module.json")}
    out: dict[str, list[str]] = {}
    for p in sorted(modules_dir.glob("*/module.json")):
        folder = p.parent.name
        try:
            mod = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            out[folder] = [f"{folder}: invalid JSON: {e}"]
            continue
        errs = validate_module(mod, known_modules=folders, folder=folder)
        if errs:
            out[folder] = errs
    return out
