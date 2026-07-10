"""PDF manipulation — merge / split / rotate / extract / info — via **pypdf** (BSD; NO PyMuPDF/AGPL).

Server-side heavy lifting for the PDF markup stack: combine a drawing set into one file, pull a page
range, rotate scanned sheets. Pure byte-in / byte-out; nothing touches the DB. Kept deliberately to
permissively-licensed pypdf so the product stays cleanly proprietary-licensable (see the pdf-markup
plan) — true redaction/OCR (which would need PyMuPDF/AGPL) are intentionally out of scope."""
from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter


def info(data: bytes) -> dict:
    """Page count + basic flags for an uploaded PDF."""
    r = PdfReader(io.BytesIO(data))
    return {"pages": len(r.pages), "encrypted": bool(r.is_encrypted)}


def merge(files: list[bytes]) -> bytes:
    """Concatenate several PDFs into one, in order."""
    w = PdfWriter()
    for data in files:
        for pg in PdfReader(io.BytesIO(data)).pages:
            w.add_page(pg)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def split(data: bytes) -> list[bytes]:
    """One single-page PDF per page of the input."""
    out: list[bytes] = []
    for pg in PdfReader(io.BytesIO(data)).pages:
        w = PdfWriter()
        w.add_page(pg)
        b = io.BytesIO()
        w.write(b)
        out.append(b.getvalue())
    return out


def extract(data: bytes, pages: list[int]) -> bytes:
    """A new PDF of just the given 1-based page numbers (out-of-range pages are skipped)."""
    r = PdfReader(io.BytesIO(data))
    n = len(r.pages)
    w = PdfWriter()
    for p in pages:
        if 1 <= p <= n:
            w.add_page(r.pages[p - 1])
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def rotate(data: bytes, angle: int, pages: list[int] | None = None) -> bytes:
    """Rotate pages by `angle` (rounded to a multiple of 90). `pages` (1-based) limits the rotation;
    None rotates all."""
    a = round((angle % 360) / 90) * 90 % 360
    r = PdfReader(io.BytesIO(data))
    w = PdfWriter()
    for i, pg in enumerate(r.pages, 1):
        if a and (pages is None or i in pages):
            pg.rotate(a)
        w.add_page(pg)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def zip_bytes(files: list[bytes], stem: str = "page") -> bytes:
    """Zip a list of PDF byte blobs as page-01.pdf … (for the split endpoint)."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, b in enumerate(files, 1):
            z.writestr(f"{stem}-{i:02d}.pdf", b)
    return buf.getvalue()


def parse_pages(spec: str | None) -> list[int]:
    """'1,3,5-7' -> [1,3,5,6,7]. Empty/invalid parts are skipped."""
    out: list[int] = []
    for part in (spec or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            except ValueError:
                continue
        elif part.isdigit():
            out.append(int(part))
    return out
