"""COST-DB — a local, **vintage-versioned** cost database (offline first slice).

Every priced row hangs off a `CostDataset` vintage, so a project can **pin** the exact vintage its estimate
was built on and stay reproducible after newer data lands. This module ships the **offline public importer**
(builds a `public_local` vintage from the app's shipped benchmark rates — no network, no subscription) plus
the vintage resolver, `is_latest` management, and project pinning. The `cloud_api` importer (manifest +
signed bundle download from massing.cloud), real public-source ingest (BLS/FRED/DoD/Census), location factors,
and PPI escalation-forward are later build-order steps — see docs/cost-db-import-plan.md.
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
    installed vintage ≤ the requested year (or the newest overall if none is older)."""
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
