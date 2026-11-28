"""Read the game's own post-click reveal out of a recorded round (truth label source).

After the click the medallion parks over the TRUE holder for ~1-2 s (090812: reveal_slot 2 while
the click was 4). The live reader can miss it (reveal None at 0.89 on two rounds); this scans every
frame recorded after the live window with `find_marker_slot` + the settle reader and reports the
vote counts per slot, so a label is a measurement with counts, not a reading by eye.

    python dev/tools/jochul_reveal_label.py <round_dir> [--from S]
"""
import argparse
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
import jochul  # noqa: E402


def label(d, t_from=None):
    import cv2
    meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
    times = meta['times']
    t_from = jochul.SHUFFLE_DELAY + jochul.READ_CAP_S if t_from is None else t_from
    marker, settle, timeline = Counter(), Counter(), []
    for i, t in enumerate(times):
        if t < t_from:
            continue
        f = cv2.imread(os.path.join(d, '%05d.jpg' % i))
        m = jochul.find_marker_slot(f)
        s = jochul.read_settled(f)
        sc = jochul.marker_scores(f)
        if m:
            marker[m] += 1
        if s:
            settle[s] += 1
        timeline.append((round(t, 2), m, s, round(max(sc.values()), 3)))
    return {'round': os.path.basename(os.path.normpath(d)), 'from_s': t_from,
            'frames_scanned': len(timeline), 'marker_votes': dict(marker), 'settle_votes': dict(settle),
            'clicked': meta.get('clicked'), 'live_reveal': meta.get('reveal_slot'),
            'live_reveal_conf': meta.get('reveal_conf'), 'timeline': timeline}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('round_dir')
    ap.add_argument('--from', dest='t_from', type=float)
    ap.add_argument('--timeline', action='store_true')
    a = ap.parse_args()
    r = label(a.round_dir, a.t_from)
    tl = r.pop('timeline')
    print(json.dumps(r, ensure_ascii=False))
    if a.timeline:
        for row in tl:
            if row[1] or row[2]:
                print('  t=%-6s marker=%s settle=%s best=%s' % row)


if __name__ == '__main__':
    main()
