"""
Canonical URLs, sitemap base, and robots for search engines.

Set PUBLIC_SITE_URL (https://yourdomain.com, no trailing slash) in production so
sitemaps, canonical tags, and robots Sitemap: line match your Google Search Console
property (avoids www/non-www and http/https redirect mismatches).
"""

from __future__ import annotations


def public_site_origin(app, request) -> str:
    """
    Preferred absolute origin for canonical URLs and sitemap <loc> entries.

    Uses PUBLIC_SITE_URL when set; otherwise derives from the current request
    (respects X-Forwarded-Proto behind reverse proxies).
    """
    cfg = (app.config.get("PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if cfg:
        return cfg
    host = (getattr(request, "host", None) or "").strip()
    if not host:
        try:
            ur = (getattr(request, "url_root", None) or "").strip()
            if ur:
                return ur.rstrip("/")
        except Exception:
            pass
        return ""
    proto = "https"
    if not getattr(request, "is_secure", False):
        try:
            xf = (request.headers.get("X-Forwarded-Proto", "") or "").lower()
        except Exception:
            xf = ""
        if xf != "https":
            proto = "http"
    return f"{proto}://{host}"


def canonical_url_for_request(app, request) -> str:
    """Full canonical URL for the current path (no query string)."""
    base = public_site_origin(app, request).rstrip("/")
    if not base:
        return ""
    path = getattr(request, "path", None) or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return f"{base}{path}"
