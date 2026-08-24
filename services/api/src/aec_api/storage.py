"""Object storage with pluggable backends (guide §1, §7).

- Local filesystem for dev (default).
- MinIO / S3 for self-host/prod when S3_ENDPOINT is set (boto3).

Both expose the same interface incl. byte-range reads, so `.frag` tiles and attachments can
be served with HTTP range requests (streaming / resumable downloads)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

_SAFE_SEG = re.compile(r"^[A-Za-z0-9._-]+$")

#: S3 requires every multipart part except the last to be >= 5 MiB. The streaming writer buffers to
#: this floor before flushing a part, so peak memory during an upload is one part, not one object.
_PART_SIZE = 8 * 1024 * 1024


class TooLarge(Exception):
    """A streamed upload passed the caller's byte budget.

    Raised by `put_stream` rather than returned, so a caller that ignores the return value cannot
    end up having stored an object it meant to refuse. Both backends clean up before it propagates:
    the local one deletes its `.part` file, the S3 one aborts the multipart upload.
    """


def safe_seg(seg: str) -> str:
    """Validate a single path segment (e.g. a project id / model id) before it's used to build a
    filesystem path — rejects traversal, separators, and NUL. Project/model ids are opaque
    hex/UUID keys, so the [A-Za-z0-9._-] whitelist never rejects a legitimate one. Raises ValueError.

    **Returns the MATCH, not the argument.** The two are equal strings, so no caller behaviour
    changes — but the returned value is derived from the whitelist match rather than being the
    caller's object passed straight through. That difference is the whole point: until 2026-08-02
    this returned `seg`, so the untrusted value flowed onward untouched and every downstream
    `mkdir`/`read_bytes` stayed tainted no matter how many checks sat in between. Static analysis
    kept reporting `py/path-injection` at those sinks and it was *right about the dataflow* — the
    sanitisation was real but invisible, expressed as a guard clause rather than as a value.

    The repo's answer to that had been to dismiss the alerts (29 of them). Six of those dismissed
    sites then needed containment barriers added anyway, and a genuine arbitrary-file-write turned
    up in the same family that the scanner never flagged — so "false positive, dismiss" was the
    wrong instinct twice over. Expressing the sanitiser in the data, not just in control flow, is
    the fix that makes the claim checkable instead of asserted.
    """
    if not seg or seg in (".", ".."):
        raise ValueError(f"unsafe path segment: {seg!r}")
    m = _SAFE_SEG.match(seg)
    if not m:
        raise ValueError(f"unsafe path segment: {seg!r}")
    return m.group(0)


def contained_path(base, *parts: str) -> Path:
    """Join `parts` under `base` and refuse anything that RESOLVES outside it.

    `safe_seg` validates one segment and is the right tool when every component is a segment you
    control. It cannot help when a component is a whole client-supplied *name* — a filename read from
    an uploaded container, say — because the traversal need not be its first segment. A prefix like
    `f"{pid}_{name}"` makes the leading `..` part of a literal directory name, which reads as safe and
    is not: the segments after it still walk up, so enough of them leave the base directory. Prefixing
    changes the depth required and nothing else.

    Resolving first and testing containment afterwards is therefore the barrier, not a second opinion
    on it — it answers "where does this actually land", which is the only question that matters and
    the one string inspection cannot answer. Same idiom as `LocalBackend._p` and the ensure-model path.

    Raises ValueError; callers surface it as a 400. Returns the resolved path.
    """
    root = Path(base).resolve()
    dest = root.joinpath(*parts).resolve()
    if dest != root and not dest.is_relative_to(root):
        raise ValueError(f"path escapes its base directory: {'/'.join(map(str, parts))!r}")
    return dest


def validate_key(key: str) -> str:
    """Validate a whole storage key, for EVERY backend — not just the one that has a filesystem.

    This lived inside `LocalBackend._p`, so the two shipped backends disagreed about the same key:
    `../../etc/x` raised on local and was accepted by S3, which stores it as an object whose name
    merely contains dots. Neither is a traversal on S3 — the point is the disagreement. A key written
    under one profile could not be read back under the other, and a defence-in-depth control silently
    applied to only half of the deployments, with nothing to say which half you were on.

    So the guard belongs to the *interface*, not to an implementation, and `test_storage_key_parity`
    asserts the two backends refuse the SAME SET of keys rather than merely each refusing something.
    Set-equality is what stops the next backend from diverging quietly too; a per-backend checklist
    would not have caught this one, since S3's entry would simply never have been written.

    Rejects: empty, NUL, absolute (`/` or `\\`), and any `..` segment. Tenancy is NOT enforced here —
    keys are server-composed as `{pid}/…` at the callers, and a key naming another project is a
    routing/authz question, not a storage one. Raises ValueError.
    """
    if (not key or key.startswith(("/", "\\"))
            or ".." in key.replace("\\", "/").split("/")):
        raise ValueError(f"unsafe storage key: {key!r}")
    # Every C0 control character, not just NUL. NUL was singled out because it truncates a C string
    # at the syscall boundary, but the rest of the range is no more legitimate in a key and several
    # are actively dangerous downstream: \r and \n forge lines in any log or manifest that lists
    # keys, and \t and the escape character misalign anything that renders them.
    #
    # THIS IS THE SAME BACKEND DIVERGENCE THE DOCSTRING ABOVE DESCRIBES, found the same way. Reverting
    # this check to the old NUL-only rule leaks exactly ONE key of the thirty-three: `\x7f`. The other
    # C0 characters appear to be refused — but by NTFS rejecting an invalid filename, not by us. S3
    # has no such filesystem and would have stored every one of them, so the two backends disagreed
    # about thirty-one keys and the local one's accident hid it. An implementation detail standing in
    # for a guard is exactly what moved `..` out of `LocalBackend._p` in the first place.
    #
    # Additive on purpose. Tightening this to an allowlist like `safe_seg`'s
    # `[A-Za-z0-9._-]` is the change that suggests itself here and it CANNOT be made: attachment
    # keys carry a user-supplied filename, so spaces, parentheses and non-ASCII are all legitimate
    # today and an allowlist would reject uploads that work now — a contract change for every
    # caller, dressed as a hardening. No real filename contains a control character, so this
    # rejects nothing that currently succeeds.
    if any(ch < " " or ch == "\x7f" for ch in key):
        raise ValueError(f"unsafe storage key (control character): {key!r}")
    return key


class Backend(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def put_stream(self, key: str, chunks, max_bytes: int | None = None) -> int: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def size(self, key: str) -> int: ...
    def get_range(self, key: str, start: int, end: int) -> bytes: ...


class LocalBackend:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _p(self, key: str) -> Path:
        # shared bar first — validate_key rejects empty/NUL/absolute/`..` — so local and S3 agree on
        # which keys exist at all — attachment keys carry a user-supplied filename.
        validate_key(key)
        # local-only second bar: even a syntactically clean key must resolve inside the root (symlinks,
        # drive-relative oddities). S3 has no filesystem to escape, which is why this half stays here.
        dest = (self.root / key).resolve()
        if dest != self.root and not dest.is_relative_to(self.root):
            raise ValueError(f"unsafe storage key: {key!r}")
        return dest

    def put(self, key: str, data: bytes) -> str:
        dest = self._p(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return key

    def put_stream(self, key: str, chunks, max_bytes: int | None = None) -> int:
        """Write an iterable of byte chunks without holding the whole object. Returns bytes written.

        Written to a `.part` file and renamed at the end, so a refusal or a crash mid-write cannot
        leave a TRUNCATED object at the real key. A half-written file at the final key is worse than
        no file: `exists()` reports it, `size()` reports a plausible number, and every reader
        downstream treats it as a complete upload.
        """
        dest = self._p(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        written = 0
        try:
            with open(part, "wb") as fh:
                for chunk in chunks:
                    if not chunk:
                        continue
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise TooLarge(f"upload exceeds {max_bytes} bytes")
                    fh.write(chunk)
            part.replace(dest)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return written

    def get(self, key: str) -> bytes:
        return self._p(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._p(key).exists()

    def delete(self, key: str) -> None:
        self._p(key).unlink(missing_ok=True)

    def size(self, key: str) -> int:
        return self._p(key).stat().st_size

    def version(self, key: str) -> str:
        st = self._p(key).stat()
        return f'"{st.st_size:x}-{int(st.st_mtime):x}"'   # cheap, changes whenever the file is rewritten

    def get_range(self, key: str, start: int, end: int) -> bytes:
        with open(self._p(key), "rb") as fh:
            fh.seek(start)
            return fh.read(end - start + 1)

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under a prefix (project teardown). Returns files removed. The prefix
        goes through the same containment guard as keys."""
        import shutil
        root = self._p(prefix.rstrip("/"))
        if not root.exists():
            return 0
        n = sum(1 for p in root.rglob("*") if p.is_file()) if root.is_dir() else 1
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
        else:
            root.unlink(missing_ok=True)
        return n


class S3Backend:
    """MinIO/S3 via boto3. Bucket auto-created. Enabled by S3_ENDPOINT env."""

    def __init__(self):
        import boto3  # lazy: only needed when S3 is configured

        self.bucket = os.environ.get("S3_BUCKET", "aec-bim")
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT"],
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
            region_name=os.environ.get("S3_REGION", "us-east-1"),
        )
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes) -> str:
        validate_key(key)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def put_stream(self, key: str, chunks, max_bytes: int | None = None) -> int:
        """Multipart upload from an iterable of chunks. Returns bytes written.

        Multipart rather than buffering into one `put_object` because buffering here would defeat
        the entire purpose — the object would be whole in memory again at the moment it is sent.
        S3 requires every part except the last to be at least 5 MiB, so chunks are accumulated to
        that floor before a part is flushed; the buffer is bounded by `_PART_SIZE`, not by the
        object.

        On any failure the upload is ABORTED, not left open: an abandoned multipart upload is
        invisible to `list_objects` and to `exists()` while still being billed and still holding
        the parts. That is the S3 form of the truncated-file problem the local backend avoids with
        a `.part` rename.
        """
        validate_key(key)
        buf = bytearray()
        parts: list[dict] = []
        written = 0
        up = self.client.create_multipart_upload(Bucket=self.bucket, Key=key)
        uid = up["UploadId"]

        def flush() -> None:
            n = len(parts) + 1
            r = self.client.upload_part(Bucket=self.bucket, Key=key, UploadId=uid,
                                        PartNumber=n, Body=bytes(buf))
            parts.append({"ETag": r["ETag"], "PartNumber": n})
            buf.clear()

        try:
            for chunk in chunks:
                if not chunk:
                    continue
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise TooLarge(f"upload exceeds {max_bytes} bytes")
                buf.extend(chunk)
                if len(buf) >= _PART_SIZE:
                    flush()
            if buf or not parts:      # a zero-byte object still needs one (empty) part
                flush()
            self.client.complete_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=uid,
                MultipartUpload={"Parts": parts})
        except BaseException:
            try:
                self.client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=uid)
            except Exception:
                pass                  # the original failure is the one worth raising
            raise
        return written

    def get(self, key: str) -> bytes:
        validate_key(key)
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        validate_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def size(self, key: str) -> int:
        validate_key(key)
        return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def version(self, key: str) -> str:
        validate_key(key)
        h = self.client.head_object(Bucket=self.bucket, Key=key)
        return (h.get("ETag") or f'"{h["ContentLength"]:x}"').strip('"').join('""')

    def get_range(self, key: str, start: int, end: int) -> bytes:
        validate_key(key)
        obj = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
        return obj["Body"].read()

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under a prefix (project teardown). Paginates list_objects_v2."""
        validate_key(prefix.rstrip("/"))
        n = 0
        token = None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix.rstrip("/") + "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kw)
            keys = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
            if keys:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
                n += len(keys)
            if not resp.get("IsTruncated"):
                return n
            token = resp.get("NextContinuationToken")


def _make_backend() -> Backend:
    if os.environ.get("S3_ENDPOINT"):
        return S3Backend()
    return LocalBackend(os.environ.get("STORAGE_DIR", "./storage"))


_backend: Backend | None = None


def backend() -> Backend:
    global _backend
    if _backend is None:
        _backend = _make_backend()
    return _backend


# module-level convenience (back-compat with existing callers)
def put(key: str, data: bytes) -> str:
    return backend().put(key, data)


def put_stream(key: str, chunks, max_bytes: int | None = None) -> int:
    """Store an object from an iterable of chunks without materialising it. Returns bytes written.

    The back half of R39-UPLOAD-CAP-APP / R41-UPLOAD-WARK. `put(key, data: bytes)` was the only
    write, so every one of the 36+ `await file.read()` call sites had no alternative to holding the
    whole upload in memory — the API offered no other shape. Bounding the request body (see
    `bodycap.MaxBodySizeMiddleware`) stops the *unbounded* case; this is what lets a caller stop
    holding even a bounded one.

    `max_bytes` is a second, independent bound at the point of storage. It is not redundant with
    the middleware: the middleware limits one REQUEST, while a handler may write several objects
    from one request, and some callers (imports, generated exports) produce bytes that never came
    from a request at all.
    """
    return backend().put_stream(key, chunks, max_bytes)


# --- streaming helpers: the callers' half of R41-UPLOAD-WARK ----------------------------------
# `put_stream` shipped in v0.3.876 with NO adopters, so every upload route still did
# `data = await file.read()` and held the whole object. These two functions are what a route needs
# to stop doing that, and they are here rather than in a router so the four converted routes share
# one implementation instead of four hand-rolled chunk loops.

#: 1 MiB. Large enough that a 300 MB IFC is ~300 iterations rather than 300k, small enough that
#: concurrent uploads do not add up to anything interesting. NOT tuned to S3's 5 MiB part floor —
#: `S3Backend.put_stream` accumulates to that floor itself, so a caller choosing this number does
#: not need to know S3 exists.
UPLOAD_CHUNK = 1 << 20


def upload_chunks(upload, chunk: int = UPLOAD_CHUNK):
    """Iterate a Starlette `UploadFile`'s bytes without materialising it.

    **The object is already on disk.** Starlette spools an UploadFile to a temporary file past a
    small threshold, so `await file.read()` was never reading from the network — it was reading a
    file that already existed into a `bytes` the size of the upload. That is the whole defect: the
    expensive part is not the transfer, it is the copy.

    Synchronous on purpose. Both backends' `put_stream` take a plain iterable and are meant to be
    called inside `run_in_threadpool`, so an async generator here would be unusable by them.
    """
    f = upload.file
    f.seek(0)
    while True:
        b = f.read(chunk)
        if not b:
            return
        yield b


def stream_to_path(dest, chunks, max_bytes: int | None = None) -> int:
    """Write chunks to an ARBITRARY filesystem path (not a storage key). Returns bytes written.

    Needed because two of the converted routes must leave a copy somewhere the converter can open
    by path, which `put_stream` cannot do — it writes to a storage key, and on S3 there is no path
    at all. Same `.part`-then-rename discipline for the same reason: a truncated file at the final
    name is worse than no file, because `exists()` reports it and every reader downstream treats it
    as a complete upload.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    written = 0
    try:
        with open(part, "wb") as fh:
            for c in chunks:
                if not c:
                    continue
                written += len(c)
                if max_bytes is not None and written > max_bytes:
                    raise TooLarge(f"upload exceeds {max_bytes} bytes")
                fh.write(c)
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return written


def file_chunks(src, chunk: int = UPLOAD_CHUNK):
    """Iterate a file already on disk — pairs with `stream_to_path` when a route needs BOTH a local
    working copy and a durable one, so the object is never whole in memory on either write."""
    with open(src, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                return
            yield b


def get_chunks(key: str, chunk: int = UPLOAD_CHUNK):
    """Iterate an object already in storage, without ever holding it whole.

    The read counterpart to `put_stream`. `get_range` has existed for a while — ranged READS were
    supported while writes were all-or-nothing — but nothing turned it into a stream, so a route that
    wanted to copy a stored object into another one had only `get()`, which materialises it. That is
    the shape R41-UPLOAD-WARK exists to remove, and it would have come straight back the first time an
    assembled 200 MB upload was registered as a model.

    Bounded by the object's size at the start: an object being appended to while this runs would
    otherwise never end, and nothing in this codebase appends to a stored object.
    """
    total = size(key)
    at = 0
    while at < total:
        end = min(at + chunk, total)
        b = backend().get_range(key, at, end)
        if not b:
            return                       # a backend that returns nothing must not spin forever
        yield b
        at += len(b)


def get(key: str) -> bytes:
    return backend().get(key)


def exists(key: str) -> bool:
    return backend().exists(key)


def delete(key: str) -> None:
    backend().delete(key)


def delete_prefix(prefix: str) -> int:
    """Remove every object under `prefix` (e.g. a whole project's blobs on delete)."""
    return backend().delete_prefix(prefix)      # type: ignore[attr-defined]


def size(key: str) -> int:
    return backend().size(key)


def version(key: str) -> str:
    """A cheap content validator (ETag value) — changes when the object is rewritten."""
    b = backend()
    try:
        return b.version(key)              # type: ignore[attr-defined]
    except AttributeError:
        return f'"{b.size(key):x}"'        # fallback: size only


def path(key: str) -> Path:
    """Filesystem path (local backend only — used by the converter to write .frag)."""
    b = backend()
    if isinstance(b, LocalBackend):
        return b._p(key)
    return Path(os.environ.get("STORAGE_DIR", "./storage")) / key
