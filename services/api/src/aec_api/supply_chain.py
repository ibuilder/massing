"""SEC-SUPPLY (R16 Tier-3) — supply-chain hardening, deterministic and dependency-free.

Three cherry-picked, offline pieces (this does *not* replace CodeQL or the esc() XSS discipline):

- **license audit** — walk the installed Python distributions (``importlib.metadata``, stdlib) and classify
  each declared license as **permitted** (MIT / BSD / Apache / ISC / PSF / Unlicense / Zlib / CC0 /
  BSL-1.0 — the project's standing constraint) · **copyleft** (GPL / AGPL / LGPL / MPL / EPL / CDDL /
  EUPL — disallowed) · unknown.
  Mechanically enforces the no-AGPL rule instead of relying on review. ``python -m aec_api.supply_chain``
  prints the audit; with ``--gate`` it exits non-zero on **strong** copyleft (GPL/AGPL) that is not
  declared in :data:`SHIP_EXCLUDED` — usable as a CI/skill gate.

  **This sentence used to say "exits non-zero if any copyleft component is found", and both halves
  were wrong** — weak copyleft never failed it, and strong copyleft failed it even when purged from
  every artifact. The second error was the expensive one: `bcf-client` (GPLv3, an unconditional
  requirement of the LGPL `ifctester` we do need) has been in `SHIP_EXCLUDED` and purged by the
  container since it was found, so `--gate` exited 1 on a correct, policy-compliant tree — every
  time, for anyone following the hardening runbook that says to run it before a release. `--gate`
  and `test_license_gate.py` are two enforcement paths for ONE policy and they disagreed, with the
  test right and the CLI wrong. **A permanently red gate gets switched off** — this module's own
  audit note says so about weak copyleft, and then the strong path acquired the same defect.
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
# CC0-1.0 and BSL-1.0 added 2026-08-10 on the owner's instruction. CC0 was already SHIPPING — 59
# files under services/data/families/external/ declare it — so the written rule was narrower than
# reality; it is a public-domain dedication, strictly more permissive than MIT.
#
# **BSL-1.0 is the Boost Software License** — permissive, MIT-like, no copyleft. **BUSL-1.1 is the
# Business Source License** — source-available, NOT open source, and not permitted. One letter
# apart, opposite ends of the spectrum, so the pairing is worth stating even though the pattern
# turns out to separate them easily.
#
# *This comment said, at length and with confidence, that `\b` was what kept BUSL out. It is not.*
# "BUSL" is B-U-S-L and does not contain the substring "bsl" at all, so even a bare `bsl`
# alternative cannot match it — a mutation removing the anchors left every BUSL test passing, which
# is how the claim was caught. The anchors stay for the same reason every other alternative here
# carries them (prose hits inside longer words: the "EXEMPLARY"/"mpl" case in the line above), not
# because BUSL depends on them. Recorded rather than quietly reworded, because a wrong explanation
# beside correct code is the kind of thing the next reader believes.
_PERMITTED_RE = re.compile(r"\bmit\b|\bbsd\b|apache|\bisc\b|python software foundation|\bpsf\b|"
                           r"unlicense|public domain|\bzlib\b|\b0bsd\b|\bwtfpl\b|"
                           r"\bcc0\b|creative commons zero|\bbsl\b|boost software", re.I)
_COPYLEFT_RE = re.compile(r"\b[al]?gpl|\bmpl\b|mozilla public|\bepl\b|eclipse public|\bcddl\b|\beupl\b|"
                          r"affero|copyleft|gnu (lesser|general|affero)", re.I)
_STRONG_RE = re.compile(r"\ba?gpl|affero", re.I)   # GPL/AGPL — matches gplv3/agpl, NOT lgpl


def classify_license(text: str) -> str:
    """permitted / copyleft / unknown for a declared license string.

    **A package offering a permitted licence AMONG SEVERAL is permitted** — that is what dual
    licensing means: the recipient chooses, and we choose the permissive one. `odfpy` declares
    "Apache **or** GPL **or** LGPL" and copyleft-wins-ties classified it as copyleft, which is simply
    wrong; it would have had us excluding a dependency we are entitled to use under Apache.

    The distinction that keeps this honest is *whether a permitted option is actually on offer*.
    PyMuPDF declares "AGPL 3.0 **or** Artifex Commercial" — also a choice, but the only free option is
    AGPL, and a commercial licence is not in the permitted set, so it stays copyleft. Correct in both
    directions, which a blanket "any permitted mention wins" rule would not be.

    Where no permitted alternative is offered, copyleft still wins the tie: a GPL-with-linking-exception
    is surfaced for a human rather than quietly accepted. Word-boundary matched to avoid prose hits.
    """
    t = (text or "").strip()
    if not t:
        return "unknown"
    copyleft, permitted = bool(_COPYLEFT_RE.search(t)), bool(_PERMITTED_RE.search(t))
    if copyleft and permitted:
        return "permitted"          # a choice is offered and we take the permissive one
    if copyleft:
        return "copyleft"
    if permitted:
        return "permitted"
    return "unknown"


def is_dual_licensed(text: str) -> bool:
    """True when both a permitted and a copyleft option are declared — reported, not hidden.

    Worth surfacing separately from a plain permitted result: the classification depends on a choice
    somebody made, and if the upstream ever drops the permissive option the answer changes silently.
    """
    t = (text or "").strip()
    return bool(_COPYLEFT_RE.search(t)) and bool(_PERMITTED_RE.search(t))


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


# ---------------------------------------------------------------------------------------------------
# What must NOT ship, declared ONCE.
#
# A dependency can be necessary to *install* and still be something we must not distribute — a
# permissively-licensed library can require a copyleft one it only uses on a path we never take.
# Hard-coding the remedy in each build file solves exactly one package: the next transitive arrival
# needs somebody to remember the PyInstaller specs and the Dockerfile all over again, and the failure
# is silent because a shipped artifact does not announce what is inside it.
#
# So the list lives here and everything else derives from it:
#   * `desktop.spec` / `sidecar.spec` read `excluded_import_names()` for PyInstaller's `excludes`;
#   * the container runs `python -m aec_api.supply_chain --purge` after installing;
#   * `test_license_gate` asserts every strong-copyleft package in the shipped closure is either in
#     here or explicitly accepted, so finding one and forgetting to act on it fails a build.
#
# Adding an exclusion is one line. Keys are distribution names; `import_name` is what PyInstaller
# needs (they differ — `bcf-client` installs the module `bcf`).
SHIP_EXCLUDED: dict[str, dict[str, str]] = {
    "bcf-client": {
        "import_name": "bcf",
        "why": "GPLv3. An unconditional requirement of `ifctester` (LGPLv3, which is fine and which "
               "we do need), but it backs ifctester's BCF *reporter* and we import only "
               "`ifctester.ids` — verified to load zero bcf modules. Our own BCF handling is "
               "`bcf_io.py`. Installed so ifctester's metadata is satisfied; excluded from every "
               "artifact so no GPLv3 is distributed.",
    },
}


def excluded_import_names() -> list[str]:
    """Module names the packagers must leave out. Read by `desktop.spec` and `sidecar.spec`."""
    return sorted(v["import_name"] for v in SHIP_EXCLUDED.values())


def excluded_distributions() -> list[str]:
    """Distribution names the container removes after install. Read by `--purge`."""
    return sorted(SHIP_EXCLUDED)


def purge_excluded(*, dry_run: bool = False) -> dict[str, Any]:
    """Uninstall everything in `SHIP_EXCLUDED`. Idempotent — absent is success, not an error.

    Deliberately tolerant: the image may be rebuilt from a lock that no longer pins the package, and
    a build that fails because there was nothing to remove would be a build failing for succeeding.
    """
    import subprocess

    removed, absent = [], []
    for dist in excluded_distributions():
        try:
            import importlib.metadata as im
            im.distribution(dist)
        except Exception:                                    # noqa: BLE001 — not installed is fine
            absent.append(dist)
            continue
        if dry_run:
            removed.append(dist)
            continue
        r = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", dist],  # noqa: S603
                           capture_output=True, text=True, check=False)
        (removed if r.returncode == 0 else absent).append(dist)
    return {"removed": removed, "absent": absent, "declared": excluded_distributions(),
            "note": "Excluded from the shipped artifact — see SHIP_EXCLUDED for why each is listed."}


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


# --- SEC-SUPPLY: the MCP tool-poisoning self-audit --------------------------------------------------
# "Tool poisoning" = hostile instructions smuggled into an MCP tool's name/description, which agents
# read as trusted context. We audit OUR OWN catalog for the known smuggling shapes so a poisoned tool
# (a bad merge, a compromised dependency regenerating the catalog) surfaces instead of shipping.
# Written as ESCAPES, never as the characters themselves. This class used to contain the literal
# code points, so the line rendered as `re.compile("[-]")` to every reader — the one place in the
# codebase where invisible characters ARE the threat model was the one place you could not review.
# It also meant the class could be narrowed in a diff that looks identical to the eye, disabling
# this control invisibly, which is the attack the file exists to catch. bandit B613 flagged it HIGH
# and the report is non-blocking, so nothing acted on it.
#
# Reading it as escapes is what exposed the real gap: the old class covered zero-width and joiner
# characters but NONE of the bidi controls — including U+202E RLO, the primary Trojan Source
# primitive (CVE-2021-42574). Those are the ones that matter most here: they make a string RENDER
# differently from its bytes, so an agent reads the smuggled instruction while a human reviewing
# the tool description sees innocuous text. Verified: a description containing U+202E passed.
_INVISIBLE = re.compile(
    "["
    "\u00ad"              # SOFT HYPHEN
    "\u061c"              # ARABIC LETTER MARK
    "\u200b-\u200f"       # ZWSP, ZWNJ, ZWJ, LRM, RLM
    "\u202a-\u202e"       # LRE, RLE, PDF, LRO, RLO  <- Trojan Source overrides
    "\u2060-\u2064"       # WORD JOINER, invisible operators
    "\u2066-\u2069"       # LRI, RLI, FSI, PDI       <- Trojan Source isolates
    "\ufeff"              # ZERO WIDTH NO-BREAK SPACE / BOM
    "]")
_INJECTION = re.compile(
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions|"
    r"system\s+prompt|do\s+not\s+tell\s+the\s+user|"
    r"<\s*(system|assistant)\s*>|<!--|"
    r"exfiltrat|send\s+(the\s+)?(api\s+key|credentials|token)", re.IGNORECASE)
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{60,}={0,2}")
_URL = re.compile(r"https?://", re.IGNORECASE)


def mcp_tool_audit() -> dict[str, Any]:
    """Scan the MCP tool catalog (names, descriptions, schema descriptions) for poisoning shapes:
    invisible unicode, injection phrasing, HTML/system-tag smuggling, long base64 runs, and URLs
    (a tool description has no business linking out). Deterministic; findings carry a snippet."""
    from . import mcp_tools

    def _texts(tool: dict) -> list[tuple[str, str]]:
        out = [("name", str(tool.get("name") or "")), ("description", str(tool.get("description") or ""))]
        props = ((tool.get("input_schema") or {}).get("properties") or {})
        for pname, p in props.items():
            if isinstance(p, dict) and p.get("description"):
                out.append((f"param:{pname}", str(p["description"])))
        return out

    findings: list[dict[str, Any]] = []
    tools = mcp_tools.TOOLS
    for tool in tools:
        for where, text in _texts(tool):
            for kind, rx, sev in (("invisible_unicode", _INVISIBLE, "high"),
                                  ("injection_phrase", _INJECTION, "high"),
                                  ("base64_blob", _B64_RUN, "medium"),
                                  ("url_in_description", _URL, "medium")):
                m = rx.search(text)
                if m:
                    findings.append({"tool": tool.get("name"), "where": where, "kind": kind,
                                     "severity": sev,
                                     "snippet": text[max(0, m.start() - 20):m.end() + 20][:120]})
    return {"tools_scanned": len(tools), "findings": findings, "clean": not findings,
            "note": "Self-audit of the MCP catalog for tool-poisoning shapes (invisible unicode, "
                    "injection phrasing, tag/comment smuggling, base64 blobs, outbound URLs)."}


def _main(argv: list[str] | None = None) -> int:
    """Print the audit. With --gate, exit non-zero only on STRONG copyleft (GPL/AGPL) that is NOT in
    SHIP_EXCLUDED — so the gate fails on the hard line, but not on the accepted LGPL/MPL core deps and
    not on a package that `--purge` removes from every artifact. Default is informational (exit 0).
    With `mcp-audit`, run the MCP tool-poisoning self-audit instead (always exit 0 — non-gating; add
    --gate to fail on any high-severity finding)."""
    argv = argv if argv is not None else sys.argv[1:]
    if "mcp-audit" in argv:
        r = mcp_tool_audit()
        print(f"SEC-SUPPLY MCP self-audit: {r['tools_scanned']} tools scanned · "
              f"{len(r['findings'])} finding(s)")
        for f in r["findings"]:
            print(f"  {f['severity'].upper():6} {f['tool']}.{f['where']} [{f['kind']}]: {f['snippet']!r}")
        highs = [f for f in r["findings"] if f["severity"] == "high"]
        return 1 if ("--gate" in argv and highs) else 0
    if "--purge" in argv:
        # Used by the container after `pip install`: remove what must not be distributed.
        out = purge_excluded(dry_run="--dry-run" in argv)
        for d in out["removed"]:
            print(f"purged (excluded from artifact): {d}")
        for d in out["absent"]:
            print(f"not installed, nothing to purge: {d}")
        return 0

    a = license_audit()
    print(f"SEC-SUPPLY license audit: {a['total']} components · {a['permitted']} permitted · "
          f"{a['copyleft_count']} copyleft ({a['strong_copyleft_count']} strong GPL/AGPL) · "
          f"{a['unknown_count']} unknown")
    # A strong-copyleft package that is DECLARED IN `SHIP_EXCLUDED` is purged from every artifact by
    # `--purge` (the container does this after `pip install`), so it is installed here and shipped
    # nowhere. Saying so on the line itself is the point: the previous output tagged it `STRONG` with
    # no further comment, which reads as an unaddressed violation of the project's hardest licence
    # rule and sent at least one reader hunting for a breach that had been handled a release earlier.
    excluded = {k.lower() for k in SHIP_EXCLUDED}
    for c in a["copyleft"]:
        if not c["strong_copyleft"]:
            tag = "weak     "
        elif c["name"].lower() in excluded:
            tag = "STRONG*  "
        else:
            tag = "STRONG   "
        print(f"  {tag} {c['name']} {c['version']}  [{c['license'][:60]}]")
    blocking = [c for c in a["strong_copyleft"] if c["name"].lower() not in excluded]
    if any(c["strong_copyleft"] and c["name"].lower() in excluded for c in a["copyleft"]):
        print("  * STRONG copyleft, but declared in SHIP_EXCLUDED and removed from every artifact "
              "by `--purge` — installed, never distributed. See SHIP_EXCLUDED for the reason.")
    if "--gate" in argv:
        print("GATE FAIL: " + ", ".join(c["name"] for c in blocking) if blocking
              else "GATE OK: no strong copyleft is distributed.")
    return 1 if ("--gate" in argv and blocking) else 0


if __name__ == "__main__":
    sys.exit(_main())
