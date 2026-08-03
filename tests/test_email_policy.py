"""Unit tests for signup email policy (no Flask app required)."""

from app.services.email_policy import is_blocked_email_domain, validate_signup_email


def test_blocks_reserved_and_disposable():
    assert is_blocked_email_domain("a@example.com")
    assert is_blocked_email_domain("a@EXAMPLE.COM")
    assert is_blocked_email_domain("x@mailinator.com")
    assert is_blocked_email_domain("x@foo.mailinator.com")
    assert is_blocked_email_domain("x@yopmail.com")


def test_allows_common_providers():
    for addr in (
        "trader@gmail.com",
        "me@icloud.com",
        "name@outlook.com",
        "x@yahoo.com",
        "a@proton.me",
    ):
        assert not is_blocked_email_domain(addr)
        email, err = validate_signup_email(addr)
        assert err is None and email == addr.lower()


def test_allow_test_domains_flag():
    assert not is_blocked_email_domain("qa@example.com", allow_test_domains=True)
    assert is_blocked_email_domain("qa@example.com", allow_test_domains=False)
