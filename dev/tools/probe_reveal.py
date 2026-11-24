import glob, sys
import cv2, numpy as np
sys.path.insert(0, '.')
import jochul

fs = sorted(glob.glob('dev/fixtures/jochul_round1/*.jpg'))
print('n', len(fs))


def green_scores(f):
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    H, S, V = (hsv[..., i].astype(int) for i in range(3))
    out = []
    for x in jochul.SETTLE_SLOTS:
        b = (slice(60, 300), slice(max(0, x - 40), x + 40))
        out.append(int(((H[b] >= 40) & (H[b] <= 95) & (S[b] >= 90) & (V[b] >= 70)).sum()))
    return out


for i in (60, 100, 140, 158, 165, 170, 175, 180, 185, 190, 195, 200, 206):
    f = cv2.imread(fs[i])
    if f is None:
        print(i, 'unreadable')
        continue
    reg = jochul.crop_region(f)
    print(i, 'marker', jochul.find_marker_slot(reg), 'green', green_scores(reg))
