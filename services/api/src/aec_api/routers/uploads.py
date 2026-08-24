"""R41-UPLOAD-WARK — the resumable upload handshake.

An IFC revision is large and mostly identical to the one before it. Today every upload is a single
multipart POST, so a model that changed in one storey costs a full transfer, and a connection that
drops at 90% costs all of it again. This is the three-request protocol that fixes both:

    POST  /projects/{pid}/uploads/handshake              -> {upload_id, chunk_size, need: [...]}
    PUT   /projects/{pid}/uploads/{uid}/chunk/{index}    -> {stored: true}
    POST  /projects/{pid}/uploads/{uid}/complete         -> {key, bytes}

**Resuming is not a code path.** The upload id is derived from the content (see `resumable.py`), so a
client that lost its connection re-handshakes with the same file, gets the same id, and is told which
chunks are still missing. Starting and resuming are the same request; the second one just gets a
shorter list. Deduplication falls out of the same fact — an unchanged re-upload needs nothing and
completes without transferring a byte.

**Every chunk is verified on arrival, against the hash the manifest promised.** That is deliberately
earlier than it needs to be: the alternative is to hash the assembled object at the end, which detects
the same corruption but only after the whole transfer, and cannot say *which* chunk was wrong. A
refusal here names the upload, the chunk index and the size received, so a client can retry ONE chunk
instead of the whole upload. Corruption is caught before IFC-to-Fragments conversion ever runs on it.

**The assembled size is checked against the bytes actually written, never the declared size.** The
declared size is a claim by an untrusted caller; it is checked at the handshake so an oversized upload
is refused before any transfer, and checked *again* at assembly against reality.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import resumable, storage
from ..db import get_db
from ..models import Project
from ..rbac import require_role
from ..resumable import MAX_UPLOAD_BYTES

router = APIRouter()
_log = logging.getLogger("aec.uploads")


def assembled_key(pid: str, uid: str) -> str:
    """Where the finished object lives. Deduplication and completion both key off this."""
    return f"projects/{pid}/uploads/{uid}"


def _project(db: Session, pid: str) -> None:
    """404 for an unknown project, before any chunk is accepted or any key is derived from `pid`."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")


@router.post("/projects/{pid}/uploads/handshake")
def handshake(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
              _: str = Depends(require_role("editor"))) -> dict:
    """Begin — or resume — an upload. Same request either way.

    Takes `{size, chunk_hashes: [sha256, ...], filename?}` and answers with the upload id, the chunk
    size the client must use, and the indices still needed. `need: []` means the server already holds
    every chunk: the client can go straight to `complete`, which is the deduplication case.
    """
    _project(db, pid)
    try:
        chunk, hashes = resumable.validate_manifest(
            body.get("size"), body.get("chunk_hashes"), MAX_UPLOAD_BYTES)
    except ValueError as e:
        # 422 rather than 400: the request is well-formed JSON that describes an upload we will not
        # accept, and the message says exactly which part of the manifest is wrong.
        raise HTTPException(422, str(e)) from None

    uid = resumable.upload_id(pid, int(body["size"]), hashes)

    # DEDUPLICATION happens here, against the ASSEMBLED object — not against the chunks.
    #
    # `complete` deletes the parts once it has written the whole, so asking "which chunks am I still
    # missing?" of a file that finished uploading yesterday answers "all of them". The first version of
    # this route did exactly that, which would have made the entry's "an unchanged re-upload needs
    # nothing" false in the one case it was written for. The finished object is the thing to look for.
    if storage.exists(assembled_key(pid, uid)):
        return {"upload_id": uid, "chunk_size": chunk, "chunks": len(hashes),
                "need": [], "complete": True, "already": True}

    need = [i for i in range(len(hashes))
            if not storage.exists(resumable.chunk_key(pid, uid, i))]
    return {
        "upload_id": uid,
        "chunk_size": chunk,
        "chunks": len(hashes),
        "need": need,
        "complete": not need,
        "already": False,
    }


@router.put("/projects/{pid}/uploads/{uid}/chunk/{index}")
async def put_chunk(pid: str, uid: str, index: int, request: Request,
                    db: Session = Depends(get_db),
                    _: str = Depends(require_role("editor"))) -> dict:
    """Store one chunk, verified against the hash the manifest promised for it.

    The expected hash travels in `X-Chunk-Sha256` rather than being looked up from a stored manifest.
    That keeps the server stateless between the handshake and the chunks — there is no session to
    expire mid-upload — and it is safe because the upload id is *derived from* the manifest: a client
    that lies about a chunk hash computes a different id and writes into a different upload, which is
    its own, and cannot corrupt anyone else's.
    """
    _project(db, pid)
    if index < 0 or index >= resumable.MAX_CHUNKS:
        raise HTTPException(422, f"chunk index {index} out of range 0..{resumable.MAX_CHUNKS - 1}")
    expect = request.headers.get("x-chunk-sha256", "")
    if not resumable.is_hash(expect):
        raise HTTPException(422, "X-Chunk-Sha256 must be a sha256 hex digest")

    data = await request.body()
    if not data:
        raise HTTPException(422, f"chunk {index} is empty")
    actual = resumable.hash_bytes(data)
    if actual != expect.lower():
        # Loud and specific: which upload, which chunk, how big it was. A client can retry ONE chunk
        # from this; "upload failed" would make it retry everything.
        #
        # No byte offset: this route does not know the file size, so it cannot compute one — and the
        # first draft of this message multiplied its way to a plausible-looking number that would have
        # been wrong for every chunk but the first. A fabricated offset in an error is worse than a
        # missing one, because it reads like evidence.
        raise HTTPException(422, f"chunk {index} of upload {uid[:12]} does not match its promised "
                                 f"hash: expected {expect[:12]}…, got {actual[:12]}… "
                                 f"({len(data)} bytes received)")
    storage.put(resumable.chunk_key(pid, uid, index), data)
    return {"stored": True, "index": index, "bytes": len(data)}


@router.post("/projects/{pid}/uploads/{uid}/complete")
def complete(pid: str, uid: str, body: dict = Body(...), db: Session = Depends(get_db),
             _: str = Depends(require_role("editor"))) -> dict:
    """Assemble the chunks into one object and drop the parts.

    Streams them: the assembled object is written through `storage.put_stream`, so a 200 MB IFC never
    exists as a single `bytes` in this process. That is the other half of R39-UPLOAD-CAP-APP, and it
    is why this route was worth writing rather than bolting resumption onto the existing multipart
    POST, which materialises the whole body by construction.
    """
    _project(db, pid)
    key = assembled_key(pid, uid)
    # Idempotent: completing an upload that is already assembled returns the same answer rather than
    # re-reading chunks that were deleted. A client that lost the response to its first `complete` will
    # retry, and a 409 there would look like corruption.
    if storage.exists(key):
        return {"key": key, "bytes": storage.size(key), "chunks": body.get("chunks"), "already": True}

    chunks = body.get("chunks")
    if not isinstance(chunks, int) or isinstance(chunks, bool) or not (0 < chunks <= resumable.MAX_CHUNKS):
        raise HTTPException(422, f"chunks must be an integer in 1..{resumable.MAX_CHUNKS}")
    missing = [i for i in range(chunks) if not storage.exists(resumable.chunk_key(pid, uid, i))]
    if missing:
        raise HTTPException(409, f"upload {uid[:12]} is missing chunk(s) {missing} — handshake again "
                                 f"to get the current need list")

    def _parts():
        for i in range(chunks):
            yield storage.get(resumable.chunk_key(pid, uid, i))

    try:
        # `max_bytes` is the REAL bound: it counts what is written, so a client that under-declared its
        # size at the handshake is still stopped here. put_stream cleans up its partial object on
        # refusal, which is why the cap belongs at the write rather than in a check before it.
        written = storage.put_stream(key, _parts(), max_bytes=MAX_UPLOAD_BYTES)
    except ValueError as e:
        storage.delete_prefix(resumable.chunk_prefix(pid, uid))
        raise HTTPException(413, str(e)) from None

    storage.delete_prefix(resumable.chunk_prefix(pid, uid))
    _log.info("assembled upload %s for %s: %d bytes from %d chunks", uid[:12], pid, written, chunks)
    return {"key": key, "bytes": written, "chunks": chunks, "already": False}
