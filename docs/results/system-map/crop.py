import sys
from playwright.sync_api import sync_playwright
OUT=sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__('os').environ.get('PW_CHROMIUM') or None, args=['--use-angle=metal'])
    pg = b.new_page(viewport={'width':1280,'height':800}, device_scale_factor=2)
    for q,name in [('?select=safety','look-safety'),('?select=gemini','look-gemini'),('?select=rewind','look-rewind'),('?select=privacy','look-privacy'),('?select=guide','look-guide')]:
        pg.goto('http://127.0.0.1:8471/map.html'+q); pg.wait_for_timeout(1800)
        pg.locator('.look').screenshot(path=f'{OUT}/crop-{name}.png')
    pg.goto('http://127.0.0.1:8471/map.html'); pg.wait_for_timeout(2500)
    pg.screenshot(path=f'{OUT}/crop-server-pulses.png', clip={'x':380,'y':160,'width':420,'height':300})
    pg.screenshot(path=f'{OUT}/crop-parts-cloud.png', clip={'x':260,'y':500,'width':240,'height':160})
    pg.screenshot(path=f'{OUT}/crop-gemini.png', clip={'x':780,'y':120,'width':260,'height':170})
    pg.locator('.bar').screenshot(path=f'{OUT}/crop-controls.png')
    # hover tooltip
    box = pg.evaluate("(()=>{const l=[...document.querySelectorAll('.lab.node')].find(e=>e.textContent.startsWith('Router'));const r=l.getBoundingClientRect();return [r.x+r.width/2, r.y-14]})()")
    pg.mouse.move(box[0], box[1]); pg.wait_for_timeout(400)
    pg.screenshot(path=f'{OUT}/crop-hover-router.png', clip={'x':box[0]-160,'y':box[1]-80,'width':440,'height':200})
    print('tip', pg.evaluate("document.getElementById('tip').hidden"))
    # real click on Gemini node
    g = pg.evaluate("(()=>{const l=[...document.querySelectorAll('.lab.node')].find(e=>e.textContent.startsWith('Gemini'));const r=l.getBoundingClientRect();return [r.x+r.width/2, r.y-14]})()")
    pg.mouse.click(g[0], g[1]); pg.wait_for_timeout(1200)
    print('panel after click:', pg.evaluate("document.getElementById('panel').hidden ? 'hidden' : document.querySelector('#panel h2').textContent"))
    pg.screenshot(path=f'{OUT}/1280-click-gemini.png')
