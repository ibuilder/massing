"""Drawing-sheet extraction — turn a 2D PDF set (or a pasted sheet index) into structured sheet records.

Reading actual drawings/specs into data is the AI-native move competitors lead with; here it stays
offline-first and honest. The deterministic path parses the PDF text layer (or pasted text) for sheet
numbers and titles with a transparent pattern and infers the discipline from the sheet prefix — it never
invents a sheet. When ANTHROPIC_API_KEY is set the extraction can be enriched by the model, but the
fallback already produces a usable sheet index that can bulk-create drawing records."""
from __future__ import annotations

import re
from typing import Any

# Sheet-number prefix -> discipline (AIA/US-CAD convention). Longest prefixes first.
DISCIPLINE = {
    "AD": "Architectural", "SK": "Sketch", "ID": "Interiors", "FP": "Fire Protection",
    "FA": "Fire Alarm", "LS": "Life Safety", "A": "Architectural", "S": "Structural",
    "M": "Mechanical", "E": "Electrical", "P": "Plumbing", "C": "Civil", "L": "Landscape",
    "G": "General", "T": "Telecom", "Q": "Equipment", "FS": "Food Service",
}
# A sheet number: 1-2 letter discipline + optional dash + 2-4 digits (+ optional suffix letter).
_SHEET_RE = re.compile(r"\b([A-Z]{1,2})[-\.]?(\d{2,4}[A-Z]?)\b")


def _discipline(prefix: str) -> str:
    return DISCIPLINE.get(prefix.upper(), DISCIPLINE.get(prefix[:1].upper(), "General"))


def extract_from_text(text: str, *, max_sheets: int = 1000) -> list[dict[str, Any]]:
    """Parse a sheet index / drawing-list text blob into [{number, title, discipline}]. One sheet per
    line where a sheet number is found; the rest of the line (cleaned) becomes the title. Deduped by
    number, first title wins."""
    seen: dict[str, dict] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SHEET_RE.search(line)
        if not m:
            continue
        number = f"{m.group(1).upper()}-{m.group(2).upper()}"
        # title = the line minus the matched number, trimmed of separators/dot leaders
        title = (line[:m.start()] + " " + line[m.end():]).strip()
        title = re.sub(r"[.\-_\s]{2,}", " ", title).strip(" .-_\t")
        if number not in seen:
            seen[number] = {"number": number, "title": title[:200], "discipline": _discipline(m.group(1))}
        if len(seen) >= max_sheets:
            break
    # order by discipline then number for a tidy index
    return sorted(seen.values(), key=lambda s: (s["discipline"], s["number"]))


def extract_pdf(pdf_bytes: bytes, *, max_pages: int = 30) -> dict[str, Any]:
    """Extract a sheet index from a PDF's text layer. Returns sheets + the method used (image-only
    scans with no text layer yield nothing deterministically — the caller can fall back to AI)."""
    text = ""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages[:max_pages]:
            text += "\n" + (page.extract_text() or "")
    except Exception as e:                             # noqa: BLE001 — a bad PDF shouldn't 500
        return {"sheets": [], "method": "error", "pages": 0, "error": str(e)[:200]}
    sheets = extract_from_text(text)
    return {
        "sheets": sheets, "method": "deterministic",
        "has_text_layer": bool(text.strip()),
        "note": ("Parsed the PDF text layer for sheet numbers + titles." if sheets
                 else "No sheet numbers found in the text layer — this may be an image-only scan; "
                      "set ANTHROPIC_API_KEY to extract from page images."),
    }


def to_drawing_records(sheets: list[dict]) -> list[dict]:
    """Map extracted sheets to `drawing` module create bodies (number is the required key)."""
    out = []
    for s in sheets:
        out.append({"number": s["number"], "title": s.get("title") or "",
                    "discipline": s.get("discipline") or "General", "sheet_number": s["number"]})
    return out
