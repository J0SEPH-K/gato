import sys, os, glob, io
sys.path.insert(0, r'C:\Gato')
import cv2, numpy as np
out = io.open(r'C:\Gato\probe\med_out.txt', 'w', encoding='utf-8')
def P(*a):
    print(*a, file=out, flush=True)

CLICK_X = {1:354, 2:431, 3:518, 4:598, 5:678}
WIN = 45
Y1, Y2 = 231, 345

dirs = []
for pat in (r'C:\Gato\jochul_fail\20261125_154408', r'C:\Gato\jochul_rounds\round_20261125_154414'):
    dirs.extend(sorted(glob.glob(pat)))
P('DIRS', dirs)

for d in dirs:
    P('====', d)
    try:
        files = sorted(os.listdir(d))
    except Exception as e:
        P('listdir fail', e)
        continue
    for f in files:
        p = os.path.join(d, f)
        if not f.lower().endswith('.png'):
            P('  file', f)
            continue
        img = cv2.imread(p)
        if img is None:
            P(f, 'UNREADABLE')
            continue
        h, w = img.shape[:2]
        P(f, 'shape', w, h)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([12, 110, 140]), np.array([38, 255, 255]))
        counts = {}
        for s, cx in CLICK_X.items():
            x1 = max(0, cx - WIN)
            x2 = min(w, cx + WIN)
            y2 = min(h, Y2)
            counts[s] = int(mask[Y1:y2, x1:x2].sum() // 255)
        P('  gold_mass', ' '.join('%d=%d' % (k, counts[k]) for k in sorted(counts)))
        best = max(counts, key=counts.get)
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        top2 = ranked[1][1] if len(ranked) > 1 else 0
        gap = (counts[best] - top2) / float(counts[best]) if counts[best] else 0.0
        P('  best_slot', best, 'gap', round(gap, 4))
        try:
            sc = None
            if hasattr(cv2, 'matchTemplate'):
                pass
            import jochul as J
            if hasattr(J, 'marker_scores'):
                sc = J.marker_scores(img)
                P('  marker_scores', sc)
        except Exception as e:
            P('  marker_scores_err', type(e).__name__, e)

P('DONE')
out.close()
