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
