"""Convert an IFC into a scene package from the command line.

``python -m massingifc_ifc <model.ifc> --out <directory>``

Server-side conversion is the arrangement the architecture assumes: convert once, somewhere with
time and memory, and let clients load the result rather than parsing IFC in every session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from massingifc_scene import (
    DirectoryArchive,
    GeoReference,
    ScenePackageError,
    ZipArchive,
    validate_scene_package,
    write_scene_package,
)

from .audit import audit_conversion
from .convert import convert_ifc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="massingifc_ifc", description=__doc__)
    parser.add_argument("ifc", type=Path, help="the IFC file to convert")
    parser.add_argument("--out", type=Path, required=True, help="output directory or .zip")
    parser.add_argument(
        "--fragments",
        type=Path,
        help="a .frag binary to carry as the geometry payload",
    )
    parser.add_argument("--crs", help='source CRS, e.g. "EPSG:27700"')
    parser.add_argument(
        "--origin-offset",
        help="x,y,z subtracted from world coordinates to keep the scene near the origin",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="skip comparing the package against the source file",
    )
    parser.add_argument("--no-properties", action="store_true")
    parser.add_argument("--no-relationships", action="store_true")
    arguments = parser.parse_args(argv)

    geo = None
    if arguments.crs:
        offset = None
        if arguments.origin_offset:
            try:
                offset = [float(part) for part in arguments.origin_offset.split(",")]
            except ValueError:
                print("error: --origin-offset must be three numbers, x,y,z", file=sys.stderr)
                return 2
            if len(offset) != 3:
                print("error: --origin-offset must be three numbers, x,y,z", file=sys.stderr)
                return 2
        geo = GeoReference(source_crs=arguments.crs, units="m", origin_offset=offset)
    elif arguments.origin_offset:
        # An offset without a CRS is a number with no frame to be an offset in.
        print("error: --origin-offset needs --crs", file=sys.stderr)
        return 2

    try:
        geometry = arguments.fragments.read_bytes() if arguments.fragments else None
        scene, payloads = convert_ifc(
            arguments.ifc,
            include_properties=not arguments.no_properties,
            include_relationships=not arguments.no_relationships,
            geometry=geometry,
            geo_reference=geo,
            # Only when the audit is off. The audit reports unreached products too, and more
            # precisely; printing both trains a reader to skim past warnings.
            on_warning=(
                (lambda message: print(f"warning: {message}", file=sys.stderr))
                if arguments.no_audit
                else None
            ),
        )
    except (ScenePackageError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if not arguments.no_audit:
        fidelity = audit_conversion(arguments.ifc, scene)
        for issue in fidelity.issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}", file=sys.stderr)
        print(f"fidelity: {fidelity.summary()}", file=sys.stderr)
        if not fidelity.faithful:
            return 1

    report = validate_scene_package(scene)
    for issue in report.issues:
        print(f"{issue.severity}: {issue.code}: {issue.message}", file=sys.stderr)
    if not report.valid:
        return 1

    out = arguments.out
    try:
        if out.suffix.lower() == ".zip":
            with ZipArchive(out, "w") as archive:
                write_scene_package(archive, scene, payloads)
        else:
            write_scene_package(DirectoryArchive(out), scene, payloads)
    except (ScenePackageError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"{len(scene.nodes)} elements -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
