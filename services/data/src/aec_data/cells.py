"""One spreadsheet-cell guard, shared by every CSV and XLSX writer in both packages.

Excel and Sheets execute a cell beginning `=`, `+`, `-` or `@`, so any user-supplied text written
into a spreadsheet is code in the reader's application. Prefixing an apostrophe forces the cell to
text; `aec_api.routers.standards.roundtrip_export`'s diff parser strips exactly one, which is why
that is the escape rather than a quote or a leading space.

**It lives in `aec_data` because that is the lower package** — `aec_api` imports `aec_data`, not the
other way round — so both the API's CSV writers and this package's XLSX writer can share ONE
definition. Two spellings of a security guard is how one of them stops being applied, which this
repository has now been bitten by once (PR #471 found the module CSV export unguarded while
`roundtrip_export` beside it was guarded).

**openpyxl is narrower than CSV and it was measured, not assumed**: writing `=cmd|'/c calc'!A1`
produces a cell with `data_type='f'` — a live formula — while `+SUM(A1:A9)` is stored as
`data_type='s'`, an ordinary string. So only the `=` lead becomes a formula *in the file*. The guard
still covers all four leads there, because a value re-typed or pasted by the reader is evaluated by
the same rules the CSV path faces, and a guard that is narrower than the threat is the harder one to
reason about later.
"""
from __future__ import annotations

from typing import Any

#: The characters a spreadsheet treats as the start of a formula.
FORMULA_LEADS = ("=", "+", "-", "@")


def _is_number(s: str) -> bool:
    """Is `s` a plain number? A NEGATIVE NUMBER STARTS WITH A FORMULA LEAD, and escaping it is a
    data defect, not a safety measure.

    This is not hypothetical and it is not theoretical: PR #471 guarded every cell of the module CSV
    export on the reasoning that "a guard applied per-column is one column away from being
    forgotten", and shipped. The next sweep measured `cost_impact = -500.0` exporting as `'-500.0`
    — a text cell where a number belongs, in a sheet somebody sums. `-500.00` in a ledger and
    `-123.456` in a survey coordinate file are both ordinary data.

    `-1+1` is NOT a number and stays escaped, which is the case worth keeping: the danger is an
    EXPRESSION beginning with a lead, not a signed value.
    """
    try:
        float(s)
    except (TypeError, ValueError):
        return False
    return True


def cell(v: Any) -> str:
    """`v` as text, with a spreadsheet formula lead neutralised — unless it is simply a number."""
    s = "" if v is None else str(v)
    if s[:1] not in FORMULA_LEADS or _is_number(s):
        return s
    return "'" + s
