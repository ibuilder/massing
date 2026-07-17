"""Model capabilities + IFC schema detection (D4x) and a model-staleness signature (B2x).

D4x — IFC5/IFCX is a JSON schema not yet parsable by our web-ifc / Fragments stack; rather than fail
cryptically on such a file, we sniff the source model's header, report the detected schema, and say
plainly whether it's supported. The read path lands upstream.

B2x — the 2D drawings regenerate on demand from the live model, so "is my 2D stale?" reduces to "did the
model change since I last rendered?". `model_signature` returns a cheap, stable fingerprint of the loaded
model (element count + a hash of GlobalIds); the client compares it across renders to know when to
regenerate — the tractable slice of live-2D propagation without an event bus.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

SUPPORTED_SCHEMAS = ["IFC2X3", "IFC4", "IFC4X3"]
_SCHEMA_RE = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", re.IGNORECASE)


def detect_schema(path: str | None) -> dict[str, Any]:
    """Sniff the IFC schema from the file header — supports STEP (IFC-SPF) + detects IFC5/IFCX (JSON)."""
    if not path or not os.path.exists(path):
        return {"detected": None, "supported": None, "note": "no source model on this project"}
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return {"detected": None, "supported": None, "note": "could not read the source model"}
    if head.lstrip()[:1] in (b"{", b"["):
        return {"detected": "IFC5 / IFCX (JSON)", "supported": False, "data_readable": True,
                "note": "IFC5/IFCX is a JSON-based schema. The DATA read path is supported — elements + "
                        "properties parse into the model index (analytics, audits, exports all work). "
                        "Geometry RENDERING lands when web-ifc / Fragments add IFC5 support upstream."}
    m = _SCHEMA_RE.search(head)
    schema = m.group(1).decode("ascii", "ignore").upper() if m else None
    supported = bool(schema and any(schema.startswith(s) for s in SUPPORTED_SCHEMAS))
    return {"detected": schema, "supported": supported,
            "note": "STEP (IFC-SPF) schema read from the file header."
                    + ("" if supported else " Not a currently-supported read schema.")}


def capabilities(source_ifc: str | None) -> dict[str, Any]:
    """What IFC this build can read, plus the detected schema of the project's loaded model."""
    return {
        "supported_read_schemas": SUPPORTED_SCHEMAS,
        "loaded_model": detect_schema(source_ifc),
        "ifc5": {"status": "data",
                 "data_read": True, "geometry_read": False,
                 "note": "IFC5 / IFCX / ifcJSON DATA is parsed into the model index (elements + "
                         "properties) — analytics, audits and exports work on it now. Geometry "
                         "RENDERING lands when web-ifc / Fragments ship IFC5 support upstream."},
    }


def model_signature(idx: dict[str, dict] | None) -> dict[str, Any]:
    """A cheap, stable fingerprint of the loaded model so the client can detect 2D staleness."""
    if not idx:
        return {"model_loaded": False, "elements": 0, "signature": None,
                "note": "No model loaded. 2D regenerates on demand from the live model when one is."}
    keys = sorted(idx.keys())
    digest = hashlib.sha1("|".join(keys).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]  # non-crypto fingerprint
    return {"model_loaded": True, "elements": len(keys), "signature": f"{len(keys)}-{digest}",
            "note": "Compare this signature across renders; a change means the 2D drawings are stale and "
                    "should be regenerated (they render live from the model on request)."}
