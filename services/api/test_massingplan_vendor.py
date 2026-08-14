"""R43-PLAN-DRIFT (the half that needs no cadence decision) — the vendored copy is unmodified.

The roadmap files PLAN-DRIFT as blocked on *cadence*: how often to ask whether upstream has moved.
That is a real open question and this file does not answer it. It answers the other half, which was
never blocked — **has anyone edited the copy HERE?** — and that question needs no schedule, no
network and no decision, only the recipe `VENDOR.md` already writes down.

`VENDOR.md` earned this test. It records a content digest and, unusually, the method for recomputing
it, after the previous digest turned out to be unreproducible by any recipe anyone could find. Its
own words: *"a recorded verification value nobody can recompute is not a verification, it is a
decoration."* A recipe stated in prose and never executed is one revision away from being decoration
again — so it is executed here.

**The expected digest is PARSED from VENDOR.md, never hardcoded.** Copying the value into this file
would create a second source of truth, and the first thing a re-sync would do is make them disagree
— with the test still green against its own stale copy. Whoever re-syncs updates VENDOR.md, and this
follows.

**Scope, because it is narrower than it looks.** The digest covers `massingplan/core/` only. The
top-level `__init__.py` is OURS — a three-line shim that is not upstream's and must not be in a
digest that claims to describe upstream's tree. Getting that wrong is not hypothetical: the first
attempt at reproducing this value hashed the whole vendored directory, got a mismatch, and the
mismatch was the measurement rather than the artifact.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

from vendor_drift import read_digest, read_pin

HERE = pathlib.Path(__file__).parent
VENDOR = HERE / "src" / "massingplan"
CORE = VENDOR / "core"
DOC = VENDOR / "VENDOR.md"

FAILED: list[str] = []


def check(name: str, ok: bool, why: str = "", note: str = "") -> None:
    """`why` is printed only on FAILURE, `note` only on success.

    Split because the shared helper in this repo prints one `detail` either way, which puts the
    failure explanation on a PASS line — a log that contradicts its own verdict. That has already
    misled this work once today (a "FAILED" that had actually succeeded), and a reader skimming for
    trouble finds the scariest sentence sitting under the word PASS.
    """
    print(("PASS  " if ok else "FAIL  ") + name + ((f"   {note}" if note else "") if ok
                                                   else (f"   {why}" if why else "")))
    if not ok:
        FAILED.append(name)


def core_files() -> list[pathlib.Path]:
    """Every `*.py` under core/, sorted by full path — the recipe's population."""
    return sorted((p for p in CORE.rglob("*.py") if "__pycache__" not in str(p)),
                  key=lambda p: str(p).replace("\\", "/"))


def content_digest(files: list[pathlib.Path]) -> str:
    """VENDOR.md's recipe, executed.

    CRLF is normalised to LF and that is load-bearing rather than tidy: this repo sets `* text=auto`,
    so a Windows checkout holds CRLF on disk while `git show` emits LF. A byte comparison against
    upstream reports every line of every file as changed — during the last sync that turned 1 real
    change into 7 files that "looked modified".
    """
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


check("the vendored tree is present", CORE.is_dir(), str(CORE))
check("VENDOR.md is present", DOC.is_file(), str(DOC))
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

doc = DOC.read_text(encoding="utf-8")
files = core_files()

# Silence is not a signal: an empty glob hashes to a constant, and a constant compared against a
# recorded constant would pass forever over a deleted tree.
check("the recipe's population is non-empty", len(files) >= 15,
      "core/ is empty or unreadable", note=f"{len(files)} .py under core/")

# Parsed via `vendor_drift`, not a regex of our own. The weekly drift check reads the SAME pin from
# the SAME document; two independent parses could disagree about which commit VENDOR.md names, and
# neither would notice, because each would be self-consistent.
recorded = read_digest(doc)
check("VENDOR.md records a content digest", recorded is not None,
      "no `| Content digest | `…`` row found")
pin = read_pin(doc)
check("VENDOR.md records a full 40-hex commit pin", pin is not None,
      "a short pin cannot identify a commit unambiguously")

if recorded:
    computed = content_digest(files)
    check("the vendored core matches the digest VENDOR.md records",
          computed == recorded,
          f"computed {computed}, recorded {recorded} — either someone edited a vendored "
          f"file (fix it UPSTREAM and re-sync; a local patch is a fork the next sync silently "
          f"reverts) or the tree was re-synced without updating VENDOR.md",
          note=f"{computed} over {len(files)} files")

# The twin. Everything above is satisfied by a digest function that returns a constant, so this
# proves the recipe actually reads the bytes: perturbing one file must change the answer.
if files:
    real = content_digest(files)
    h = hashlib.sha256()
    for i, f in enumerate(files):
        h.update(f.name.encode())
        body = f.read_bytes().replace(b"\r\n", b"\n")
        h.update(body + (b"#" if i == 0 else b""))     # one byte, in one file
    check("...and one added byte in one file changes it", h.hexdigest()[:16] != real,
          "the digest ignores content — it is not verifying anything")

# The property the whole adoption rests on. `core` is stdlib-only BY CONTRACT, and that is what
# makes vendoring it a copy rather than a dependency decision; asserted per file rather than trusted.
STDLIB_OK = {
    "__future__", "typing", "collections", "dataclasses", "datetime", "enum", "math", "re", "json",
    "itertools", "functools", "heapq", "bisect", "random", "statistics", "abc", "copy", "csv", "io",
    "os", "sys", "xml", "zipfile", "pathlib", "decimal", "fractions", "operator", "string",
    "textwrap", "uuid", "warnings", "contextlib", "logging", "hashlib", "struct", "time", "calendar",
}
import ast  # noqa: E402

offenders: list[str] = []
for f in files:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in STDLIB_OK:
                    offenders.append(f"{f.name}: import {a.name}")
        elif isinstance(n, ast.ImportFrom) and not n.level:
            root = (n.module or "").split(".")[0]
            if root and root not in STDLIB_OK:
                offenders.append(f"{f.name}: from {n.module}")
check("the vendored core imports the standard library and nothing else", not offenders,
      "; ".join(offenders[:5]), note=f"checked {len(files)} files")

# The local shim is ours and is deliberately OUTSIDE the digest. Asserted so nobody "fixes" the
# recipe by widening it to the whole directory — which is exactly the wrong correction, and the one
# a mismatch invites.
shim = VENDOR / "__init__.py"
check("the top-level __init__.py is ours and stays outside the digest",
      shim.is_file() and shim not in files,
      "if this file entered the digest the recorded value could never reproduce")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_massingplan_vendor OK  ({len(files)} core files, digest matches VENDOR.md)")
