"""Replay a recorded 조철 round through the CURRENT decision chain, offline.

Input: a `debug/jochul_rounds/round_*` folder (board-crop JPGs + meta.json with `times`, written
by `jochul.RoundRecorder`, whose clock starts when `_handle_jochul` starts) and, optionally, the
round's `jochul_pkts/pkt_*.log`.

The chain mirrors `brain._handle_jochul_inner`:
  1. start slot: medallion lock / colour pattern over recorder t in [0, SHUFFLE_DELAY)
  2. live window: frames with recorder t in [SHUFFLE_DELAY, SHUFFLE_DELAY + READ_CAP_S), fed to the
     same `_on_frame` logic (reveal-burst marker after REVEAL_GUARD_S, settle reader once the row
     is still), stopping early when the marker locks
  3. pkt: `pktjochul.PktJochul.solve(first)` on the packet log
  4. answer = pkt, else marker/settle lock, else `solve_tracked` over the window frames
Frames recorded AFTER the live window (the click and the game's reveal) are never shown to the
chain, so the post-click reveal cannot leak into the replayed answer.

    python dev/tools/jochul_round_replay.py <round_dir> [--pkt <pkt.log>] [--truth N | --not N]
Prints a JSON line per round (`--json`) or a readable block.
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'probe'))
import jochul  # noqa: E402
import pktjochul  # noqa: E402

MODEL = os.path.join(REPO, 'assets', 'models', 'jochul', 'jochul.pt')


def load_round(d):
    import cv2
    meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
    times = list(meta['times'])
    frames = [cv2.imread(os.path.join(d, '%05d.jpg' % i)) for i in range(len(times))]
    return meta, frames, times


def start_slot(frames, times):
    """brain: sample from t=0 until the marker locks or SHUFFLE_DELAY passes."""
    marker_seen, pattern_seen = [], []
    for f, t in zip(frames, times):
        if t >= max(jochul.FIRST_TILE_DELAY, jochul.SHUFFLE_DELAY):
            break
        pattern_seen.append(jochul.find_first_tile(f))
        if jochul.marker_lock(marker_seen, jochul.find_marker_slot(f)):
            break
    mv, pv = jochul.vote_marker(marker_seen), jochul.vote_marker(pattern_seen)
    return mv or pv, {'medal': mv, 'pattern': pv}


def live_window(frames, times):
    """brain._on_frame over the record_all window. Returns (win_frames, win_times, st)."""
    import cv2
    st = {'prev': None, 'still': 0, 'votes': [], 'marker_votes': [], 'marker': None, 'locked': None,
          'marker_t': None, 'locked_t': None}
    t0 = jochul.SHUFFLE_DELAY
    wf, wt = [], []
    for f, rt in zip(frames, times):
        if rt < t0:
            continue
        t = rt - t0
        if t >= jochul.READ_CAP_S or st['marker'] is not None:
            break
        wf.append(f)
        wt.append(t)
        if t >= jochul.REVEAL_GUARD_S:
            hit = jochul.marker_lock(st['marker_votes'], jochul.find_marker_slot(f))
            if hit and st['marker'] is None:
                st['marker'], st['marker_t'] = hit, round(t, 2)
        band = jochul.row_band(f)
        if st['prev'] is not None:
            dif = float(np.mean(cv2.absdiff(band, st['prev'])))
            st['still'] = st['still'] + 1 if dif < 3.0 else 0
        st['prev'] = band
        if st['still'] < 5:
            continue
        a = jochul.read_settled(f)
        if jochul.settle_vote(st['votes'], a) and st['locked'] is None:
            st['locked'], st['locked_t'] = a, round(t, 2)
    st.pop('prev')
    return wf, wt, st


def pkt_solve(path, first):
    if not path:
        return None, 'no pkt log'
    import replay as probe_replay
    rec = pktjochul.PktJochul()
    rec.begin()
    for direction, payload in probe_replay.load(path):
        rec.feed(direction, payload)
    return rec.solve(first)


_SOLVER = None


def solver():
    global _SOLVER
    if _SOLVER is None:
        _SOLVER = jochul.JochulSolver(MODEL)
        _SOLVER.preload()
    return _SOLVER


def track_votes(frames, times, first):
    """The answer comes from the shipped `JochulSolver.solve_tracked` (the function brain calls);
    the per-setting breakdown is recomputed on the same detections for the report only."""
    s = solver()
    dets = s.detect_centroids(frames)
    real_detect = s.detect_centroids
    s.detect_centroids = lambda frames, conf=0.20: dets   # detect once, reuse for the real call
    try:
        ans, info = s.solve_tracked(frames, times, first)
    finally:
        s.detect_centroids = real_detect
    per = []
    for gate, decay in s.ENSEMBLE_SETTINGS:
        a, why = jochul.track_centroids(np.asarray(times), dets, first, gate=gate, decay=decay)
        per.append({'gate': gate, 'decay': decay, 'ans': a, 'info': why})
    return ans, info, per, dets


def replay(d, pkt=None, first=None):
    meta, frames, times = load_round(d)
    f_slot, f_info = start_slot(frames, times)
    use_first = first or f_slot
    wf, wt, st = live_window(frames, times)
    p_ans, p_info = pkt_solve(pkt, use_first)
    out = {'round': os.path.basename(os.path.normpath(d)), 'frames': len(frames),
           'window_frames': len(wf), 'window_s': round(wt[-1], 2) if wt else 0,
           'first_replayed': f_slot, 'first_info': f_info, 'first_live': meta.get('first'),
           'first_used': use_first, 'pkt': p_ans, 'pkt_info': p_info,
           'marker': st['marker'], 'marker_t': st['marker_t'], 'settle': st['locked'],
           'settle_t': st['locked_t'], 'live_clicked': meta.get('clicked'),
           'live_reveal': meta.get('reveal_slot'), 'live_passed': meta.get('passed')}
    if p_ans is not None:
        out.update(answer=p_ans, source='pkt')
        return out
    if st['marker'] or st['locked']:
        out.update(answer=st['marker'] or st['locked'], source='marker' if st['marker'] else 'settle')
        return out
    ans, info, per, _dets = track_votes(wf, wt, use_first)
    out.update(answer=ans, source='tracker' if ans is not None else 'abstain', track_info=info,
               votes=[(p['gate'], p['decay'], p['ans'], p['info']) for p in per])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('round_dir')
    ap.add_argument('--pkt')
    ap.add_argument('--first', type=int)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    r = replay(a.round_dir, a.pkt, a.first)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, default=str))
        return
    for k, v in r.items():
        if k == 'votes':
            for g, dcy, ans, info in v:
                print('   gate=%-5s decay=%-4s -> %-4s %s' % (g, dcy, ans, info))
        else:
            print('%-15s %s' % (k, v))


if __name__ == '__main__':
    main()
