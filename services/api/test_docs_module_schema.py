"""The module-authoring guide lists EXACTLY the field types the platform accepts.

`docs/authoring-modules.md` is the specification a third party writes a module against — the whole
promise of the config-driven layer is that you need no code, which makes the document the product
surface. So it is worth exactly as much as it is accurate, and prose has no way to fail.

**It had already drifted.** The guide listed 10 field types; the schema accepted 16. Missing were
`percent`, `table`, `checkbox`, `email`, `phone` and `file` — including the two most recently added,
which is the pattern: a type gets added to `FIELD_TYPES`, the loader accepts it, the renderer handles
it, and the one artefact a stranger reads never learns about it. An author following the guide would
have used `number` for a percentage and a `textarea` for a list, which is precisely the paper-form
shape the field sweep spent a week undoing.

This is the same class as the four staleness bugs the docs gates already cover (a README flag 50
releases stale, a tutorial naming a deleted sample). The fix is the same: **stop asking people to
remember, and read the file from disk.**

Deliberately a SET comparison in both directions rather than a count:
  * a type in the schema but not the doc -> an author cannot discover it
  * a type in the doc but not the schema -> an author is told to use something the loader refuses,
    which is worse, because it fails only after they have written the module

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_docs_module_schema.py
"""
import os
import re

DOC = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "authoring-modules.md")

from aec_api.module_schema import _NUMERIC_TYPES, FIELD_TYPES, TABLE_COLUMN_TYPES  # noqa: E402

with open(DOC, encoding="utf-8") as fh:
    text = fh.read()

assert len(text) > 2000, f"{DOC} is suspiciously short — did it move?"

# ---- 1. the field-type table lists exactly FIELD_TYPES -------------------------------------------
# The table rows look like `| `text` | single-line input | … |`, so the type is the first inline-code
# cell of a row. Scoped to the section so a stray mention elsewhere in the prose is not counted as a
# table entry — the population must be the TABLE, not the document.
sec = text[text.index("## 2. Fields"):text.index("### 2.1")]
# The HEADER row is also `| `type` | … |`, so it parses as a field type called "type" and the check
# fails on an extra the guide never claimed. Caught by this test on its first run — a parser that
# reads its own header as data is the reason to assert both directions rather than just "nothing
# missing", which would have passed.
documented = {m.group(1) for m in re.finditer(r"^\|\s*`([a-z]+)`\s*\|(?!\s*Renders as)", sec, re.M)}
assert documented, "could not parse the field-type table — its shape changed"

missing = sorted(FIELD_TYPES - documented)
extra = sorted(documented - FIELD_TYPES)
assert not missing, (
    f"field types the platform accepts but the guide does not list: {missing}. An author cannot use "
    "what the documentation does not mention — this is how the guide came to omit `percent` and "
    "`table` while the loader accepted both.")
assert not extra, (
    f"field types the guide lists but the platform refuses: {extra}. Worse than an omission: the "
    "module fails to load only after it has been written.")

# ---- 2. the table-column subset is documented, and documented as a SUBSET -----------------------
col_sec = text[text.index("### 2.3"):text.index("## 3.")]
col_documented = {m.group(1) for m in re.finditer(r"`([a-z]+)`", col_sec)}
col_missing = sorted(TABLE_COLUMN_TYPES - col_documented)
assert not col_missing, f"table column types not documented: {col_missing}"
# and the exclusions are stated, because "why can't I use a reference column" is the first question
for excluded in ("nested table", "rollup", "reference"):
    assert excluded in col_sec, f"the guide does not say why {excluded!r} is not a column type"

# ---- 3. the numeric types are named as the ones that take a unit --------------------------------
unit_sec = text[text.index("### 2.1"):text.index("### 2.2")]
for t in _NUMERIC_TYPES:
    assert f"`{t}`" in unit_sec, f"`{t}` takes a unit but §2.1 does not say so"

# ---- 4. the rules a module author will otherwise get wrong ---------------------------------------
# Each of these is a real constraint enforced by a gate elsewhere. A guide that omits them sends the
# author to a failing build with no explanation, which is the same defect as an undocumented type.
for phrase, why in (
    ("adjacent", "fieldset contiguity — the renderer draws a duplicate heading otherwise"),
    ("additive", "text->reference conversion is unsafe; the convention is to add beside"),
    ("total_column", "a table's total must name a numeric column"),
    ("totals_into", "a table can drive a sibling numeric field; engines read that field"),
    ("unmapped section", "a section with no room makes the module unreachable"),
):
    assert phrase in text, f"the guide does not cover: {why}"

# ---- 5. the seven rooms, named ------------------------------------------------------------------
from aec_api.rooms import ROOMS  # noqa: E402

for r in ROOMS:
    assert r["label"] in text, f"room {r['label']!r} is not named in the guide"

print(f"DOCS MODULE SCHEMA OK - the authoring guide lists exactly the {len(FIELD_TYPES)} field types "
      f"the platform accepts and the {len(TABLE_COLUMN_TYPES)} allowed table-column types, states why "
      "the excluded column types are excluded, names the numeric types that take a unit, covers the "
      "four rules a gate elsewhere enforces (fieldset contiguity, the additive text+reference "
      "convention, a numeric total_column, and an unmapped section being a hard failure), and names "
      "all seven rooms. Asserted as a SET in BOTH directions: a type the schema accepts but the guide "
      "omits cannot be discovered, and a type the guide lists but the schema refuses fails only after "
      "the module has been written. The guide had drifted to 10 of 16 types before this gate existed.")
