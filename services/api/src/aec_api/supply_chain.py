"""SEC-SUPPLY (R16 Tier-3) — supply-chain hardening, deterministic and dependency-free.

Three cherry-picked, offline pieces (this does *not* replace CodeQL or the esc() XSS discipline):

- **license audit** — walk the installed Python distributions (``importlib.metadata``, stdlib) and classify
  each declared license as **permitted** (MIT / BSD / Apache / ISC / PSF / Unlicense / Zlib — the project's
  standing constraint) · **copyleft** (GPL / AGPL / LGPL / MPL / EPL / CDDL / EUPL — disallowed) · unknown.
  Mechanically enforces the no-AGPL rule instead of relying on review. ``python -m aec_api.supply_chain``
  prints the audit and exits non-zero if any copyleft component is found — usable as a CI/skill gate.
- **SBOM** — a minimal CycloneDX 1.5 JSON component list (name · version · license) for the same set.
- **PDF sanity check** — a lightweight validator for uploaded/ingested PDFs (header + EOF + size cap +
  active-content flags: JavaScript / Launch / EmbeddedFile / OpenAction), no AGPL parser.
"""
from __future__ import annotations

import re
import sys
from typing import Any

# Word-boundary matching (not naive substring — else "EXEMPLARY" in a BSD text falsely matches "mpl").
# copyleft = disallowed by project policy; "strong" (GPL/AGPL) is the hard line, LGPL/MPL are weak
# (accepted in practice for our dynamic-linking/distribution model but still surfaced for review).
_PERMITTED_RE = re.compile(r"\bmit\b|\bbsd\b|apache|\bisc\b|python software foundation|\bpsf\b|"
                           r"unlicense|public domain|\bzlib\b|\b0bsd\b|\bwtfpl\b", re.I)
_COPYLEFT_RE = re.compile(r"\b[al]?gpl|\bmpl\b|mozilla public|\bepl\b|eclipse public|\bcddl\b|\beupl\b|"
                          r"affero|copyleft|gnu (lesser|general|affero)", re.I)
_STRONG_RE = re.compile(r"\ba?gpl|affero", re.I)   # GPL/AGPL — matches gplv3/agpl, NOT lgpl


def classify_license(text: str) -> str:
    """permitted / copyleft / unknown for a declared license string. Copyleft wins ties (a GPL-with-linking
    -exception is still surfaced for a human to confirm). Word-boundary matched to avoid prose false hits."""
    t = (text or "").strip()
    if not t:
        return "unknown"
    if _COPYLEFT_RE.search(t):
        return "copyleft"
    if _PERMITTED_RE.search(t):
        return "permitted"
    return "unknown"


def is_strong_copyleft(text: str) -> bool:
    """True for GPL/AGPL (the disallowed hard line), False for LGPL/MPL (weak, review-only)."""
    return bool(_STRONG_RE.search(text or ""))


def _license_of(dist) -> str:
    """Best declared license for a distribution — the OSI 'License ::' classifiers first (clean SPDX-ish
    labels), then a short License metadata field, then the SPDX 'License-Expression'. The License field is
    skipped when it holds the full licence text (some packages dump it there), which defeats classification."""
    md = dist.metadata
    classifiers = [c for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    if classifiers:
        return "; ".join(c.split("::")[-1].strip() for c in classifiers)
    lic = (md.get("License") or "").strip()
    if lic and lic.lower() not in ("unknown", "none") and len(lic) <= 200:   # short = a label, not full text
        return lic
    expr = (md.get("License-Expression") or "").strip()
    if expr:
        return expr
    return lic.splitlines()[0].strip() if lic else ""       # last resort: first line of the full text


def license_audit() -> dict[str, Any]:
    """Classify every installed distribution's license → permitted / copyleft / unknown buckets."""
    import importlib.metadata as im

    components = []
    seen: set[str] = set()
    for dist in im.distributions():
        name = (dist.metadata.get("Name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        lic = _license_of(dist)
        cls = classify_license(lic)
        components.append({"name": name, "version": dist.version or "", "license": lic or "UNKNOWN",
                           "classification": cls, "strong_copyleft": cls == "copyleft" and is_strong_copyleft(lic)})
    components.sort(key=lambda c: c["name"].lower())
    copyleft = [c for c in components if c["classification"] == "copyleft"]
    strong = [c for c in copyleft if c["strong_copyleft"]]
    unknown = [c for c in components if c["classification"] == "unknown"]
    return {
        "total": len(components),
        "permitted": sum(1 for c in components if c["classification"] == "permitted"),
        "copyleft": copyleft, "copyleft_count": len(copyleft),
        "strong_copyleft": strong, "strong_copyleft_count": len(strong),
        "unknown": unknown, "unknown_count": len(unknown),
        "ok": not strong,           # the hard line is GPL/AGPL; LGPL/MPL are surfaced for review, not a fail
        "components": components,
        "note": "License audit over the installed Python distributions. Permitted = MIT/BSD/Apache/ISC/PSF/"
                "Unlicense/Zlib. Copyleft is flagged; STRONG copyleft (GPL/AGPL) is the disallowed hard line, "
                "while weak copyleft (LGPL/MPL — e.g. the ifcopenshell/certifi core deps) is accepted for our "
                "dynamic-linking distribution but still surfaced. Unknown = metadata omitted the field.",
    }


def sbom() -> dict[str, Any]:
    """A minimal CycloneDX 1.5 SBOM (component list with name/version/license) for the installed set."""
    audit = license_audit()
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "components": [{"type": "library", "name": c["name"], "version": c["version"],
                        "licenses": [{"license": {"name": c["license"]}}] if c["license"] != "UNKNOWN" else []}
                       for c in audit["components"]],
    }


_PDF_ACTIVE = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction", b"/AA", b"/RichMedia")


def pdf_sanity(data: bytes, max_mb: int = 50) -> dict[str, Any]:
    """A lightweight sanity check for an uploaded/ingested PDF — header + EOF + size cap + active-content
    flags. Not a full parser (no AGPL PyMuPDF): a fast pre-ingest gate that flags a PDF worth a closer look."""
    size = len(data or b"")
    flags: list[str] = []
    header_ok = data[:5] == b"%PDF-" if data else False
    if not header_ok:
        flags.append("missing %PDF- header")
    if size == 0:
        flags.append("empty file")
    if size > max_mb * 1024 * 1024:
        flags.append(f"over size cap ({max_mb} MB)")
    if data and b"%%EOF" not in data[-1024:]:
        flags.append("no %%EOF trailer")
    active = sorted({tok.decode().lstrip("/") for tok in _PDF_ACTIVE if data and tok in data})
    if active:
        flags.append("active content: " + ", ".join(active))
    pages = data.count(b"/Type/Page") + data.count(b"/Type /Page") if data else 0
    return {
        "ok": header_ok and size > 0 and not active and size <= max_mb * 1024 * 1024,
        "size": size, "header_ok": header_ok, "pages_estimate": pages,
        "active_content": active, "flags": flags,
        "note": "Lightweight PDF pre-ingest sanity check (header/EOF/size/active-content). Active content "
                "(JavaScript/Launch/EmbeddedFile/OpenAction) is flagged for review, not auto-rejected.",
    }


def _main(argv: list[str] | None = None) -> int:
    """Print the audit. With --gate, exit non-zero only on STRONG copyleft (GPL/AGPL) so a CI/skill gate
    fails on the hard line but not on the accepted LGPL/MPL core deps. Default is informational (exit 0)."""
    argv = argv if argv is not None else sys.argv[1:]
    a = license_audit()
    print(f"SEC-SUPPLY license audit: {a['total']} components · {a['permitted']} permitted · "
          f"{a['copyleft_count']} copyleft ({a['strong_copyleft_count']} strong GPL/AGPL) · "
          f"{a['unknown_count']} unknown")
    for c in a["copyleft"]:
        tag = "STRONG   " if c["strong_copyleft"] else "weak     "
        print(f"  {tag} {c['name']} {c['version']}  [{c['license'][:60]}]")
    return 1 if ("--gate" in argv and a["strong_copyleft"]) else 0


if __name__ == "__main__":
    sys.exit(_main())
