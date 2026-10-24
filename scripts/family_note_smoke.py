"""Two real Chromium tabs, fixture text only. Run against A_EYE_MOCK=1 LOCAL_ONLY=1.

Uses an actual on-device speech voice; fails closed if none exists. No media saved.
"""
import sys
import time
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8034'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
    context = browser.new_context(permissions=['camera', 'microphone'])
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
    user = context.new_page()
    errors = []
    user.on('pageerror', lambda e: errors.append(str(e)))
    user.goto(base + '/agent.html?vad=0')
    user.click('button[data-pack="general"]')
    user.wait_for_function("document.getElementById('proof-cloud-calls').textContent === 'Cloud AI calls: 0'")
    user.locator('#family-panel summary').click()
    user.wait_for_function("document.getElementById('family-task').options.length > 0")
    assert user.locator('#family-contact option').count() == 1
    user.fill('#family-name', 'Fixture Parent')
    user.fill('#family-relation', 'parent')
    user.check('#family-consent')
    user.click('#family-add')
    user.wait_for_function("document.getElementById('family-contact').options.length === 2")
    user.select_option('#family-contact', index=1)
    user.check('#family-complete')
    user.wait_for_function("speechSynthesis.getVoices().some(v => v.localService && v.lang.startsWith('en'))", timeout=15000)
    user.click('#family-draft')
    user.wait_for_function("!document.getElementById('family-send').disabled", timeout=60000)
    user.click('#family-send')
    user.locator('#family-link').wait_for(state='visible')
    link = user.locator('#family-link').get_attribute('href')
    assert user.locator('#family-pictures').inner_text() == 'Pictures sent: 0'
    assert user.locator('#proof-cloud-calls').inner_text() == 'Cloud AI calls: 0'
    parent = context.new_page()
    parent.set_viewport_size({'width': 390, 'height': 844})
    parent.on('pageerror', lambda e: errors.append(str(e)))
    parent.goto(link)
    parent.click('#parent-open')
    parent.locator('#parent-form').wait_for(state='visible')
    assert parent.locator('#parent-note').inner_text() == user.locator('#family-preview').inner_text()
    parent.fill('#parent-reply', 'Nice work! Check it once more tomorrow.')
    start = time.monotonic()
    parent.locator('#parent-form button').click()
    user.wait_for_function("document.getElementById('family-reply').textContent.includes('Nice work!')", timeout=10000)
    elapsed = time.monotonic() - start
    user.wait_for_function("document.getElementById('family-status').textContent === 'Reply read aloud.'", timeout=60000)
    user.screenshot(path='/private/tmp/family-note-user.png')
    parent.screenshot(path='/private/tmp/family-note-parent.png')
    parent.goto('about:blank')
    parent.goto(link)
    parent.click('#parent-open')
    parent.wait_for_function("document.getElementById('parent-status').textContent.includes('used or expired')")
    assert not errors, errors
    print(f'Family two-tab E2E: PASS; reply visible in {elapsed:.2f}s; single-use replay refused; Pictures sent: 0; Cloud AI calls: 0')
    print('Read aloud: native on-device speech completed for note and reply (physical hearing not measured).')
    browser.close()
