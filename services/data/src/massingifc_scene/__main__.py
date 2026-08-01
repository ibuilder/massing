"""Inspect a scene package from the command line.

``python -m massingifc_scene <package>`` — a directory or a ``.zip``.

Exists because the first question about any new format is "did that work?", and answering it should
not require writing a script. It is also the smallest useful engine-side consumer: everything it
prints, an importer had to resolve.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import zipfile
from pathlib import Path

from .codec import DirectoryArchive, ZipArchive
from .importer import SceneImporter
from .model import ScenePackageError


def _archive(path: Path, stack: contextlib.ExitStack):
    """Open a package, translating filesystem failures into the error type this CLI reports.

    A zip is registered with the caller's `ExitStack` so its handle is closed on the way out —
    on Windows an open `ZipFile` keeps the file locked, which matters as soon as anything calls
    `main()` more than once in a process.
    """
    if path.is_dir():
        return DirectoryArchive(path)
    if path.suffix.lower() == ".zip":
        try:
            return stack.enter_context(ZipArchive(path))
        except (OSError, zipfile.BadZipFile) as error:
            raise ScenePackageError(f"Could not open {path}: {error}") from error
    if not path.exists():
        raise ScenePackageError(f"{path} does not exist")
    raise ScenePackageError(f"{path} is neither a package directory nor a .zip")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="massingifc_scene", description=__doc__)
    parser.add_argument("package", type=Path, help="package directory or .zip")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument(
        "--element", metavar="GLOBALID", help="show one element by its IFC GlobalId"
    )
    parser.add_argument("--classes", action="store_true", help="list IFC classes present")
    arguments = parser.parse_args(argv)

    with contextlib.ExitStack() as stack:
        try:
            importer = SceneImporter.open(_archive(arguments.package, stack))
        except ScenePackageError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        return _report(importer, arguments)


def _report(importer: SceneImporter, arguments: argparse.Namespace) -> int:
    """Print whichever view the flags asked for. Split out so the archive's lifetime is
    bounded by the caller's `ExitStack` rather than by this function returning."""
    if arguments.element:
        node = importer.node(arguments.element)
        if node is None:
            print(f"error: no element with GlobalId {arguments.element!r}", file=sys.stderr)
            return 1
        detail = {
            "globalId": node.global_id,
            "name": node.name,
            "ifcClass": node.ifc_class,
            "level": node.level_global_id,
            "parent": node.parent_global_id,
            "payload": node.payload_id,
            "ancestors": [entry.global_id for entry in importer.ancestors(node.global_id)],
            "children": [entry.global_id for entry in importer.children(node.global_id)],
            "properties": {
                entry.name: dict(entry.properties)
                for entry in importer.property_sets(node.global_id)
            },
        }
        print(json.dumps(detail, indent=2))
        return 0

    if arguments.classes:
        for name in importer.classes():
            print(f"{len(importer.by_class(name)):>7}  {name}")
        return 0

    summary = importer.summary()
    if arguments.json:
        print(json.dumps(summary, indent=2))
    else:
        for key, value in summary.items():
            print(f"{key:>16}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
