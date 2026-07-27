# Third-party attributions

Massing is built on open-source work. This file records third-party code or formats we have
re-implemented or adapted, beyond the dependencies pinned in `requirements.txt` / `package.json`.

## Lucide icons — vendored (ISC License)

The interface icon set is **[Lucide](https://lucide.dev)**. The icons this app uses are copied
verbatim into `apps/web/src/ui/icons.ts` as SVG path data — **vendored, not depended on**: there is
no npm package and no CDN, which is what the offline requirement needs, and none of the ~1,500 icons
we do not use reaches the bundle. Path data is copied from upstream, never redrawn, because an icon
redrawn from memory is a different icon wearing the same name.

ISC requires that the copyright notice and the permission notice appear in all copies. They follow in
full:

```
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

Lucide is a maintained fork of Feather (MIT). ISC is a permissive licence, functionally equivalent to
MIT, and compatible with this project's MIT/BSD/Apache-only dependency rule. *(GitHub's licence
detector reports `NOASSERTION` for the Lucide repository; the `LICENSE` file itself is ISC, which is
why it was read rather than trusted to the summary.)*

## ISO 21597 (ICDD) container format — implemented from the published standard

The project package (`.mmproj` today, an **ISO 21597-1** *Information Container for linked Document
Delivery* once R28-ICDD lands) is implemented from the **published specification**, not from any
vendor's code: the container layout (`/Payload documents/`, `/Payload triples/`,
`/Ontology resources/`, `index.rdf`) and the Part 2 link types are defined by
[ISO 21597-1:2020](https://www.iso.org/standard/74389.html) and
[ISO 21597-2:2020](https://www.iso.org/standard/74390.html).

A published standard may be implemented freely; the ISO *documents* are copyrighted and are **not**
redistributed here — no specification text is copied into this repository, and no clause is
reproduced beyond the structural names any implementation must use.

**`rdflib` (BSD-3-Clause)** is the RDF library approved for the linkset half of that work. It is
permissive and compatible with this project's MIT/BSD/Apache-only dependency rule. It is pinned in
`services/api/requirements.in` **in the change that first uses it** — a dependency carried ahead of
its code is supply-chain surface with no offsetting benefit, and the lockfile gate requires
`requirements.lock` to be regenerated in the same commit.

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

## Structural steel section dimensions — AISC (facts, re-keyed)

The W-shape dimensions in `services/data/src/aec_data/steel.py` (overall depth, flange width, flange &
web thickness) are **facts** re-keyed from the publicly published **AISC Shapes Database** (imperial).
Dimensions of standard sections are facts, not copyrightable; we do **not** redistribute AISC's database
file. They feed IFC's native parametric `IfcIShapeProfileDef`, so no geometry is imported. US reinforcing
bar diameters (#3–#11) are likewise standard nominal facts.

## Standards & formats

IFC / STEP (buildingSMART), ISO 19650, glTF 2.0 (Khronos), Apache Parquet, BCF (buildingSMART),
NCS (National CAD Standard), CSI MasterFormat/UniFormat, IECC — all open industry standards.
IDS specifications (e.g. national BIM standards) are read from user-supplied `.ids` files via
`ifctester`; none are bundled from third-party repositories.
