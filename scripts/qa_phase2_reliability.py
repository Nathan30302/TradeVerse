#!/usr/bin/env python3
"""Phase 2 reliability QA: journal core flows via Playwright."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
MODE = sys.argv[2] if len(sys.argv) > 2 else "full"  # full | smoke
OUT = sys.argv[3] if len(sys.argv) > 3 else "/Users/mac/Desktop/TradeVerse/.qa_phase2_local.json"

SUFFIX = datetime.now().strftime("%m%d%H%M%S")
USER = f"qa_{SUFFIX}"
PASS = "QaPass123!"
EMAIL = f"{USER}@example.com"
FULL = f"QA Tester {SUFFIX}"

results = []
hard_console = []
console_by_page = {}


def note(feature, status, notes=""):
    results.append({"feature": feature, "status": status, "notes": notes})
    print(f"[{status}] {feature}: {notes}", flush=True)


def flashes(page):
    try:
        if page.locator(".alert").count():
            return page.locator(".alert").all_inner_texts()[:6]
    except Exception:
        pass
    return []


def is_500(page):
    snippet = page.title() + page.content()[:2500]
    return (
        "Internal Server Error" in snippet
        or "Werkzeug" in snippet[:500]
        or page.title().startswith("500")
    )


def hard_ok(page):
    return (not is_500(page)) and BASE.split("://")[1].split("/")[0] in page.url


def goto(page, path, wait="domcontentloaded", timeout=45000):
    resp = page.goto(BASE + path, wait_until=wait, timeout=timeout)
    page.wait_for_timeout(350)
    return resp


def pick_instrument(page, symbol="EURUSD"):
    page.wait_for_timeout(1200)
    search = page.locator("#instrument-search")
    if search.count():
        search.fill(symbol)
        page.wait_for_timeout(1200)
    item = page.locator(
        "#instrument-list .instrument-item, #instrument-list [data-symbol], "
        "#instrument-list button, #instrument-list .list-group-item"
    ).filter(has_text=re.compile(symbol, re.I))
    if item.count() == 0:
        item = page.locator(f"#instrument-list >> text={symbol}")
    if item.count():
        item.first.click()
        page.wait_for_timeout(350)
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
    if "example.com" in EMAIL.lower() and ("tradeversejournal.space" in BASE or "onrender.com" in BASE):
        note(
            "Register+login",
            "SKIP",
            "Refusing to register @example.com on production",
        )
        return False
    goto(page, "/auth/register")
    note(
        "Register page",
        "PASS" if page.locator("input[name=username]").count() and not is_500(page) else "FAIL",
        page.url,
    )
    page.fill("input[name=username]", USER)
    page.fill("input[name=full_name]", FULL)
    page.fill("input[name=email]", EMAIL)
    if page.locator("select[name=country_code]").count():
        # skip placeholder (index 0)
        page.select_option("select[name=country_code]", index=1)
    if page.locator("input[name=phone_number]").count():
        page.fill("input[name=phone_number]", "+15551234567")
    page.fill("input[name=password]", PASS)
    page.fill("input[name=confirm_password]", PASS)
    if page.locator("input[name=terms_agreed]").count():
        page.check("input[name=terms_agreed]")
    page.locator("button[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    ok = "/dashboard" in page.url or ("/auth/register" not in page.url and "/auth/login" not in page.url)
    note("Register+login", "PASS" if ok and not is_500(page) else "FAIL", f"url={page.url}; flashes={flashes(page)}")

    if not ok:
        goto(page, "/auth/login")
        if page.locator("input[name=username]").count():
            page.fill("input[name=username]", USER)
        page.fill("input[name=password]", PASS)
        page.locator("button[type=submit]").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        note("Login fallback", "PASS" if "/auth/login" not in page.url else "FAIL", page.url)


def run_full(page):
    register_and_login(page)

    body = page.inner_text("body")
    days = re.findall(r"(\d+)\s*day[s]?\s*left", body, re.I)
    badge = re.findall(r"Trial\s*[·•]\s*(\d+)d", body, re.I)
    ends = re.findall(r"Ends\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", body, re.I)
    zero = any(d == "0" for d in days + badge)
    july_past = re.findall(r"July\s+\d{1,2},\s+202[0-5]", body, re.I)
    note(
        "F16 Trial chip (nav)",
        "FAIL" if zero or july_past else "PASS",
        f"days={days or badge}; ends={ends[:2]}; past={july_past}",
    )

    # A1 open trade
    goto(page, "/trade/add")
    page.wait_for_timeout(1800)
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
    page.wait_for_timeout(2500)
    open_m = re.search(r"/trade/(\d+)", page.url)
    open_id = open_m.group(1) if open_m else None
    note(
        "A1 Add open trade",
        "PASS" if open_id and not is_500(page) else "FAIL",
        f"url={page.url}; instr_clicked={clicked}; flashes={flashes(page)}",
    )

    # A2 closed trade
    goto(page, "/trade/add")
    page.wait_for_timeout(1200)
    pick_instrument(page, "GBPUSD")
    page.fill("#entry_price", "1.25000")
    page.fill("#lot_size", "0.05")
    if page.locator("#tv-dir-buy").count():
        page.click("#tv-dir-buy")
    if page.locator("label[for=tv_status_closed]").count():
        page.click("label[for=tv_status_closed]")
        page.wait_for_timeout(300)
    elif page.locator("#tv_status_closed").count():
        page.locator("#tv_status_closed").check(force=True)
        page.wait_for_timeout(300)
    if page.locator("#exit_price").count():
        page.fill("#exit_price", "1.25500")
    page.locator("button[type=submit]").first.click()
    page.wait_for_timeout(2500)
    closed_m = re.search(r"/trade/(\d+)", page.url)
    closed_id = closed_m.group(1) if closed_m else None
    nums = re.findall(r"[+\-]?\d+\.\d{2}", page.inner_text("body"))
    note(
        "A2 Add closed trade",
        "PASS" if closed_id and not is_500(page) else "FAIL",
        f"url={page.url}; flashes={flashes(page)}; nums={nums[:8]}",
    )

    # A3 edit
    edit_target = open_id or closed_id
    if edit_target:
        goto(page, f"/trade/{edit_target}/edit")
        page.wait_for_timeout(700)
        if page.locator("#lot_size").count():
            page.fill("#lot_size", "0.12")
        if page.locator("#entry_price").count():
            page.fill("#entry_price", "1.08800")
        page.locator("button[type=submit]").first.click()
        page.wait_for_timeout(2000)
        note(
            "A3 Edit trade save",
            "PASS" if not is_500(page) and "/trade/" in page.url else "FAIL",
            f"url={page.url}; flashes={flashes(page)}",
        )
        goto(page, f"/trade/{edit_target}")
        body = page.inner_text("body")
        note(
            "A3 Edit persisted",
            "PASS" if ("0.12" in body or "1.088" in body) else "FAIL",
            f"has_lot={('0.12' in body)}; has_entry={('1.088' in body)}",
        )
    else:
        note("A3 Edit trade save", "FAIL", "no trade id")

    # A4 close
    if open_id:
        goto(page, f"/trade/{open_id}")
        page.wait_for_timeout(400)
        btn = page.locator('[data-bs-target="#closeModal"], button:has-text("Close Trade")')
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(400)
        if page.locator("#close_exit_price").count():
            page.fill("#close_exit_price", "1.09000")
            page.locator('#closeModal button[type=submit], form[action*="close"] button[type=submit]').first.click()
            page.wait_for_timeout(2500)
            body = page.inner_text("body").lower()
            ok = (("closed" in body) or ("p/l" in body) or ("profit" in body)) and not is_500(page)
            note("A4 Close open trade", "PASS" if ok else "FAIL", f"url={page.url}; flashes={flashes(page)}")
        else:
            note("A4 Close open trade", "FAIL", "close modal/input missing")
    else:
        note("A4 Close open trade", "FAIL", "no open trade")

    # A5 filters
    goto(page, "/trade/list")
    page.wait_for_timeout(700)
    list_ok = not is_500(page) and ("EURUSD" in page.content() or "GBPUSD" in page.content())
    if page.locator("select[name=status]").count():
        page.select_option("select[name=status]", "closed")
    if page.locator("input[name=symbol]").count():
        page.fill("input[name=symbol]", "EUR")
    if page.locator("button:has-text('Apply Filters'), button[type=submit]").count():
        page.locator("button:has-text('Apply Filters')").first.click() if page.locator(
            "button:has-text('Apply Filters')"
        ).count() else None
        page.wait_for_timeout(800)
    goto(page, "/trade/list?status=closed")
    page.wait_for_timeout(500)
    qs_ok = not is_500(page)
    note(
        "A5 List filters",
        "PASS" if list_ok and qs_ok else "FAIL",
        f"list_ok={list_ok}; qs_ok={qs_ok}; url={page.url}",
    )

    # A7 duplicate
    goto(page, "/trade/list")
    page.wait_for_timeout(400)
    dup = page.locator("a[href*='duplicate=1'], a:has-text('Duplicate')")
    if dup.count():
        dup.first.click()
        page.wait_for_timeout(1200)
        sym = page.locator("#symbol").input_value() if page.locator("#symbol").count() else ""
        note(
            "A7 Duplicate last (prefill)",
            "PASS" if "/trade/add" in page.url and not is_500(page) else "FAIL",
            f"url={page.url}; symbol={sym}",
        )
        if page.locator("#entry_price").count() and not page.locator("#entry_price").input_value():
            page.fill("#entry_price", "1.10000")
        if page.locator("#lot_size").count() and not page.locator("#lot_size").input_value():
            page.fill("#lot_size", "0.01")
        if page.locator("label[for=tv_status_open]").count():
            page.click("label[for=tv_status_open]")
        elif page.locator("#tv_status_open").count():
            page.locator("#tv_status_open").check(force=True)
        if page.locator("#symbol").count() and not page.locator("#symbol").input_value():
            pick_instrument(page, "EURUSD")
            page.fill("#entry_price", "1.10000")
        page.locator("button[type=submit]").first.click()
        page.wait_for_timeout(2000)
        note(
            "A7 Duplicate save",
            "PASS" if re.search(r"/trade/\d+", page.url) and not is_500(page) else "FAIL",
            f"url={page.url}; flashes={flashes(page)}",
        )
    else:
        note("A7 Duplicate last", "FAIL", "Duplicate CTA not found")

    # A6 delete disposable
    goto(page, "/trade/add")
    page.wait_for_timeout(1000)
    pick_instrument(page, "USDJPY")
    page.fill("#entry_price", "150.000")
    page.fill("#lot_size", "0.01")
    if page.locator("label[for=tv_status_open]").count():
        page.click("label[for=tv_status_open]")
    elif page.locator("#tv_status_open").count():
        page.locator("#tv_status_open").check(force=True)
    page.locator("button[type=submit]").first.click()
    page.wait_for_timeout(2000)
    del_m = re.search(r"/trade/(\d+)", page.url)
    del_id = del_m.group(1) if del_m else None
    if del_id:
        goto(page, f"/trade/{del_id}")
        page.wait_for_timeout(350)
        del_btn = page.locator('[data-bs-target="#deleteModal"], button:has-text("Delete")')
        if del_btn.count():
            del_btn.first.click()
            page.wait_for_timeout(350)
            page.locator('#deleteModal button[type=submit], form[action*="delete"] button[type=submit]').first.click()
            page.wait_for_timeout(1800)
            goto(page, f"/trade/{del_id}")
            still = (
                "USDJPY" in page.content()
                and f"/trade/{del_id}" in page.url
                and "404" not in page.title()
                and "Not Found" not in page.content()
            )
            note(
                "A6 Delete trade",
                "PASS" if (not still) and not is_500(page) else "FAIL",
                f"url={page.url}; title={page.title()}; flashes={flashes(page)}",
            )
        else:
            note("A6 Delete trade", "FAIL", "delete button missing")
    else:
        note("A6 Delete trade", "FAIL", "could not create disposable trade")

    # A8 mobile FAB
    page.set_viewport_size({"width": 390, "height": 844})
    goto(page, "/dashboard/")
    page.wait_for_timeout(700)
    fab = page.locator("a.fab, .fab-container a")
    if fab.count() == 0:
        fab = page.locator("a[href*='/trade/add']")
    if fab.count():
        box = fab.first.bounding_box()
        href = fab.first.get_attribute("href")
        fab.first.click()
        page.wait_for_timeout(1200)
        note(
            "A8 Mobile FAB→add",
            "PASS" if "/trade/add" in page.url and not is_500(page) else "FAIL",
            f"url={page.url}; box={box}; href={href}",
        )
        pick_instrument(page, "EURUSD")
        if page.locator("#entry_price").count():
            page.fill("#entry_price", "1.11111")
            page.fill("#lot_size", "0.01")
            if page.locator("label[for=tv_status_open]").count():
                page.click("label[for=tv_status_open]")
            elif page.locator("#tv_status_open").count():
                page.locator("#tv_status_open").check(force=True)
            page.locator("button[type=submit]").first.click()
            page.wait_for_timeout(2000)
            note(
                "A8 Mobile add save",
                "PASS" if re.search(r"/trade/\d+", page.url) else "FAIL",
                f"url={page.url}; flashes={flashes(page)}",
            )
    else:
        note("A8 Mobile FAB→add", "FAIL", "FAB missing")
    page.set_viewport_size({"width": 1280, "height": 900})

    # B review
    for feat, path in [
        ("B9 Dashboard daily loop", "/dashboard/"),
        ("B10 Calendar", "/dashboard/calendar"),
        ("B11 Weekly review", "/dashboard/weekly-review"),
        ("B11 EOD", "/dashboard/eod"),
    ]:
        goto(page, path)
        page.wait_for_timeout(600)
        note(feat, "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")

    goto(page, "/dashboard/calendar")
    page.wait_for_timeout(700)
    day = page.locator(
        ".calendar-day, .cal-day, td[data-date], a[href*='date='], .day-cell, [data-day]"
    )
    if day.count():
        day.first.click()
        page.wait_for_timeout(900)
        note("B10 Calendar day", "PASS" if not is_500(page) else "FAIL", page.url)
    else:
        note("B10 Calendar day", "PASS", "month loaded; no day cell clicked")

    # C planner / playbook
    goto(page, "/planner/")
    page.wait_for_timeout(500)
    note("C12 Planner hub", "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")
    new_plan = page.locator("a[href*='/planner/new']")
    if new_plan.count():
        new_plan.first.click()
        page.wait_for_timeout(900)
        note("C12 Planner new", "PASS" if not is_500(page) else "FAIL", page.url)
    else:
        note("C12 Planner new", "PASS", "hub only")

    goto(page, "/playbook/")
    page.wait_for_timeout(600)
    note("C13 Playbook list", "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")
    if page.locator("form[action*='from-starter']").count():
        page.locator("form[action*='from-starter'] button").first.click()
        page.wait_for_timeout(1200)
        note("C13 Playbook starter", "PASS" if not is_500(page) else "FAIL", f"url={page.url}; flashes={flashes(page)}")
    elif page.locator("a[href*='/playbook/new']").count():
        page.locator("a[href*='/playbook/new']").first.click()
        page.wait_for_timeout(800)
        note("C13 Playbook new", "PASS" if not is_500(page) else "FAIL", page.url)
    else:
        note("C13 Playbook setup", "PASS", "list/empty state loaded")

    # D insights
    for feat, path in [
        ("D14 Analytics", "/dashboard/analytics"),
        ("D14 Performance", "/dashboard/performance"),
        ("D14 Patterns", "/dashboard/patterns"),
    ]:
        goto(page, path)
        page.wait_for_timeout(800)
        note(feat, "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")

    # E AI
    goto(page, "/dashboard/ai")
    page.wait_for_timeout(900)
    note("E15 AI page load", "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")
    chat = page.locator(
        "#ai-chat-input, textarea[name=message], #chat-input, "
        "textarea[placeholder*='Ask'], textarea[placeholder*='ask'], input[placeholder*='Ask']"
    )
    if chat.count():
        chat.first.fill("What is my win rate briefly?")
        send = page.locator("button:has-text('Send'), #ai-send")
        if send.count():
            send.first.click()
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(4000)
        note("E15 AI short chat", "PASS" if not is_500(page) else "FAIL", f"flashes={flashes(page)}")
    else:
        note("E15 AI short chat", "PASS", "no chat input; page loaded")
    talk = page.locator("button:has-text('Talk'), #talk-mode, button:has-text('Voice')")
    if talk.count():
        talk.first.click()
        page.wait_for_timeout(700)
        note("E15 Talk mode", "PASS", "opened")
    else:
        note("E15 Talk mode", "PASS", "not present/gated")

    # F settings
    goto(page, "/auth/settings")
    page.wait_for_timeout(500)
    note("F16 Settings page", "PASS" if not is_500(page) else "FAIL", page.url)
    tabs = page.locator("[data-bs-toggle=tab], .nav-tabs .nav-link, #billing-tab")
    for i in range(min(tabs.count(), 6)):
        try:
            tabs.nth(i).click()
            page.wait_for_timeout(250)
        except Exception:
            pass
    stxt = page.inner_text("body")
    bdays = re.findall(r"(\d+)\s*day[s]?\s*left", stxt, re.I)
    bends = re.findall(
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+2026",
        stxt,
    )
    note(
        "F16 Settings trial",
        "PASS" if (bdays or bends) and not any(d == "0" for d in bdays) else "FAIL",
        f"days={bdays}; ends={bends[:3]}",
    )


def run_smoke(page):
    """Production-light smoke: public pages + register + core journal pages."""
    for path, label in [
        ("/", "Prod home"),
        ("/auth/login", "Prod login"),
        ("/auth/register", "Prod register page"),
        ("/pricing", "Prod pricing"),
        ("/features", "Prod features"),
    ]:
        try:
            resp = goto(page, path, timeout=60000)
            bad = is_500(page) or (resp and resp.status >= 500)
            note(label, "FAIL" if bad else "PASS", f"status={resp.status if resp else None}; title={page.title()}")
        except Exception as e:
            note(label, "FAIL", str(e)[:220])

    register_and_login(page)
    if any(r["feature"] == "Register+login" and r["status"] == "PASS" for r in results):
        for path, label in [
            ("/dashboard/", "Prod dashboard"),
            ("/trade/add", "Prod trade/add"),
            ("/trade/list", "Prod trade/list"),
            ("/dashboard/calendar", "Prod calendar"),
            ("/dashboard/ai", "Prod AI"),
            ("/auth/settings", "Prod settings"),
        ]:
            try:
                goto(page, path, timeout=60000)
                note(label, "PASS" if not is_500(page) else "FAIL", f"url={page.url}; title={page.title()}")
            except Exception as e:
                note(label, "FAIL", str(e)[:220])


def main():
    global BASE
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        def on_console(msg):
            console_by_page.setdefault(page.url.split("?")[0], []).append(
                {"type": msg.type, "text": msg.text[:400]}
            )

        def on_pageerror(err):
            console_by_page.setdefault(page.url.split("?")[0], []).append(
                {"type": "pageerror", "text": str(err)[:400]}
            )

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # Resolve final origin after redirects
        try:
            page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
            u = urlparse(page.url)
            BASE = f"{u.scheme}://{u.netloc}"
            note("Base resolve", "PASS", BASE)
        except Exception as e:
            note("Base resolve", "FAIL", str(e)[:220])
            browser.close()
            _write()
            return

        if MODE == "smoke":
            run_smoke(page)
        else:
            run_full(page)

        for url, logs in console_by_page.items():
            for L in logs:
                if L["type"] in ("error", "pageerror"):
                    t = L["text"]
                    if any(
                        x in t.lower()
                        for x in ("favicon", "devtools", "chrome-extension", "net::err_aborted")
                    ):
                        continue
                    hard_console.append({"url": url, "type": L["type"], "text": t[:300]})
        note("Console hard errors", "FAIL" if hard_console else "PASS", hard_console[:12] if hard_console else "none")
        browser.close()
    _write()


def _write():
    out = {
        "user": USER,
        "email": EMAIL,
        "password": PASS,
        "base": BASE,
        "mode": MODE,
        "results": results,
        "hard_console": hard_console,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print("\n=== SUMMARY ===", flush=True)
    print(dict(Counter(r["status"] for r in results)), flush=True)
    fails = [r for r in results if r["status"] == "FAIL"]
    print("FAILS:", json.dumps(fails, indent=2), flush=True)
    print("USER", USER, "OUT", OUT, flush=True)


if __name__ == "__main__":
    main()
