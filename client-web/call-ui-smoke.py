"""Real Chromium UI checks against an isolated local mock backend. Synthetic media only.
Run with a Python environment containing Playwright; server Python is an argument.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('A_EYE_UI_PROOF_DIR', str(ROOT / 'docs/results/call-ui-web')))
BASE = 'http://127.0.0.1:8137'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='call-ui-smoke-') as temp:
        token = secrets.token_urlsafe(32)
        env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
        env.update(A_EYE_TOKEN=token, A_EYE_MOCK='1', LOCAL_ONLY='1',
                   A_EYE_MEMORY_DIR=temp + '/memory', CLOUD_BUDGET_PATH=temp + '/budget.sqlite3',
                   PYTHONPATH=str(ROOT), ROUTER='off')
        with open('/private/tmp/call-ui-smoke-server.log', 'w') as log:
            server = subprocess.Popen([sys.argv[1], '-m', 'uvicorn', 'server.app:app', '--host',
                                       '127.0.0.1', '--port', '8137', '--no-access-log'],
                                      cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    try:
                        with urlopen(BASE + '/agent.html', timeout=.5) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise AssertionError('Mock server did not start')
                capture(token)
            finally:
                server.terminate()
                server.wait(timeout=10)


def capture(token):
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
        for width, height in ((1280, 844), (390, 844), (768, 1024), (844, 390)):
            errors, sent = [], []
            context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='no-preference' if width == 1280 else 'reduce', permissions=['camera', 'microphone'])
            # Real local mock pipeline. No external provider requests; retain the existing Google opt-out.
            context.add_init_script("""localStorage.setItem('aeye.cloud', JSON.stringify({google:false,cartesia:true}));
              const WS = window.WebSocket; window.__sockets = [];
              window.WebSocket = class extends WS { constructor(...args) { super(...args); window.__sockets.push(this); } };""")
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASE) else route.abort())
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('websocket', lambda ws: ws.on('framesent', lambda frame: sent.append(json.loads(frame))))
            page.goto(BASE + '/agent.html?token=' + token)
            page.get_by_role('button', name='Call', exact=True).wait_for()
            assert page.locator('#picker button:visible').count() == 2
            assert page.locator('#picker .open-settings').count() == 1
            assert page.locator('.intro-title').inner_text().replace('\n', ' ').strip() == 'I look, point, and remember.'
            for selector in ('.intro-title', '.intro-note', '#picker .open-settings'):
                assert_in_view(page, selector)
            assert page.locator('#picker').evaluate('(el) => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight')
            assert page.locator('.intro-title').evaluate('(el) => el.clientHeight <= parseFloat(getComputedStyle(el).lineHeight) * 2 + 1')
            page.wait_for_timeout(1250)
            assert page.locator('.intro-verb').first.evaluate('(el) => getComputedStyle(el).opacity') == '1'
            if width == 1280:
                page.emulate_media(reduced_motion='reduce')
            assert page.locator('.intro-verb').first.evaluate('(el) => getComputedStyle(el).animationName') == 'none'
            page.keyboard.press('Tab')
            assert page.locator('#picker .open-settings').evaluate('(el) => el === document.activeElement')
            page.keyboard.press('Enter')
            assert page.locator('#settings').is_visible()
            page.locator('#settings-done').click()
            assert page.locator('[data-mode]:visible, #pair-call:visible, #pair-request:visible, #memory-aid:visible, #caregiver-link:visible').count() == 0
            assert page.locator('.intro-note').inner_text() == 'Video and pictures are not saved unless you turn on Rewind or the memory aid.'
            assert_in_view(page, '#ring-hint')
            page.screenshot(path=str(OUT / f'after-start-{width}.png'))
            page.get_by_role('button', name='Call', exact=True).focus()
            page.keyboard.press('Enter')
            page.wait_for_function("document.getElementById('conn-status').textContent === 'Connected'")
            hello = next(m for m in sent if m['type'] == 'hello')
            assert hello['pack'] == 'general' and not hello['camera']
            assert hello['cloud']['cartesia'] is False
            if page.locator('#start-overlay').is_visible():
                page.locator('#start-overlay').click()
            page.evaluate("""session => window.__sockets.at(-1).send(JSON.stringify({v:2,type:'user_text',session_id:session,text:'What do you see?',final:true,source:'typed'}))""", hello['session_id'])
            page.wait_for_function("document.getElementById('replies').textContent.trim().length > 0")
            page.wait_for_timeout(3200)  # Old idle folding must never hide End call.
            for control in ('#start-camera', '#mic', '#end-call', '#rewind-btn', '#rewind-keep'):
                assert_in_view(page, control)
            page.screenshot(path=str(OUT / f'after-call-{width}.png'))
            page.locator('#call .open-settings').click()
            assert page.locator('#settings').inner_text().find('Cartesia') == -1
            assert page.locator('#settings').inner_text().find('Memory aid') == -1
            page.screenshot(path=str(OUT / f'after-settings-{width}.png'))
            page.locator('#hold-toggle').check()
            page.locator('#settings-done').click()
            assert page.locator('#mic').get_attribute('aria-label') == 'Hold to talk'
            mic = page.locator('#mic').bounding_box()
            page.mouse.move(mic['x'] + mic['width']/2, mic['y'] + mic['height']/2)
            page.mouse.down()
            page.wait_for_timeout(300)
            assert page.locator('#mic').get_attribute('aria-label') == 'Listening, release to send'
            page.mouse.up()
            assert page.locator('#mic').get_attribute('aria-label') == 'Hold to talk'
            # Keep/rewind wire messages are checked without enabling real recording: camera remains off.
            page.locator('#rewind-keep').check()
            page.wait_for_timeout(100)
            assert any(m['type'] == 'rewind' and m['on'] and m['keep'] for m in sent)
            page.locator('#rewind-btn').click()
            assert not page.locator('#rewind-keep').is_checked()
            page.locator('#start-camera').click()
            page.wait_for_function("document.getElementById('start-camera').getAttribute('aria-pressed') === 'true'")
            page.wait_for_timeout(1200)
            assert any(m['type'] == 'frame' for m in sent)
            page.locator('#end-call').click()
            assert page.locator('#picker').is_visible()
            assert page.evaluate("document.getElementById('camera').srcObject === null")
            assert not page.locator('#rewind-keep').is_checked()
            assert not errors, errors
            print(f'UI {width}x{height}: PASS; connected mock call, camera, hold, retention, end; page errors 0')
            context.close()
        browser.close()
    print('CALL UI BROWSER: PASS; 12 screenshots; synthetic media only; no live provider proof')


def assert_in_view(page, selector):
    item = page.locator(selector)
    assert item.is_visible(), selector
    box = item.bounding_box()
    view = page.viewport_size
    assert box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= view['width'] + 1 and box['y'] + box['height'] <= view['height'] + 1, (selector, box, view)


if __name__ == '__main__':
    main()
