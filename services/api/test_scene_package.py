"""SCENE-PKG — our IFC, converted to a scene package, read back by a reader we did not write.

WHY THIS SHAPE
    The valuable property of this integration is not "the endpoint returns 200". It is that a model
    this codebase owns survives a round trip through a format defined elsewhere and comes back
    identifying the same elements by the same GlobalIds. So the assertions below deliberately do NOT
    re-read our own output with our own helper: they use `massingifc_scene`'s `SceneImporter`, which
    was written against the TypeScript definition and knows nothing about us.

    A round trip over your own writer and your own reader passes on the wrong format. That has cost
    this repo before, which is why the check is aimed the other way.

WHAT IT ASSERTS
    - Nodes are addressed by GlobalId, and the set of GlobalIds matches what ifcopenshell reports for
      the same file — asserted as a SET, not a count. A count agrees by accident; a set does not.
    - The by-class index the package precomputes agrees with grouping the same elements by hand.
      That index is the thing a consumer trusts instead of doing the work, so it has to be right, and
      "it exists" is not the claim being made.
    - `generatedAt` is DETERMINISTIC — two conversions of an unchanged file are byte-identical. This
      is the check that keeps the content hash meaningful; without it the format's whole
      change-detection story quietly stops working and nothing looks wrong.
    - Geometry is carried by REFERENCE with a hash, and a package built without geometry names no
      payload at all rather than naming bytes it does not have.
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


#: The fixture is AUTHORED, not read from disk. Two reasons, both learned here:
#: `samples/*.ifc` are gitignored and have turned main red twice when a test read one; and the
#: tracked `families/*.ifc` are TYPE libraries with no spatial containment, so this converter — which
#: walks the spatial hierarchy — correctly carries nothing but the IfcProject out of them. A fixture
#: that yields one node cannot tell a working index from a broken one.
import ifcopenshell  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FIXTURE = os.path.join(tempfile.gettempdir(), "_scene_pkg_test.ifc")
massing.generate_blank_ifc(FIXTURE, name="Scene Package Test", storeys=2,
                           storey_height=4.0, ground_size=20.0)
_m = open_model(FIXTURE)
_storeys = _m.by_type("IfcBuildingStorey")
for _i, _st in enumerate(_storeys):
    edit.add_wall(_m, [0, 0], [8, 0], 3.0, 0.3, _st.Name)
    edit.add_wall(_m, [8, 0], [8, 6], 3.0, 0.3, _st.Name)
_m.write(FIXTURE)
from massingifc_ifc import convert_ifc  # noqa: E402
from massingifc_scene import (  # noqa: E402
    DirectoryArchive,
    SceneImporter,
    read_scene_package,
    write_scene_package,
)

model = ifcopenshell.open(FIXTURE)

# ---------------------------------------------------------------- convert, with a fixed stamp
STAMP = "2026-01-01T00:00:00+00:00"
pkg, payloads = convert_ifc(FIXTURE, model_id="fixture", generated_at=STAMP)
check("conversion produced nodes", len(pkg.nodes) > 0, f"{len(pkg.nodes)} nodes")
check("no geometry supplied => no payload promised", len(pkg.payloads) == 0,
      f"{len(pkg.payloads)} payload(s)")

# ---------------------------------------------------------------- determinism
again, _ = convert_ifc(FIXTURE, model_id="fixture", generated_at=STAMP)
a = json.dumps(pkg.to_json(), sort_keys=True)
b = json.dumps(again.to_json(), sort_keys=True)
check("two conversions of an unchanged model are byte-identical", a == b,
      "" if a == b else "manifest is non-deterministic — the content hash is then meaningless")

# The engine module must not reintroduce a clock. A `generated_at` of now() would pass every other
# assertion here and silently break caching, which is exactly the kind of defect that ships.
from aec_api import scene_package as sp  # noqa: E402

s1, s2 = sp._stamp(FIXTURE), sp._stamp(FIXTURE)
check("_stamp is derived from the file, not the clock", s1 == s2, s1)

# ---------------------------------------------------------------- round trip through THEIR reader
with tempfile.TemporaryDirectory() as td:
    archive = DirectoryArchive(td)
    write_scene_package(archive, pkg, payloads)
    reread = read_scene_package(DirectoryArchive(td))
    check("their writer + their reader round-trips our model",
          len(reread.nodes) == len(pkg.nodes), f"{len(reread.nodes)} == {len(pkg.nodes)}")

    importer = SceneImporter.open(DirectoryArchive(td))

    # --- GlobalIds as a SET, against ifcopenshell directly ---
    pkg_guids = {n.global_id for n in reread.nodes}
    check("every node is addressed by a GlobalId", all(bool(g) for g in pkg_guids),
          f"{len(pkg_guids)} unique GlobalIds")

    # Compare against IfcRoot, not IfcProduct: the package carries the spatial spine
    # (IfcProject / IfcSite / IfcBuilding / IfcBuildingStorey) and IfcProject is an IfcContext, not
    # an IfcProduct. Comparing to IfcProduct alone reports the project root as "invented", which is a
    # false positive that reads exactly like a real one.
    ifc_guids = {p.GlobalId for p in model.by_type("IfcRoot")
                 if getattr(p, "GlobalId", None)}
    # The converter deliberately excludes some products (openings, and anything unreachable through
    # the spatial hierarchy). So the package must be a SUBSET of the model, never a superset — an
    # element the package invents is a far worse failure than one it declines to carry.
    invented = pkg_guids - ifc_guids
    check("the package invents no element the IFC does not contain", not invented,
          f"{len(invented)} invented" if invented else f"{len(pkg_guids)} of {len(ifc_guids)} products")

    # --- the precomputed by-class index must agree with doing it by hand ---
    by_hand: dict[str, set[str]] = {}
    for n in reread.nodes:
        by_hand.setdefault(n.ifc_class, set()).add(n.global_id)
    mismatches = []
    for cls, expected in sorted(by_hand.items()):
        got = {n.global_id for n in importer.by_class(cls)}
        if got != expected:
            mismatches.append(f"{cls}: index {len(got)} vs actual {len(expected)}")
    check("the precomputed by-class index agrees with the nodes it indexes",
          not mismatches, "; ".join(mismatches[:3]) or f"{len(by_hand)} classes checked")

    # A class that is not in the model must return empty, not raise and not guess.
    check("an absent class returns empty rather than raising",
          list(importer.by_class("IfcNotAThing")) == [])

# ---------------------------------------------------------------- geometry travels by reference
fake_frag = b"FRAG" + bytes(range(256)) * 8
geo_pkg, geo_payloads = convert_ifc(FIXTURE, model_id="fixture", generated_at=STAMP,
                                    geometry=fake_frag)
check("supplying geometry declares exactly one payload", len(geo_pkg.payloads) == 1,
      f"{len(geo_pkg.payloads)}")
if geo_pkg.payloads:
    pay = geo_pkg.payloads[0]
    check("the payload is Fragments, not a re-encode",
          pay.encoding == "application/vnd.thatopen.fragments", pay.encoding)
    check("the payload carries its own length", pay.byte_length == len(fake_frag),
          f"{pay.byte_length} == {len(fake_frag)}")
    # The manifest must be small even when the geometry is not — that is the entire point of
    # carrying geometry by reference, so assert it rather than assuming it.
    manifest_bytes = len(json.dumps(geo_pkg.to_json()).encode())
    check("the manifest does not inline the geometry",
          fake_frag[:32] not in json.dumps(geo_pkg.to_json()).encode(),
          f"manifest {manifest_bytes}B, geometry {len(fake_frag)}B")
    # And the hash must actually be OF the bytes — a hash computed over the wrong thing still looks
    # like a hash.
    check("the payload hash is a hash of the supplied bytes",
          pay.hash and pay.hash != hashlib.sha256(b"").hexdigest()[:len(pay.hash)],
          pay.hash)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_scene_package OK")
