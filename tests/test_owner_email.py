"""Unit tests for owner email helper (no SMTP)."""

from types import SimpleNamespace

from app.services.owner_email import apply_email_placeholders, mail_is_configured


def test_apply_email_placeholders_replaces():
    u = SimpleNamespace(username="jane", email="jane@example.com")
    out = apply_email_placeholders(
        "Hi {username} — {app_name} — {email} — {login_url}",
        user=u,
        app_name="TradeVerse",
        login_url="https://app.example.com/auth/login",
    )
    assert "jane" in out
    assert "jane@example.com" in out
    assert "TradeVerse" in out
    assert "https://app.example.com/auth/login" in out


def test_mail_is_configured_requires_all():
    assert not mail_is_configured({})
    assert mail_is_configured(
        {"MAIL_USERNAME": "a@x.com", "MAIL_PASSWORD": "secret"}
    )
    assert mail_is_configured(
        {
            "MAIL_USERNAME": "a",
            "MAIL_PASSWORD": "b",
            "MAIL_DEFAULT_SENDER": "noreply@x.com",
        }
    )
