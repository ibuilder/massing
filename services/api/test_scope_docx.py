"""SCOPE-DOCX — Exhibit A as an editable Word document, carrying the SAME clauses as the signed PDF.

WHY THE FORMAT EXISTS. The PDF is the signed instrument; the .docx is the copy a subcontractor
redlines and sends back. Scope negotiation is redlining — "here is our scope, strike what you don't
hold" — and a PDF is the wrong object for that exchange. The alternative in practice is the sub
retyping the exhibit, which is exactly where clauses go missing.

WHAT THIS ASSERTS, and the third check is the one with teeth:

  1. The bytes are a **valid Word package** — a zip whose `word/document.xml` exists and whose
     integrity check passes. Word refusing to open a contract exhibit is the failure mode that would
     land on a subcontractor rather than on us, and it is why `python-docx` was taken instead of
     hand-rolling the OOXML.
  2. Merge tokens are **resolved** — an unsubstituted `{{project}}` shipped in a contract document is
     worse than a missing one, because it reads as a template somebody forgot to fill.
  3. **The DOCX, the PDF and the preview carry the same clause set.** All three call
     `scope_library.exhibit_clauses`, extracted when this became the third caller. Two copies of that
     filter is precisely how a plumbing subcontract came to print 31 clauses into a signed PDF against
     11 in its preview, with 20 duplicated from the agreement body. Asserting equality here is what
     stops a third copy re-opening it.

Deliberately NOT asserted: visual layout. Whether a heading is 14pt is not a property anybody argues
over, and a test that pinned it would fail on every styling change while catching nothing that
matters.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_scope_docx.py
"""
import io
import os
import re
import sys
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./test_scope_docx.db"
os.environ["STORAGE_DIR"] = "./test_storage_scope_docx"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scope_docx.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import scope_docx  # noqa: E402
from aec_api import scope_library as sl  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


CTX = {"project": "Tower A", "vendor": "ACME Plumbing", "trade": "Plumbing",
       "owner": "Acme Developers", "retainage": "10%"}

blob = scope_docx.build(CTX)

# --- 1. Word can open it ---------------------------------------------------------------------------
check("the output is a zip", blob[:2] == b"PK", f"starts {blob[:4]!r}")
zf = zipfile.ZipFile(io.BytesIO(blob))
check("...whose integrity check passes", zf.testzip() is None, str(zf.testzip()))
check("...containing word/document.xml", "word/document.xml" in zf.namelist(),
      f"parts: {zf.namelist()[:6]}")
xml = zf.read("word/document.xml").decode("utf-8")

# --- 2. the merge actually merged -------------------------------------------------------------------
check("the document names the project and the vendor",
      "Tower A" in xml and "ACME Plumbing" in xml)
_leftover = re.findall(r"\{\{\w+\}\}", xml)[:4]
check("no unresolved {{token}} survives into a contract document",
      "{{" not in xml,
      f"leftover: {_leftover} — an unfilled token reads as a template nobody completed")
check("the resolved division is named, not just its number",
      "Division 22" in xml and (sl.division_name("22") or "") in xml,
      "a bare number makes a reader look up which trade this exhibit is for")

# --- 3. THE assertion: same clauses as the PDF and the preview --------------------------------------
expected = sl.exhibit_clauses(None, "Plumbing")
check("the DOCX has clauses at all", len(expected) > 0, "nothing to compare — vacuous below")

# Titles are the observable identity in the rendered XML; ids are not printed.
missing = [c["title"] for c in expected if c["title"] not in xml]
check("every clause the shared selector returns is IN the document", not missing,
      f"{missing[:4]} selected but not rendered")

conditions = [c for c in sl.clauses_by_ids(sl.default_ids("Plumbing"))
              if c["category"] not in sl.EXHIBIT_CATEGORIES]
leaked = [c["title"] for c in conditions if c["title"] in xml]
check("and NO conditions clause reached it — those belong to the agreement body", not leaked,
      f"{leaked[:4]} printed in Exhibit A as well as Article 3 — the double-print defect, in Word")
check("...and the conditions set is non-empty, so that check is not vacuous",
      len(conditions) > 3, f"{len(conditions)} conditions clauses")

# --- exclusions are given their own visible section --------------------------------------------------
excl = [c for c in expected if c["category"] == "Exclusions"]
check("the exhibit states exclusions", len(excl) > 0, "the boundary is the half this library is for")
check("...under their own heading, not buried among inclusions", "Exclusions" in xml,
      "an exclusion nobody can find is functionally unstated")

# --- numbering is literal text, and matches every other format ---------------------------------------
numbers = [c["number"] for c in sl.numbered(expected)]
check("clause numbers are printed as text", all(n in xml for n in numbers[:6]),
      f"missing {[n for n in numbers[:6] if n not in xml]} — Word's own list numbering renumbers on "
      f"edit, which is the one thing that must not happen to a cited clause")

# --- the empty case says so rather than looking short -------------------------------------------------
empty = scope_docx.build({**CTX, "trade": "Plumbing"}, clause_ids=["no-such-clause-id"])
exml = zipfile.ZipFile(io.BytesIO(empty)).read("word/document.xml").decode("utf-8")
check("an empty selection says so out loud", "No scope clauses selected" in exml,
      "an empty exhibit attached to a subcontract reads as 'no scope was agreed'")

print(f"\ntest_scope_docx {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
