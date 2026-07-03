"""AI drafting endpoints — turn a note or a source document into an editable first-draft RFI, submittal
summary, or trade scope of work. Stateless: returns a draft the user reviews before creating a record
(the web app POSTs the accepted draft to the normal module-create endpoint). Each accepts an uploaded
PDF (text extracted per page for citations) or pasted text."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from .. import drafting
from ..rbac import require_role
from ..throttle import rate_limited

router = APIRouter()

# AI drafting calls an LLM per request (override: AEC_THROTTLE_DRAFT_RPM).
_throttle = rate_limited("draft", 30)


async def _pages_from(file: UploadFile | None, text: str | None) -> list[dict]:
    if file is not None:
        data = await file.read()
        return await run_in_threadpool(drafting.extract_text, data, file.filename or "")
    body = text or ""
    return [{"page": 1, "text": body}] if body else []


@router.post("/projects/{pid}/draft/rfi")
async def draft_rfi_ep(pid: str, note: str = Form(""), file: UploadFile | None = File(None),
                       text: str | None = Form(None), _: str = Depends(require_role("reviewer")),
                       __: None = Depends(_throttle)):
    pages = await _pages_from(file, text)
    return await run_in_threadpool(drafting.draft_rfi, note, pages)


@router.post("/projects/{pid}/draft/submittal-summary")
async def draft_submittal_ep(pid: str, file: UploadFile | None = File(None),
                             text: str | None = Form(None), _: str = Depends(require_role("reviewer")),
                             __: None = Depends(_throttle)):
    pages = await _pages_from(file, text)
    return await run_in_threadpool(drafting.summarize_submittal, pages)


@router.post("/projects/{pid}/draft/scope")
async def draft_scope_ep(pid: str, trade: str = Form("General"), file: UploadFile | None = File(None),
                         text: str | None = Form(None), _: str = Depends(require_role("reviewer")),
                         __: None = Depends(_throttle)):
    pages = await _pages_from(file, text)
    return await run_in_threadpool(drafting.draft_scope, pages, trade)
