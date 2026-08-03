"""Registration email quality, duplicates, and abuse guards."""

import pytest

from app import create_app, db
from app.models.user import User
from app import schema_compat
from app.services.email_policy import is_blocked_email_domain, validate_signup_email
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


def _signup(client, *, username, email, full_name="New User", password="SecurePass1!", **extra):
    data = {
        "username": username,
        "email": email,
        "password": password,
        "confirm_password": password,
        "full_name": full_name,
        "country_code": "US",
        **extra,
    }
    return client.post("/auth/register", data=data, follow_redirects=False)


def test_register_creates_user_and_logs_in(app, client):
    resp = _signup(client, username="newsignup", email="newsignup@example.com")
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


def test_login_succeeds_for_existing_user(app, client):
    with app.app_context():
        u = User(username="signintest", email="signintest@example.com", full_name="Sign In Test")
        u.set_password("SecurePass1!")
        db.session.add(u)
        db.session.commit()

    resp = client.post(
        "/auth/login",
        data={
            "username": "signintest",
            "password": "SecurePass1!",
            "remember": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/dashboard" in (resp.headers.get("Location") or "")

    with client.session_transaction() as sess:
        assert sess.get("_user_id") is not None


def test_register_duplicate_email_flash(app, client):
    _signup(client, username="userone", email="dup@example.com", full_name="First User")
    client.get("/auth/logout", follow_redirects=True)
    resp = client.post(
        "/auth/register",
        data={
            "username": "usertwo",
            "email": "dup@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "Second User",
            "country_code": "US",
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
            "password": "short",
            "confirm_password": "short",
            "full_name": "Weak Pass",
            "country_code": "US",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "8 characters" in body or "password" in body


def test_register_rejects_password_without_number(app, client):
    resp = client.post(
        "/auth/register",
        data={
            "username": "nonum",
            "email": "nonum@example.com",
            "password": "PasswordOnly",
            "confirm_password": "PasswordOnly",
            "full_name": "No Num",
            "country_code": "US",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "number" in body


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
            "country_code": "US",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "full name" in body or "accounts" in body


def test_email_policy_blocks_example_and_disposable():
    assert is_blocked_email_domain("bot@example.com", allow_test_domains=False)
    assert is_blocked_email_domain("x@mailinator.com", allow_test_domains=False)
    assert not is_blocked_email_domain("trader@gmail.com", allow_test_domains=False)
    assert not is_blocked_email_domain("me@icloud.com", allow_test_domains=False)
    email, err = validate_signup_email("qa3@example.com", allow_test_domains=False)
    assert email is None and err and "real email" in err.lower()


def test_register_rejects_example_com_when_policy_enforced(app, client):
    app.config["ALLOW_TEST_EMAIL_DOMAINS"] = False
    resp = client.post(
        "/auth/register",
        data={
            "username": "qa3fake",
            "email": "qa3_ask@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "QA Fake",
            "country_code": "US",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "real email" in body or "temporary" in body or "fake" in body
    with app.app_context():
        assert User.query.filter_by(username="qa3fake").first() is None


def test_register_accepts_gmail_when_policy_enforced(app, client):
    app.config["ALLOW_TEST_EMAIL_DOMAINS"] = False
    resp = _signup(client, username="realtrader", email="realtrader@gmail.com")
    assert resp.status_code in (302, 303)
    with app.app_context():
        assert User.query.filter_by(email="realtrader@gmail.com").first() is not None


def test_register_rate_limits_same_ip(app, client):
    app.config["REGISTER_MAX_PER_IP_HOUR"] = 2
    app.config["REGISTER_IP_WINDOW_SECONDS"] = 3600
    reset_register_rate_limits()
    assert _signup(client, username="rate1", email="rate1@example.com").status_code in (302, 303)
    client.get("/auth/logout", follow_redirects=True)
    assert _signup(client, username="rate2", email="rate2@example.com").status_code in (302, 303)
    client.get("/auth/logout", follow_redirects=True)
    resp = client.post(
        "/auth/register",
        data={
            "username": "rate3",
            "email": "rate3@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!",
            "full_name": "Rate Three",
            "country_code": "US",
        },
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True).lower()
    assert "too many" in body or "try again later" in body
    with app.app_context():
        assert User.query.filter_by(username="rate3").first() is None
