"""Durable upload storage: disk + S3-compatible backends."""

from __future__ import annotations

import os

import pytest

from app import create_app, db
from app.services import object_storage
from app.services import uploads_storage as us


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEVERSE_DATA_DIR", str(tmp_path))
    application = create_app("testing")
    application.config["TRADEVERSE_DATA_DIR"] = str(tmp_path)
    with application.app_context():
        db.drop_all()
        db.create_all()
        yield application


@pytest.fixture(autouse=True)
def _reset_object_storage(monkeypatch):
    object_storage.reset_client_cache()
    for key in (
        "S3_BUCKET",
        "AWS_S3_BUCKET",
        "R2_BUCKET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_ENDPOINT_URL",
        "S3_PUBLIC_BASE_URL",
        "S3_PREFIX",
        "UPLOAD_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)
    object_storage.reset_client_cache()
    yield
    object_storage.reset_client_cache()


def test_put_bytes_disk_and_read_back(app, tmp_path):
    with app.app_context():
        rel = "uploads/avatars/u1_test.png"
        data = b"\x89PNG\r\n\x1a\nfake"
        assert us.put_bytes(rel, data, content_type="image/png") == rel
        assert us.exists(rel)
        assert us.read_bytes(rel) == data
        local = us.find_local_file(rel)
        assert local and os.path.isfile(local)


def test_serve_upload_from_disk(app, tmp_path):
    with app.app_context():
        rel = "uploads/trade_screenshots/before_1.png"
        us.put_bytes(rel, b"img-bytes", content_type="image/png")
        with app.test_request_context("/"):
            resp = us.serve_upload(rel)
            assert resp is not None
            assert resp.status_code == 200


def test_delete_upload_removes_local(app, tmp_path):
    with app.app_context():
        rel = "uploads/playbook/u9_abc.png"
        us.put_bytes(rel, b"pb")
        us.delete_upload(rel)
        assert not us.exists(rel)


def test_object_storage_put_get_via_fake_client(app, tmp_path, monkeypatch):
    store = {}

    class FakeBody:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

    class FakeClient:
        class exceptions:
            class NoSuchKey(Exception):
                pass

        def put_object(self, Bucket, Key, Body, **kwargs):
            store[Key] = Body if isinstance(Body, (bytes, bytearray)) else bytes(Body)

        def get_object(self, Bucket, Key):
            if Key not in store:
                raise FakeClient.exceptions.NoSuchKey()
            return {"Body": FakeBody(store[Key])}

        def head_object(self, Bucket, Key):
            if Key not in store:
                raise Exception("404")
            return {}

        def delete_object(self, Bucket, Key):
            store.pop(Key, None)

    monkeypatch.setenv("S3_BUCKET", "tv-test")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aki")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("S3_PREFIX", "prod")
    object_storage.reset_client_cache()
    monkeypatch.setattr(object_storage, "_client", lambda: FakeClient())

    assert object_storage.is_configured()
    assert object_storage.object_key("uploads/avatars/a.png") == "prod/uploads/avatars/a.png"

    with app.app_context():
        rel = "uploads/avatars/a.png"
        us.put_bytes(rel, b"avatar-bytes", content_type="image/png")
        assert store["prod/uploads/avatars/a.png"] == b"avatar-bytes"
        local = us.find_local_file(rel)
        if local and os.path.isfile(local):
            os.remove(local)
        assert us.read_bytes(rel) == b"avatar-bytes"
        with app.test_request_context("/"):
            resp = us.serve_upload(rel)
            assert resp is not None


def test_storage_backend_name_ephemeral_without_disk(app, monkeypatch, tmp_path):
    static_like = tmp_path / "app" / "static"
    static_like.mkdir(parents=True)
    monkeypatch.setenv("TRADEVERSE_DATA_DIR", str(static_like))
    app.config["TRADEVERSE_DATA_DIR"] = str(static_like)
    with app.app_context():
        assert us.storage_backend_name() == "ephemeral"


def test_media_url_avatar_proxy(app):
    with app.app_context():
        url = us.media_url("uploads/avatars/u1_abc.png")
        assert "/avatar/u1_abc.png" in url


def test_storage_backend_s3_when_configured(app, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "tv")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "y")
    object_storage.reset_client_cache()
    with app.app_context():
        assert us.storage_backend_name() == "s3"
