"""Vendored subset of MassingCloud/massingcapture — `probe/` only.

**This is a PARTIAL vendor, and that is deliberate.** See VENDOR.md for the pin and the reasoning.
Unlike `massingplan`, where we copy the whole `core/` tree because a partial copy is how two
implementations start, massingcapture is a whole *application*: it ships a FastAPI server, a demo,
and a bridge to `massingviser` — a platform this project explicitly did not adopt. Copying it whole
would import a second web server and a dependency on a rejected platform.

`probe/` is the part that is free to take: eleven modules, standard library only, verified per module
rather than inferred from the upstream `dependencies = []`. That distinction matters, because the
manifest headline is true while every *adapter* is gated behind a real extra — `crs` needs pyproj,
`drone` needs pymavlink, `plan` needs pypdfium2, `pointcloud` needs open3d. None of those are
declared here, so adopting an adapter is a new-dependency decision rather than a vendoring one.

What this subset gives us, in two halves that only work together:

* **`classify/`** — content-first identification. `classify_file` reads what a file *is* from its
  bytes. Demonstrated, not assumed: an IFC renamed to `.jpg` still classifies as `ifc`.
* **`probe/`** — thirty-two per-format summarisers behind one `PROBES` table, dispatched by the
  format string classify produced. It parses the E57 XML index and the LAS public header without
  pye57 or laspy, so identification and basic metadata need no optional install at all.

**`probe/` alone was the original plan and it was half a capability.** `probe(path, asset_format)`
takes the format as an argument — it summarises a format you have already named, and the "reads the
bytes rather than the extension" property lives entirely in `classify/`. Vendoring only `probe/`
would have shipped the dispatch table without the thing that makes it content-first. Caught by
reading the entry point instead of the README.

Deliberately no re-export of `probe` here. Importing this package should not drag in eleven modules
for a caller that wants one; `from massingcapture.probe import e57` is the intended shape.
"""
from __future__ import annotations

__all__: list[str] = []
