"""Preconstruction intelligence endpoints — review an incoming contract for risky clauses, detect
scope gaps in specs/notes, and answer questions about a document with page citations. Each accepts
either an uploaded PDF (text extracted server-side) or pasted text. Stateless (no persistence)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from .. import review
from ..rbac import require_role
from ..throttle import rate_limited

router = APIRouter()

# AI review calls an LLM per request — cap tighter than normal reads (override: AEC_THROTTLE_REVIEW_RPM).
_throttle = rate_limited("review", 30)


async def _text_from(file: UploadFile | None, text: str | None) -> tuple[str, list[dict]]:
    if file is not None:
        # PDF text extraction is CPU-bound; keep it off the event loop.
        pages = await run_in_threadpool(review.extract_text, await file.read(), file.filename or "")
        return review._full_text(pages), pages
    body = text or ""
    return body, [{"page": 1, "text": body}]


@router.post("/projects/{pid}/review/contract")
async def review_contract_ep(pid: str, file: UploadFile | None = File(None),
                             text: str | None = Form(None), _: str = Depends(require_role("viewer")),
                             __: None = Depends(_throttle)):
    # review_* call the LLM (blocking network I/O via the sync SDK) — run off-loop so one review
    # doesn't stall every other request sharing this worker.
    body, _pages = await _text_from(file, text)
    return await run_in_threadpool(review.review_contract, body)


@router.post("/projects/{pid}/review/scope")
async def review_scope_ep(pid: str, file: UploadFile | None = File(None),
                          text: str | None = Form(None), _: str = Depends(require_role("viewer")),
                          __: None = Depends(_throttle)):
    body, _pages = await _text_from(file, text)
    return await run_in_threadpool(review.scope_gaps, body)


@router.post("/projects/{pid}/review/ask")
async def review_ask_ep(pid: str, question: str = Form(...), file: UploadFile | None = File(None),
                        text: str | None = Form(None), _: str = Depends(require_role("viewer")),
                        __: None = Depends(_throttle)):
    _body, pages = await _text_from(file, text)
    return await run_in_threadpool(review.ask_doc, question, pages)
