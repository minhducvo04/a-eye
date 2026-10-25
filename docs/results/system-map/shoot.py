import json, sys, statistics
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8471/map.html'
SHOTS = [
    ('1536-name', 1536, 864, '?still=1'),
    ('1280-name', 1280, 800, '?still=1'),
    ('390-name', 390, 844, '?still=1'),
    ('1280-autoplay', 1280, 800, ''),
    ('390-autoplay', 390, 844, ''),
    ('390-cost', 390, 844, '?mode=cost'),
    ('390-index', 390, 844, '?panel=index'),
    ('390-cost-selected', 390, 844, '?mode=cost&select=gemini'),
    ('1280-guide-panel', 1280, 800, '?select=guide'),
    ('1280-privacy-panel', 1280, 800, '?select=privacy'),
    ('1280-scale', 1280, 800, '?panel=scale'),
    ('1280-flow-guest', 1280, 800, '?flow=guest'),
    ('390-scale', 390, 844, '?panel=scale'),
    ('1280-cost-panel', 1280, 800, '?panel=cost'),
    ('390-cost-panel', 390, 844, '?panel=cost'),
    ('390-privacy-panel', 390, 844, '?select=privacy'),
    ('390-flow-guest', 390, 844, '?flow=guest'),
    ('1280-speed', 1280, 800, '?mode=speed'),
    ('1280-cost', 1280, 800, '?mode=cost'),
    ('1280-router-panel', 1280, 800, '?mode=speed&select=router'),
    ('1280-safety-panel', 1280, 800, '?select=safety'),
    ('1280-memory-panel', 1280, 800, '?select=recent'),
    ('1280-saved-panel', 1280, 800, '?select=saved'),
    ('1280-flow-hazard', 1280, 800, '?flow=hazard'),
    ('1280-index', 1280, 800, '?panel=index'),
    ('390-speed', 390, 844, '?mode=speed'),
    ('390-router-panel', 390, 844, '?select=router'),
    ('1536-reduced', 1536, 864, ''),
]
only = sys.argv[2:] or None
report = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__('os').environ.get('PW_CHROMIUM') or None, args=['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'])
    for name, w, h, q in SHOTS:
        if only and name not in only:
            continue
        pg = b.new_page(viewport={'width': w, 'height': h}, device_scale_factor=2 if w == 390 else 1, reduced_motion='reduce' if 'reduced' in name else 'no-preference')
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + q)
        pg.wait_for_function('window.__map && window.__map.ready', timeout=20000)
        pg.wait_for_timeout(2500)
        for attempt in range(3):
            try:
                pg.screenshot(path=str(OUT / f'{name}.png'), timeout=20000); break
            except Exception as ex:
                errs.append('screenshot retry: ' + str(ex)[:60])
        rects = pg.evaluate("[...document.querySelectorAll('.lab')].filter(e=>!e.classList.contains('hide') && +e.style.opacity>=0.8).map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height,e.classList.contains('zone')]})")
        (OUT / f'{name}.rects.json').write_text(json.dumps(rects))
        ft = pg.evaluate('window.__map.frameTimes.slice(30)')
        ft = sorted(ft)
        report[name] = {'p50_ms': round(statistics.median(ft), 1) if ft else None,
                        'p95_ms': round(ft[int(len(ft) * 0.95) - 1], 1) if ft else None,
                        'frames': len(ft), 'errors': errs[:5], 'reduced': pg.evaluate('window.__map.reduced')}
        if name == '1280-name':
            renderer = pg.evaluate("(() => { const gl = document.createElement('canvas').getContext('webgl'); const d = gl.getExtension('WEBGL_debug_renderer_info'); return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'unknown'; })()")
            report['gl_renderer'] = renderer
        pg.close()
    b.close()
print(json.dumps(report, indent=1))
(OUT / 'frames.json').write_text(json.dumps(report, indent=1))
