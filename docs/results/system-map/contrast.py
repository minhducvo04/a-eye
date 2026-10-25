import json, sys, numpy as np
from PIL import Image
from pathlib import Path
D = Path(sys.argv[1])
def lum(c):
    c = c / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]
out = {}
for name in ['1536-name', '1280-name', '1280-speed', '1280-cost', '390-name', '390-speed', '390-cost']:
    img = np.asarray(Image.open(D / f'{name}.png').convert('RGB')).astype(float)
    scale = img.shape[1] / (1536 if name.startswith('1536') else 1280 if name.startswith('1280') else 390)
    ratios = []
    for x, y, w, h, zone in json.loads((D / f'{name}.rects.json').read_text()):
        x0, y0, x1, y1 = [int(round(v * scale)) for v in (x + 3, y + 3, x + w - 3, y + h - 3)]
        if x1 <= x0 or y1 <= y0 or x0 < 0 or y0 < 0: continue
        L = lum(img[y0:y1, x0:x1]).ravel()
        if L.size < 20: continue
        bg = np.percentile(L, 50) if not zone else np.percentile(L, 50)
        text = np.percentile(L, 98)
        ratios.append(((text + 0.05) / (bg + 0.05), zone))
    r = sorted(v for v, z in ratios if not z)
    rz = sorted(v for v, z in ratios if z)
    out[name] = {'labels': len(r), 'worst': round(r[0], 2), 'p5': round(float(np.percentile(r, 5)), 2), 'median': round(float(np.median(r)), 2),
                 'zone_worst': round(rz[0], 2) if rz else None}
print(json.dumps(out, indent=1))
(D / 'contrast.json').write_text(json.dumps(out, indent=1))
