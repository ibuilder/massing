"""``massingcapture.classify`` -- deciding what a file *is*, from its content.

The rule the research brief states and this package enforces: **never assume an extension means one
thing.** A ``.ply`` is a point cloud, a mesh or a Gaussian splat. A ``.json`` is a 3D Tiles tileset,
a glTF, an Earth Studio camera path or a node graph. A ``.tif`` is an orthomosaic or a scanned
drawing. Classifying on suffix alone gets each of those wrong often enough to matter, and the way it
goes wrong -- a splat classified as measurable geometry -- is the way that costs somebody money.

So: read the magic bytes, read the header, and only fall back to the extension where the format
genuinely carries no signature (``.splat``, ``.ptx``, ``.frag``). Every classification says what
evidence it rests on, and ``confidence`` distinguishes "this file said so" from "this file's name
said so".
"""

from __future__ import annotations

from .sniff import (
    Classification,
    classify_bytes,
    classify_file,
    extension_hint,
    is_probably_text,
)

__all__ = [
    "Classification",
    "classify_bytes",
    "classify_file",
    "extension_hint",
    "is_probably_text",
]
