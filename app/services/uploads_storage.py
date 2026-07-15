"""
Persistent user media storage (avatars, trade screenshots, replay).

On Render / ephemeral hosts, files under the app tree or /tmp disappear on
redeploy/restart. Prefer TRADEVERSE_DATA_DIR (persistent disk). Always fall
back to reading legacy static/ and /tmp paths so old links still resolve.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from flask import current_app, has_app_context, url_for


def _env_data_dir() -> Optional[str]:
    for key in ("TRADEVERSE_DATA_DIR", "PERSISTENT_DISK_PATH", "RENDER_DISK_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    return None


def persistent_data_root() -> str:
    """Durable root (e.g. /var/data). Uploads live under ``{root}/uploads/...``."""
    env = _env_data_dir()
    if env:
        return env
    if has_app_context():
        cfg = current_app.config.get("TRADEVERSE_DATA_DIR")
        if cfg:
            return str(cfg).rstrip("/")
        flask_env = (current_app.config.get("ENV") or os.environ.get("FLASK_ENV") or "").lower()
        if flask_env == "production":
            return "/var/data"
        return os.path.join(current_app.root_path, "static")
    if (os.environ.get("FLASK_ENV") or "").lower() == "production":
        return "/var/data"
    return os.path.join("app", "static")


def ensure_upload_dirs() -> dict:
    """Create avatar + screenshot + replay + playbook dirs; return resolved paths."""
    root = persistent_data_root()
    # root is either /var/data or .../static → uploads always under root/uploads
    base_uploads = os.path.join(root, "uploads")
    avatars = os.path.join(base_uploads, "avatars")
    shots = os.path.join(base_uploads, "trade_screenshots")
    replay = os.path.join(base_uploads, "replay")
    playbook = os.path.join(base_uploads, "playbook")
    for path in (base_uploads, avatars, shots, replay, playbook):
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
    }


def avatars_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("AVATARS_FOLDER")
        if cfg:
            try:
                os.makedirs(cfg, exist_ok=True)
            except OSError:
                pass
            return str(cfg)
    return ensure_upload_dirs()["avatars"]


def screenshots_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("TRADE_SCREENSHOTS_FOLDER")
        if cfg:
            try:
                os.makedirs(cfg, exist_ok=True)
            except OSError:
                pass
            return str(cfg)
    return ensure_upload_dirs()["trade_screenshots"]


def replay_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("REPLAY_UPLOADS_FOLDER")
        if cfg:
            try:
                os.makedirs(cfg, exist_ok=True)
            except OSError:
                pass
            return str(cfg)
    return ensure_upload_dirs()["replay"]


def playbook_images_dir() -> str:
    if has_app_context():
        cfg = current_app.config.get("PLAYBOOK_IMAGES_FOLDER")
        if cfg:
            try:
                os.makedirs(cfg, exist_ok=True)
            except OSError:
                pass
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


def resolve_avatar_file(filename: str) -> Optional[Tuple[str, str]]:
    """Return (directory, filename) if found on disk."""
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    candidates = [avatars_dir(), *_legacy_avatar_dirs()]
    seen = set()
    for folder in candidates:
        if not folder or folder in seen:
            continue
        seen.add(folder)
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            return folder, name
    return None


def resolve_screenshot_file(filename: str) -> Optional[Tuple[str, str]]:
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    candidates = [screenshots_dir(), *_legacy_screenshot_dirs()]
    seen = set()
    for folder in candidates:
        if not folder or folder in seen:
            continue
        seen.add(folder)
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            return folder, name
    return None


def resolve_playbook_file(filename: str) -> Optional[Tuple[str, str]]:
    name = os.path.basename((filename or "").strip())
    if not name or ".." in name:
        return None
    candidates = [playbook_images_dir(), *_legacy_playbook_dirs()]
    seen = set()
    for folder in candidates:
        if not folder or folder in seen:
            continue
        seen.add(folder)
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            return folder, name
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
    try:
        if s.startswith("uploads/avatars/"):
            fname = s.split("/", 2)[-1]
            return url_for("main.avatar_file", filename=fname)
        if s.startswith("uploads/trade_screenshots/"):
            return url_for("main.planner_screenshot_file", stored=s)
        if s.startswith("uploads/playbook/"):
            return url_for("main.playbook_image_file", stored=s)
        return url_for("static", filename=s)
    except Exception:
        if s.startswith("uploads/avatars/"):
            return f"/avatar/{s.split('/', 2)[-1]}"
        if s.startswith("uploads/trade_screenshots/"):
            return f"/planner-screenshot/{s}"
        if s.startswith("uploads/playbook/"):
            return f"/playbook-image/{s}"
        return f"/static/{s}"
