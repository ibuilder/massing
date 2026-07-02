"""Preconstruction intelligence endpoints — review an incoming contract for risky clauses, detect
scope gaps in specs/notes, and answer questions about a document with page citations. Each accepts
either an uploaded PDF (text extracted server-side) or pasted text. Stateless (no persistence)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from .. import review
from ..rbac import require_role

router = APIRouter()


async def _text_from(file: UploadFile | None, text: str | None) -> tuple[str, list[dict]]:
    if file is not None:
        pages = review.extract_text(await file.read(), file.filename or "")
        return review._full_text(pages), pages
    body = text or ""
    return body, [{"page": 1, "text": body}]


@router.post("/projects/{pid}/review/contract")
async def review_contract_ep(pid: str, file: UploadFile | None = File(None),
                             text: str | None = Form(None), _: str = Depends(require_role("viewer"))):
    body, _pages = await _text_from(file, text)
    return review.review_contract(body)


@router.post("/projects/{pid}/review/scope")
async def review_scope_ep(pid: str, file: UploadFile | None = File(None),
                          text: str | None = Form(None), _: str = Depends(require_role("viewer"))):
    body, _pages = await _text_from(file, text)
    return review.scope_gaps(body)


@router.post("/projects/{pid}/review/ask")
async def review_ask_ep(pid: str, question: str = Form(...), file: UploadFile | None = File(None),
                        text: str | None = Form(None), _: str = Depends(require_role("viewer"))):
    _body, pages = await _text_from(file, text)
    return review.ask_doc(question, pages)
