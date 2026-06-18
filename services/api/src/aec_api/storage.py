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
        return self.root / key

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

    def get_range(self, key: str, start: int, end: int) -> bytes:
        with open(self._p(key), "rb") as fh:
            fh.seek(start)
            return fh.read(end - start + 1)


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

    def get_range(self, key: str, start: int, end: int) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
        return obj["Body"].read()


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


def size(key: str) -> int:
    return backend().size(key)


def path(key: str) -> Path:
    """Filesystem path (local backend only — used by the converter to write .frag)."""
    b = backend()
    if isinstance(b, LocalBackend):
        return b._p(key)
    return Path(os.environ.get("STORAGE_DIR", "./storage")) / key
