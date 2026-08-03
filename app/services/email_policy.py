"""
Signup email policy: format checks + disposable / fake domain blocklist.

Default stance is a blocklist (allow real providers worldwide) rather than a
gmail-only allowlist. Testing may relax blocks via config.
"""

from __future__ import annotations

import os
import re
from typing import Optional

# RFC-lite local@domain; register route also uses a similar pattern.
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Domains that are not usable for contacting a real person / are common abuse vectors.
# Keep lowercase; matching is on the registrable email domain (last two labels when
# obvious, else full domain after @).
BLOCKED_EMAIL_DOMAINS = frozenset(
    {
        # Reserved / documentation / local
        "example.com",
        "example.org",
        "example.net",
        "example.edu",
        "test.com",
        "test.org",
        "localhost",
        "invalid",
        "localdomain",
        # Disposable / temporary (common)
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "sharklasers.com",
        "grr.la",
        "guerrillamailblock.com",
        "pokemail.net",
        "spam4.me",
        "10minutemail.com",
        "10minutemail.net",
        "tempmail.com",
        "temp-mail.org",
        "temp-mail.io",
        "tmpmail.org",
        "tmpmail.net",
        "throwaway.email",
        "yopmail.com",
        "yopmail.fr",
        "cool.fr.nf",
        "jetable.org",
        "nwldx.com",
        "trashmail.com",
        "trashmail.me",
        "trashmail.net",
        "maildrop.cc",
        "discard.email",
        "discardmail.com",
        "mailnesia.com",
        "getnada.com",
        "nada.email",
        "emailondeck.com",
        "fakeinbox.com",
        "mailcatch.com",
        "mailnull.com",
        "spamgourmet.com",
        "mintemail.com",
        "mytemp.email",
        "tempail.com",
        "tempr.email",
        "dispostable.com",
        "mailforspam.com",
        "spamobox.com",
        "moakt.com",
        "inboxbear.com",
        "mailtemp.net",
        "tempinbox.com",
        "throwam.com",
        "getairmail.com",
        "mohmal.com",
        "burnermail.io",
        "mailpoof.com",
        "mailsac.com",
        "guerrillamail.biz",
    }
)


def normalize_email(raw: str | None) -> str:
    """Lowercase + strip; empty string if missing."""
    return (raw or "").strip().lower()


def email_domain(email: str) -> str:
    """Return domain part of a normalized email, or ''."""
    e = normalize_email(email)
    if "@" not in e:
        return ""
    return e.rsplit("@", 1)[-1].strip().lower()


def _extra_blocked_from_env() -> set[str]:
    raw = (os.environ.get("TV_EXTRA_BLOCKED_EMAIL_DOMAINS") or "").strip()
    if not raw:
        return set()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def is_blocked_email_domain(email: str, *, allow_test_domains: bool = False) -> bool:
    """
    True if the email's domain is disposable, reserved, or otherwise blocked.

    When allow_test_domains is True (testing / explicit env), example.com and
    similar reserved domains are permitted so automated tests can still register.
    """
    domain = email_domain(email)
    if not domain:
        return True
    if allow_test_domains and domain in {
        "example.com",
        "example.org",
        "example.net",
        "test.com",
    }:
        return False
    blocked = set(BLOCKED_EMAIL_DOMAINS) | _extra_blocked_from_env()
    if domain in blocked:
        return True
    # Block subdomains of blocked parents (e.g. foo.mailinator.com)
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in blocked:
            return True
    return False


def validate_signup_email(
    raw: str | None,
    *,
    allow_test_domains: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """
    Validate and normalize a signup email.

    Returns (normalized_email, error_message). error_message is None on success.
    """
    email = normalize_email(raw)
    if not email:
        return None, "Email is required."
    if len(email) > 120:
        return None, "Email address is too long."
    if not _EMAIL_RE.match(email):
        return None, "Please provide a valid email address."
    if is_blocked_email_domain(email, allow_test_domains=allow_test_domains):
        return (
            None,
            "Please use a real email address we can contact you on "
            "(for example Gmail, iCloud, Outlook). Temporary or fake addresses are not allowed.",
        )
    return email, None
