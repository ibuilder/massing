# Data service (Phase 5)

IfcOpenShell-powered extraction & export. Reads the **source IFC** (not the tiles).
Everything keyed by GUID so it reconciles against model updates.

Endpoints (→ XLSX/CSV):
- `/exports/qto` — quantity takeoff from `IfcElementQuantity` / Psets; geometry-derived
  fallback; cost-code mapping (CSI MasterFormat / UniFormat) → 5D estimate.
- `/exports/schedule` — 4D activity↔element mapping; drives viewer color/visibility by date.
- `/exports/spaces` — `IfcSpace` area/volume/occupancy; net vs gross; program-vs-actual.
- `/exports/cobie` — COBie handover data for owner/FM.
- Generic schedule builder: pick IFC class + Pset fields + grouping → table → export.

See root guide §8.
