"""COST-DB — a local, **vintage-versioned** cost database (offline first slice).

Every priced row hangs off a `CostDataset` vintage, so a project can **pin** the exact vintage its estimate
was built on and stay reproducible after newer data lands. This module ships the **offline public importer**
(builds a `public_local` vintage from the app's shipped benchmark rates — no network, no subscription), the
vintage resolver, `is_latest` management, project pinning, and **project localization + escalation**
(`rates_for_project`): a vintage's national-average rates multiplied by the project region's cost index and
escalated from the vintage year to the construction midpoint, off the shipped market table — still offline.
The `cloud_api` importer (manifest + signed bundle download from massing.cloud) and real public-source ingest
(BLS/FRED/DoD/Census) are later build-order steps — see docs/cost-db-import-plan.md.
"""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import classification as cls
from .estimate import DEFAULT_RATES
from .models import CostDataset, CostItem, Project

# QTO billing unit -> unit of measure stored on the cost item.
_UOM = {"area": "m2", "volume": "m3", "length": "m", "count": "ea"}
SOURCE_SET = "public"
ORIGIN_LOCAL = "public_local"
SOURCE_CUSTOM = "custom"
ORIGIN_CUSTOM = "custom"


def parse_cost_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize a firm's cost book into `[{ifc_class, total_cost, description?, uom?, masterformat_code?}]`.

    Accepts either a flat `{ifc_class: rate}` map (the quickest form) or a list of row dicts (each with
    `ifc_class` + a rate under `total_cost`/`rate`/`cost`, and optional `description`/`uom`/
    `masterformat_code`/`uniformat_code`). Rows without an `ifc_class` or a finite positive rate are
    dropped. Pure — no DB — so it's unit-tested and reused by the CSV/JSON/endpoint paths."""
    def _rate(d: dict) -> float | None:
        for k in ("total_cost", "rate", "cost", "unit_cost"):
            v = d.get(k)
            if v is not None:
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    return None
                return f if f > 0 else None
        return None

    raw: list[dict[str, Any]]
    if isinstance(payload, dict):
        raw = [{"ifc_class": k, "total_cost": v} for k, v in payload.items()]
    elif isinstance(payload, list):
        raw = [d for d in payload if isinstance(d, dict)]
    else:
        return []
    out: list[dict[str, Any]] = []
    for d in raw:
        ic = (d.get("ifc_class") or "").strip()
        rate = _rate(d)
        if not ic or rate is None:
            continue
        row: dict[str, Any] = {"ifc_class": ic, "total_cost": rate}
        for k in ("description", "uom", "masterformat_code", "uniformat_code"):
            if d.get(k):
                row[k] = d[k]
        out.append(row)
    return out


def import_custom_vintage(db: Session, rows: list[dict[str, Any]], vintage: int,
                          quarter: int | None = None, name: str | None = None) -> CostDataset:
    """Install a firm's own cost book as a `custom`-origin vintage for `vintage` year. Re-importing the
    same (year, quarter) **replaces** that custom vintage's items in place (a firm re-uploading a corrected
    book), so there's never a duplicate. Sets it latest. `rows` are as `parse_cost_rows` returns.
    Missing MasterFormat codes are filled from the classification spine off the IFC class."""
    if not rows:
        raise ValueError("no priced rows to import (need at least one {ifc_class, rate})")
    ds = db.scalar(select(CostDataset).where(
        CostDataset.vintage_year == vintage, CostDataset.quarter == quarter,
        CostDataset.source_set == SOURCE_CUSTOM, CostDataset.origin == ORIGIN_CUSTOM))
    if ds is None:
        ds = CostDataset(vintage_year=vintage, quarter=quarter, source_set=SOURCE_CUSTOM,
                         tier="enterprise", origin=ORIGIN_CUSTOM)
        db.add(ds)
        db.flush()
    else:                                           # replace the items of the existing custom vintage
        for it in db.scalars(select(CostItem).where(CostItem.dataset_id == ds.id)):
            db.delete(it)
        db.flush()
    ds.notes = (name or f"custom cost book, vintage {vintage}") + f" ({len(rows)} items)"
    items = []
    for r in rows:
        code = r.get("masterformat_code")
        title = r.get("description")
        if not code or not title:
            c, t = cls.classify(r["ifc_class"], "masterformat")
            code = code or c
            title = title or t
        items.append(CostItem(dataset_id=ds.id, masterformat_code=code, description=title,
                              uniformat_code=r.get("uniformat_code"), uom=r.get("uom") or "ea",
                              ifc_class=r["ifc_class"], total_cost=float(r["total_cost"])))
    db.add_all(items)
    _set_latest(db, ds)
    db.commit()
    db.refresh(ds)
    return ds


def _build_public_items(dataset_id: str) -> list[CostItem]:
    """The offline public vintage: one priced `CostItem` per shipped benchmark rate, MasterFormat-coded via
    the classification spine and linked to its IFC class so the model takeoff prices straight through."""
    items: list[CostItem] = []
    for ifc_class, (unit, rate) in DEFAULT_RATES.items():
        code, title = cls.classify(ifc_class, "masterformat")
        items.append(CostItem(dataset_id=dataset_id, masterformat_code=code, description=title,
                              uom=_UOM.get(unit, unit), ifc_class=ifc_class, total_cost=float(rate)))
    return items


def list_available_public() -> list[dict[str, Any]]:
    """What the offline public importer can build. A single evergreen `public` line — any requested year
    builds the same shipped-benchmark baseline (real per-year public-source data + PPI escalation-forward are
    later build steps). Mirrors `DatasetImporter.list_available()` for the public origin."""
    return [{"source_set": SOURCE_SET, "origin": ORIGIN_LOCAL, "tier": "free",
             "note": "shipped benchmark baseline; any vintage year"}]


def import_public_vintage(db: Session, vintage: int, quarter: int | None = None) -> CostDataset:
    """Build (or return, idempotently) a public-local cost vintage for `vintage` year. Sets it as the latest
    installed vintage. Offline — no network, no subscription."""
    existing = db.scalar(select(CostDataset).where(
        CostDataset.vintage_year == vintage, CostDataset.quarter == quarter,
        CostDataset.source_set == SOURCE_SET, CostDataset.origin == ORIGIN_LOCAL))
    if existing is not None:
        _set_latest(db, existing)
        return existing
    ds = CostDataset(vintage_year=vintage, quarter=quarter, source_set=SOURCE_SET, tier="free",
                     origin=ORIGIN_LOCAL,
                     notes=f"public benchmark baseline, vintage {vintage}"
                           + (f" Q{quarter}" if quarter else ""))
    db.add(ds)
    db.flush()                                  # assign ds.id before the children reference it
    db.add_all(_build_public_items(ds.id))
    _set_latest(db, ds)
    db.commit()
    db.refresh(ds)
    return ds


def _set_latest(db: Session, ds: CostDataset) -> None:
    """Flag `ds` as the single latest installed vintage (clears the flag on every other dataset)."""
    for other in db.scalars(select(CostDataset).where(CostDataset.is_latest.is_(True))):
        if other.id != ds.id:
            other.is_latest = False
    ds.is_latest = True
    db.flush()


def latest(db: Session) -> CostDataset | None:
    return db.scalar(select(CostDataset).where(CostDataset.is_latest.is_(True)))


def resolve(db: Session, vintage: int | Literal["latest"] = "latest", quarter: int | None = None,
            policy: Literal["strict", "nearest"] = "nearest") -> CostDataset | None:
    """Resolve a vintage request to an installed dataset. `latest` → the flagged latest; a specific year →
    that (year, quarter), else the fallback policy: `strict` returns None; `nearest` returns the newest
    installed vintage ≤ the requested year (or, when none is older, the OLDEST installed vintage — the
    nearest one above the request)."""
    installed = list(db.scalars(select(CostDataset).order_by(
        CostDataset.vintage_year.desc(), CostDataset.quarter.desc())))
    if not installed:
        return None
    if vintage == "latest":
        return latest(db) or installed[0]
    exact = next((d for d in installed if d.vintage_year == vintage
                  and (quarter is None or d.quarter == quarter)), None)
    if exact is not None:
        return exact
    if policy == "strict":
        return None
    older = [d for d in installed if d.vintage_year <= int(vintage)]
    return older[0] if older else installed[-1]


def pin_project(db: Session, project: Project, dataset_id: str | None) -> None:
    """Pin a project's estimate to a cost vintage (None = follow the latest installed vintage)."""
    project.cost_dataset_id = dataset_id
    db.commit()


def dataset_for_project(db: Session, project: Project) -> CostDataset | None:
    """The vintage a project's estimate resolves through: its pinned dataset, else the latest installed."""
    if project.cost_dataset_id:
        ds = db.get(CostDataset, project.cost_dataset_id)
        if ds is not None:
            return ds
    return latest(db)


def dataset_dict(ds: CostDataset, item_count: int | None = None) -> dict[str, Any]:
    return {"id": ds.id, "vintage_year": ds.vintage_year, "quarter": ds.quarter,
            "source_set": ds.source_set, "tier": ds.tier, "origin": ds.origin,
            "is_latest": bool(ds.is_latest), "imported_at": ds.imported_at.isoformat() if ds.imported_at else None,
            "notes": ds.notes, **({"item_count": item_count} if item_count is not None else {})}


def list_datasets(db: Session) -> list[dict[str, Any]]:
    out = []
    for ds in db.scalars(select(CostDataset).order_by(
            CostDataset.vintage_year.desc(), CostDataset.quarter.desc())):
        n = db.scalar(select(CostItem.id).where(CostItem.dataset_id == ds.id).limit(1))
        cnt = len(list(db.scalars(select(CostItem.id).where(CostItem.dataset_id == ds.id)))) if n else 0
        out.append(dataset_dict(ds, item_count=cnt))
    return out


def rates_for(db: Session, dataset_id: str) -> dict[str, float]:
    """The `{ifc_class: total_cost}` rate map for a vintage — a drop-in override for the estimate engine so
    a project's takeoff prices through its pinned vintage."""
    return {it.ifc_class: it.total_cost
            for it in db.scalars(select(CostItem).where(CostItem.dataset_id == dataset_id))
            if it.ifc_class}


def rates_for_project(db: Session, project: Project, *, region: str | None = None,
                      start_year: int | None = None, duration_months: int | None = None,
                      to_year: int | None = None, rate_pct: float | None = None
                      ) -> tuple[dict[str, float] | None, dict[str, Any] | None]:
    """The project's per-class rate map **localized and escalated**, plus the adjustment metadata.

    A vintage stores national-average rates for its year. Two offline reference adjustments make them
    project-real: the region's **location cost index** (a metro/region multiplier) and **escalation** from
    the vintage year to the construction midpoint (or `to_year`). Both come from the shipped market table —
    no network. Returns `(None, None)` when no vintage is installed, so the caller falls back to the shipped
    benchmark rates exactly as before. `region`/timeline are resolved by the caller (from the project's
    market assumption); passing none yields the neutral global-average index (1.00) and no escalation."""
    from . import market_intelligence as mi
    ds = dataset_for_project(db, project)
    if ds is None:
        return None, None
    base = rates_for(db, ds.id)
    loc = float(mi.region_data(region).get("location_index") or 1.0)
    ef = mi.escalation_factor(region, from_year=ds.vintage_year, start_year=start_year,
                              duration_months=duration_months, to_year=to_year, rate_pct=rate_pct)
    combined = loc * ef["factor"]
    adjusted = {c: round(rate * combined, 2) for c, rate in base.items()}
    meta = {"dataset_id": ds.id, "vintage_year": ds.vintage_year,
            "location_index": round(loc, 4), "escalation": {**ef, "factor": round(ef["factor"], 4)},
            "combined_factor": round(combined, 4),
            "note": "National-average vintage rates localized by the region cost index and escalated from "
                    "the vintage year to the construction midpoint (shipped market table; offline)."}
    return adjusted, meta
