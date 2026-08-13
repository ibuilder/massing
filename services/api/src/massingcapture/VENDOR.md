# Vendored: massingcapture `classify/` + `probe/`

`classify/` and `probe/` from **MassingCloud/massingcapture**, copied verbatim.

| | |
|---|---|
| Upstream | https://github.com/MassingCloud/massingcapture |
| Commit | `1a31e1be69320734e5b2cc001fea6f2acbbea78a` |
| Synced | 2026-08-11 |
| Licence | **MIT** — read from the repo's `LICENSE` file |
| Scope | **PARTIAL** — `classify/` + `probe/` only. See below. |
| Local deviations | **NONE** |

## The licence needed reading, not querying

`gh repo list --json licenseInfo` reports **`NO-LICENSE` for every repo in the MassingCloud org**,
including this one and including massingbill, whose `LICENSE` file plainly reads `MIT License`.
GitHub's detection is not populated there. The standing rule — read the LICENSE file, not the API
field, not the README badge, not the repo description — is what produced the MIT above.

## Why this one is PARTIAL, when massingplan is not

`massingplan/core/` is a subtree that exists to be vendored, so we take **all** of it: a partial copy
is how two implementations start, and upstream's drift check watches both directions.

massingcapture is a whole **application**. It ships `server/api.py` (31 KB of FastAPI), a `demo.py`,
and `bridge/massingviser.py` — a bridge to a platform this project explicitly did not adopt. Copying
it whole would import a second web server and a dependency on a rejected platform.

So the scope is deliberately two packages, and the drift story is written here **before** the copy
rather than discovered later: any upstream `--check` will report the absent packages as missing, and
that is expected rather than drift.

## What is deliberately NOT taken

`adapters/` — and not because of size. Every useful adapter sits behind a real extra:

| module | requires | do we have it? |
|---|---|---|
| `adapters/crs.py` | `pyproj>=3.6`, imported unconditionally | **no** |
| `adapters/drone.py` | `pymavlink>=2.4` | **no** |
| `adapters/plan.py` | `pypdfium2>=4.30`, `pillow` | **no** |
| `adapters/pointcloud.py` | `open3d>=0.18` | **no** |
| `adapters/media.py` | `opencv-python` | partial |

Upstream declares `dependencies = []`, which is **true of the manifest and misleading about the
modules**. Taking an adapter is a new-dependency decision needing explicit sign-off, not a vendoring
decision. Same caveat massingplan's VENDOR.md makes in reverse: read the directory, not the project
manifest.

## Why both packages, not just `probe/`

The original plan was `probe/` alone. That would have shipped **half a capability**.

`probe(path, asset_format)` takes the format as an argument — it summarises a format you have
*already named*. The content-first property, the thing actually worth having, lives entirely in
`classify/`. Found by reading the entry point rather than the README, which describes the package as
"content-first format detection" without saying which half does it.

`classify/sniff.py` imports `..probe.ply` and `..probe.structured`, so the two are a unit anyway.

## Verified before shipping

- **Standard library only, per module**, across all 14 files — checked by reading imports, not by
  trusting `dependencies = []`. Held by `test_massingcapture_vendor.py`.
- **No import escapes the vendored subset**: nothing reaches `..adapters`, `..ingest`, `..server`.
- **Content-first detection actually works**: an IFC file renamed to `.jpg` classifies as `ifc`.
  That case is in the test, because "reads the bytes not the extension" is precisely the claim that
  an extension-keyed implementation would also appear to satisfy on correctly-named files.

## How the content digest is computed

Same recipe as `massingplan/VENDOR.md`, and written down for the same reason — the digest recorded
there before 2026-08-11 could not be reproduced by any recipe, which makes it a decoration rather
than a verification.

```
sha256 over, for each *.py in the vendored packages at the pin, sorted by full path:
    basename  then  file bytes with CRLF normalised to LF
truncated to 16 hex chars
```

CRLF normalisation is load-bearing, not cosmetic: this repo sets `* text=auto`, so a Windows
checkout has CRLF on disk while `git show` emits LF, and a byte comparison against upstream reports
every line of every file as changed.

| Content digest | `see test_massingcapture_vendor.py` — computed and asserted there, so it cannot drift from the recipe |
