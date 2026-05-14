"""Profile POST: core fields save even when optional country/phone validation fails."""

import pytest

from app import create_app, db, schema_compat
from app.models.user import User


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


def test_profile_saves_full_name_when_phone_invalid(app, client):
    user = User(
        username="profuser",
        email="prof@example.com",
        full_name="Old Name",
        phone_number="+15551234567",
        country_code="US",
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)

    resp = client.post(
        "/auth/profile",
        data={
            "full_name": "New Legal Name",
            "bio": "",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
            "country_code": "US",
            "phone_number": "bad",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with app.app_context():
        db.session.expire_all()
        u = db.session.get(User, user.id)
        assert u.full_name == "New Legal Name"
        assert u.phone_number == "+15551234567"


def test_profile_preserves_phone_when_settings_form_omits_country_fields(app, client):
    """Account settings posts no country/phone keys — must not clear stored values."""
    user = User(
        username="setuser",
        email="set@example.com",
        full_name="A",
        phone_number="+260971234567",
        country_code="ZM",
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)

    resp = client.post(
        "/auth/profile",
        data={
            "full_name": "A",
            "bio": "",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
            "after_save": "settings",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with app.app_context():
        db.session.expire_all()
        u = db.session.get(User, user.id)
        assert u.phone_number == "+260971234567"
        assert u.country_code == "ZM"
        assert u.preferred_currency == "USD"


def test_profile_get_renders(app, client):
    user = User(username="getprof", email="get@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/auth/login",
        data={"username": "getprof", "password": "password123"},
        follow_redirects=False,
    )
    resp = client.get("/auth/profile")
    assert resp.status_code == 200
    assert b"My Profile" in resp.data


def test_profile_truncates_long_full_name(app, client):
    user = User(username="longname", email="long@example.com", full_name="Short")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)

    long_name = "N" * 150
    client.post(
        "/auth/profile",
        data={
            "full_name": long_name,
            "bio": "",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
        },
        follow_redirects=False,
    )
    with app.app_context():
        u = db.session.get(User, user.id)
        assert u.full_name == ("N" * 100)


def test_profile_strips_nul_bytes_from_bio(app, client):
    user = User(username="nulbio", email="nul@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)

    client.post(
        "/auth/profile",
        data={
            "full_name": "X",
            "bio": "hello\x00world",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
        },
        follow_redirects=False,
    )
    with app.app_context():
        u = db.session.get(User, user.id)
        assert u.bio == "helloworld"


def test_settings_page_includes_profile_fields(app, client):
    user = User(username="setview", email="setview@example.com", country_code="US")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/auth/login",
        data={"username": "setview", "password": "password123"},
        follow_redirects=False,
    )
    resp = client.get("/auth/settings")
    assert resp.status_code == 200
    assert b"multipart/form-data" in resp.data
    assert b'name="avatar"' in resp.data
    assert b'settings-country' in resp.data


def test_login_history_get(app, client):
    user = User(username="histuser", email="hist@example.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/auth/login",
        data={"username": "histuser", "password": "password123"},
        follow_redirects=False,
    )
    resp = client.get("/auth/login-history")
    assert resp.status_code == 200
    assert b"Login history" in resp.data
