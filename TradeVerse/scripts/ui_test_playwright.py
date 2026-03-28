from playwright.sync_api import sync_playwright
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width":1280, "height":720}, record_video_dir=OUTPUT_DIR)
    page = context.new_page()

    logs = []
    def on_console(msg):
        try:
            logs.append(f"{msg.type}: {msg.text}")
        except Exception:
            logs.append(f"console: (unserializable)")
    page.on('console', on_console)

    page.goto('http://127.0.0.1:5000', wait_until='networkidle')
    page.wait_for_timeout(5000)

    # screenshot
    screenshot_path = os.path.join(OUTPUT_DIR, 'home.png')
    page.screenshot(path=screenshot_path, full_page=True)

    # wait a bit to collect video
    page.wait_for_timeout(4000)

    # close context to flush video
    context.close()
    browser.close()

    # save logs
    with open(os.path.join(OUTPUT_DIR, 'console.log'), 'w', encoding='utf-8') as f:
        for l in logs:
            f.write(l + '\n')

    print('artifacts saved to', OUTPUT_DIR)
