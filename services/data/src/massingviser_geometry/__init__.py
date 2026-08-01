"""Vendored geometry from `MassingCloud/massingviser` — server-side spatial acceleration.

Only `bvh.py` is taken. The rest of that project's `geometry/` package is deliberately NOT here:
`payload.py` defines its own flat binary mesh format ("MVMS"), which would compete with Fragments —
and Fragments is this platform's geometry format, carried end to end rather than re-encoded. Taking a
second binary format to gain a spatial index would be paying an architectural cost for an unrelated
benefit.

See VENDOR.md in this directory.
"""
from .bvh import Aabb, Bvh
from .lod import DecimatedMesh, cluster_decimate, decimate_to_budget, lod_chain

__all__ = ["Aabb", "Bvh", "DecimatedMesh", "cluster_decimate", "decimate_to_budget", "lod_chain"]
