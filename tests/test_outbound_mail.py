"""Outbound mail backends (Brevo / Resend / SMTP preference)."""

import pytest

from app import create_app
from app.services.outbound_mail import mail_is_configured, preferred_backend


@pytest.fixture
def app():
    return create_app("testing")


def test_preferred_backend_none(monkeypatch, app):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("SENDINBLUE_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    with app.app_context():
        app.config["BREVO_API_KEY"] = ""
        app.config["RESEND_API_KEY"] = ""
        app.config["MAIL_USERNAME"] = None
        app.config["MAIL_PASSWORD"] = None
        assert preferred_backend() == "none"
        assert mail_is_configured() is False


def test_preferred_backend_brevo(monkeypatch, app):
    monkeypatch.setenv("BREVO_API_KEY", "x-test-key")
    with app.app_context():
        assert preferred_backend() == "brevo"
        assert mail_is_configured() is True
