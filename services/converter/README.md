# Converter service (Phase 1)

Turns incoming IFC (and optionally RVT) into web-ready Fragments tiles + a lightweight
properties index. **Convert once, serve `.frag` forever.**

- `IFC → .frag` (open, main path): Node worker using `@thatopen/fragments` `IfcImporter`
  with local web-ifc WASM. Writes `<model_id>.frag` to object storage.
- `RVT → IFC` (optional, **paid**): Autodesk APS Model Derivative API, behind a feature
  flag + cost warning. No open-source RVT reader exists. Reuses the IFC path after.
- Properties index: per-element GUID, IFC class, name, storey, Psets → queryable store so
  the API/tree never re-parse geometry.

See root guide §4. `src/ifcToFrag.ts` is the entry point (stub to be implemented).
