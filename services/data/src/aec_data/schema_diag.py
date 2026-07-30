"""R31-SCHEMA-DIAG — validate an IFC against the SCHEMA, not against a spec.

Everything else in this package scores a model against *rules*. `validate.py` runs a buildingSMART
IDS spec through ifctester and reports rule compliance. `norm_valid.py` runs the normative gauntlet
(units assigned, relationships well-formed). Both answer "does this model say what we require?"

**Nothing answered "is this file structurally a valid IFC?"** — an unknown entity type, a `#12345`
that resolves to nothing, an abstract type instantiated directly, a `$` in a slot the schema declares
mandatory, an attribute list of the wrong length. Those are a different failure class, and a model can
score **100% IDS-compliant while another tool refuses to import it**.

That gap did not matter while the platform only read IFC. It matters now that it **writes** it: since
authoring became a first-class goal we emit files, and this is the class of defect a viewer hides —
the geometry still renders, so the file looks fine right up to the moment somebody else opens it.

## Why this is a text pass and not an ifcopenshell walk

The interesting files are the ones **ifcopenshell will not open.** A diagnostic that needs a loaded
model cannot speak about the case it exists for; it reports "failed to parse" and stops, which is the
same information the user already had. So the checks here stream the STEP text and never construct a
model — they work on a file no reader will accept, and locate the fault by instance id.

That is also why this is a char loop rather than a regex over each instance. An attribute list is a
nested, quote-bearing grammar; a regex that pretends otherwise either mis-splits or backtracks, and a
`\\s*`-prefixed quantifier over free text is how this repo earned a ReDoS alert once already.

## The schema is the oracle, never a list in this file

Valid entity names, abstractness, attribute counts and optionality all come from
`ifcopenshell_wrapper.schema_by_name(...)`, which is a reader nobody here wrote. A hand-maintained set
of IFC class names would be wrong within one release of IFC4X3 and wrong *silently* — it would report
a real entity as unknown, or worse, accept a misspelling because the list never had the real name to
disagree with.

Findings are `(code, severity, instance, entity, message)`. `error` means a conforming reader may
reject the file; `warning` means it is accepted but the content is suspect.
"""
from __future__ import annotations

import os
import re
from typing import Any

import ifcopenshell.ifcopenshell_wrapper as _wrapper

#: Schemas this build can introspect. Derived by asking, not by declaring — see module docstring.
#: Ordered longest-first so `IFC4X3_ADD2` is matched before `IFC4` when normalising a header string.
_KNOWN_SCHEMAS = ("IFC4X3_ADD2", "IFC4X3", "IFC4X1", "IFC4", "IFC2X3")

_SCHEMA_RE = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']{1,80})'", re.IGNORECASE)

#: `#123 =` at the start of an instance. Bounded digits: an id longer than this is not an id.
_INSTANCE_RE = re.compile(r"#(\d{1,12})\s*=\s*", re.ASCII)

#: In-memory cap for the FULL diagnostic. `diagnose_text` holds the whole file as a `str` plus a map of
#: every `#N` reference, so peak memory is roughly 2-3x the file size — a 51 MB model costs a few
#: hundred MB. This was **512 MB and that was a lie**: a 512 MB cap cannot be honoured by a whole-file
#: read, and the first full-suite run proved it. `test_schema_diag` raised `MemoryError` and took
#: `test_clash_xml_import` and `test_cbs` down with it, because a diagnostic that exhausts the process
#: does not fail alone. A cap you cannot honour is worse than no cap: it reads as a considered limit.
#:
#: The streaming pre-flight (`scan_unterminated_string`) is not affected and has no such limit — it is
#: the one that runs on the hot path, and it is chunked precisely so it never holds the file.
MAX_BYTES = 96 * 1024 * 1024

MAX_FINDINGS_PER_CODE = 100

#: Cap on tracked `#N` references. The map exists to name the instance that made a dangling reference,
#: which is what makes a finding actionable, but on a 1 M-instance model it is the single largest
#: allocation in the module. Past this the DANGLING_REF check stops accumulating and says so.
MAX_TRACKED_REFS = 400_000


#: Chunk size for the streaming pre-flight. Big enough that a 50 MB file is a handful of reads.
_CHUNK = 1 << 20


def scan_unterminated_string(path: str) -> bool:
    """True if the file ends inside a `'…'` literal — the one fault that CRASHES the parser.

    Runs on the hot path in `ifc_loader.open_model`, so it is a **fast filter with a careful confirm**
    rather than a character walk. A byte-at-a-time scan of a 51 MB model measured **6.4 s**, which is
    30-60% on top of `ifcopenshell.open` itself — far too much to pay on every first open.

    **The filter is quote-count parity, and it is deliberately only trusted in one direction.** Every
    complete string literal contributes an even number of `'` characters — one to open, one to close,
    and two more for each doubled escape — so an odd total means the file ends inside a string. Even
    parity therefore returns immediately, which is every valid file, using `bytes.count` in C.

    The asymmetry is on purpose. `/* … */` comments can hold a stray apostrophe and shift parity, so
    parity alone could be wrong either way. Getting it wrong in the two directions is not equally bad:

    - a **false negative** leaves us exactly where we were before this screen existed — the parser
      crashes on a file it was already crashing on;
    - a **false positive** REFUSES A VALID MODEL, which is a worse bug than the crash it prevents.

    So odd parity never decides anything on its own; it only escalates to the comment-aware confirm.

    **Why this specific fault gets its own function.** `ifcopenshell` 0.8.5 **segfaults** on an IFC
    whose last string literal is never closed — reproduced 3/3, exit 139. A segfault is not an
    exception: `try/except` cannot catch it, so the process handling the upload dies. Other structural
    breaks are not like this. An unclosed parenthesis and a file truncated mid-instance both fail the
    checks in this module and ifcopenshell opens them **without complaint**, so screening on "does not
    parse" would refuse files that work today. The screen has to be exactly as narrow as the crash.
    """
    quotes = 0
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(_CHUNK)
            if not buf:
                break
            quotes += buf.count(b"'")
    if quotes % 2 == 0:
        return False
    # Odd parity: suspicious, and rare enough to afford the exact answer. Reading it whole is bounded
    # by the same cap `diagnose_file` uses — above that, decline to screen rather than hold 2 GB in
    # memory. Declining is the safe direction: it is the behaviour that predates this function.
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return False
    except OSError:
        return False
    with open(path, encoding="utf-8", errors="replace") as fh:
        return _text_ends_in_string(fh.read())


def _finding(code: str, severity: str, message: str, *,
             instance: int | None = None, entity: str | None = None,
             attribute: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message,
            "instance": instance, "entity": entity, "attribute": attribute}


def normalise_schema(raw: str | None) -> str | None:
    """Map a `FILE_SCHEMA` string onto a schema this build can load, or `None`.

    Real headers carry things like `IFC4X3_ADD2`, `IFC4`, and occasionally junk. Matching
    longest-first matters: a prefix test in the other order resolves `IFC4X3` to `IFC4` and then
    validates the file against the wrong schema — which produces confident, wrong findings rather
    than an honest "cannot check".
    """
    if not raw:
        return None
    up = re.sub(r"[^A-Z0-9]", "", raw.upper())
    for s in _KNOWN_SCHEMAS:
        if up.startswith(re.sub(r"[^A-Z0-9]", "", s)):
            return s
    return None


class _SchemaFacts:
    """Entity names, abstractness and attribute shape for one schema — read from ifcopenshell."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._schema = _wrapper.schema_by_name(name)
        self.entities: set[str] = set()
        self.abstract: set[str] = set()
        self.non_entities: set[str] = set()
        for d in self._schema.declarations():
            nm = d.name().upper()
            if d.as_entity() is not None:
                self.entities.add(nm)
                if d.as_entity().is_abstract():
                    self.abstract.add(nm)
            else:
                # type_declaration / enumeration_type / select_type. These are legal INSIDE an
                # attribute (`IFCLABEL('x')`) and illegal as a top-level instance, so they must be
                # told apart from a name that is simply not in the schema at all.
                self.non_entities.add(nm)

    def slots(self, entity_uc: str) -> tuple[int, tuple[tuple[str, bool], ...]] | None:
        """`(slot count, ((attribute name, optional), …))` for an entity, or None if not an entity.

        The count includes DERIVED attributes: they occupy a slot in the SPF instance, written `*`.
        Getting that wrong would flag every subtype with a derived attribute as malformed.
        """
        try:
            decl = self._schema.declaration_by_name(entity_uc)
        except RuntimeError:
            return None
        ent = decl.as_entity()
        if ent is None:
            return None
        attrs = tuple((a.name(), bool(a.optional())) for a in ent.all_attributes())
        return len(attrs), attrs

    def derived_flags(self, entity_uc: str) -> tuple[bool, ...]:
        try:
            ent = self._schema.declaration_by_name(entity_uc).as_entity()
        except RuntimeError:
            return ()
        return tuple(bool(x) for x in ent.derived()) if ent is not None else ()


def split_attributes(body: str) -> list[str] | None:
    """Split one instance's top-level attribute list. `None` if the parentheses never balance.

    `body` is everything from the `(` after the entity name to the matching `)`. Handles SPF string
    escaping (`''` inside `'…'`), nested lists and constructed types, and `/* … */` comments. This is
    the piece a regex cannot do: `IFCAXIS2PLACEMENT3D(#5,$)` inside an attribute must stay one token,
    and a `,` inside a quoted name must not split anything.
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    i, n = 0, len(body)
    in_str = False
    while i < n:
        c = body[i]
        if in_str:
            cur.append(c)
            if c == "'":
                if i + 1 < n and body[i + 1] == "'":   # an escaped quote, not the end of the string
                    cur.append("'")
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
            cur.append(c)
        elif c == "/" and i + 1 < n and body[i + 1] == "*":
            j = body.find("*/", i + 2)
            if j == -1:
                return None
            i = j + 2
            continue
        elif c == "(":
            depth += 1
            cur.append(c)
        elif c == ")":
            depth -= 1
            if depth < 0:
                return None
            cur.append(c)
        elif c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if depth != 0 or in_str:
        return None
    tail = "".join(cur).strip()
    if tail or out:
        out.append(tail)
    return out


def _instances(text: str):
    """Yield `(instance_id, ENTITY_UC, body)` for each `#N = ENTITY(...)` in the DATA section.

    Instances are terminated by `;` at nesting depth 0 and may span lines, so the scan tracks depth
    rather than splitting on newlines — a multi-line `IFCSHAPEREPRESENTATION` is completely ordinary
    and a line-based reader would report every one of them as truncated.
    """
    start = text.upper().find("DATA;")
    pos = 0 if start == -1 else start + 5
    while True:
        m = _INSTANCE_RE.search(text, pos)
        if not m:
            return
        iid = int(m.group(1))
        j = m.end()
        # entity keyword
        k = j
        while k < len(text) and (text[k].isalnum() or text[k] == "_"):
            k += 1
        entity = text[j:k].upper()
        if not entity:
            pos = m.end()
            continue
        # find the balanced attribute list
        while k < len(text) and text[k] in " \t\r\n":
            k += 1
        if k >= len(text) or text[k] != "(":
            yield iid, entity, None
            pos = k
            continue
        depth, in_str, p = 0, False, k
        while p < len(text):
            c = text[p]
            if in_str:
                if c == "'":
                    if p + 1 < len(text) and text[p + 1] == "'":
                        p += 2
                        continue
                    in_str = False
            elif c == "'":
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            p += 1
        if depth != 0:
            yield iid, entity, None
            return
        yield iid, entity, text[k + 1:p]
        pos = p + 1


_REF_RE = re.compile(r"#(\d{1,12})", re.ASCII)


def diagnose_text(text: str, *, schema_hint: str | None = None) -> dict[str, Any]:
    """Structural diagnostics over IFC-SPF text. See module docstring for the check list."""
    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    def add(f: dict[str, Any]) -> None:
        counts[f["code"]] = counts.get(f["code"], 0) + 1
        if counts[f["code"]] <= MAX_FINDINGS_PER_CODE:
            findings.append(f)

    hdr = _SCHEMA_RE.search(text)
    raw_schema = hdr.group(1) if hdr else None
    schema = normalise_schema(schema_hint or raw_schema)
    if schema is None:
        add(_finding("SCHEMA_UNSUPPORTED", "error",
                     f"FILE_SCHEMA is {raw_schema!r}; this build can check "
                     f"{', '.join(_KNOWN_SCHEMAS)}. Structural checks below are skipped, so a clean "
                     f"result here does NOT mean the file is valid."))
        return {"schema": raw_schema, "checked_schema": None, "passed": False,
                "instances": 0, "summary": _summarise(findings, counts), "findings": findings}

    facts = _SchemaFacts(schema)
    defined: set[int] = set()
    referenced: dict[int, int] = {}     # ref id -> first instance that referenced it
    total = 0

    for iid, entity, body in _instances(text):
        total += 1
        if iid in defined:
            add(_finding("DUPLICATE_ID", "error", f"#{iid} is defined more than once", instance=iid,
                         entity=entity))
        defined.add(iid)

        if body is None:
            add(_finding("UNPARSEABLE_INSTANCE", "error",
                         "attribute list is missing or its parentheses never close",
                         instance=iid, entity=entity))
            continue

        if len(referenced) < MAX_TRACKED_REFS:
            for rm in _REF_RE.finditer(body):
                referenced.setdefault(int(rm.group(1)), iid)

        if entity not in facts.entities:
            if entity in facts.non_entities:
                add(_finding("NOT_AN_ENTITY", "error",
                             f"{entity} is a type/enumeration in {schema}, not an entity — it is "
                             f"legal inside an attribute but cannot be a top-level instance",
                             instance=iid, entity=entity))
            else:
                add(_finding("UNKNOWN_ENTITY", "error",
                             f"{entity} is not declared in {schema}", instance=iid, entity=entity))
            continue
        if entity in facts.abstract:
            add(_finding("ABSTRACT_ENTITY", "error",
                         f"{entity} is ABSTRACT in {schema} and cannot be instantiated; use a "
                         f"concrete subtype", instance=iid, entity=entity))

        parts = split_attributes(body)
        if parts is None:
            add(_finding("UNPARSEABLE_ATTRS", "error", "attribute list could not be split",
                         instance=iid, entity=entity))
            continue
        shape = facts.slots(entity)
        if shape is None:
            continue
        want, attrs = shape
        got = len(parts)
        if got != want:
            add(_finding("ATTR_COUNT", "error",
                         f"{entity} declares {want} attributes in {schema}; this instance has {got}",
                         instance=iid, entity=entity))
            continue
        derived = facts.derived_flags(entity)
        for idx, (val, (aname, optional)) in enumerate(zip(parts, attrs)):
            is_derived = idx < len(derived) and derived[idx]
            if val == "*" and not is_derived:
                add(_finding("UNEXPECTED_DERIVED", "error",
                             f"{aname} is written as derived (*) but {entity} does not derive it",
                             instance=iid, entity=entity, attribute=aname))
            elif val == "$" and not optional and not is_derived:
                add(_finding("MISSING_REQUIRED", "error",
                             f"{aname} is mandatory for {entity} in {schema} but is $",
                             instance=iid, entity=entity, attribute=aname))
            elif val == "" and want > 1:
                add(_finding("EMPTY_SLOT", "error",
                             f"{aname} is an empty slot; SPF requires $ for unset",
                             instance=iid, entity=entity, attribute=aname))

    for ref, by in sorted(referenced.items()):
        if ref not in defined:
            add(_finding("DANGLING_REF", "error",
                         f"#{ref} is referenced by #{by} but never defined", instance=by))
    if len(referenced) >= MAX_TRACKED_REFS:
        # Said out loud, because "no dangling references found" and "stopped looking for them" are
        # the same output otherwise — the exact shape of a cap that hides its own truncation.
        add(_finding("REFS_NOT_FULLY_CHECKED", "warning",
                     f"reference tracking stopped at {MAX_TRACKED_REFS} distinct ids; "
                     f"DANGLING_REF is incomplete for this model"))

    if _text_ends_in_string(text):
        add(_finding("UNTERMINATED_STRING", "error",
                     "the file ends inside an unclosed ' literal — ifcopenshell 0.8.5 SEGFAULTS on "
                     "this (not an exception; the process dies), so it is refused before any read"))

    if total == 0:
        add(_finding("NO_INSTANCES", "error",
                     "no `#N = ENTITY(...)` instances found — not an IFC-SPF file, or the DATA "
                     "section is empty"))

    summary = _summarise(findings, counts)
    return {"schema": raw_schema, "checked_schema": schema,
            "passed": summary["error"] == 0, "instances": total,
            "summary": summary, "findings": findings}


def _text_ends_in_string(text: str) -> bool:
    """In-memory twin of `scan_unterminated_string`. Asserted equal to it in the tests, because two
    implementations of one rule WILL drift — the whole point of `assert-read-write-symmetry`."""
    in_str = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if not in_str and c == "/" and i + 1 < n and text[i + 1] == "*":
            # A comment may contain an apostrophe, which is exactly what makes raw parity unsafe.
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c != "'":
            i += 1
            continue
        if not in_str:
            in_str = True
            i += 1
        elif i + 1 < n and text[i + 1] == "'":
            i += 2
        else:
            in_str = False
            i += 1
    return in_str


def _summarise(findings: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
    """Totals from `counts`, NOT from the truncated `findings` list.

    The distinction is the whole point: `findings` is capped per code so a file with 40,000 dangling
    references does not produce a 40,000-row payload, but the *count* must stay true. Summarising the
    truncated list would report 100 and read as a nearly-clean file.
    """
    err = sum(n for c, n in counts.items() if _SEVERITY.get(c, "error") == "error")
    warn = sum(n for c, n in counts.items() if _SEVERITY.get(c, "error") == "warning")
    return {"error": err, "warning": warn, "by_code": dict(sorted(counts.items())),
            "reported": len(findings), "truncated": any(n > MAX_FINDINGS_PER_CODE
                                                        for n in counts.values())}


#: Severity per code, so `_summarise` never has to re-derive it from the truncated finding list.
_SEVERITY = {
    "SCHEMA_UNSUPPORTED": "error", "DUPLICATE_ID": "error", "UNPARSEABLE_INSTANCE": "error",
    "UNPARSEABLE_ATTRS": "error", "UNKNOWN_ENTITY": "error", "NOT_AN_ENTITY": "error",
    "ABSTRACT_ENTITY": "error", "ATTR_COUNT": "error", "MISSING_REQUIRED": "error",
    "UNEXPECTED_DERIVED": "error", "EMPTY_SLOT": "error", "DANGLING_REF": "error", "UNTERMINATED_STRING": "error",
    "NO_INSTANCES": "error",
    "REFS_NOT_FULLY_CHECKED": "warning", "FILE_TOO_LARGE": "error",
}


def diagnose_file(path: str, *, schema_hint: str | None = None) -> dict[str, Any]:
    """Diagnose an IFC-SPF file on disk. Never loads a model, so a broken file is still diagnosable."""
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        return {"schema": None, "checked_schema": None, "passed": False, "instances": 0,
                "summary": {"error": 1, "warning": 0, "by_code": {"FILE_TOO_LARGE": 1},
                            "reported": 1, "truncated": True},
                "findings": [_finding("FILE_TOO_LARGE", "error",
                                      f"{size} bytes exceeds the {MAX_BYTES}-byte in-memory cap for the full "
                                      f"diagnostic; the streaming pre-flight still applies")]}
    with open(path, encoding="utf-8", errors="replace") as fh:
        return diagnose_text(fh.read(), schema_hint=schema_hint)
