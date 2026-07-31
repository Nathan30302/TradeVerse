"""
S3-compatible object storage (AWS S3, Cloudflare R2, MinIO, etc.).

When configured, user media (avatars, screenshots, playbook, replay) is stored
durably outside the Render container filesystem so redeploys cannot wipe it.

Env (any of the bucket names enables this backend when credentials are present):
  S3_BUCKET / AWS_S3_BUCKET / R2_BUCKET
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION          (default: auto — works for R2; use e.g. us-east-1 for AWS)
  S3_ENDPOINT_URL    (required for R2: https://<accountid>.r2.cloudflarestorage.com)
  S3_PUBLIC_BASE_URL (optional public/CDN base; if set, media_url may redirect there)
  S3_PREFIX          (optional key prefix, e.g. tradeverse/)
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


def _env(*keys: str, default: str = "") -> str:
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return default


def bucket_name() -> str:
    return _env("S3_BUCKET", "AWS_S3_BUCKET", "R2_BUCKET")


def is_configured() -> bool:
    """True when bucket + access key + secret are all set."""
    return bool(bucket_name() and _env("AWS_ACCESS_KEY_ID") and _env("AWS_SECRET_ACCESS_KEY"))


def public_base_url() -> str:
    return _env("S3_PUBLIC_BASE_URL", "R2_PUBLIC_BASE_URL").rstrip("/")


def key_prefix() -> str:
    raw = _env("S3_PREFIX").strip().strip("/")
    return f"{raw}/" if raw else ""


def object_key(rel_path: str) -> str:
    """Map DB relative path (uploads/avatars/x.png) to the S3 object key."""
    s = (rel_path or "").replace("\\", "/").lstrip("/")
    if s.startswith("static/"):
        s = s[len("static/") :]
    return f"{key_prefix()}{s}"


@lru_cache(maxsize=1)
def _client():
    if not is_configured():
        return None
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        logger.warning("S3/R2 configured but boto3 is not installed")
        return None

    region = _env("AWS_REGION", "AWS_DEFAULT_REGION", default="auto") or "auto"
    endpoint = _env("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL")
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": _env("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": _env("AWS_SECRET_ACCESS_KEY"),
        "region_name": region,
        "config": BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    }
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client(**kwargs)


def reset_client_cache() -> None:
    """Clear cached boto client (tests / env changes)."""
    clear = getattr(_client, "cache_clear", None)
    if callable(clear):
        clear()


def put_bytes(rel_path: str, data: bytes, content_type: Optional[str] = None) -> bool:
    """Upload bytes for a relative media path. Returns True on success."""
    client = _client()
    if not client:
        return False
    key = object_key(rel_path)
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    try:
        client.put_object(Bucket=bucket_name(), Key=key, Body=data, **extra)
        return True
    except Exception:
        logger.exception("S3 put_object failed key=%s", key)
        return False


def get_bytes(rel_path: str) -> Optional[bytes]:
    """Download object bytes, or None if missing / not configured."""
    client = _client()
    if not client:
        return None
    key = object_key(rel_path)
    try:
        resp = client.get_object(Bucket=bucket_name(), Key=key)
        body = resp.get("Body")
        if body is None:
            return None
        return body.read()
    except client.exceptions.NoSuchKey:  # type: ignore[attr-defined]
        return None
    except Exception as exc:
        # botocore ClientError with 404
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        logger.exception("S3 get_object failed key=%s", key)
        return None


def exists(rel_path: str) -> bool:
    client = _client()
    if not client:
        return False
    key = object_key(rel_path)
    try:
        client.head_object(Bucket=bucket_name(), Key=key)
        return True
    except Exception:
        return False


def delete(rel_path: str) -> bool:
    client = _client()
    if not client:
        return False
    key = object_key(rel_path)
    try:
        client.delete_object(Bucket=bucket_name(), Key=key)
        return True
    except Exception:
        logger.exception("S3 delete_object failed key=%s", key)
        return False


def public_url_for(rel_path: str) -> Optional[str]:
    """Absolute public URL when S3_PUBLIC_BASE_URL is set; else None (use app proxy)."""
    base = public_base_url()
    if not base:
        return None
    key = object_key(rel_path)
    return f"{base}/{key}"
