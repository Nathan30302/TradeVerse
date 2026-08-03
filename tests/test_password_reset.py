"""Password / username recovery via email."""

from unittest.mock import patch

import pytest

from app import create_app, db, schema_compat
from app.models.user import User
from app.services.account_recovery import load_reset_token, make_reset_token
from app.services.signup_abuse import reset_register_rate_limits


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        reset_register_rate_limits()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _user(app, email="trader@example.com", username="trader1", password="SecurePass1!"):
    with app.app_context():
        u = User(username=username, email=email, full_name="Trader One")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def test_reset_token_roundtrip(app):
    uid = _user(app)
    with app.app_context():
        u = db.session.get(User, uid)
        token = make_reset_token(u)
        payload, err = load_reset_token(token)
        assert err is None
        assert payload["uid"] == uid
        assert payload["email"] == "trader@example.com"


def test_forgot_password_page_loads(client):
    resp = client.get("/auth/forgot-password")
    assert resp.status_code == 200
    assert b"reset" in resp.data.lower() or b"email" in resp.data.lower()


def test_forgot_password_generic_success_without_mail(app, client):
    _user(app)
    with patch("app.services.account_recovery.mail_is_configured", return_value=False):
        resp = client.post(
            "/auth/forgot-password",
            data={"email": "trader@example.com"},
            follow_redirects=True,
        )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "contact" in body or "not configured" in body or "email" in body


def test_forgot_password_sends_when_mail_ok(app, client):
    _user(app)
    with patch("app.services.account_recovery.mail_is_configured", return_value=True), patch(
        "app.services.account_recovery.send_recovery_email", return_value=True
    ) as send:
        resp = client.post(
            "/auth/forgot-password",
            data={"email": "trader@example.com"},
            follow_redirects=True,
        )
    assert resp.status_code == 200
    assert send.called
    body = resp.get_data(as_text=True).lower()
    assert "if an account exists" in body or "sent" in body


def test_reset_password_updates_login(app, client):
    uid = _user(app)
    with app.app_context():
        u = db.session.get(User, uid)
        token = make_reset_token(u)

    resp = client.post(
        f"/auth/reset-password/{token}",
        data={"new_password": "NewPass99", "confirm_password": "NewPass99"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/auth/login" in (resp.headers.get("Location") or "")

    login = client.post(
        "/auth/login",
        data={"username": "trader1", "password": "NewPass99"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)


def test_login_page_has_forgot_link(client):
    resp = client.get("/auth/login")
    assert b"forgot-password" in resp.data or b"Forgot password" in resp.data
