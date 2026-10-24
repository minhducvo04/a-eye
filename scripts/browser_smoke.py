"""Browser smoke test for /agent.html: fails on any console error and checks the camera and mic toggles.

Runs a real Chromium (Playwright) with a fake camera and microphone against a running server:

    uv run --with playwright python scripts/browser_smoke.py http://127.0.0.1:8010
    (first time only: uv run --with playwright python -m playwright install chromium)

Checks: no console errors or page errors from load to the end; the pack picker starts a session; Camera on flips
its state and frames start; Mic flips its state; Hold to talk can be pressed; a typed question gets a reply
caption. Exit 0 on pass. Synthetic media only (Chromium's fake devices).
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010").rstrip("/")
IGNORED = ("favicon.ico",)


def main():
    problems, sent = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-ui-for-media-stream",
                                          "--use-fake-device-for-media-stream"])
        page = browser.new_context(permissions=["camera", "microphone"]).new_page()
        page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}")
                if m.type == "error" and not any(x in m.text for x in IGNORED) else None)
        page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
        page.on("websocket", lambda ws: ws.on("framesent", lambda f: sent.append(f)))

        page.goto(BASE + "/agent.html")
        page.wait_for_timeout(1200)
        page.click('button[data-pack="general"]')
        page.wait_for_timeout(600)
        if page.locator("#start-overlay:not(.hidden)").count():
            page.click("#start-overlay")
            page.wait_for_timeout(400)

        def pressed(sel):
            return page.get_attribute(sel, "aria-pressed")

        before = pressed("#start-camera")
        page.click("#start-camera")
        page.wait_for_timeout(2500)
        after = pressed("#start-camera")
        msgs = []
        for f in sent:
            try:
                msgs.append(json.loads(f))
            except (TypeError, ValueError):
                pass
        frames = sum(1 for m in msgs if m.get("type") == "frame")
        if before == after:
            problems.append(f"camera toggle did not change state ({before} -> {after})")
        if not any(m.get("type") == "camera" and m.get("on") is True for m in msgs):
            problems.append("no camera on message sent")
        if frames == 0:
            problems.append("no frames sent after Camera on")

        mic_before = pressed("#mic")
        page.click("#mic", timeout=3000)
        page.wait_for_timeout(1200)
        if pressed("#mic") == mic_before:
            problems.append(f"mic toggle did not change state ({mic_before})")

        hold = page.locator("#hold")
        if hold.count():
            box = hold.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.wait_for_timeout(600)
            page.mouse.up()

        page.fill('input[placeholder="Type a message"]', "what do you see?")
        page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
        text = page.locator("body").inner_text()
        if "Helper" not in text:
            problems.append("no helper reply caption after a typed question")
        browser.close()

    print(json.dumps({"frames_sent": frames, "problems": problems}, indent=1))
    print("BROWSER SMOKE PASS" if not problems else "BROWSER SMOKE FAIL")
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
