"""Per-second 마패-hit timeline per round. python dev/tools/jochul_marker_timeline.py <dir>"""
import glob, json, os, sys
import cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import jochul

for p in sorted(glob.glob(os.path.join(sys.argv[1], 'round_*'))):
    meta = json.load(open(os.path.join(p, 'meta.json'), encoding='utf-8'))
    files = sorted(glob.glob(os.path.join(p, '*.jpg')) + glob.glob(os.path.join(p, '*.png')))
    print('%s first=%s truth=%s frames=%d' % (os.path.basename(p),
          meta.get('first') or meta.get('start_slot'),
          meta.get('truth') or meta.get('reveal_slot'), len(files)))
    secs = {}
    for i, fp in enumerate(files):
        f = cv2.imread(fp)
        if f is None:
            continue
        if f.shape[1] > 800:
            f = jochul.crop_region(f)
        s = jochul.find_marker_slot(f)
        k = int(meta['times'][min(i, len(meta['times']) - 1)])
        c = secs.setdefault(k, [0, 0, {}])
        c[0] += 1
        if s:
            c[1] += 1
            c[2][s] = c[2].get(s, 0) + 1
    for k in sorted(secs):
        n, h, slots = secs[k]
        print('  t=%2ds hits %2d/%2d modal=%s' % (k, h, n, max(slots, key=slots.get) if slots else '-'))
