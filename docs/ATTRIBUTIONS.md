# Third-party attributions

Massing is built on open-source work. This file records third-party code or formats we have
re-implemented or adapted, beyond the dependencies pinned in `requirements.txt` / `package.json`.

## Ara3D SDK — format inspiration (MIT)

The columnar BIM data layer and the BFAST/G3D/VIM reader draw on the **[Ara3D SDK](https://github.com/ara3d/ara3d-sdk)**
(© Ara 3D Inc., MIT License):

- `services/api/src/aec_api/bim_columns.py` — a string/number-interned **columnar** representation of the
  property index, persisted as Parquet for analytics. Inspired by Ara3D's `BimOpenSchema` (columnar,
  interned, Parquet/DuckDB-friendly). Our implementation is independent Python; no Ara3D code was copied.
- `services/data/src/aec_data/bfast.py` — a pure-Python reader/writer for the **BFAST** container and a
  summariser for **G3D** geometry and **VIM** files. Re-implemented from the public, documented BFAST
  layout; no Ara3D source copied.

The MIT license permits this use with attribution, which this file provides.

## Standards & formats

IFC / STEP (buildingSMART), ISO 19650, glTF 2.0 (Khronos), Apache Parquet, BCF (buildingSMART),
NCS (National CAD Standard), CSI MasterFormat/UniFormat, IECC — all open industry standards.
IDS specifications (e.g. national BIM standards) are read from user-supplied `.ids` files via
`ifctester`; none are bundled from third-party repositories.
