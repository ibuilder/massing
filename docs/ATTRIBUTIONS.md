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

## Market-escalation seed defaults — public headline figures

The default regional escalation rates, average labour US$/hr, location indices and the warm/cold sector
signal in `services/api/src/aec_api/market_intelligence.py` are seeded from the **public headline
figures** in **Turner & Townsend's *Global Construction Market Intelligence 2026*** (e.g. ~4.5% global
cost inflation for 2026; regional average labour rates; the data-centre / advanced-manufacturing-led
warm market vs the cold residential/commercial market). These are **illustrative, editable defaults**
attributed to their public summary — **not** the proprietary dataset, which is not embedded or
redistributed. A deployment overrides them with its own current rates (or a per-project
`market_assumption` record).

## Standards & formats

IFC / STEP (buildingSMART), ISO 19650, glTF 2.0 (Khronos), Apache Parquet, BCF (buildingSMART),
NCS (National CAD Standard), CSI MasterFormat/UniFormat, IECC — all open industry standards.
IDS specifications (e.g. national BIM standards) are read from user-supplied `.ids` files via
`ifctester`; none are bundled from third-party repositories.
