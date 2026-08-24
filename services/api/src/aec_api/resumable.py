"""R41-UPLOAD-WARK — content-addressed resumable upload, the pure half.

IFC revisions are large and mostly identical between uploads, so re-uploading a model that changed in
one storey currently costs a full transfer. This is the arithmetic and the identity behind a handshake
that fixes that; the routes live in `routers/uploads.py` and the bytes live in `storage`.

Everything here is pure — no I/O, no storage, no request — because the parts that are easy to get
subtly wrong are the *decisions*: how big a chunk is, what an upload is called, and whether a chunk
that arrived is the chunk that was promised. Those are testable without a network.

THE CHUNK **COUNT** IS BOUNDED, NOT THE CHUNK **SIZE**
------------------------------------------------------
The obvious design fixes the part size — 8 MiB, say — and lets the count follow. That gives a
handshake manifest that grows linearly with the file: a 4 GiB point cloud would declare 512 hashes,
and the manifest is sent on every resume. So the count is capped instead and the size follows, which
keeps the manifest roughly constant however large the upload gets.

The floor matters as much as the cap. Without `MIN_CHUNK` a 40 KB file would be split into 128 chunks
of 320 bytes, and the per-chunk overhead would dwarf the payload.

THE IDENTITY IS DERIVED FROM THE CONTENT, WHICH IS WHY RESUMPTION IS NOT A CODE PATH
------------------------------------------------------------------------------------
`upload_id = sha256(salt + size + chunk hashes)`. A client that lost its connection re-handshakes with
the same file, computes the same id, and the server answers with the chunks it still needs. There is
no "resume" endpoint and no server-side session to expire, because resuming and starting are the same
request — the second one just gets a shorter `need` list. Deduplication falls out of the same fact: an
unchanged re-upload needs nothing.

**The salt is the project id, deliberately.** Content-addressing across the whole platform would let
one project discover whether another holds a given file by handshaking for it and reading `need: []`
— a cross-tenant existence oracle, which is a disclosure even though no bytes are returned. Scoping
the identity per project costs duplicate storage of a file two projects genuinely share, and buys a
boundary that does not depend on anyone remembering to check.

WHAT THIS DOES NOT DECIDE
-------------------------
The **assembled** size is checked at completion by the route, against the bytes actually written —
never against the size declared here. A declared size is a claim by the client, and the whole point of
the cap is to bound what an untrusted caller can make the server store.
"""
from __future__ import annotations

import hashlib
import math
import os

#: The upload cap, in bytes. Defined HERE rather than in `main` because both the ASGI body-size
#: middleware and this handshake have to agree on it, and a second `int(os.environ[...])` somewhere
#: else is a value that drifts the first time someone changes the default. `main` imports this one.
MAX_UPLOAD_BYTES = int(os.environ.get("AEC_MAX_UPLOAD_MB", "1024")) * 1024 * 1024   # default 1 GB

#: Never more than this many chunks in a manifest, whatever the file size.
MAX_CHUNKS = 64
#: ...and never a chunk smaller than this, whatever the file size.
MIN_CHUNK = 1 << 20          # 1 MiB
#: Chunk sizes are rounded up to this, so a manifest carries round numbers rather than 5,592,406.
CHUNK_GRANULARITY = 1 << 20

#: A chunk hash is a sha256 hex digest, and nothing else is accepted.
HASH_LEN = 64


def plan_chunk_size(size: int) -> int:
    """The chunk size for a file of `size` bytes: the smallest that keeps the count within MAX_CHUNKS.

    Rounded up to `CHUNK_GRANULARITY`, so the number a client is told is one a human can also verify.
    """
    if size <= 0:
        return MIN_CHUNK
    needed = math.ceil(size / MAX_CHUNKS)
    rounded = math.ceil(max(needed, MIN_CHUNK) / CHUNK_GRANULARITY) * CHUNK_GRANULARITY
    return int(rounded)


def chunk_count(size: int, chunk: int) -> int:
    """How many chunks a file of `size` splits into. Zero bytes is ONE empty chunk, not zero chunks.

    A zero-chunk upload would complete without any chunk ever being verified, so an empty file would
    take a path nothing else takes — and that path would be the one nobody tests.
    """
    if chunk <= 0:
        raise ValueError("chunk size must be positive")
    return max(1, math.ceil(size / chunk))


def upload_id(salt: str, size: int, chunk_hashes: list[str]) -> str:
    """Identity for an upload, derived from its content. See the module docstring for the salt.

    The size is folded in as well as the hashes: two different files can only collide here if every
    chunk hash collides, but including the length makes the identity wrong-by-construction for a
    truncated manifest rather than merely unlikely.
    """
    h = hashlib.sha256()
    h.update(salt.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(int(size)).encode("ascii"))
    for c in chunk_hashes:
        h.update(b"\x00")
        h.update(c.encode("ascii"))
    return h.hexdigest()


def is_hash(value: object) -> bool:
    """A sha256 hex digest and nothing else — the manifest comes from a browser."""
    return isinstance(value, str) and len(value) == HASH_LEN and all(
        c in "0123456789abcdef" for c in value.lower()
    )


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chunk_key(pid: str, uid: str, index: int) -> str:
    """Where one chunk lives while the upload is incomplete."""
    return f"uploads/{pid}/{uid}/{index:04d}.part"


def chunk_prefix(pid: str, uid: str) -> str:
    """Everything belonging to one upload, for the cleanup after assembly."""
    return f"uploads/{pid}/{uid}/"


def validate_manifest(size: object, hashes: object, max_bytes: int) -> tuple[int, list[str]]:
    """Check a client-supplied manifest, or raise `ValueError` with a message a caller can return.

    Refusals are LOUD and specific — the house style, and the reason is the same one the reference
    implementation gives for its sparse-file check: a handshake that quietly accepts a manifest it
    cannot honour produces a corrupt object later, somewhere else, with nothing pointing back here.

    The declared size is checked against the cap so an oversized upload is refused BEFORE a single
    chunk is transferred. It is never trusted as the final word — the route re-checks the bytes it
    actually assembled.
    """
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError(f"size must be a non-negative integer, got {size!r}")
    if size > max_bytes:
        raise ValueError(f"declared size {size} exceeds the {max_bytes}-byte upload cap")
    if not isinstance(hashes, list) or not hashes:
        raise ValueError("chunk_hashes must be a non-empty list of sha256 hex digests")
    if len(hashes) > MAX_CHUNKS:
        raise ValueError(f"{len(hashes)} chunks exceeds the {MAX_CHUNKS}-chunk manifest limit")
    for i, c in enumerate(hashes):
        if not is_hash(c):
            raise ValueError(f"chunk {i}: not a sha256 hex digest ({c!r})")

    chunk = plan_chunk_size(size)
    expected = chunk_count(size, chunk)
    if len(hashes) != expected:
        raise ValueError(
            f"manifest declares {len(hashes)} chunks but {size} bytes at {chunk} bytes/chunk is "
            f"{expected} — the client used a different chunk size")
    return chunk, list(hashes)
