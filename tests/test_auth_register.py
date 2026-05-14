"""Registration flow: schema-compat inserts, trial env parsing, auto-login."""

import pytest

from app import create_app, db
from app.models.user import User
from app import schema_compat


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_register_creates_user_and_logs_in(app, client):
    resp = client.post(
        "/auth/register",
        data={
            "username": "newsignup",
            "email": "newsignup@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "New User",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/dashboard" in resp.headers.get("Location", "")

    with client.session_transaction() as sess:
        uid = sess.get("_user_id")
    assert uid is not None

    with app.app_context():
        u = db.session.get(User, int(uid))
        assert u is not None
        assert u.email == "newsignup@example.com"
        assert u.subscription_tier == "pro_plus"
        assert u.theme == "dark"


def test_register_duplicate_email_flash(app, client):
    client.post(
        "/auth/register",
        data={
            "username": "userone",
            "email": "dup@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "First User",
        },
        follow_redirects=True,
    )
    resp = client.post(
        "/auth/register",
        data={
            "username": "usertwo",
            "email": "dup@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "Second User",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "already" in body.lower() or "registered" in body.lower()


def test_register_rejects_weak_password(app, client):
    resp = client.post(
        "/auth/register",
        data={
            "username": "weakpw",
            "email": "weakpw@example.com",
            "password": "alllowercase1!",
            "confirm_password": "alllowercase1!",
            "full_name": "Weak Pass",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "uppercase" in body


def test_register_limits_duplicate_full_name(app, client):
    """Seed two accounts with the same display name, then block a third signup."""
    pw = "SecurePass1!"
    name = "Unique Limit Test Name"
    with app.app_context():
        for i in range(2):
            u = User(username=f"lim{i}", email=f"lim{i}@example.com", full_name=name)
            u.set_password(pw)
            db.session.add(u)
        db.session.commit()

    resp = client.post(
        "/auth/register",
        data={
            "username": "lim3",
            "email": "lim3@example.com",
            "password": pw,
            "confirm_password": pw,
            "full_name": name,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "full name" in body or "accounts" in body
