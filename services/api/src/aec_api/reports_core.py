"""Report Center — the neutral report model + shared formatting, decoupled from the builders and the
renderers. `Report` is the intermediate structure every builder produces and every renderer consumes
(PDF/Excel), so it lives here with no dependency on either side."""
from __future__ import annotations

from typing import Any


def money(v: Any) -> str:
    """Format a value as whole dollars ("$1,234"); non-numeric / None -> "$0"."""
    try:
        return f"${float(v or 0):,.0f}"
    except (TypeError, ValueError):
        return "$0"


class Report:
    """Neutral report structure → rendered to PDF or Excel."""
    def __init__(self, title: str, subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.kpis: list[tuple[str, str]] = []
        self.tables: list[dict[str, Any]] = []   # {name, headers:[str], rows:[[..]]}
        self.charts: list[dict[str, Any]] = []   # {kind:'bar'|'line', name, categories, series:[{name,values}]}

    def kpi(self, label: str, value: Any):
        self.kpis.append((label, str(value)))
        return self

    def table(self, name: str, headers: list[str], rows: list[list[Any]]):
        self.tables.append({"name": name, "headers": headers, "rows": rows})
        return self

    def chart(self, kind: str, name: str, categories: list[str], series: list[dict[str, Any]]):
        """A bar or line chart for the PDF (the Excel keeps the underlying table for re-charting)."""
        self.charts.append({"kind": kind, "name": name, "categories": categories, "series": series})
        return self
