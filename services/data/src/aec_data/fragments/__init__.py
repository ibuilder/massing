"""Read and write `.frag` (Fragments) from Python — the desktop app's converter.

`services/converter/src/cli.mjs` is Node, and the packaged desktop app ships no Node runtime, so the
3D view there was permanently empty (DESKTOP-FRAGMENTS). `ifcopenshell` is already bundled and
already tessellates, so the missing half was the file format — see `schema.py` for how it was
recovered and `codec.py` for the encoder.
"""
from .codec import FragModel, Mesh, dumps, loads

__all__ = ["FragModel", "Mesh", "dumps", "loads"]
