"""
Package a project into the sample library.

Exports a live project to a `.mass` container and drops it in `samples/`, where `GET /samples` will
describe it from its own manifest.

Deliberately a thin wrapper over `bundle.export_bundle`: the sample library must be built by the same
writer the product uses, so a packaged sample cannot encode a format the importer does not read. The
one thing this adds is a **check that it opens** — writing bytes nobody has read back is how a
library fills up with containers that look fine in a listing and fail on click.

    ./.venv/Scripts/python.exe build_samples.py --list
    ./.venv/Scripts/python.exe build_samples.py --project <pid> --out ../../samples
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "samples")


def slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in name.strip()]
    out = "".join(keep)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "sample"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="project id to package")
    ap.add_argument("--out", default=DEFAULT_OUT, help="library directory")
    ap.add_argument("--name", help="filename stem (default: slugified project name)")
    ap.add_argument("--list", action="store_true", dest="do_list", help="list projects and exit")
    args = ap.parse_args()

    from aec_api import bundle as bundle_io
    from aec_api.db import SessionLocal
    from aec_api.models import Project

    db = SessionLocal()
    try:
        if args.do_list or not args.project:
            rows = db.query(Project).order_by(Project.name).all()
            if not rows:
                print("no projects in this database")
                return 1
            print(f"{len(rows)} project(s):")
            for p in rows:
                print(f"  {p.id}   {p.name}")
            if not args.project:
                print("\npass --project <id> to package one")
            return 0

        p = db.query(Project).filter(Project.id == args.project).one_or_none()
        if p is None:
            print(f"no such project: {args.project}", file=sys.stderr)
            return 1

        data = bundle_io.export_bundle(db, args.project)
        stem = args.name or slug(p.name)
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{stem}.mass")
        with open(path, "wb") as fh:
            fh.write(data)
        print(f"wrote {path}  ({len(data):,} bytes)")

        # Read it back through the library's own reader. A container that writes cleanly and does not
        # describe cleanly is the failure this catches — and it is the one a listing hides, because a
        # broken sample still appears in the catalog, just with `readable: false`.
        os.environ["AEC_SAMPLES_DIR"] = os.path.abspath(args.out)
        import importlib

        from aec_api import samples as samples_io
        samples_io = importlib.reload(samples_io)
        found = next((c for c in samples_io.catalog() if c["id"] == f"{stem}.mass"), None)
        if not found:
            print("ERROR: written, but the library does not list it", file=sys.stderr)
            return 1
        if not found.get("readable"):
            print("ERROR: written, but its manifest does not read back", file=sys.stderr)
            return 1
        print(f"  verified: {found['name']!r}  {found['elements']} elements, "
              f"{found['entries']} entries, tables={found['contents']}")
        # A container the reader can DESCRIBE is not the same as one a user can USE. On 2026-07-28
        # this script printed "verified" for a container holding neither `model.frag` nor the element
        # index — it had a source `.ifc`, and `has_geometry` accepts `.frag` OR `.ifc`, so the one
        # check that should have caught it passed for the wrong reason.
        #
        # The cause was environment, not code: `STORAGE_DIR` was unset, so `storage.exists()` looked
        # in a different directory than the API writes to and every blob silently "did not exist".
        # That is worth failing on rather than warning about — a sample packaged against the wrong
        # storage is indistinguishable from a project with no model until somebody opens it.
        import zipfile as _zip
        with _zip.ZipFile(path) as _z:
            names = set(_z.namelist())
        problems = []
        if "geometry/model.frag" not in names:
            problems.append("no geometry/model.frag — nothing will render")
        if "index/props.json" not in names:
            problems.append("no index/props.json — the model cannot be queried (no browser, "
                            "no element list, no takeoff)")
        if found["elements"] == 0:
            problems.append("0 elements — a real building does not have zero")
        if problems:
            print(f"\nERROR: {path} is not a usable sample:", file=sys.stderr)
            for p_ in problems:
                print(f"  - {p_}", file=sys.stderr)
            print("\n  Most likely STORAGE_DIR / DATABASE_URL do not match the API that authored it.\n"
                  f"  The API stores blobs under STORAGE_DIR/<pid>/; check that {args.project} has\n"
                  "  model.frag and props.json there, and re-run with the same env the server uses.",
                  file=sys.stderr)
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
