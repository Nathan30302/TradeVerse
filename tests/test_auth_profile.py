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
