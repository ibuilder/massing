"""
The sample library — showcase projects as `.mass` containers.

Until now "load a sample" meant three bare `.frag` files: geometry, and nothing else. You could spin
the model and that was the whole demonstration. Every number the product exists to produce — the
estimate, the schedule, the RFIs, the drawings — was absent, so the sample showed the viewer and hid
the platform.

A `.mass` container already carries all of it (`bundle.py`: geometry + every table + blobs, verified
round-tripping on 2026-07-28). So a sample is not a new artifact type, it is **the container we
already ship, packaged**. That is why this module is small: it lists a directory and hands bytes to
`bundle.import_bundle`, which is the same path a user's own `.mass` takes. A sample that opened
through a private path would be a demo of something other than the product.

**Resolution is by enumeration, never by joining.** `read(sample_id)` selects from the directory's
own listing rather than composing a path out of caller input. That shape is deliberate and this
codebase has a memory about it: a path built from a request parameter is a path-traversal finding no
amount of validation argues away, while a path chosen from a listing cannot leave the directory at
all — there is nothing to escape from.
"""
from __future__ import annotations

import json
import os
import zipfile
from functools import lru_cache
from typing import Any

#: Where the packaged containers live. An operator can point this elsewhere; the default sits beside
#: the repo so a checkout is demonstrable with no configuration.
_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "samples")

#: A sample is refused rather than served if it is implausibly large — the library is curated content
#: we package ourselves, so anything here at hundreds of megabytes is a packaging mistake, not a user
#: upload. Failing loudly at list time beats a browser hanging on a click.
MAX_SAMPLE_BYTES = 256 * 1024 * 1024


def samples_dir() -> str:
    return os.environ.get("AEC_SAMPLES_DIR") or _DEFAULT_DIR


def _entries() -> list[str]:
    """Every `.mass` file in the library, by bare filename. The only source of valid ids."""
    d = samples_dir()
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    out = []
    for n in names:
        if not n.lower().endswith(".mass"):
            continue
        try:
            if os.path.isfile(os.path.join(d, n)) and os.path.getsize(os.path.join(d, n)) <= MAX_SAMPLE_BYTES:
                out.append(n)
        except OSError:
            continue
    return out


def _describe(path: str, name: str) -> dict[str, Any]:
    """What is inside one container, read from its own manifest.

    The manifest is written by `bundle.export_bundle`, so the description of a sample is produced by
    the same code that produced the sample — there is no second, hand-maintained catalog file to
    drift out of agreement with the actual contents. A catalog beside the artifacts is a promise;
    the manifest is a measurement.
    """
    # Every key present on every path. A container we cannot read still yields a complete record —
    # otherwise a consumer reading `sample.elements` gets a KeyError for exactly the corrupt entry it
    # most needs to render, and one bad file in the library breaks the whole panel.
    info: dict[str, Any] = {
        "id": name,
        "name": os.path.splitext(name)[0].replace("_", " ").replace("-", " ").strip(),
        "bytes": 0, "entries": 0, "contents": {}, "readable": False,
        "elements": 0, "has_geometry": False, "format": None, "version": None,
    }
    try:
        info["bytes"] = os.path.getsize(path)
        with zipfile.ZipFile(path) as z:
            info["entries"] = len(z.namelist())
            try:
                man = json.loads(z.read("manifest.json").decode("utf-8"))
            except (KeyError, ValueError, UnicodeDecodeError):
                return info                      # a zip we cannot describe is still listable
            info["readable"] = True
            info["format"] = man.get("format")
            info["version"] = man.get("version")
            if man.get("project", {}).get("name"):
                info["name"] = man["project"]["name"]
            # Row counts per table — this is what makes the library legible: a viewer can say
            # "42 elements, 6 RFIs, a full estimate" instead of listing opaque filenames.
            tables = man.get("tables") or {}
            info["contents"] = {k: v for k, v in tables.items() if isinstance(v, int) and v > 0}
            info["elements"] = info["contents"].get("element", 0)
            info["has_geometry"] = any(n.endswith((".frag", ".ifc")) for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        pass
    return info


@lru_cache(maxsize=1)
def _catalog_cached(stamp: tuple) -> list[dict[str, Any]]:
    d = samples_dir()
    return [_describe(os.path.join(d, n), n) for n in _entries()]


def _stamp() -> tuple:
    """Directory fingerprint, so the catalog re-reads when the library changes but not per request.

    Keyed on (name, size, mtime) rather than mtime of the directory alone: on Windows a directory's
    mtime does not always move when a file inside it is rewritten in place, which would serve a stale
    description of a sample that had actually been re-packaged.
    """
    d = samples_dir()
    out = []
    for n in _entries():
        try:
            st = os.stat(os.path.join(d, n))
            out.append((n, st.st_size, int(st.st_mtime)))
        except OSError:
            continue
    return tuple(out)


def catalog() -> list[dict[str, Any]]:
    """The library, described. Empty list when the directory is absent — never an error: a checkout
    without packaged samples is a valid state, and the UI shows "no samples" rather than a crash."""
    return list(_catalog_cached(_stamp()))


def read(sample_id: str) -> bytes | None:
    """The bytes of one sample, or None if there is no such sample.

    The id is matched against the directory listing; it is never joined onto a root. A caller sending
    `../../etc/passwd` finds no match in the listing and gets None, which is the same answer as a
    typo — there is no path to traverse because no path was ever built from the input.
    """
    if sample_id not in _entries():
        return None
    try:
        with open(os.path.join(samples_dir(), sample_id), "rb") as fh:
            return fh.read()
    except OSError:
        return None
