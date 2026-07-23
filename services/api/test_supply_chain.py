"""SEC-SUPPLY — license audit (permitted / copyleft / strong-copyleft classification, word-boundary
matched) + a CycloneDX SBOM + a lightweight uploaded-PDF sanity check.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_supply_chain.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_supply_chain.db"
os.environ["STORAGE_DIR"] = "./test_storage_supply"

from aec_api import supply_chain as sc  # noqa: E402

# --- classification (word-boundary, not naive substring) -------------------------------------------
assert sc.classify_license("MIT License") == "permitted"
assert sc.classify_license("BSD-3-Clause") == "permitted"
assert sc.classify_license("Apache Software License; Apache-2.0") == "permitted"
assert sc.classify_license("GNU General Public License v3 (GPLv3)") == "copyleft"
assert sc.classify_license("GNU Lesser General Public License v3 or later (LGPLv3+)") == "copyleft"
assert sc.classify_license("Mozilla Public License 2.0 (MPL 2.0)") == "copyleft"
assert sc.classify_license("") == "unknown"
assert sc.classify_license("Proprietary") == "unknown"
# the bug fix: a raw BSD licence text containing "EXEMPLARY" must NOT match "mpl" → not copyleft
bsd_text = ("Redistribution and use ... THIS SOFTWARE IS PROVIDED ... EXEMPLARY, OR CONSEQUENTIAL "
            "DAMAGES ... ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE.")
assert sc.classify_license(bsd_text) != "copyleft", "EXEMPLARY must not false-match mpl"

# strong (GPL/AGPL) vs weak (LGPL/MPL)
assert sc.is_strong_copyleft("GPLv3") and sc.is_strong_copyleft("GNU AFFERO GPL 3.0")
assert not sc.is_strong_copyleft("LGPLv3+") and not sc.is_strong_copyleft("MPL-2.0")
assert not sc.is_strong_copyleft("MIT License")

# --- audit over the real installed set: structure + internal consistency ---------------------------
a = sc.license_audit()
assert a["total"] > 0 and len(a["components"]) == a["total"], a["total"]
assert a["copyleft_count"] == len(a["copyleft"]) and a["strong_copyleft_count"] == len(a["strong_copyleft"])
assert all(c["strong_copyleft"] for c in a["strong_copyleft"]), a["strong_copyleft"]
assert a["ok"] == (a["strong_copyleft_count"] == 0)         # the gate hinges on strong copyleft only
assert all(set(c) >= {"name", "version", "license", "classification"} for c in a["components"])

# --- SBOM shape (CycloneDX 1.5) --------------------------------------------------------------------
b = sc.sbom()
assert b["bomFormat"] == "CycloneDX" and b["specVersion"] == "1.5", b
assert b["components"] and all(c["type"] == "library" and c["name"] for c in b["components"]), b["components"][:2]

# --- PDF sanity check ------------------------------------------------------------------------------
clean = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n2 0 obj<</Type/Page>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
r = sc.pdf_sanity(clean)
assert r["ok"] and r["header_ok"] and not r["active_content"], r
assert r["pages_estimate"] == 1, r

evil = b"%PDF-1.4\n1 0 obj<</OpenAction<</S/JavaScript/JS(app.alert(1))>>>>endobj\n%%EOF"
r2 = sc.pdf_sanity(evil)
assert not r2["ok"] and "JavaScript" in r2["active_content"] and "OpenAction" in r2["active_content"], r2

assert sc.pdf_sanity(b"not a pdf")["header_ok"] is False
assert "empty file" in sc.pdf_sanity(b"")["flags"]
assert "over size cap (1 MB)" in sc.pdf_sanity(b"%PDF-1.4" + b"0" * (2 * 1024 * 1024) + b"%%EOF", max_mb=1)["flags"]

# --- the CLI gate: informational by default (exit 0), fails only on --gate with strong copyleft -----
assert sc._main([]) == 0, "default run is informational"

print("SEC-SUPPLY OK - license audit classifies the installed distributions permitted / copyleft (word-"
      "boundary matched, so a BSD text's 'EXEMPLARY' no longer false-matches 'mpl'), splitting STRONG "
      "GPL/AGPL (the disallowed hard line) from weak LGPL/MPL (the accepted ifcopenshell/certifi core deps); "
      "emits a CycloneDX 1.5 SBOM; and the PDF sanity check passes a clean 1-page PDF, flags JavaScript + "
      "OpenAction active content, and rejects a non-PDF / empty / oversized file. The CLI gate is "
      "informational by default and fails only with --gate on strong copyleft.")
