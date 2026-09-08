"""Tiny XLSX writer wrapper so every export shares formatting (guide §8 → XLSX/CSV)."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .cells import cell as _cell


def write_sheets(path: str, sheets: dict[str, tuple[Sequence[str], Sequence[Sequence[Any]]]]) -> str:
    """sheets = { sheet_name: (headers, rows) }. Returns the path written."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(title=name[:31])
        ws.append([_cell(h) for h in headers])
        for c in ws[1]:
            c.font = Font(bold=True)
        # CSV-SWEEP — a string cell beginning "=" is written by openpyxl as a live FORMULA
        # (measured: data_type='f'), so a COBie workbook handed to an owner would carry whatever a
        # vendor name contained. Numbers, dates and None must NOT be stringified, or every numeric
        # column in every export becomes text — so only str values go through the guard.
        for row in rows:
            ws.append([_cell(v) if isinstance(v, str) else v for v in row])
        # rough autofit
        for col_idx, header in enumerate(headers, start=1):
            width = max(len(str(header)), 10)
            for row in rows[:200]:
                if col_idx - 1 < len(row) and row[col_idx - 1] is not None:
                    width = max(width, min(len(str(row[col_idx - 1])), 60))
            ws.column_dimensions[get_column_letter(col_idx)].width = width + 2
        ws.freeze_panes = "A2"
    wb.save(path)
    return path
