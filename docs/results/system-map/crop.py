import sys
from playwright.sync_api import sync_playwright
OUT=sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__('os').environ.get('PW_CHROMIUM') or None, args=['--use-angle=metal'])
    pg = b.new_page(viewport={'width':1280,'height':800}, device_scale_factor=2)
    for q,name in [('?select=safety','look-safety'),('?select=gemini','look-gemini'),('?select=rewind','look-rewind'),('?select=privacy','look-privacy'),('?select=guide','look-guide')]:
        pg.goto('http://127.0.0.1:8471/map.html'+q); pg.wait_for_timeout(1800)
        pg.locator('.look').screenshot(path=f'{OUT}/crop-{name}.png')
    pg.goto('http://127.0.0.1:8471/map.html?still=1'); pg.wait_for_timeout(2500)
    def around(prefix, w, h, dy=-40):
        r = pg.evaluate("(p)=>{const l=[...document.querySelectorAll('.lab.node')].find(e=>e.textContent.startsWith(p));const r=l.getBoundingClientRect();return [r.x+r.width/2, r.y]}", prefix)
        return {'x': max(0, r[0]-w/2), 'y': max(0, r[1]+dy-h/2), 'width': w, 'height': h}
    pg.screenshot(path=f'{OUT}/crop-server-pulses.png', clip=around('A-Eye server', 460, 320))
    pg.screenshot(path=f'{OUT}/crop-parts-cloud.png', clip=around('Parts shelf', 260, 180))
    pg.screenshot(path=f'{OUT}/crop-gemini.png', clip=around('Gemini', 300, 200))
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
