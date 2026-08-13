"""The vendored massingcapture subset — the properties we actually depend on.

`src/massingcapture/` is a PARTIAL vendor of MassingCloud/massingcapture at
`1a31e1be69320734e5b2cc001fea6f2acbbea78a`: `classify/` + `probe/` only. VENDOR.md carries the
reasoning; this file holds the two claims that would otherwise be prose.

**1. Standard library only.** Upstream declares `dependencies = []`, which is true of the manifest
and misleading about the modules — every `adapters/*` sits behind a real extra (pyproj, pymavlink,
pypdfium2, open3d), none of which we declare. The subset we took is genuinely stdlib-only, and that
is the property the whole adoption rests on, so it is asserted per file rather than believed.

**2. Detection is content-first.** The README says "content-first format detection". An
implementation that keyed off file extensions would look identical on every correctly-named file in
any fixture. The only test that separates them is a file whose extension LIES, so that is the test.

Also worth recording: the original plan was to vendor `probe/` alone, which would have shipped half
a capability. `probe(path, asset_format)` takes the format as an argument; the content-first property
lives entirely in `classify/`. Reading the entry point is what caught it.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import shutil
import sys
import tempfile

VENDOR = pathlib.Path(__file__).parent / "src" / "massingcapture"

#: Modules a stdlib-only subset may import. Anything outside this set is either a third-party
#: dependency we have not declared or a reach into a package we deliberately did not vendor.
STDLIB_OK = {
    "__future__", "typing", "collections", "dataclasses", "pathlib", "functools", "enum", "os",
    "re", "io", "sys", "json", "math", "struct", "zlib", "zipfile", "hashlib", "base64",
    "binascii", "xml", "datetime", "itertools", "shutil", "tempfile", "logging", "csv", "gzip",
    "mmap", "array", "string", "textwrap", "urllib", "uuid", "warnings", "contextlib", "abc",
    "codecs", "unicodedata", "operator", "bisect", "statistics", "decimal", "fractions",
}

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


files = sorted(VENDOR.rglob("*.py"))

# Silence is not a signal: an empty glob would satisfy every "no bad import" assertion below.
check("the vendored subset is present", len(files) >= 12, f"{len(files)} .py files under {VENDOR}")

# --- 1. stdlib only, per file --------------------------------------------------------------------
offenders: list[str] = []
for f in files:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in STDLIB_OK:
                    offenders.append(f"{f.name}: import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:           # relative — checked separately below
                continue
            root = (node.module or "").split(".")[0]
            if root and root not in STDLIB_OK:
                offenders.append(f"{f.name}: from {node.module}")

check("the vendored subset imports the standard library and nothing else", not offenders,
      "; ".join(offenders) or f"checked {len(files)} files")

# --- the subset must not reach into packages we did NOT vendor ------------------------------------
# `classify/sniff.py` legitimately does `from ..probe import ply`. A reach into ..adapters, ..ingest
# or ..server would be a broken copy that happens to import because those names do not exist here —
# it would fail at call time, not import time, which is the worst place to find out.
escapes: list[str] = []
for f in files:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        # level 1 is a SIBLING inside the same package (`from .mesh import ...`) and is always
        # within the subset. Only level >= 2 climbs out of the package, and from there the only
        # landing places that exist here are `probe` and `classify`. An earlier version of this
        # check rejected every level-1 import and failed on legitimate intra-package code — the
        # rule was wrong, not the vendored copy.
        if node.level >= 2:
            head = (node.module or "").split(".")[0]
            if head not in ("probe", "classify"):
                escapes.append(f"{f.name}: from {'.' * node.level}{node.module}")

check("nothing reaches outside the two vendored packages", not escapes,
      "; ".join(escapes) or "only .probe / .classify relative imports")

# --- 2. detection is content-first, not extension-first -------------------------------------------
sys.path.insert(0, str(VENDOR.parent))
from massingcapture.classify import classify_file  # noqa: E402
from massingcapture.probe import PROBES, probe  # noqa: E402

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "samples" / "basichouse.ifc"
if not SAMPLE.exists():
    print("SKIP  sample model missing:", SAMPLE)
else:
    honest = classify_file(str(SAMPLE))
    fmt = getattr(honest, "asset_format", None) or getattr(honest, "format", None)
    check("an IFC named .ifc classifies as ifc", fmt == "ifc", f"got {fmt!r}")

    # THE test. An extension-keyed implementation passes everything above and fails only here.
    tmpdir = tempfile.mkdtemp()
    try:
        liar = pathlib.Path(tmpdir) / "actually_an_ifc.jpg"
        shutil.copy(SAMPLE, liar)
        lying = classify_file(str(liar))
        lfmt = getattr(lying, "asset_format", None) or getattr(lying, "format", None)
        check("an IFC renamed .jpg STILL classifies as ifc — detection reads bytes, not the name",
              lfmt == "ifc",
              f"got {lfmt!r}; if this says 'jpeg' the classifier is keyed on the extension and the "
              f"content-first claim is false")

        # And the probe dispatched from that classification must produce real content, not an
        # empty dict — "it returned something" is not the same as "it read the file".
        summary = probe(str(liar), lfmt) if lfmt else {}
        check("the probe dispatched from content returns actual metadata",
              bool(summary.get("ifc_schema")),
              f"keys={sorted(k for k in summary if not k.startswith('probe'))[:5]}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

check("the probe table covers the formats the adoption was for",
      {"e57", "las", "ply", "ifc", "splat", "glb"} <= set(PROBES),
      f"{len(PROBES)} formats registered")

# --- 3. the content digest, computed by the recipe VENDOR.md states -------------------------------
# Recorded rather than pinned to a literal: a digest asserted against a hardcoded value fails on the
# next legitimate re-sync and teaches people to edit the number. What must not drift is the RECIPE,
# so the recipe lives here and the value is printed for VENDOR.md to quote.
h = hashlib.sha256()
for f in files:
    h.update(f.name.encode())
    h.update(f.read_bytes().replace(b"\r\n", b"\n"))
print(f"      content digest (CRLF-normalised, name+bytes, sorted): {h.hexdigest()[:16]}")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_massingcapture_vendor OK")
