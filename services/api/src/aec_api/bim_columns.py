"""Columnar / interned BIM data layer (G1) — a memory- and query-efficient view of the property index.

Inspired by Ara3D's BimOpenSchema (MIT): BIM data is stored **columnar** with **string/number interning**
and materialised as **Parquet** for analytical query (DuckDB / pandas / Polars / pyarrow). Our runtime
property index is a per-element JSON dict (`{guid: {…, psets:{…}}}`) — convenient but RAM-heavy on large
models because the same strings ("Concrete", "IsExternal", "Pset_WallCommon"…) repeat thousands of times.

This module builds the interned columnar form on demand:
  * a **string table** + **number table** (each distinct value stored once),
  * an **element table** (one row per element: guid, class, type, name, storey, discipline),
  * an **EAV parameter table** (one row per property/quantity: guid, group, set, prop, value) — the
    place interning pays off, since psets are highly repetitive.

`interning_stats()` quantifies the win (dedup ratio + bytes saved); `params_parquet()` emits the EAV
table as Parquet; `aggregate()` does group-by/sum via pyarrow compute (columnar, no Python row loop).
Additive: the existing `_INDEX` and `model_query` are untouched — this is the efficient analytics path.
"""
from __future__ import annotations

from typing import Any

from . import classification


def _disc(e: dict) -> str:
    return classification.discipline_name(
        classification.discipline_of_ifc_class(e.get("ifc_class") or "")) or "General"


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


def _eav_rows(idx: dict[str, dict]) -> list[dict[str, Any]]:
    """Flatten psets + qtos to (guid, group, set, prop, value_str, value_num) rows."""
    rows: list[dict[str, Any]] = []
    for gid, e in idx.items():
        for group, key in (("pset", "psets"), ("qto", "qtos")):
            sets = e.get(key)
            if not isinstance(sets, dict):
                continue
            for set_name, props in sets.items():
                if not isinstance(props, dict):
                    continue
                for prop, val in props.items():
                    rows.append({"guid": gid, "group": group, "set": set_name, "prop": prop,
                                 "value_str": "" if val is None else str(val), "value_num": _num(val)})
    return rows


def build(idx: dict[str, dict] | None) -> dict[str, Any]:
    """Interned columnar form: string table, number table, element rows, EAV parameter rows."""
    idx = idx or {}
    strings: dict[str, int] = {}
    numbers: dict[float, int] = {}

    def si(s: str | None) -> int:
        s = "" if s is None else str(s)
        return strings.setdefault(s, len(strings))

    def ni(n: float | None) -> int | None:
        return None if n is None else numbers.setdefault(n, len(numbers))

    elements = []
    for gid, e in idx.items():
        elements.append({"guid": gid, "ifc_class": si(e.get("ifc_class")),
                         "type_name": si(e.get("type_name")), "name": si(e.get("name")),
                         "storey": si(e.get("storey")), "discipline": si(_disc(e))})
    eav = _eav_rows(idx)
    params = [{"guid": r["guid"], "group": r["group"], "set": si(r["set"]), "prop": si(r["prop"]),
               "value_str": si(r["value_str"]), "value_num": ni(r["value_num"])} for r in eav]
    return {
        "strings": list(strings), "numbers": list(numbers),
        "elements": elements, "params": params,
        "counts": {"elements": len(elements), "params": len(params),
                   "unique_strings": len(strings), "unique_numbers": len(numbers)},
    }


def interning_stats(idx: dict[str, dict] | None) -> dict[str, Any]:
    """Quantify the columnar/interning win: string occurrences vs unique, and an estimate of the bytes
    a naive per-element JSON holds for those strings vs the interned table + int references."""
    idx = idx or {}
    if not idx:
        return {"model_loaded": False, "note": "No model loaded."}
    col = build(idx)
    # every element contributes 5 string slots; every param 3 string slots -> total string references
    refs = len(col["elements"]) * 5 + len(col["params"]) * 3
    unique = col["counts"]["unique_strings"]
    # naive bytes: each reference stores the full string; interned: unique strings once + 4-byte int refs
    avg_len = (sum(len(s) for s in col["strings"]) / unique) if unique else 0
    naive_bytes = int(refs * avg_len)
    interned_bytes = int(sum(len(s) for s in col["strings"]) + refs * 4)
    saved = naive_bytes - interned_bytes
    return {
        "model_loaded": True,
        "elements": col["counts"]["elements"], "param_rows": col["counts"]["params"],
        "string_references": refs, "unique_strings": unique,
        "dedup_ratio": round(refs / unique, 1) if unique else None,
        "est_naive_string_bytes": naive_bytes, "est_interned_bytes": interned_bytes,
        "est_bytes_saved": saved,
        "est_reduction_pct": round(100 * saved / naive_bytes, 1) if naive_bytes else None,
        "note": "Interning stores each distinct string once and references it by index — psets repeat "
                "the same keys/values across thousands of elements, so the columnar form is far smaller "
                "in RAM and streams to Parquet for DuckDB/pandas analytics.",
    }


def _pa():
    try:
        import pyarrow as pa
        return pa
    except ImportError as exc:  # optional dep
        raise RuntimeError("columnar analytics need the 'pyarrow' package (pip install pyarrow)") from exc


def elements_table(idx: dict[str, dict] | None):
    """A pyarrow Table of denormalised elements (strings materialised, ready for analytics)."""
    pa = _pa()
    idx = idx or {}
    cols = {"guid": [], "ifc_class": [], "type_name": [], "name": [], "storey": [], "discipline": []}
    for gid, e in idx.items():
        cols["guid"].append(gid)
        cols["ifc_class"].append(e.get("ifc_class") or "")
        cols["type_name"].append(e.get("type_name") or "")
        cols["name"].append(e.get("name") or "")
        cols["storey"].append(e.get("storey") or "")
        cols["discipline"].append(_disc(e))
    return pa.table(cols)


def params_table(idx: dict[str, dict] | None):
    """A pyarrow Table of the EAV parameter rows (guid, group, set, prop, value_str, value_num)."""
    pa = _pa()
    rows = _eav_rows(idx or {})
    cols = {k: [r[k] for r in rows] for k in ("guid", "group", "set", "prop", "value_str", "value_num")}
    return pa.table(cols)


def params_parquet(idx: dict[str, dict] | None) -> bytes:
    """The EAV parameter table as a Snappy Parquet buffer — the analytics-friendly property store."""
    import io

    import pyarrow.parquet as pq
    buf = io.BytesIO()
    pq.write_table(params_table(idx), buf, compression="snappy")
    return buf.getvalue()


def aggregate(idx: dict[str, dict] | None, group_by: str = "ifc_class") -> dict[str, Any]:
    """Columnar count group-by over the element table via pyarrow compute (no Python row loop)."""
    pa = _pa()
    t = elements_table(idx)
    if t.num_rows == 0:
        return {"group_by": group_by, "rows": [], "matched": 0}
    if group_by not in t.column_names:
        raise ValueError(f"unknown group_by '{group_by}' (have {t.column_names})")
    grouped = t.group_by(group_by).aggregate([("guid", "count")])
    keys = grouped.column(group_by).to_pylist()
    counts = grouped.column("guid_count").to_pylist()
    rows = sorted(({"group": k or "(none)", "value": c} for k, c in zip(keys, counts, strict=False)),
                  key=lambda r: r["value"], reverse=True)
    _ = pa
    return {"group_by": group_by, "matched": t.num_rows, "groups": len(rows), "rows": rows}
