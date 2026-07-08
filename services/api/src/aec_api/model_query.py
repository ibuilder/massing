"""Model analytics query layer (D1): filter + group-by + aggregate over the property index.

The ifc-lite-style "ask the model a question" analytics, on our server-Fragments architecture: group
elements by any attribute (ifc_class, discipline, storey, type_name, or a nested ``Pset::Property``) and
count them or sum a quantity (from the IFC quantity sets). Powers saved views and ad-hoc analytics
without shipping the whole model to the browser.
"""
from __future__ import annotations

from typing import Any

from . import classification

_SAVED_VIEWS = [
    {"id": "count_by_discipline", "label": "Element count by discipline", "group_by": "discipline", "agg": "count"},
    {"id": "count_by_class", "label": "Element count by IFC class", "group_by": "ifc_class", "agg": "count"},
    {"id": "count_by_storey", "label": "Element count by storey", "group_by": "storey", "agg": "count"},
    {"id": "count_by_type", "label": "Element count by type", "group_by": "type_name", "agg": "count"},
]


def _val(e: dict, field: str) -> Any:
    if field == "discipline":
        return classification.discipline_name(classification.discipline_of_ifc_class(e.get("ifc_class") or "")) \
            or "General"
    if "::" in field:
        pset, prop = field.split("::", 1)
        psets = e.get("psets")
        grp = psets.get(pset) if isinstance(psets, dict) else None
        return grp.get(prop) if isinstance(grp, dict) else None
    return e.get(field)


def _qto_sum(e: dict, quantity: str) -> float:
    qtos = e.get("qtos")
    if not isinstance(qtos, dict):
        return 0.0
    for grp in qtos.values():
        if isinstance(grp, dict) and quantity in grp:
            try:
                return float(grp[quantity])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def saved_views() -> list[dict[str, str]]:
    return [{"id": v["id"], "label": v["label"]} for v in _SAVED_VIEWS]


def query(idx: dict[str, dict] | None, group_by: str = "ifc_class", agg: str = "count",
          quantity: str | None = None, filters: dict[str, str] | None = None) -> dict[str, Any]:
    """Group the (optionally filtered) elements by `group_by`; aggregate count or sum:<quantity>."""
    if not idx:
        return {"model_scored": False, "group_by": group_by, "agg": agg, "rows": [], "matched": 0,
                "note": "No model loaded — load a model to query it."}
    elements = list(idx.values())
    filters = filters or {}
    for k, v in filters.items():
        elements = [e for e in elements if str(_val(e, k)) == str(v)]
    groups: dict[str, list[dict]] = {}
    for e in elements:
        groups.setdefault(str(_val(e, group_by) or "(none)"), []).append(e)
    rows = []
    for k, es in sorted(groups.items(), key=lambda kv: kv[0]):
        if agg.startswith("sum") and quantity:
            rows.append({"group": k, "value": round(sum(_qto_sum(e, quantity) for e in es), 2),
                         "count": len(es)})
        else:
            rows.append({"group": k, "value": len(es), "count": len(es)})
    rows.sort(key=lambda r: r["value"], reverse=True)
    return {"model_scored": True, "group_by": group_by, "agg": agg, "quantity": quantity,
            "filters": filters, "matched": len(elements), "groups": len(rows), "rows": rows,
            "note": "Grouped + aggregated over the property index. Use saved views or pass "
                    "group_by / agg=sum&quantity=<QtoName> / filters."}


def run_saved(idx: dict[str, dict] | None, view_id: str) -> dict[str, Any]:
    v = next((x for x in _SAVED_VIEWS if x["id"] == view_id), None)
    if not v:
        return {"error": f"unknown saved view '{view_id}'", "available": [x["id"] for x in _SAVED_VIEWS]}
    return {"view": v["id"], "label": v["label"], **query(idx, v["group_by"], v["agg"])}


# --- D2: model data export (columnar-friendly rows -> CSV / JSON-LD; no external dependency) --------
_EXPORT_COLS = ["guid", "ifc_class", "type_name", "name", "storey", "discipline"]


def export_rows(idx: dict[str, dict] | None) -> list[dict[str, Any]]:
    """Flatten the property index to a columnar row set (one row per element)."""
    if not idx:
        return []
    return [{"guid": gid, "ifc_class": e.get("ifc_class", ""), "type_name": e.get("type_name", ""),
             "name": e.get("name", ""), "storey": e.get("storey", ""), "discipline": _val(e, "discipline")}
            for gid, e in idx.items()]


def to_csv(idx: dict[str, dict] | None) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_EXPORT_COLS)
    w.writeheader()
    for row in export_rows(idx):
        w.writerow(row)
    return buf.getvalue()


def to_parquet(idx: dict[str, dict] | None) -> bytes:
    """The element set as an Apache Parquet buffer (columnar analytics — DuckDB / pandas / Polars).

    Parquet needs the optional ``pyarrow`` dependency; when it isn't installed we raise a clear
    RuntimeError (the endpoint maps it to 503) rather than failing cryptically, matching the E57 path.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # optional dep — see requirements.txt
        raise RuntimeError(
            "Parquet export needs the 'pyarrow' package (pip install pyarrow). CSV / JSON-LD export "
            "work without it.") from exc
    import io
    rows = export_rows(idx)
    table = pa.table({col: [r.get(col) for r in rows] for col in _EXPORT_COLS})
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def to_jsonld(idx: dict[str, dict] | None) -> dict[str, Any]:
    """A JSON-LD graph of the model elements (bSDD-style vocab, GlobalId as @id)."""
    ctx = {"@vocab": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/",
           "guid": "@id", "ifcClass": "ifc_class", "typeName": "type_name",
           "storey": "storey", "discipline": "discipline"}
    graph = [{"@id": r["guid"], "@type": r["ifc_class"] or "IfcRoot", "typeName": r["type_name"],
              "name": r["name"], "storey": r["storey"], "discipline": r["discipline"]}
             for r in export_rows(idx)]
    return {"@context": ctx, "@graph": graph, "count": len(graph)}
