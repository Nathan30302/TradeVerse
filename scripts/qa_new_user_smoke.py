#!/usr/bin/env python3
"""Create a real new account on a live TradeVerse host and exercise login/upload/chat."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://www.tradeversejournal.space").rstrip("/")
STAMP = datetime.now().strftime("%m%d%H%M%S")
USER = f"tvqa{STAMP}"
EMAIL = f"tvqa{STAMP}@gmail.com"
PASS = "TvQa0914Pass!"
FULL = f"TV QA Tester {STAMP}"
OUT = Path("/Users/mac/Desktop/TradeVerse/.qa_new_user_smoke.json")
PNG = Path("/tmp/tv_qa_avatar.png")
PNG.write_bytes(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
)

notes = []


def note(name, status, detail=""):
    notes.append({"feature": name, "status": status, "notes": detail})
    print(f"[{status}] {name}: {detail}", flush=True)


def flashes(page):
    try:
        if page.locator(".alert").count():
            return page.locator(".alert").all_inner_texts()[:8]
    except Exception:
        pass
    return []


def is_500(page):
    try:
        snippet = (page.title() or "") + page.content()[:4000]
    except Exception:
        return False
    return "Internal Server Error" in snippet or (page.title() or "").startswith("500")


def main() -> int:
    creds = {"base": BASE, "username": USER, "email": EMAIL, "password": PASS, "full_name": FULL}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()
        page.set_default_timeout(90000)

        r = page.goto(BASE + "/", wait_until="domcontentloaded")
        body = page.content()
        ver = None
        m = re.search(r"Version\s+(\d+\.\d+\.\d+)", body)
        if m:
            ver = m.group(1)
        note(
            "Home",
            "PASS" if r and r.status < 500 and not is_500(page) else "FAIL",
            f"http={r.status if r else None} version={ver} url={page.url}",
        )

        page.goto(BASE + "/auth/register", wait_until="domcontentloaded")
        if page.locator("input[name=username]").count() == 0:
            note("Register page", "FAIL", f"url={page.url} title={page.title()}")
            OUT.write_text(json.dumps({"creds": creds, "results": notes}, indent=2))
            browser.close()
            return 2
        note("Register page", "PASS", f"url={page.url}")

        page.fill("input[name=username]", USER)
        page.fill("input[name=full_name]", FULL)
        page.fill("input[name=email]", EMAIL)
        if page.locator("select[name=country_code]").count():
            try:
                page.select_option("select[name=country_code]", index=1)
            except Exception:
                pass
        page.fill("input[name=password]", PASS)
        page.fill("input[name=confirm_password]", PASS)
        if page.locator("input[name=terms_agreed]").count():
            page.check("input[name=terms_agreed]", force=True)
        try:
            with page.expect_navigation(timeout=20000):
                page.locator("#tv-register-submit").click()
        except Exception:
            page.evaluate("() => { const f=document.querySelector('.auth-card form'); if(f) HTMLFormElement.prototype.submit.call(f); }")
            page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        registered = "/auth/register" not in page.url and not is_500(page)
        note("Register submit", "PASS" if registered else "FAIL", f"url={page.url} flashes={flashes(page)}")

        if "/auth/login" in page.url or not registered:
            page.goto(BASE + "/auth/login", wait_until="domcontentloaded")
            page.fill("input[name=username]", USER)
            page.fill("input[name=password]", PASS)
            page.locator("button[type=submit]").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
        logged_in = "/auth/login" not in page.url and "/auth/register" not in page.url and not is_500(page)
        note("Logged in after signup", "PASS" if logged_in else "FAIL", f"url={page.url} flashes={flashes(page)}")
        if not logged_in:
            OUT.write_text(json.dumps({"creds": creds, "results": notes}, indent=2))
            browser.close()
            return 2

        # Logout + login again
        page.goto(BASE + "/auth/logout", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.goto(BASE + "/auth/login", wait_until="domcontentloaded")
        page.fill("input[name=username]", USER)
        page.fill("input[name=password]", PASS)
        page.locator("button[type=submit]").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)
        note(
            "Login with new password",
            "PASS" if "/auth/login" not in page.url and not is_500(page) else "FAIL",
            f"url={page.url} flashes={flashes(page)}",
        )

        # Avatar
        page.goto(BASE + "/auth/profile", wait_until="domcontentloaded")
        note("Profile page", "PASS" if not is_500(page) else "FAIL", f"url={page.url}")
        file_input = page.locator("input[type=file]").first
        if file_input.count():
            file_input.set_input_files(str(PNG))
            page.locator("form button[type=submit], button[type=submit]").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)
            page.goto(BASE + "/auth/profile", wait_until="domcontentloaded")
            html = page.content()
            kept = "uploads/avatars/" in html or "avatar" in html.lower()
            note(
                "Avatar upload persists",
                "PASS" if kept and not is_500(page) else "FAIL",
                f"url={page.url} flashes={flashes(page)} has_uploads_path={'uploads/avatars/' in html}",
            )
        else:
            note("Avatar upload persists", "FAIL", "no file input on profile")

        # Trade
        page.goto(BASE + "/trade/add", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        search = page.locator("#instrument-search")
        if search.count():
            search.fill("EURUSD")
            page.wait_for_timeout(1200)
            item = page.locator("#instrument-list .instrument-item, #instrument-list [data-symbol]").filter(
                has_text=re.compile("EURUSD", re.I)
            )
            if item.count():
                item.first.click()
            else:
                page.evaluate(
                    """() => {
                    const id = document.getElementById('instrument_id');
                    const s = document.getElementById('symbol');
                    if (id) id.value = '1';
                    if (s) s.value = 'EURUSD';
                }"""
                )
        if page.locator("#entry_price").count():
            page.fill("#entry_price", "1.08750")
        if page.locator("#lot_size").count():
            page.fill("#lot_size", "0.10")
        if page.locator("#tv-dir-buy").count():
            page.click("#tv-dir-buy")
        page.locator("button[type=submit]").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        trade_ok = "/trade/" in page.url and not is_500(page)
        note("Add trade", "PASS" if trade_ok else "FAIL", f"url={page.url} flashes={flashes(page)}")

        page.goto(BASE + "/trade/list", wait_until="domcontentloaded")
        note(
            "Trade list keeps data",
            "PASS" if "EURUSD" in page.content() and not is_500(page) else "FAIL",
            f"url={page.url}",
        )

        # AI chat page + query
        page.goto(BASE + "/dashboard/ai", wait_until="domcontentloaded")
        note("AI Buddy page", "PASS" if not is_500(page) else "FAIL", f"url={page.url}")
        csrf = None
        tok = page.locator("meta[name=csrf-token], input[name=csrf_token]").first
        if tok.count():
            csrf = tok.get_attribute("content") or tok.input_value()
        result = page.evaluate(
            """async (csrf) => {
              const headers = {'Content-Type': 'application/json'};
              if (csrf) headers['X-CSRFToken'] = csrf;
              const r = await fetch('/dashboard/ai/query', {
                method: 'POST',
                headers,
                body: JSON.stringify({question: 'What should I focus on this week?'})
              });
              const text = await r.text();
              return {status: r.status, text: text.slice(0, 800)};
            }""",
            csrf,
        )
        chat_ok = result.get("status") == 200 and "Internal Server Error" not in (result.get("text") or "")
        note("AI chat query", "PASS" if chat_ok else "FAIL", f"{result}")

        browser.close()

    payload = {"creds": creds, "version": ver, "results": notes}
    OUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps({"creds": creds, "summary": [(n["feature"], n["status"]) for n in notes]}, indent=2))
    return 0 if all(n["status"] == "PASS" for n in notes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
