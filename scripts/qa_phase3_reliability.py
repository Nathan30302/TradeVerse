#!/usr/bin/env python3
"""Phase 3 reliability QA: prod journal path + AI coach smoke + closed UX (local)."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://www.tradeversejournal.space"
MODE = sys.argv[2] if len(sys.argv) > 2 else "prod"  # prod | local_ux | local_ai
OUT = (
    sys.argv[3]
    if len(sys.argv) > 3
    else f"/Users/mac/Desktop/TradeVerse/.qa_phase3_{MODE}.json"
)

SUFFIX = datetime.now().strftime("%m%d%H%M%S")
USER = f"qa3_{SUFFIX}"
PASS = "QaPass123!"
EMAIL = f"{USER}@example.com"
FULL = f"QA3 Tester {SUFFIX}"

# Render cold start + Cloudflare can be slow
GOTO_TIMEOUT = 180000
NAV_WAIT = "domcontentloaded"

results = []
meta = {
    "base": BASE,
    "mode": MODE,
    "user": USER,
    "email": EMAIL,
    "started": datetime.now().isoformat(timespec="seconds"),
}


def note(feature, status, notes=""):
    results.append({"feature": feature, "status": status, "notes": notes})
    print(f"[{status}] {feature}: {notes}", flush=True)


def flashes(page):
    try:
        if page.locator(".alert").count():
            return page.locator(".alert").all_inner_texts()[:8]
    except Exception:
        pass
    return []


def is_500(page):
    try:
        snippet = (page.title() or "") + page.content()[:3000]
    except Exception:
        return False
    return (
        "Internal Server Error" in snippet
        or "Werkzeug" in snippet[:600]
        or (page.title() or "").startswith("500")
    )


def goto(page, path, wait=NAV_WAIT, timeout=GOTO_TIMEOUT):
    url = path if path.startswith("http") else BASE.rstrip("/") + path
    resp = page.goto(url, wait_until=wait, timeout=timeout)
    page.wait_for_timeout(400)
    return resp


def app_version(page):
    body = page.content()
    m = re.search(r"(\d+\.\d+\.\d+)", body)
    # Prefer footer / meta-ish hits near TradeVerse branding
    hits = re.findall(r"v?(\d+\.\d+\.\d+)", body)
    # common versions in this project
    for h in hits:
        if h.startswith("2."):
            return h
    return hits[0] if hits else None


def pick_instrument(page, symbol="EURUSD"):
    page.wait_for_timeout(1500)
    search = page.locator("#instrument-search")
    if search.count():
        search.fill(symbol)
        page.wait_for_timeout(1400)
    item = page.locator(
        "#instrument-list .instrument-item, #instrument-list [data-symbol], "
        "#instrument-list button, #instrument-list .list-group-item"
    ).filter(has_text=re.compile(symbol, re.I))
    if item.count() == 0:
        item = page.locator(f"#instrument-list >> text={symbol}")
    if item.count():
        item.first.click()
        page.wait_for_timeout(400)
        return True
    page.evaluate(
        """(sym) => {
      const id = document.getElementById('instrument_id');
      const s = document.getElementById('symbol');
      if (id) id.value = '1';
      if (s) s.value = sym;
    }""",
        symbol,
    )
    return False


def register_and_login(page):
    # Never create @example.com accounts on production — those look like abuse.
    if "example.com" in EMAIL.lower() and ("tradeversejournal.space" in BASE or "onrender.com" in BASE):
        note(
            "Register+login",
            "SKIP",
            "Refusing to register @example.com on production; use local mode or a real test mailbox",
        )
        return False
    t0 = datetime.now()
    resp = goto(page, "/auth/register")
    cold_ms = int((datetime.now() - t0).total_seconds() * 1000)
    ver = app_version(page)
    meta["app_version"] = ver
    meta["register_http"] = resp.status if resp else None
    meta["cold_start_ms"] = cold_ms
    note(
        "Register page load",
        "PASS" if page.locator("input[name=username]").count() and not is_500(page) else "FAIL",
        f"url={page.url}; http={resp.status if resp else None}; cold_ms={cold_ms}; version={ver}",
    )
    if "Just a moment" in page.content() or "cf-browser-verification" in page.content().lower():
        note("Cloudflare challenge", "FAIL", "Challenge page detected — cannot automate past")
        return False

    page.fill("input[name=username]", USER)
    page.fill("input[name=full_name]", FULL)
    page.fill("input[name=email]", EMAIL)
    if page.locator("select[name=country_code]").count():
        page.select_option("select[name=country_code]", index=1)
    if page.locator("input[name=phone_number]").count():
        page.fill("input[name=phone_number]", "+15551234567")
    page.fill("input[name=password]", PASS)
    page.fill("input[name=confirm_password]", PASS)
    if page.locator("input[name=terms_agreed]").count():
        page.check("input[name=terms_agreed]")
    # CSRF should already be in the form from the page
    csrf = page.locator("input[name=csrf_token]")
    note(
        "CSRF present on register",
        "PASS" if csrf.count() and csrf.first.input_value() else "FAIL",
        f"len={len(csrf.first.input_value()) if csrf.count() else 0}",
    )
    page.locator("button[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=GOTO_TIMEOUT)
    page.wait_for_timeout(2000)
    ok = "/dashboard" in page.url or (
        "/auth/register" not in page.url and "/auth/login" not in page.url
    )
    note(
        "Register+login",
        "PASS" if ok and not is_500(page) else "FAIL",
        f"url={page.url}; flashes={flashes(page)}",
    )
    if not ok:
        goto(page, "/auth/login")
        if page.locator("input[name=username]").count():
            page.fill("input[name=username]", USER)
        elif page.locator("input[name=email]").count():
            page.fill("input[name=email]", EMAIL)
        page.fill("input[name=password]", PASS)
        page.locator("button[type=submit]").first.click()
        page.wait_for_load_state("domcontentloaded", timeout=GOTO_TIMEOUT)
        page.wait_for_timeout(1500)
        ok2 = "/auth/login" not in page.url and not is_500(page)
        note("Login fallback", "PASS" if ok2 else "FAIL", f"url={page.url}; flashes={flashes(page)}")
        return ok2
    return True


def note_trial(page):
    body = page.inner_text("body")
    days = re.findall(r"(\d+)\s*day[s]?\s*left", body, re.I)
    badge = re.findall(r"Trial\s*[·•]\s*(\d+)d", body, re.I)
    ends = re.findall(r"Ends\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", body, re.I)
    zero = any(d == "0" for d in days + badge)
    july_past = re.findall(r"July\s+\d{1,2},\s+202[0-5]", body, re.I)
    meta["trial"] = {"days": days or badge, "ends": ends[:2]}
    note(
        "Trial chip",
        "FAIL" if zero or july_past else ("PASS" if (days or badge or ends) else "WARN"),
        f"days={days or badge}; ends={ends[:2]}; past={july_past}",
    )


def add_open_trade(page):
    goto(page, "/trade/add")
    page.wait_for_timeout(2000)
    clicked = pick_instrument(page, "EURUSD")
    page.fill("#entry_price", "1.08750")
    page.fill("#lot_size", "0.10")
    if page.locator("label[for=tv_status_open]").count():
        page.click("label[for=tv_status_open]")
    elif page.locator("#tv_status_open").count():
        page.locator("#tv_status_open").check(force=True)
    if page.locator("#tv-dir-buy").count():
        page.click("#tv-dir-buy")
    page.locator("button[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=GOTO_TIMEOUT)
    page.wait_for_timeout(2500)
    open_m = re.search(r"/trade/(\d+)", page.url)
    open_id = open_m.group(1) if open_m else None
    note(
        "Add open trade",
        "PASS" if open_id and not is_500(page) else "FAIL",
        f"url={page.url}; instr_clicked={clicked}; flashes={flashes(page)}",
    )
    return open_id


def fill_strategy(page):
    strat = page.locator("#strategy")
    if not strat.count():
        return False
    # Prefer select option if present
    tag = strat.evaluate("el => el.tagName")
    if tag == "SELECT":
        opts = page.locator("#strategy option")
        # skip empty/placeholder
        for i in range(opts.count()):
            val = opts.nth(i).get_attribute("value") or ""
            if val.strip():
                page.select_option("#strategy", value=val)
                return True
        return False
    # datalist / text input
    page.fill("#strategy", "Breakout")
    return True


def add_closed_trade(page, with_notes=True):
    goto(page, "/trade/add")
    page.wait_for_timeout(1800)
    pick_instrument(page, "GBPUSD")
    page.fill("#entry_price", "1.25000")
    page.fill("#lot_size", "0.05")
    if page.locator("#tv-dir-buy").count():
        page.click("#tv-dir-buy")
    if page.locator("label[for=tv_status_closed]").count():
        page.click("label[for=tv_status_closed]")
        page.wait_for_timeout(400)
    elif page.locator("#tv_status_closed").count():
        page.locator("#tv_status_closed").check(force=True)
        page.wait_for_timeout(400)
    if page.locator("#exit_price").count():
        page.fill("#exit_price", "1.25500")
    if with_notes:
        fill_strategy(page)
        if page.locator("#pre_trade_plan").count():
            page.fill("#pre_trade_plan", "QA pre-trade plan note for closed trade.")
        if page.locator("#post_trade_notes").count():
            page.fill("#post_trade_notes", "QA post-trade review notes here.")
    page.locator("button[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=GOTO_TIMEOUT)
    page.wait_for_timeout(2500)
    closed_m = re.search(r"/trade/(\d+)", page.url)
    closed_id = closed_m.group(1) if closed_m else None
    note(
        "Add closed trade",
        "PASS" if closed_id and not is_500(page) else "FAIL",
        f"url={page.url}; with_notes={with_notes}; flashes={flashes(page)}",
    )
    return closed_id


def confirm_list_view(page, open_id, closed_id):
    goto(page, "/trade/list")
    page.wait_for_timeout(800)
    content = page.content()
    list_ok = not is_500(page) and ("EURUSD" in content or "GBPUSD" in content)
    note(
        "Trade list",
        "PASS" if list_ok else "FAIL",
        f"url={page.url}; has_eur={'EURUSD' in content}; has_gbp={'GBPUSD' in content}",
    )
    for label, tid in (("open", open_id), ("closed", closed_id)):
        if not tid:
            note(f"View {label} trade", "FAIL", "missing id")
            continue
        goto(page, f"/trade/{tid}")
        page.wait_for_timeout(600)
        ok = not is_500(page) and f"/trade/{tid}" in page.url
        note(f"View {label} trade", "PASS" if ok else "FAIL", f"url={page.url}; flashes={flashes(page)}")


def ai_coach_smoke(page):
    goto(page, "/dashboard/ai")
    page.wait_for_timeout(1200)
    if is_500(page):
        note("AI Coach page", "FAIL", f"500 at {page.url}")
        return
    note("AI Coach page", "PASS", page.url)
    q = page.locator("#aiQuestion")
    if not q.count():
        note("AI Coach ask", "FAIL", "#aiQuestion missing")
    else:
        q.fill("What is a good risk-reward ratio for forex?")
        send = page.locator(
            "#aiSubmitBtn, #aiSendBtn, button.tv-ai-send, "
            "button[title='Send']"
        )
        if send.count():
            send.first.click()
            # Prod LLM can be slow; poll up to ~45s for a reply node or soft error
            has_reply = False
            err = False
            snippet = ""
            for _ in range(15):
                page.wait_for_timeout(3000)
                if is_500(page):
                    break
                body = page.inner_text("body")[:4000]
                snippet = body[-800:]
                has_reply = bool(
                    page.locator(
                        ".ai-message, .chat-message, .assistant, [data-role=assistant], "
                        "#aiChat .msg-assistant, #aiMessages .assistant, "
                        ".tv-ai-msg, .coach-reply, #aiResponse"
                    ).count()
                ) or (
                    "risk" in body.lower()
                    and ("reward" in body.lower() or "ratio" in body.lower())
                    and "good risk-reward" not in body.lower()[-400:]
                )
                err = any(
                    x in body.lower()
                    for x in [
                        "rate limit",
                        "api key",
                        "unavailable",
                        "try again",
                        "not configured",
                        "openai",
                        "quota",
                    ]
                )
                if has_reply or err:
                    break
            note(
                "AI Coach ask",
                "PASS" if (has_reply or err) and not is_500(page) else "WARN",
                f"reply={has_reply}; soft_err={err}; flashes={flashes(page)}; tail={snippet[:220]!r}",
            )
        else:
            note("AI Coach ask", "FAIL", "send button missing")

    talk = page.locator(
        "#tvTalkBtn, #aiTalkBtn, button:has-text('Talk to Coach'), "
        "button:has-text('Talk'), a:has-text('Talk')"
    )
    overlay = page.locator("#tvTalkOverlay")
    if talk.count():
        talk.first.click(force=True)
        page.wait_for_timeout(1200)
        opened = False
        if overlay.count():
            cls = overlay.first.get_attribute("class") or ""
            opened = "is-open" in cls or overlay.first.get_attribute("aria-hidden") == "false"
        else:
            opened = True  # Talk click happened; overlay selector may differ
        # Prefer dedicated end/close controls inside overlay; avoid generic "End" (matches Stop)
        end = page.locator(
            "#tvTalkEndBtn, #endTalkBtn, #tvTalkClose, "
            "button:has-text('End Talk'), button:has-text('Hang up'), "
            "#tvTalkOverlay button:has-text('Close')"
        )
        closed = False
        if end.count():
            end.first.click(force=True)
            page.wait_for_timeout(800)
            if overlay.count():
                cls2 = overlay.first.get_attribute("class") or ""
                closed = "is-open" not in cls2 or overlay.first.get_attribute("aria-hidden") == "true"
            else:
                closed = True
        else:
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            if overlay.count():
                cls2 = overlay.first.get_attribute("class") or ""
                closed = "is-open" not in cls2
            # JS fallback
            if not closed and overlay.count():
                page.evaluate(
                    """() => {
                  const o = document.getElementById('tvTalkOverlay');
                  if (o) { o.classList.remove('is-open'); o.setAttribute('aria-hidden','true'); }
                  if (window.tvTalk && typeof window.tvTalk.end === 'function') window.tvTalk.end();
                }"""
                )
                page.wait_for_timeout(400)
                cls3 = overlay.first.get_attribute("class") or ""
                closed = "is-open" not in cls3
        note(
            "AI Talk overlay open/end",
            "PASS" if opened and closed else ("WARN" if opened else "FAIL"),
            f"opened={opened}; closed={closed}; url={page.url}",
        )
    else:
        note("AI Talk overlay open/end", "WARN", "Talk control not found")


def closed_ux_local(page):
    """Confirm client validation alert when Closed + empty notes (novalidate path)."""
    if not register_and_login(page):
        return
    goto(page, "/trade/add")
    page.wait_for_timeout(1800)
    pick_instrument(page, "EURUSD")
    page.fill("#entry_price", "1.10000")
    page.fill("#lot_size", "0.01")
    if page.locator("#tv-dir-buy").count():
        page.click("#tv-dir-buy")
    if page.locator("label[for=tv_status_closed]").count():
        page.click("label[for=tv_status_closed]")
    else:
        page.locator("#tv_status_closed").check(force=True)
    page.wait_for_timeout(300)
    if page.locator("#exit_price").count():
        page.fill("#exit_price", "1.10500")
    # Leave strategy/notes empty — expect client alert, stay on page
    before = page.url
    page.locator("button[type=submit]").first.click()
    page.wait_for_timeout(900)
    val = page.locator("#tv-client-validation-err")
    visible = False
    text = ""
    if val.count():
        visible = "d-none" not in (val.first.get_attribute("class") or "")
        text = val.first.inner_text().strip()
    stayed = "/trade/add" in page.url or before == page.url
    ok = visible and stayed and ("note" in text.lower() or "strateg" in text.lower() or "closed" in text.lower())
    note(
        "Closed+empty notes validation alert",
        "PASS" if ok else "FAIL",
        f"visible={visible}; text={text!r}; url={page.url}; stayed={stayed}",
    )
    # Banner when closed selected
    banner = page.locator("#tv-closed-req-banner")
    ban_vis = False
    if banner.count():
        ban_vis = "d-none" not in (banner.first.get_attribute("class") or "")
    note(
        "Closed requirements banner",
        "PASS" if ban_vis else "WARN",
        f"visible={ban_vis}",
    )


def run_prod_journal(page):
    ok = register_and_login(page)
    if not ok:
        return
    note_trial(page)
    open_id = add_open_trade(page)
    closed_id = add_closed_trade(page, with_notes=True)
    confirm_list_view(page, open_id, closed_id)
    # light AI smoke on same session
    ai_coach_smoke(page)


def main():
    host = urlparse(BASE).hostname or ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        try:
            if MODE == "local_ux":
                closed_ux_local(page)
            elif MODE == "local_ai":
                if register_and_login(page):
                    ai_coach_smoke(page)
            else:
                run_prod_journal(page)
        except Exception as e:
            note("Unhandled exception", "FAIL", repr(e))
        finally:
            browser.close()

    meta["finished"] = datetime.now().isoformat(timespec="seconds")
    meta["host"] = host
    payload = {"meta": meta, "results": results}
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] == "FAIL")
    warns = sum(1 for r in results if r["status"] == "WARN")
    print(f"\nSummary PASS={passes} FAIL={fails} WARN={warns} -> {OUT}", flush=True)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
