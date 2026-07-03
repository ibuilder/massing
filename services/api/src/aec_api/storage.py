"""Object storage with pluggable backends (guide §1, §7).

- Local filesystem for dev (default).
- MinIO / S3 for self-host/prod when S3_ENDPOINT is set (boto3).

Both expose the same interface incl. byte-range reads, so `.frag` tiles and attachments can
be served with HTTP range requests (streaming / resumable downloads)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class Backend(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def size(self, key: str) -> int: ...
    def get_range(self, key: str, start: int, end: int) -> bytes: ...


class LocalBackend:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _p(self, key: str) -> Path:
        # containment guard: a key like "../../etc/x" must never resolve outside the storage root
        # (attachment keys include a user-supplied filename). Reject anything that escapes.
        dest = (self.root / key).resolve()
        if dest != self.root and self.root not in dest.parents:
            raise ValueError(f"unsafe storage key: {key!r}")
        return dest

    def put(self, key: str, data: bytes) -> str:
        dest = self._p(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return key

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
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def size(self, key: str) -> int:
        return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def version(self, key: str) -> str:
        h = self.client.head_object(Bucket=self.bucket, Key=key)
        return (h.get("ETag") or f'"{h["ContentLength"]:x}"').strip('"').join('""')

    def get_range(self, key: str, start: int, end: int) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
        return obj["Body"].read()

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under a prefix (project teardown). Paginates list_objects_v2."""
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
