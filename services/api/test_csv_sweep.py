"""CSV-SWEEP — every spreadsheet a person opens goes through one cell guard, and numbers survive it.

PR #471 fixed spreadsheet formula injection in the module CSV export and lifted the guard beside
`roundtrip_export`, which already had it. That fixed two instances. **It did not sweep the class**,
and the class had four more members, measured live:

  * `accounting.to_gl_csv` — `vendor` and `memo` are record text, in a general-ledger CSV an
    accountant opens. A vendor named `=cmd|'/c calc'!A1` reached the Vendor column verbatim.
  * `aec_data.xlsx.write_sheets` — every XLSX export, including the COBie workbook handed to an
    owner at turnover. Measured: openpyxl writes a string beginning `=` with `data_type='f'` — a
    LIVE FORMULA in the file. (Narrower than CSV, and worth stating precisely: `+SUM(A1:A9)` is
    stored as `data_type='s'`. Assuming "same as CSV" would have been wrong.)
  * `model_query.to_csv` — element names out of an uploaded IFC.
  * `layout.to_penzd_csv` — survey points.

**And the sweep found a regression that #471 itself shipped.** That PR guarded *every* cell of the
module export, reasoning that "a guard applied per-column is one column away from being forgotten".
The reasoning is fine; the guard was wrong. **A negative number begins with a formula lead**, so
`cost_impact = -500.0` exported as `'-500.0` — a text cell where a number belongs, in a sheet
somebody sums. Survey coordinates are the same shape and would have been corrupted outright.

So the guard is now number-aware: a lead is escaped only when the value is not simply a number.
`-1+1` stays escaped, because the danger is an EXPRESSION opening with a lead, not a signed value.

The population is DERIVED here, not listed — a writer added next year is in scope automatically, and
the deriver is proved against a known-unguarded writer before its clean report is believed.

Run: PYTHONPATH=src:../data/src ./.venv/bin/python test_csv_sweep.py
"""
import ast
import os
import pathlib
import subprocess

os.environ["DATABASE_URL"] = "sqlite:///./test_csvsweep.db"
os.environ["STORAGE_DIR"] = "./test_csvsweep_storage"

for f in ("./test_csvsweep.db",):
    if os.path.exists(f):
        os.remove(f)

from aec_api import accounting, layout  # noqa: E402
from aec_data.cells import FORMULA_LEADS, cell  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


# ---- the guard itself -----------------------------------------------------------------------------
check("every executable lead is escaped",
      [cell(c + "x") for c in FORMULA_LEADS] == ["'=x", "'+x", "'-x", "'@x"])
check("ordinary text is untouched", cell("Acme Electrical") == "Acme Electrical")
check("None and empty are empty", cell(None) == "" and cell("") == "")

# THE case #471 got wrong. Each of these is ordinary data in a real export.
for v in ("-500.00", "-123.456", "-1", "+5", "1e-3", "-0.0"):
    check(f"a plain number is NOT escaped: {v}", cell(v) == v, f"got {cell(v)!r}")
# ...and the case that keeps the guard meaningful: an expression, not a signed value.
check("an expression opening with a lead IS escaped", cell("-1+1") == "'-1+1")
check("a lone sign is escaped", cell("-") == "'-")

# ---- the writers, exercised rather than read ------------------------------------------------------
EVIL, EXPR = "=cmd|'/c calc'!A1", "+SUM(A1:A9)"

gl = accounting.to_gl_csv([{"date": "2026-01-01", "ref": "CR-1", "vendor": EVIL,
                            "cost_code": "01-100", "memo": EXPR, "amount": -500.00,
                            "status": "approved", "kind": "bill"}])
row = gl.strip().split("\n")[1]
check("GL CSV: a malicious vendor is neutralised", "'=cmd" in row, row)
check("GL CSV: a malicious memo is neutralised", "'+SUM" in row, row)
check("GL CSV: a NEGATIVE amount stays a number", ",-500.00," in row or row.endswith(",-500.00"),
      f"an accountant sums this column; {row}")

pts = layout.to_penzd_csv([{"number": "P1", "e": -1234.567, "n": -98.7, "z": -3.21,
                            "description": "=HYPERLINK(1)"}])
pl = pts.strip().split("\n")[1]
check("survey points: a formula description is neutralised", "'=HYPERLINK" in pl, pl)
check("survey points: negative coordinates are NOT escaped",
      "-1234.567" in pl and "'-1234.567" not in pl,
      f"escaping a coordinate corrupts the import this format exists for; {pl}")

# The bar bending schedule: `mark` / `size` / `shape_family` come off an uploaded IFC, so anyone who
# can hand the project a model controls them; the rest of the row is numbers a fabricator sums.
from aec_data.rebar_rules import bbs_csv  # noqa: E402

bbs = bbs_csv({"rows": [{"mark": EVIL, "size": "H16", "diameter_mm": 16.0, "shape": "straight",
                         "shape_family": EXPR, "bends": 0, "legs_mm": [], "bend_angles_deg": [],
                         "cut_length_m": 5.5, "count": 12, "unit_mass_kg_m": 1.58,
                         "total_length_m": 66.0, "total_kg": -104.3}],
               "bars": 12, "total_length_m": 66.0, "total_kg": -104.3})
br = bbs.strip().split("\n")[1]
check("BBS: a malicious bar mark is neutralised", "'=cmd" in br, br)
check("BBS: a malicious shape family is neutralised", "'+SUM" in br, br)
check("BBS: a negative mass stays a number", ",-104.3" in br and "'-104.3" not in br,
      f"a fabricator totals this column; {br}")

# ---- XLSX: measured, because openpyxl is narrower than CSV and the difference matters --------------
from openpyxl import load_workbook  # noqa: E402

from aec_data.xlsx import write_sheets  # noqa: E402

path = write_sheets("./test_csvsweep_x.xlsx",
                    {"COBie": (["Name", "Vendor", "Qty"],
                               [["Air Handler", EVIL, 42], ["Pump", EXPR, -3.5]])})
ws = load_workbook(path)["COBie"]
types = {c.coordinate: (c.data_type, c.value) for r in ws.iter_rows() for c in r}
check("XLSX: no cell is a live formula",
      not [k for k, (t, _) in types.items() if t == "f"],
      f"{[k for k, (t, _) in types.items() if t == 'f']}")
check("XLSX: the malicious vendor became text", types["B2"][0] == "s" and types["B2"][1].startswith("'"))
check("XLSX: numbers are still NUMBERS, not stringified",
      types["C2"] == ("n", 42) and types["C3"] == ("n", -3.5),
      f"{types['C2']} {types['C3']} — stringifying every cell would break every numeric column")
os.remove(path)

# ---- the OTHER class: IIF delimiter injection ------------------------------------------------------
#
# The QuickBooks IIF export carries the same record text and is deliberately NOT formula-guarded —
# QuickBooks does not evaluate a leading `=`, and an apostrophe would corrupt the vendor name on
# import. Its own exposure is the delimiters: IIF is tab-separated with newline-terminated records
# and no quoting, so a tab or newline in `vendor`/`memo`/`cost_code` does not corrupt a field, it
# FORGES A RECORD. The count is the assertion — a fixed number of input rows must produce a fixed
# number of physical lines, whatever the text contains.
FORGE = "Acme\tBILL\t2026-01-01\t01-100\tEvil\t-9999.00\tinjected\nTRNS\tBILL"

# `amount` is an invoice amount and is positive here on purpose — `journal()` builds it from
# `sub_invoice.amount`, and `to_iif_bills` supplies the AP sign itself.
clean = accounting.to_iif_bills([{"date": "2026-01-01", "ref": "CR-1", "vendor": "Acme Electrical",
                                  "cost_code": "01-100", "memo": "ok", "amount": 500.00,
                                  "kind": "bill"}])
forged = accounting.to_iif_bills([{"date": "2026-01-01", "ref": "CR-1", "vendor": FORGE,
                                   "cost_code": "01-100", "memo": "line1\nline2", "amount": 500.00,
                                   "kind": "bill"}])
check("IIF: hostile text cannot add a physical RECORD",
      len(forged.split("\n")) == len(clean.split("\n")),
      f"clean={len(clean.split(chr(10)))} forged={len(forged.split(chr(10)))} lines")
check("IIF: hostile text cannot add a FIELD to any record",
      [ln.count("\t") for ln in forged.split("\n")] == [ln.count("\t") for ln in clean.split("\n")],
      f"{[ln.count(chr(9)) for ln in forged.split(chr(10))]}")
# ...and the vendor is still legible. Replacing each delimiter with a SPACE rather than deleting it
# is what keeps this true: stripping would run the words together into `AcmeBILL`, and rejecting the
# row would lose a real bill because somebody pasted a multi-line address into a memo.
check("IIF: the vendor survives as text, delimiters replaced rather than stripped",
      "Acme BILL 2026-01-01" in forged and "AcmeBILL" not in forged,
      f"{[ln for ln in forged.split(chr(10)) if 'Acme' in ln][:1]}")

# ---- the population, DERIVED ----------------------------------------------------------------------
#
# Listing the writers would make this a checklist that a new export silently escapes. But a
# predicate that decides what to LOOK at is the dangerous kind — everything it excludes is invisible
# to its own output — so the two sinks are named by what actually reaches a spreadsheet file:
#
#   CSV   — a `.writerow` / `.writerows` call. There is no other way to put a row in a csv writer.
#   XLSX  — a `.append(...)` call in a function that BOTH holds an openpyxl worksheet (`Workbook`,
#           `create_sheet`, `load_workbook` — the only three sources) AND `save`s it. Both halves
#           are load-bearing and each was found by a wrong draft rather than reasoned out first:
#           with `save` alone, two reportlab PDF canvases were reported (`c.save()` has nothing to
#           do with spreadsheets); with the worksheet source alone, two openpyxl READERS were —
#           `parse_table` and `parse_clash_xlsx` load a workbook and append to a python list, and
#           an import path is not an export. A function that holds a worksheet and persists it is
#           writing a spreadsheet; either half alone is a different thing entirely.
#
#           Narrowing a look-at predicate is the dangerous direction, so all four of those shapes
#           are probes below: the two authoring ones must stay reported, the four non-sinks silent.
#
# Each sink function must reference the shared guard somewhere in its body.
ROOT = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            text=True).strip())
SRC = [ROOT / "services/api/src", ROOT / "services/data/src"]
CSV_SINK = ("writerow", "writerows")
XLSX_AUTHOR = ("Workbook", "create_sheet", "load_workbook")
GUARD = ("cell", "csv_cell", "_cell")


def _names(node) -> set[str]:
    """Every attribute and identifier named anywhere inside `node`."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Name):
            out.add(n.id)
    return out


def is_sink(node) -> bool:
    """Does this function write rows into a spreadsheet file?"""
    called = {n.func.attr for n in ast.walk(node)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    if called & set(CSV_SINK):
        return True
    if "append" not in called:
        return False
    held = _names(node) & set(XLSX_AUTHOR)   # does it hold a worksheet...
    return bool(held) and "save" in called   # ...and write it to a file?


NOT_A_SINK_XLSX_READ = """
from openpyxl import load_workbook
def parse_table(blob):
    wb = load_workbook(blob, read_only=True)
    rows = []
    for r in wb.active.iter_rows(values_only=True):
        rows.append(["" if c is None else c for c in r])
    return rows
"""


def sinks(extra_src: str | None = None):
    """`[(file, func, guarded)]` for every spreadsheet-row writer in both packages."""
    out = []
    srcs = [(str(f.relative_to(ROOT)), f.read_text())
            for d in SRC for f in sorted(d.rglob("*.py"))]
    if extra_src is not None:
        srcs.append(("<probe>", extra_src))
    for rel, text in srcs:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_sink(node):
                # The guard must be CALLED, not merely named. openpyxl worksheets carry their own
                # `.cell` attribute, so a mention would let a real sink read as guarded.
                calls = {(n.func.id if isinstance(n.func, ast.Name) else n.func.attr)
                         for n in ast.walk(node) if isinstance(n, ast.Call)
                         and isinstance(n.func, (ast.Name, ast.Attribute))}
                out.append((rel, node.name, bool(calls & set(GUARD))))
    return out


# **Prove the deriver against BOTH sinks before believing it.** A detector that finds nothing in a
# clean tree and nothing in a dirty one is indistinguishable from a working one — and the first
# draft of this file self-tested only the CSV half, which is exactly how the XLSX half would have
# gone unmeasured. Each probe is the pre-fix shape of a writer this sweep actually repaired.
PRE_FIX_CSV = """
import csv, io
def to_gl_csv(entries):
    buf = io.StringIO()
    w = csv.writer(buf)
    for e in entries:
        w.writerow([e["date"], e["vendor"]])
    return buf.getvalue()
"""
PRE_FIX_XLSX = """
from openpyxl import Workbook
def write_sheets(path, sheets):
    wb = Workbook()
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(list(row))
    wb.save(path)
    return path
"""
PRE_FIX_XLSX_EDIT = """
from openpyxl import load_workbook
def annotate(path, rows):
    wb = load_workbook(path)
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    wb.save(path)
"""
# Near-misses that must NOT be reported, or "0 unguarded" only means the predicate is asleep.
NOT_A_SINK = """
def collect(items):
    out = []
    for i in items:
        out.append(i)
    return out
"""
NOT_A_SINK_PDF = """
from reportlab.pdfgen import canvas
def sheet_pdf(buf, lines):
    c = canvas.Canvas(buf)
    out = []
    for line in lines:
        out.append(line)
        c.drawString(10, 10, line)
    c.save()
    return out
"""
for label, src, want in (("CSV writerow", PRE_FIX_CSV, [("<probe>", "to_gl_csv", False)]),
                         ("XLSX worksheet append", PRE_FIX_XLSX, [("<probe>", "write_sheets", False)]),
                         ("re-saved workbook append", PRE_FIX_XLSX_EDIT, [("<probe>", "annotate", False)]),
                         ("plain list.append", NOT_A_SINK, []),
                         ("reportlab canvas save", NOT_A_SINK_PDF, []),
                         ("openpyxl reader", NOT_A_SINK_XLSX_READ, [])):
    got = [f for f in sinks(src) if f[0] == "<probe>"]
    check(f"the deriver classifies a {label} correctly", got == want,
          f"{got} — if this is wrong the report below means nothing")

found = [f for f in sinks() if f[0] != "<probe>"]
# The import TEMPLATE writes manifest labels only — no record, model or user text reaches it.
EXEMPT = {("services/api/src/aec_api/imports.py", "template_csv")}
check("the derived population is not empty", len(found) >= 8,
      f"{len(found)} sinks — a sweep over an empty population passes for the same reason a correct "
      f"one does: {sorted((f, n) for f, n, _ in found)}")
missing = [(f, n) for f, n, guarded in found if not guarded and (f, n) not in EXEMPT]
check("every spreadsheet writer in both packages names the guard", not missing,
      f"{missing}" if missing
      else f"{len(found)} sinks across 2 packages, {len(EXEMPT)} stated exemption")

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_csv_sweep OK")
raise SystemExit(1 if FAILED else 0)
