"""W9-4 (harder half) — spec/code DOCUMENT TEXT ingestion → cited NL answers.

The doc-graph links elements to spec sections and sheets; this closes the loop to the documents'
own words: ingest a specification / code-commentary / report (PDF or plain text), split it into
**cited chunks** (spec-section headers like "SECTION 09 21 16", numbered headings, page breaks),
and answer questions **extractively with citations** — every snippet names its document, section,
and page. Deterministic retrieval (token overlap with section-header boosting), fully offline; no
LLM required and none silently invoked. The answer is the source's own text, never a paraphrase —
so a superintendent quoting it on an RFI is quoting the spec, not the tool.

Storage: `{pid}/doctext/{doc_id}.json` (chunks) + `{pid}/doctext/index.json` (catalog).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import storage

_SECTION_RE = re.compile(r"^\s*(?:SECTION\s+)?(\d{2}\s?\d{2}\s?\d{2}|\d+(?:\.\d+)+)\s*[–—-]?\s*(.{0,80})$",
                         re.IGNORECASE)
_PAGE_RE = re.compile(r"\f")
_WORD_RE = re.compile(r"[a-z0-9]{2,}")
_STOP = {"the", "and", "for", "with", "shall", "all", "are", "not", "this", "that", "will",
         "any", "per", "from", "have", "has", "been", "its", "may", "each", "other"}


def _key(pid: str, name: str) -> str:
    return f"{pid}/doctext/{name}"


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP}


def extract_pdf_text(data: bytes) -> str:
    """Page texts joined with form-feeds (so page numbers survive chunking). pypdf (permissive)."""
    import io

    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def chunk_text(text: str) -> list[dict]:
    """Split document text into cited chunks: a new chunk at each spec-section / numbered heading;
    page numbers tracked via form-feed breaks. Headerless documents fall back to paragraph blocks."""
    chunks: list[dict] = []
    cur: dict | None = None
    page = 1
    blank_run = 0
    for raw_line in text.splitlines():
        page += raw_line.count("\f")
        line = raw_line.replace("\f", "").rstrip()
        m = _SECTION_RE.match(line) if line else None
        if m and len(line) < 100:
            if cur and cur["text"].strip():
                chunks.append(cur)
            cur = {"section": m.group(1).strip(), "title": (m.group(2) or "").strip(" -–—"),
                   "page": page, "text": ""}
            blank_run = 0
            continue
        if cur is None:
            cur = {"section": None, "title": None, "page": page, "text": ""}
        if not line:
            blank_run += 1
            # headerless docs: a double blank line closes a paragraph chunk (keeps citations tight)
            if blank_run >= 2 and cur["section"] is None and len(cur["text"]) > 200:
                chunks.append(cur)
                cur = {"section": None, "title": None, "page": page, "text": ""}
                blank_run = 0
            continue
        blank_run = 0
        cur["text"] += line + "\n"
    if cur and cur["text"].strip():
        chunks.append(cur)
    for i, c in enumerate(chunks):
        c["id"] = i
        c["text"] = c["text"].strip()[:4000]
        c["tokens"] = sorted(_tokens(c["text"] + " " + (c["title"] or "")))
    return [c for c in chunks if c["text"]]


def _load_index(pid: str) -> list[dict]:
    key = _key(pid, "index.json")
    if not storage.exists(key):
        return []
    try:
        data = json.loads(storage.get(key))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — a corrupt catalog lists empty; re-ingest restores it
        return []


def ingest(pid: str, name: str, text: str | None = None, pdf_bytes: bytes | None = None) -> dict:
    """Ingest one document (plain text, or a PDF via pypdf). Re-ingesting a name replaces it."""
    if pdf_bytes is not None:
        text = extract_pdf_text(pdf_bytes)
    if not (text or "").strip():
        raise ValueError("no text to ingest — supply text or a text-bearing PDF")
    doc_id = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:60]
    if not doc_id:
        raise ValueError("a document needs a name")
    chunks = chunk_text(text or "")
    if not chunks:
        raise ValueError("the document produced no usable text chunks")
    storage.put(_key(pid, f"{doc_id}.json"), json.dumps(chunks).encode())
    entries = [e for e in _load_index(pid) if e.get("doc_id") != doc_id]
    entry = {"doc_id": doc_id, "name": name.strip(), "chunks": len(chunks),
             "sections": sum(1 for c in chunks if c.get("section")),
             "ingested_at": datetime.now(timezone.utc).isoformat()}
    entries.append(entry)
    storage.put(_key(pid, "index.json"), json.dumps(entries).encode())
    return entry


def catalog(pid: str) -> dict:
    return {"documents": _load_index(pid)}


def search(pid: str, query: str, k: int = 5) -> list[dict]:
    """Top-k chunks across every ingested document — token-overlap score, section-number and title
    matches boosted (asking "09 21 16" must surface that section first)."""
    q_tokens = _tokens(query)
    q_secs = re.findall(r"\d{2}\s?\d{2}\s?\d{2}|\d+(?:\.\d+)+", query)
    hits: list[dict] = []
    for e in _load_index(pid):
        key = _key(pid, f"{e['doc_id']}.json")
        if not storage.exists(key):
            continue
        for c in json.loads(storage.get(key)):
            score = len(q_tokens & set(c.get("tokens") or []))
            sec = (c.get("section") or "").replace(" ", "")
            if sec and any(s.replace(" ", "") == sec for s in q_secs):
                score += 25
            if c.get("title") and q_tokens & _tokens(c["title"]):
                score += 3
            if score > 0:
                hits.append({"doc": e["name"], "doc_id": e["doc_id"], "section": c.get("section"),
                             "title": c.get("title"), "page": c.get("page"), "score": score,
                             "snippet": c["text"][:500]})
    hits.sort(key=lambda h: -h["score"])
    return hits[:max(1, k)]


def answer(pid: str, question: str) -> dict:
    """A cited, extractive answer: the best chunk's own text plus the supporting citations. When
    nothing matches, it says so — it never fabricates a source."""
    hits = search(pid, question, k=4)
    if not hits:
        return {"question": question, "answer": None,
                "citations": [],
                "note": "no ingested document covers this — ingest the spec/report first "
                        "(POST /doctext with a PDF or text)"}
    best = hits[0]
    where = f"{best['doc']}" + (f" §{best['section']}" if best["section"] else "") \
        + (f" ({best['title']})" if best.get("title") else "") + f", p.{best['page']}"
    return {"question": question,
            "answer": best["snippet"],
            "answered_from": where,
            "citations": [{"doc": h["doc"], "section": h["section"], "title": h.get("title"),
                           "page": h["page"], "snippet": h["snippet"][:200]} for h in hits],
            "note": "extractive — the answer is the document's own text (deterministic retrieval, "
                    "no paraphrase)"}
