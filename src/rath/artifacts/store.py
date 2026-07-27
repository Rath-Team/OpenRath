"""Tenant-scoped, content-addressed artifact stores."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast, runtime_checkable

from rath._json import JSONValue, freeze_mapping, thaw_json

__all__ = [
    "Artifact",
    "ArtifactNotFound",
    "ArtifactStore",
    "LocalArtifactStore",
    "S3ArtifactStore",
]

_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactNotFound(KeyError):
    """Raised when an artifact does not exist in the requested tenant."""


@dataclass(frozen=True, slots=True)
class Artifact:
    tenant_id: str
    digest: str
    size: int
    media_type: str
    created_at: datetime
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_scope(self.tenant_id, field_name="tenant_id")
        if not _SHA256.fullmatch(self.digest):
            raise ValueError("digest must be a lowercase SHA-256 digest")
        if self.size < 0:
            raise ValueError("size must not be negative")
        if not self.media_type.strip():
            raise ValueError("media_type must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        object.__setattr__(
            self, "metadata", freeze_mapping(self.metadata, field="artifact.metadata")
        )

    @property
    def uri(self) -> str:
        return f"artifact://{self.tenant_id}/{self.digest}"


@runtime_checkable
class ArtifactStore(Protocol):
    def put(
        self,
        tenant_id: str,
        content: bytes | BinaryIO,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, object] | None = None,
    ) -> Artifact: ...

    def get(self, tenant_id: str, digest: str) -> bytes: ...

    def stat(self, tenant_id: str, digest: str) -> Artifact: ...

    def delete(self, tenant_id: str, digest: str) -> bool: ...


class _S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> Mapping[str, Any]: ...

    def delete_objects(self, **kwargs: object) -> object: ...


def _validate_scope(value: str, *, field_name: str) -> None:
    if not _SCOPE.fullmatch(value):
        raise ValueError(f"{field_name} contains unsafe characters")


def _validate_digest(digest: str) -> None:
    if not _SHA256.fullmatch(digest):
        raise ValueError("digest must be a lowercase SHA-256 digest")


def _chunks(content: bytes | BinaryIO, size: int = 1024 * 1024) -> Iterator[bytes]:
    if isinstance(content, bytes):
        yield content
        return
    while chunk := content.read(size):
        yield chunk


def _manifest(artifact: Artifact) -> bytes:
    value = {
        "tenant_id": artifact.tenant_id,
        "digest": artifact.digest,
        "size": artifact.size,
        "media_type": artifact.media_type,
        "created_at": artifact.created_at.isoformat(),
        "metadata": thaw_json(artifact.metadata),
    }
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode()


def _parse_manifest(value: bytes) -> Artifact:
    data = json.loads(value)
    return Artifact(
        tenant_id=data["tenant_id"],
        digest=data["digest"],
        size=data["size"],
        media_type=data["media_type"],
        created_at=datetime.fromisoformat(data["created_at"]),
        metadata=data["metadata"],
    )


class LocalArtifactStore:
    """Atomic filesystem store intended for embedded and single-node operation."""

    def __init__(self, root: str | Path, *, max_bytes: int = 128 * 1024 * 1024):
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.root = Path(root).expanduser().resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def _paths(self, tenant_id: str, digest: str) -> tuple[Path, Path]:
        _validate_scope(tenant_id, field_name="tenant_id")
        _validate_digest(digest)
        directory = self.root / tenant_id / digest[:2]
        payload = directory / digest
        manifest = directory / f"{digest}.json"
        for path in (directory, payload, manifest):
            if not path.resolve(strict=False).is_relative_to(self.root):
                raise ValueError("artifact path escapes the configured root")
        return payload, manifest

    def put(
        self,
        tenant_id: str,
        content: bytes | BinaryIO,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, object] | None = None,
    ) -> Artifact:
        _validate_scope(tenant_id, field_name="tenant_id")
        digest = hashlib.sha256()
        total = 0
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.root, prefix=".upload-", delete=False
            ) as target:
                temporary = Path(target.name)
                for chunk in _chunks(content):
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ValueError("artifact exceeds configured size limit")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            artifact = Artifact(
                tenant_id=tenant_id,
                digest=digest.hexdigest(),
                size=total,
                media_type=media_type,
                created_at=datetime.now(timezone.utc),
                metadata=freeze_mapping(metadata, field="artifact.metadata"),
            )
            payload, manifest = self._paths(tenant_id, artifact.digest)
            payload.parent.mkdir(parents=True, exist_ok=True)
            if payload.exists():
                temporary.unlink(missing_ok=True)
            else:
                temporary.replace(payload)
            temporary = None
            self._atomic_write(manifest, _manifest(artifact))
            return self.stat(tenant_id, artifact.digest)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, tenant_id: str, digest: str) -> bytes:
        payload, _ = self._paths(tenant_id, digest)
        try:
            value = payload.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactNotFound(digest) from exc
        if not hashlib.sha256(value).hexdigest() == digest:
            raise IOError("artifact digest verification failed")
        return value

    def stat(self, tenant_id: str, digest: str) -> Artifact:
        _, manifest = self._paths(tenant_id, digest)
        try:
            artifact = _parse_manifest(manifest.read_bytes())
        except FileNotFoundError as exc:
            raise ArtifactNotFound(digest) from exc
        if artifact.tenant_id != tenant_id or artifact.digest != digest:
            raise IOError("artifact manifest identity mismatch")
        return artifact

    def delete(self, tenant_id: str, digest: str) -> bool:
        payload, manifest = self._paths(tenant_id, digest)
        existed = payload.exists() or manifest.exists()
        payload.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        return existed

    @staticmethod
    def _atomic_write(path: Path, value: bytes) -> None:
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".manifest-")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(value)
                target.flush()
                os.fsync(target.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class S3ArtifactStore:
    """S3-compatible store; durable identity is the SHA-256 object key."""

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "openrath",
        client: object | None = None,
        max_bytes: int = 128 * 1024 * 1024,
        **client_options: object,
    ) -> None:
        _validate_scope(bucket, field_name="bucket")
        if not prefix or prefix.startswith("/") or ".." in prefix.split("/"):
            raise ValueError("prefix must be a safe relative object prefix")
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if client is None:
            try:
                import boto3  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "S3 support requires `pip install openrath[s3]`"
                ) from exc
            client = boto3.client("s3", **client_options)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.client = cast(_S3Client, client)
        self.max_bytes = max_bytes

    def _keys(self, tenant_id: str, digest: str) -> tuple[str, str]:
        _validate_scope(tenant_id, field_name="tenant_id")
        _validate_digest(digest)
        base = f"{self.prefix}/{tenant_id}/{digest[:2]}/{digest}"
        return base, f"{base}.json"

    def put(
        self,
        tenant_id: str,
        content: bytes | BinaryIO,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, object] | None = None,
    ) -> Artifact:
        data = b"".join(_chunks(content))
        if len(data) > self.max_bytes:
            raise ValueError("artifact exceeds configured size limit")
        artifact = Artifact(
            tenant_id=tenant_id,
            digest=hashlib.sha256(data).hexdigest(),
            size=len(data),
            media_type=media_type,
            created_at=datetime.now(timezone.utc),
            metadata=freeze_mapping(metadata, field="artifact.metadata"),
        )
        payload_key, manifest_key = self._keys(tenant_id, artifact.digest)
        self.client.put_object(
            Bucket=self.bucket,
            Key=payload_key,
            Body=data,
            ContentType=media_type,
            Metadata={"sha256": artifact.digest},
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=_manifest(artifact),
            ContentType="application/json",
        )
        return artifact

    def get(self, tenant_id: str, digest: str) -> bytes:
        payload_key, _ = self._keys(tenant_id, digest)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=payload_key)
        except Exception as exc:
            if _not_found(exc):
                raise ArtifactNotFound(digest) from exc
            raise
        value = cast(bytes, response["Body"].read())
        if hashlib.sha256(value).hexdigest() != digest:
            raise IOError("artifact digest verification failed")
        return value

    def stat(self, tenant_id: str, digest: str) -> Artifact:
        _, manifest_key = self._keys(tenant_id, digest)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=manifest_key)
        except Exception as exc:
            if _not_found(exc):
                raise ArtifactNotFound(digest) from exc
            raise
        artifact = _parse_manifest(response["Body"].read())
        if artifact.tenant_id != tenant_id or artifact.digest != digest:
            raise IOError("artifact manifest identity mismatch")
        return artifact

    def delete(self, tenant_id: str, digest: str) -> bool:
        try:
            self.stat(tenant_id, digest)
        except ArtifactNotFound:
            return False
        payload_key, manifest_key = self._keys(tenant_id, digest)
        self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": payload_key}, {"Key": manifest_key}]},
        )
        return True


def _not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return str(code) in {"404", "NoSuchKey", "NotFound"}
