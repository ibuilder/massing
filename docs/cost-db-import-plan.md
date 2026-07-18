# Cost Database & Import Plan — `massing.build`

**Product:** `massing.build` (open-source, IFC-native AEC app). **Job:** maintain a local, **vintage-versioned**
(by year) cost database populated from either **(a)** free public sources directly, or **(b)** the
`massing.cloud` API when the user has a subscription — and let any project **pin** to a specific vintage,
importing the latest or a specific historical year.

Companion doc: `massing_cloud_plugin_plan.md` (the server side) · location engine:
`massing_location_cost_import_plan.md`.

> **Shipped (offline first slice, v0.3.436):** the vintage backbone (`cost_db.py`), the offline public
> importer, resolve/pin — **plus** project **localization + escalation** via `cost_db.rates_for_project`:
> a vintage's national-average rates × the project region's cost index, escalated from the vintage year to
> the construction midpoint, using the shipped market table (`market_intelligence.py`) — no network. The
> per-vintage `location_factor` / `escalation_index` DB tables below (BLS/FRED/RSMeans-grade, per-county)
> are the fuller successor and remain a later build-order step.

## 1. Requirements

- **Two ingest paths, one interface** — local public-domain build, or cloud API pull (subscription).
- **Year differentiation** — store multiple vintages side by side; import `latest` or a specific year
  (`2024`); fall back gracefully if a requested year isn't available.
- **Reproducibility** — every project references the exact vintage its estimate was built on.
- **Offline-first** — the app always works on public data even with no subscription/network.
- **Integrity** — verify checksum (and optional signature) of any cloud bundle before import.

## 2. Local database schema (SQLite default / Postgres option)

Portable types (`NUMERIC` on Postgres, `REAL`/`TEXT` on SQLite). `cost_dataset` is the versioning backbone —
every other cost table hangs off a `dataset_id`.

- **`cost_dataset`** — one row per installed vintage: `vintage_year`, `quarter` (NULL=annual), `source_set`
  (`public | public+1build | enterprise`), `tier`, `origin` (`public_local | cloud_api`), `release_uuid`
  (NULL for local), `checksum_sha256`, `is_latest`, `imported_at`, `notes`. `UNIQUE(vintage_year, quarter,
  source_set, origin)`.
- **`cost_source`** — provenance per vintage: `provider` (BLS|FRED|DOD|UFC|CENSUS|ONEBUILD|RSMEANS),
  `source_version`, `base_period`, `license_type` (public_domain|proprietary), `retrieved_at`.
- **`cost_item`** — priced line items (MasterFormat/Uniformat): `masterformat_code`, `uniformat_code`,
  `description`, `uom`, `crew_code`, `daily_output`, `labor_hours`. Index `(dataset_id, masterformat_code)`.
- **`cost_value`** — national baseline: `material_cost`, `labor_cost`, `equipment_cost`, `total_cost`,
  `labor_type` (BASE|BURDENED), `currency`.
- **`location`** — shared registry (stable keys): `location_key` (FIPS county | 3-digit ZIP | city slug),
  `name`, `state`, `county_fips`, `cbsa`, `country`, `lat`, `lng`.
- **`location_factor`** — per vintage: `location_id`, `masterformat_div` (NULL=composite), material/labor/
  equipment/total factors, `base_index` (default 100), `effective_date`. Index `(dataset_id, location_id,
  masterformat_div)`.
- **`escalation_index`** — PPI/FRED per vintage: `series_code`, `series_name`, `period` (YYYY-MM),
  `index_value`, `base_period`. Index `(dataset_id, series_code, period)`.
- **`sync_state`** — cloud connection: `cloud_base_url`, `api_key_ref` (reference to secret store, **never**
  the key), `tier`, `last_checked_at`, `remote_versions_json` (cached available releases).
- **Project pinning** — `ALTER TABLE project ADD COLUMN cost_dataset_id INTEGER REFERENCES cost_dataset(id)`.

**Why per-vintage (via `dataset_id`) not overwrite:** a 2024 estimate must stay reproducible after 2026 data
lands. Multiple vintages coexist; a project pins one; re-localize or escalate on demand.

## 3. Import architecture

Two importers behind one interface. Public → build-from-sources → upsert. Cloud → vintage-resolve →
checksum/signature verify → upsert → set `is_latest`.

```python
class DatasetImporter(Protocol):
    origin: str  # 'public_local' | 'cloud_api'
    def list_available(self) -> list[VintageRef]: ...
    def import_vintage(self, vintage: int | Literal["latest"],
                       quarter: int | None = None) -> DatasetId: ...
```

## 4. Year-differentiated import logic

`import_vintage("latest" | <year>, quarter=None)`:
- `latest` → `max(available, key=(year, quarter))`.
- specific → find `(year, quarter)`; if absent apply **fallback policy** (`strict` → raise; `nearest` →
  newest available year ≤ requested).
- **idempotent** — return the existing `dataset_id` if already installed.
- cloud origin → GET manifest, download bundle, **`_verify_checksum` (+ optional Ed25519)**, unpack; public
  origin → `_build_from_public_sources(year)` (BLS/DoD/UFC/Census).
- upsert dataset + children, then `_refresh_is_latest()`.

**Runtime source selection:** `get_importer()` returns `CloudDatasetImporter` when the subscription is active
(`sync_state.tier in ('pro','enterprise')` & valid key) else `PublicDataImporter` (always available,
offline-capable). Requesting `--source cloud` without a valid subscription **warns and falls back** to the
public importer's latest local build rather than failing.

## 5. CLI / app surface

```
massing cost list                                   # installed vintages
massing cost remote --list                          # what the cloud offers for your tier
massing cost import --vintage latest                # cloud if subscribed, else public
massing cost import --source cloud --vintage 2024   # a specific historical year
massing cost import --source public --vintage 2025  # public-only build (no subscription)
massing project set-cost-vintage <project_id> --vintage 2024
```

## 6. Sync & delta updates

- On launch / scheduled: `CloudDatasetImporter.list_available()` hits `/releases`, caches to
  `sync_state.remote_versions_json`.
- If a newer remote `is_latest` exists and auto-update is on, pull (full bundle, or `?since=` delta on
  `/cost-items` to skip unchanged rows).
- Public importer keeps `escalation_index` fresh monthly from BLS so older vintages can be **escalated
  forward** (a 2024 dataset expressed in 2026 dollars) via the stored PPI series.

## 7. Integrity & security

- All cloud traffic over HTTPS; API key as `Authorization: Bearer …`, stored in the **OS secret store / env**
  — never in the DB or repo (only a reference in `sync_state.api_key_ref`).
- Verify `sha256` (+ optional Ed25519) of every bundle before upsert; reject on mismatch.
- Imports run in a **transaction**; on failure the partial vintage rolls back so `cost_dataset` never has
  orphaned children.

## 8. How vintages feed the modules

- A project pins `cost_dataset_id`; the location-factor engine reads factors + baselines from **that vintage
  only**.
- 5D cost, estimating, GC-portal budget, FCA, and Last Planner all resolve costs through the pinned vintage →
  reproducible, defensible estimates.
- Switching a project's vintage triggers a re-localization pass (national baseline × location factor),
  optionally escalated to a target date.

## 9. Build order

1. Local schema (`cost_dataset` + children) + migrations.
2. `PublicDataImporter` (free spine) → first working vintage, offline.
3. Vintage resolver + `is_latest` management + project pinning.
4. `CloudDatasetImporter`: `list_available`, manifest + bundle download, checksum verify, upsert.
5. Subscription detection + graceful public fallback.
6. Delta sync (`?since=`) + auto-update on launch.
7. Ed25519 signature verification.
8. Escalation-forward on older vintages.

## 10. Licensing

`massing.build` (open source) ships **the public importer and adapter code only**. Proprietary data
(1build/RSMeans) arrives **exclusively** through the subscriber's authenticated `massing.cloud` pull and is
stored locally under that user's entitlement — **never** committed to or distributed with the open-source repo.
