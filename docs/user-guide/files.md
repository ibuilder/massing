# Files: what goes in, what comes out

Massing's position is that your data should leave as easily as it arrived. IFC is the source of truth,
and every derived artifact is regenerable.

## `.mass` — a project in one file

A `.mass` file is **one project**: its model, all of its data, and its attachments, in a single file you
can copy, email, archive or commit to version control. It is a **plain ZIP**.

Format id `massing.project`, version 2, media type `application/zip`.

This is why samples ship as `.mass` rather than loose IFC: a sample opens as a *project* — geometry plus
every table — which is the whole difference between this and a viewer. Full specification in
[mass-format.md](../mass-format.md).

There is also `.mmproj` via `GET /projects/{id}/bundle` and `POST /projects/import-bundle` for
project-bundle transfer.

## Input formats

| What | Notes |
| --- | --- |
| **IFC** (2x3, 4, 4.3) | The source of truth. Pre-converted to Fragments server-side. |
| **BCF** (`.bcfzip`) | Issues round-trip with any BCF-compatible tool. |
| **DXF** | 2D → BIM: floor plan becomes IFC walls + spaces. |
| **PDF** | Calibrated takeoff and markup. |
| **Point clouds** | PCD, XYZ, LAS, LAZ — as-built comparison and reference. |
| **Meshes** | OBJ, STL, PLY, glTF — reference overlay only. |
| **GIS** | GeoJSON vectors, GeoTIFF DEM terrain — georeferenced site context. |
| **Excel / CSV** | Generic import into any module. |
| **RVT** | **Optional and paid**, via Autodesk APS, behind a feature flag. Never assume RVT can be read offline. |

## Output formats

| What | Where from |
| --- | --- |
| IFC | `/publish` — the edited model, GUIDs intact |
| SVG · PDF · DXF | Drawings, sheets, schedules |
| XLSX | QTO, COBie, spaces, schedule, and every Report Center report |
| CSV | Any module register, via `/export.csv` |
| BCF | `/bcf/export` |
| PDF | Records, contracts, pay apps, WH-347, reports |
| RESO | `/listings/{lid}/reso` — MLS data-dictionary export |
| COBie | With Contact, Zone and System — the handover chain into a CMMS |

## Geometry vs data

These stay separate on purpose:

- **Geometry** streams as `.frag` tiles, pre-converted on the server.
- **Data** comes from the API.

The browser never parses full IFC at runtime. This is what lets large models open on a laptop, and it is
also why the viewer works offline — the WASM is local and tiles are self-hosted.

## Offline

The viewer runs **fully offline**: local WASM, self-hosted tiles, no third-party CDN. The desktop app
carries its own storage. Online licence validation against massing.cloud exists but is **optional and
off by default**; the tier recorded locally is authoritative until you turn it on.

## Deleting a project

`DELETE /projects/{id}` removes the rows, the geometry and the attachments. It is not a soft delete.

## Related

- [mass-format.md](../mass-format.md) — the container specification.
- [authoring.md](authoring.md) — bringing geometry in and editing it.
- [drawings.md](drawings.md) — what the document set produces.
