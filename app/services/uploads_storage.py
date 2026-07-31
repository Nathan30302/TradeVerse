"""
Persistent user media storage (avatars, trade screenshots, replay, playbook).

Backends (preferred → fallback):
  1. S3-compatible object storage when S3_BUCKET + AWS credentials are set
  2. TRADEVERSE_DATA_DIR / UPLOAD_ROOT / PERSISTENT_DISK_PATH (Render disk)
  3. app/static/uploads (local dev; ephemeral on Render — avoid in production)

DB stores relative paths like ``uploads/avatars/x.png``. Serving prefers local
disk (legacy leftovers), then object storage. Already-deleted ephemeral files
cannot be recovered.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from io import BytesIO
from typing import List, Optional, Tuple

from flask import current_app, has_app_context, send_file, send_from_directory, url_for

from app.services import object_storage

logger = logging.getLogger(__name__)


def _env_data_dir() -> Optional[str]:
    for key in (
        "TRADEVERSE_DATA_DIR",
        "UPLOAD_ROOT",
        "PERSISTENT_DISK_PATH",
        "RENDER_DISK_PATH",
    ):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    return None


def _is_writable_dir(path: str) -> bool:
    """Return True if path exists (or can be created) and is writable."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".tv_write_probe")
        with open(probe, "wb") as fh:
            fh.write(b"ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _static_fallback_root() -> str:
    if has_app_context():
        return os.path.join(current_app.root_path, "static")
    return os.path.join("app", "static")


def _path_looks_ephemeral(root: str) -> bool:
    abs_root = os.path.abspath(root)
    if abs_root.startswith("/tmp") or abs_root.startswith("/var/tmp"):
        return True
    # app/static tree inside the deploy slug
    if abs_root.rstrip("/").endswith(os.path.join("app", "static")) or abs_root.rstrip(
        "/"
    ).endswith("/static"):
        # /var/data is never named static; slug static is ephemeral on Render
        if "/var/data" in abs_root:
            return False
        return True
    return False


def persistent_data_root() -> str:
    """
    Durable root (e.g. /var/data). Uploads live under ``{root}/uploads/...``.

    If the configured path is not writable (common when Render sets
    TRADEVERSE_DATA_DIR=/var/data without mounting a disk), fall back to
    ``app/static`` so the process still boots and accepts uploads.
    """
    candidates: List[str] = []
    env = _env_data_dir()
    if env:
        candidates.append(env)
    if has_app_context():
        cfg = current_app.config.get("TRADEVERSE_DATA_DIR")
        if cfg:
            candidates.append(str(cfg).rstrip("/"))
    candidates.append(_static_fallback_root())
    candidates.append("/tmp/tradeverse_data")

    seen = set()
    for root in candidates:
        if not root or root in seen:
            continue
        seen.add(root)
        if _is_writable_dir(root):
            return root
    return candidates[0] if candidates else _static_fallback_root()


def storage_backend_name() -> str:
    """Human-readable active write backend: s3 | disk | ephemeral."""
    if object_storage.is_configured():
        return "s3"
    root = persistent_data_root()
    if _path_looks_ephemeral(root):
        return "ephemeral"
    return "disk"


def warn_if_ephemeral_storage() -> None:
    """Log a loud warning when production writes will not survive redeploy."""
    if object_storage.is_configured():
        logger.info(
            "Upload storage: S3/R2 bucket=%s (durable)",
            object_storage.bucket_name(),
        )
        return
    root = persistent_data_root()
    if _path_looks_ephemeral(root):
        logger.warning(
            "Upload storage is EPHEMERAL (root=%s). Avatars/screenshots will "
            "disappear on redeploy. Attach a Render disk at /var/data and set "
            "TRADEVERSE_DATA_DIR=/var/data, or configure S3_BUCKET + "
            "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (+ S3_ENDPOINT_URL for R2).",
            root,
        )
    else:
        logger.info("Upload storage: persistent disk root=%s", root)


def ensure_upload_dirs() -> dict:
    """Create avatar + screenshot + replay + playbook + ohlc dirs; return resolved paths."""
    root = persistent_data_root()
    base_uploads = os.path.join(root, "uploads")
    avatars = os.path.join(base_uploads, "avatars")
    shots = os.path.join(base_uploads, "trade_screenshots")
    replay = os.path.join(base_uploads, "replay")
    playbook = os.path.join(base_uploads, "playbook")
    ohlc = os.path.join(base_uploads, "ohlc_cache")
    for path in (base_uploads, avatars, shots, replay, playbook, ohlc):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return {
        "root": root,
        "uploads": base_uploads,
        "avatars": avatars,
        "trade_screenshots": shots,
        "replay": replay,
        "playbook": playbook,
        "ohlc_cache": ohlc,
        "backend": storage_backend_name(),
    }


def _normalize_rel(rel_path: str) -> str:
    s = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    if s.startswith("static/"):
        s = s[len("static/") :]
    return s


def _guess_content_type(rel_path: str) -> str:
    ctype, _ = mimetypes.guess_type(rel_path)
    return ctype or "application/octet-stream"


def _local_path_for(rel_path: str) -> str:
    """Absolute path under the active data root for a relative uploads/... key."""
    rel = _normalize_rel(rel_path)
    root = persistent_data_root()
    return os.path.join(root, rel)


def _write_local(rel_path: str, data: bytes) -> str:
    full = _local_path_for(rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(data)
    return full


def put_bytes(
    rel_path: str,
    data: bytes,
    content_type: Optional[str] = None,
) -> str:
    """
    Persist media bytes. Returns the relative path for DB storage.

    Writes to S3 when configured; always attempts a local write under the
    durable data root (or static fallback) so leftover local reads still work.
    """
    rel = _normalize_rel(rel_path)
    if not rel.startswith("uploads/"):
        raise ValueError(f"upload path must start with uploads/: {rel}")
    ctype = content_type or _guess_content_type(rel)

    s3_ok = False
    if object_storage.is_configured():
        s3_ok = object_storage.put_bytes(rel, data, content_type=ctype)
        if not s3_ok:
            logger.error("S3 upload failed for %s — falling back to local disk", rel)

    try:
        _write_local(rel, data)
    except OSError as exc:
        if not s3_ok:
            raise
        logger.warning("Local write skipped after S3 success for %s: %s", rel, exc)

    if object_storage.is_configured() and not s3_ok and not os.path.isfile(_local_path_for(rel)):
        raise OSError(f"Failed to persist upload: {rel}")

    return rel


def put_file_storage(rel_path: str, storage, content_type: Optional[str] = None) -> str:
    """Read a Werkzeug FileStorage and persist via put_bytes."""
    try:
        storage.seek(0)
    except Exception:
        pass
    data = storage.read()
    if not data:
        raise OSError("empty upload")
    ctype = content_type or getattr(storage, "mimetype", None) or _guess_content_type(rel_path)
    return put_bytes(rel_path, data, content_type=ctype)


def read_bytes(rel_path: str) -> Optional[bytes]:
    """Load bytes from local disk (any known path) or S3."""
    rel = _normalize_rel(rel_path)
    local = find_local_file(rel)
    if local and os.path.isfile(local):
        try:
            with open(local, "rb") as fh:
                return fh.read()
        except OSError:
            pass
    if object_storage.is_configured():
        return object_storage.get_bytes(rel)
    return None


def exists(rel_path: str) -> bool:
    rel = _normalize_rel(rel_path)
    if find_local_file(rel):
        return True
    if object_storage.is_configured() and object_storage.exists(rel):
        return True
    return False


def delete_upload(rel_path: str) -> None:
    """Best-effort delete from local candidates and S3."""
    rel = _normalize_rel(rel_path)
    if not rel or ".." in rel:
        return
    # All known local locations
    for folder_fn, prefix in (
        (avatars_dir, "uploads/avatars/"),
        (screenshots_dir, "uploads/trade_screenshots/"),
        (replay_dir, "uploads/replay/"),
        (playbook_images_dir, "uploads/playbook/"),
    ):
        if rel.startswith(prefix):
            name = rel[len(prefix) :]
            try:
                folders = [folder_fn()]
            except Exception:
                folders = []
            if prefix == "uploads/avatars/":
                folders.extend(_legacy_avatar_dirs())
            elif prefix == "uploads/trade_screenshots/":
                folders.extend(_legacy_screenshot_dirs())
            elif prefix == "uploads/playbook/":
                folders.extend(_legacy_playbook_dirs())
            elif prefix == "uploads/replay/":
                folders.extend(_legacy_replay_dirs())
            seen = set()
            for folder in folders:
                if not folder or folder in seen:
                    continue
                seen.add(folder)
                full = os.path.join(folder, os.path.basename(name))
                try:
                    if os.path.isfile(full):
                        os.remove(full)
                except OSError:
                    pass
            break
    # Also remove under current data root
    try:
        full = _local_path_for(rel)
        if os.path.isfile(full):
            os.remove(full)
    except OSError:
        pass
    if object_storage.is_configured():
        object_storage.delete(rel)


def find_local_file(rel_path: str) -> Optional[str]:
    """Absolute path if the file exists on any known local directory."""
    rel = _normalize_rel(rel_path)
    name = os.path.basename(rel)
    if not name or ".." in name or ".." in rel:
        return None

    candidates: List[str] = []
    # Active data root
    candidates.append(_local_path_for(rel))

    if rel.startswith("uploads/avatars/"):
        for d in [avatars_dir(), *_legacy_avatar_dirs()]:
            candidates.append(os.path.join(d, name))
    elif rel.startswith("uploads/trade_screenshots/"):
        for d in [screenshots_dir(), *_legacy_screenshot_dirs()]:
            candidates.append(os.path.join(d, name))
    elif rel.startswith("uploads/playbook/"):
        for d in [playbook_images_dir(), *_legacy_playbook_dirs()]:
            candidates.append(os.path.join(d, name))
    elif rel.startswith("uploads/replay/"):
        for d in [replay_dir(), *_legacy_replay_dirs()]:
            candidates.append(os.path.join(d, name))

    seen = set()
    for full in candidates:
        if not full or full in seen:
            continue
        seen.add(full)
        if os.path.isfile(full):
            return full
    return None


def serve_upload(rel_path: str):
    """
    Flask response for a relative uploads/... path, or None if missing.
    Local disk first, then S3.
    """
    rel = _normalize_rel(rel_path)
    local = find_local_file(rel)
    if local:
        directory, name = os.path.dirname(local), os.path.basename(local)
        return send_from_directory(directory, name)

    data = None
    if object_storage.is_configured():
        data = object_storage.get_bytes(rel)
    if data is None:
        return None
    return send_file(
        BytesIO(data),
        mimetype=_guess_content_type(rel),
        download_name=os.path.basename(rel),
        conditional=True,
    )


def avatars_dir() -> str:
    """
    Writable absolute directory for avatars.

    Prefer durable disk (TRADEVERSE_DATA_DIR) over ephemeral app/static.
    """
    candidates: List[str] = []
    env_root = _env_data_dir()
    if env_root:
        candidates.append(os.path.join(env_root, "uploads", "avatars"))
    if has_app_context():
        cfg_root = current_app.config.get("TRADEVERSE_DATA_DIR")
        if cfg_root and not _path_looks_ephemeral(str(cfg_root)):
            candidates.append(os.path.join(str(cfg_root), "uploads", "avatars"))
        cfg = current_app.config.get("AVATARS_FOLDER")
        if cfg:
            candidates.append(os.path.abspath(str(cfg)))
        candidates.append(
            os.path.abspath(os.path.join(current_app.root_path, "static", "uploads", "avatars"))
        )
    candidates.append(os.path.abspath(os.path.join("app", "static", "uploads", "avatars")))
    # Prefer non-ephemeral writable paths first
    ordered = sorted(
        enumerate(candidates),
        key=lambda iv: (0 if not _path_looks_ephemeral(os.path.dirname(os.path.dirname(iv[1]))) else 1, iv[0]),
    )
    seen = set()
    for _, folder in ordered:
        if not folder or folder in seen:
            continue
        seen.add(folder)
        if _is_writable_dir(folder):
            return folder
    return candidates[0] if candidates else os.path.abspath("uploads/avatars")


def static_avatars_mirror_dir() -> Optional[str]:
    """Secondary location under the app static tree (dev convenience only)."""
    if has_app_context():
        path = os.path.abspath(os.path.join(current_app.root_path, "static", "uploads", "avatars"))
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            return None
    return None


def screenshots_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("TRADE_SCREENSHOTS_FOLDER")
        if cfg and _is_writable_dir(str(cfg)):
            return str(cfg)
    return ensure_upload_dirs()["trade_screenshots"]


def replay_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("REPLAY_UPLOADS_FOLDER")
        if cfg and _is_writable_dir(str(cfg)):
            return str(cfg)
    return ensure_upload_dirs()["replay"]


def playbook_images_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("PLAYBOOK_IMAGES_FOLDER")
        if cfg and _is_writable_dir(str(cfg)):
            return str(cfg)
    return ensure_upload_dirs()["playbook"]


def _legacy_avatar_dirs() -> List[str]:
    dirs: List[str] = []
    if has_app_context():
        dirs.append(os.path.join(current_app.root_path, "static", "uploads", "avatars"))
    dirs.extend(["/tmp/uploads/avatars", "/tmp/avatars"])
    return dirs


def _legacy_screenshot_dirs() -> List[str]:
    dirs: List[str] = []
    if has_app_context():
        dirs.append(os.path.join(current_app.root_path, "static", "uploads", "trade_screenshots"))
    dirs.append("/tmp/uploads/trade_screenshots")
    return dirs


def _legacy_playbook_dirs() -> List[str]:
    dirs: List[str] = []
    if has_app_context():
        dirs.append(os.path.join(current_app.root_path, "static", "uploads", "playbook"))
    dirs.append("/tmp/uploads/playbook")
    return dirs


def _legacy_replay_dirs() -> List[str]:
    dirs: List[str] = []
    if has_app_context():
        dirs.append(os.path.join(current_app.root_path, "static", "uploads", "replay"))
    dirs.append("/tmp/uploads/replay")
    return dirs


def resolve_avatar_file(filename: str) -> Optional[Tuple[str, str]]:
    """Return (directory, filename) if found on local disk (legacy serve path)."""
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    found = find_local_file(f"uploads/avatars/{name}")
    if found:
        return os.path.dirname(found), os.path.basename(found)
    return None


def resolve_screenshot_file(filename: str) -> Optional[Tuple[str, str]]:
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    found = find_local_file(f"uploads/trade_screenshots/{name}")
    if found:
        return os.path.dirname(found), os.path.basename(found)
    return None


def resolve_playbook_file(filename: str) -> Optional[Tuple[str, str]]:
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    found = find_local_file(f"uploads/playbook/{name}")
    if found:
        return os.path.dirname(found), os.path.basename(found)
    return None


def resolve_replay_file(filename: str) -> Optional[Tuple[str, str]]:
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    found = find_local_file(f"uploads/replay/{name}")
    if found:
        return os.path.dirname(found), os.path.basename(found)
    return None


def media_url(stored_path: Optional[str], *, default_static: str = "img/default-avatar.svg") -> str:
    """Public URL for DB paths like uploads/avatars/x.png or uploads/trade_screenshots/y.jpg."""
    if not stored_path:
        try:
            return url_for("static", filename=default_static)
        except Exception:
            return f"/static/{default_static}"
    s = str(stored_path).strip()
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("/static/"):
        return s
    s = s.lstrip("/")
    if s.startswith("static/"):
        s = s[len("static/") :]

    # Optional direct public CDN/R2 URL (bucket must allow public GET)
    pub = object_storage.public_url_for(s) if object_storage.is_configured() else None
    if pub and s.startswith("uploads/"):
        return pub

    try:
        if s.startswith("uploads/avatars/"):
            fname = s.split("/", 2)[-1]
            return url_for("main.avatar_file", filename=fname)
        if s.startswith("uploads/trade_screenshots/"):
            return url_for("main.planner_screenshot_file", stored=s)
        if s.startswith("uploads/playbook/"):
            return url_for("main.playbook_image_file", stored=s)
        if s.startswith("uploads/replay/"):
            return url_for("replay.media", filename=s.split("/", 2)[-1])
        return url_for("static", filename=s)
    except Exception:
        if s.startswith("uploads/avatars/"):
            return f"/avatar/{s.split('/', 2)[-1]}"
        if s.startswith("uploads/trade_screenshots/"):
            return f"/planner-screenshot/{s}"
        if s.startswith("uploads/playbook/"):
            return f"/playbook-image/{s}"
        if s.startswith("uploads/replay/"):
            return f"/replay/media/{s.split('/', 2)[-1]}"
        return f"/static/{s}"
