# Source Generated with Decompyle++
# File: sprite_match.pyc (Python 3.11)

import ctypes
import ctypes.wintypes
import glob
import os
import time
import cv2
import numpy as np
from agf import AgfFile

try:
    ctypes.windll
    ctypes.WinDLL
except AttributeError:
    class _StubDLL:
        def __getattr__(self, name):
            return lambda *a, **k: 0
    class _StubLib:
        def __getattr__(self, name):
            return _StubDLL()
    ctypes.windll = _StubLib()
    ctypes.WinDLL = lambda *a, **k: _StubDLL()

(FIELD_W, FIELD_H) = (1024, 651)
MAX_MATCH_PX = 20000
CASCADE_K = 6
CASCADE_PREMIN = 1
DEFAULT_GAME_DIR = 'C:\\AKInteractive\\Gersang'

def find_game_dir():
    
    try:
        import win32gui
        import win32process
        found = []
        
        def _exe(pid):
            h = ctypes.windll.kernel32.OpenProcess(4096, False, pid)
            if not h:
                return ''
            
            try:
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                size = ctypes.wintypes.DWORD(ctypes.wintypes.MAX_PATH)
                ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                ctypes.windll.kernel32.CloseHandle(h)
                return buf.value if ok else ''
            except:
                ctypes.windll.kernel32.CloseHandle(h)


        
        def _enum(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindowTextLength(hwnd) == 0:   # decompile dropped the not
                return None
            (_, pid) = win32process.GetWindowThreadProcessId(hwnd)
            p = _exe(pid)
            if p.lower().endswith('\\gersang.exe'):
                found.append(os.path.dirname(p))
                return None

        win32gui.EnumWindows(_enum, None)
        if found:
            return found[0]
    except Exception:
        pass

    if os.path.isdir(DEFAULT_GAME_DIR):
        return DEFAULT_GAME_DIR
    return ''


def resolve_agf_paths(names, game_dir = None):
    game_dir = game_dir or find_game_dir()
    if not game_dir:
        raise FileNotFoundError('거상 설치 폴더를 찾을 수 없습니다 (게임 실행 필요)')
    quick = [
        os.path.join(game_dir, 'Assets', 'Textures', 'Characters'),
        os.path.join(game_dir, 'Assets', 'Textures', 'Skills')]
    paths = []
    deep = None
    for name in names:
        stem = name.lower()
        hit = ''
        for d in quick:
            for ext in ('.AGF', '.agf'):
                p = os.path.join(d, name + ext)
                if os.path.isfile(p):
                    hit = p
                    break
            if hit:
                break
        if not hit:
            if deep is None:
                deep = { os.path.splitext(os.path.basename(p))[0].lower(): p for p in glob.glob(os.path.join(game_dir, '**', '*.agf'), recursive = True) }
            hit = deep.get(stem, '')
        if not hit:
            raise FileNotFoundError(f'''AGF 없음: {name} (게임 폴더 {game_dir})''')
        paths.append(hit)
    return paths


def _trim(s):
    a = s[:, :, 3]
    (ys, xs) = np.where(a > 0)
    if len(xs) == 0:
        return s
    return s[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _enc(b, g, r):
    return b.astype(np.uint32) | g.astype(np.uint32) << 8 | r.astype(np.uint32) << 16


def _bg_color_counts(bg_dir, log):
    counts = { }
    files = sorted(glob.glob(os.path.join(bg_dir, '*.png'))) if bg_dir else []
    for p in files:
        im = cv2.imread(p)
        if im is None:
            continue
        if im.shape[:2] == (768, 1024):
            im = im[:FIELD_H]
        e = _enc(im[:, :, 0], im[:, :, 1], im[:, :, 2]).ravel()
        (u, c) = np.unique(e, return_counts = True)
        for k, v in zip(u.tolist(), c.tolist()):
            counts[k] = counts.get(k, 0) + v
    if files:
        log(f'''[*] 배경 코퍼스 {len(files)}장, 고유색 {len(counts)}개''')
    return counts


class SpriteMatcher:
    
    def __init__(self, agf_paths, bg_dir=None, mirror=True, n_anchors=3, n_probes=28,
                 probe_tol=3, accept=0.6, min_bits=55.0, min_frac=0.3,
                 skip_frames=None, bg_counts=None, log=print):
        self.probe_tol = int(probe_tol)
        self.accept = float(accept)
        self.min_bits = float(min_bits)
        self.min_frac = float(min_frac)
        self.log = log
        t0 = time.time()
        if bg_counts is None:
            bg_counts = _bg_color_counts(bg_dir, log) if bg_dir else { }
        self._bg_total = max(1, sum(bg_counts.values()))
        self._bgq = np.zeros((32, 32, 32), np.float64)
        if bg_counts:
            ks = np.fromiter(bg_counts.keys(), np.int64, len(bg_counts))
            vs = np.fromiter(bg_counts.values(), np.float64, len(bg_counts))
            np.add.at(self._bgq, ((ks & 255) >> 3, (ks >> 8 & 255) >> 3, (ks >> 16 & 255) >> 3), vs)
        skip_frames = skip_frames or set()
        tpl = []
        for path in agf_paths:
            stem = os.path.splitext(os.path.basename(path))[0]
            a = AgfFile(path)
            for i in range(a.nframes):
                if (stem, i) in skip_frames:
                    continue
                s = _trim(a.frame(i))
                variants = [
                    (s, f'''{stem}:{i}''')]
                if mirror:
                    variants.append((s[:, ::-1].copy(), f'''{stem}:{i}M'''))
                for im, tag in variants:
                    t = self._build_one(im, tag, bg_counts, n_anchors, n_probes)
                    if t is not None:
                        tpl.append(t)
        if not tpl:
            raise ValueError('유효한 템플릿이 없습니다')
        self.tpl = tpl
        self.w = np.array([ t['w'] for t in tpl ], np.int32)
        self.h = np.array([ t['h'] for t in tpl ], np.int32)
        (colors, items) = ([], [])
        for ti, t in enumerate(tpl):
            seen = set()
            for c, ax, ay in t['anchors']:
                (b, g, r) = (c & 255, c >> 8 & 255, c >> 16 & 255)
                for d in (0, -1, 1):
                    c2 = min(255, max(0, b + d)) | min(255, max(0, g + d)) << 8 | min(255, max(0, r + d)) << 16
                    if (c2, ax, ay) in seen:
                        continue
                    seen.add((c2, ax, ay))
                    colors.append(c2)
                    items.append((ti, ax, ay))
        colors = np.array(colors, np.uint32)
        items = np.array(items, np.int32)
        order = np.argsort(colors, kind = 'stable')
        (colors, items) = (colors[order], items[order])
        (uniq, start) = np.unique(colors, return_index = True)
        self.a_colors = uniq
        self.a_start = np.append(start, len(colors)).astype(np.int64)
        self.a_t = np.ascontiguousarray(items[:, 0])
        self.a_ax = np.ascontiguousarray(items[:, 1])
        self.a_ay = np.ascontiguousarray(items[:, 2])
        self.lutR = np.zeros(256, bool)
        self.lutR[uniq >> 16 & 255] = True
        log(f'''[*] 매처 빌드 {time.time() - t0:.1f}s — 템플릿 {len(tpl)}개, 앵커색 {len(uniq)}개, R-LUT 밀도 {self.lutR.mean() * 100:.0f}%''')
        return None

    
    def _cube_counts(self, b, g, r):
        t = self.probe_tol
        lo = [ np.clip(v - t, 0, 255).astype(np.int64) >> 3 for v in (b, g, r) ]
        hi = [ np.clip(v + t, 0, 255).astype(np.int64) >> 3 for v in (b, g, r) ]
        tot = np.zeros(len(lo[0]), np.float64)
        for ib in (0, 1):
            bb = hi[0] if ib else lo[0]
            mb = (ib == 0) | (hi[0] != lo[0])
            for ig in (0, 1):
                gg = hi[1] if ig else lo[1]
                mg = mb & ((ig == 0) | (hi[1] != lo[1]))
                for ir in (0, 1):
                    rr = hi[2] if ir else lo[2]
                    m = mg & ((ir == 0) | (hi[2] != lo[2]))
                    tot[m] += self._bgq[bb[m], gg[m], rr[m]]
        return tot

    
    def _build_one(self, s, tag, bg_counts, n_anchors, n_probes):
        (h, w) = s.shape[:2]
        if h < 25 or w < 20:
            return None
        interior = cv2.erode((s[:, :, 3] > 200).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        (ys, xs) = np.nonzero(interior)
        if len(xs) < 150:
            return None
        b, g, r = (s[ys, xs, 0].astype(np.int32), s[ys, xs, 1].astype(np.int32), s[ys, xs, 2].astype(np.int32))
        colors = _enc(s[ys, xs, 0], s[ys, xs, 1], s[ys, xs, 2])
        val = np.maximum(np.maximum(b, g), r)
        sat = (val - np.minimum(np.minimum(b, g), r)).astype(np.float64)
        distinct = (val >= 60) & (sat >= 25)
        if int(distinct.sum()) < 10:
            return None
        bgc = self._cube_counts(b, g, r)
        score = np.log2(bgc + 1.0) * 512.0 - sat
        min_d = max(6.0, (w * w + h * h) ** 0.5 / 4)
        anchors = []
        order = np.argsort(score)
        order = order[distinct[order]]
        top = ys < h * 0.4
        top_order = order[top[order]]
        if len(top_order):
            j = top_order[0]
            anchors.append((int(colors[j]), int(xs[j]), int(ys[j])))
        for j in order:
            if len(anchors) >= n_anchors:
                break
            if all(((xs[j] - ax) ** 2 + (ys[j] - ay) ** 2 >= min_d * min_d for _c, ax, ay in anchors)):
                anchors.append((int(colors[j]), int(xs[j]), int(ys[j])))
        if not anchors:
            return None
        di = np.nonzero(distinct)[0]
        n_d = min(n_probes // 2, len(di))
        sel_d = di[np.linspace(0, len(di) - 1, n_d).astype(np.int64)]
        sel_u = np.linspace(0, len(xs) - 1, min(n_probes - n_d, len(xs))).astype(np.int64)
        sel = np.unique(np.concatenate([
            sel_d,
            sel_u]))
        py, px = (ys[sel], xs[sel])
        p = (self._cube_counts(b[sel], g[sel], r[sel]) + 1.0) / self._bg_total
        wgt = np.clip(-np.log2(p), 1.0, 14.0).astype(np.float32)
        return {
            'w': w,
            'h': h,
            'tag': tag,
            'anchors': anchors,
            'px': px.astype(np.int32),
            'py': py.astype(np.int32),
            'pcol': s[py, px, :3].astype(np.int16),
            'wgt': wgt }

    
    def detect(self, frame_bgr, timings = None):
        pk = self._ensure_torch()
        if pk is not False:
            
            try:
                return self._detect_torch(frame_bgr, pk, timings)
            except Exception as e:
                self._torchpk = False
                self.log(f'''[매처] torch detect 실패 → numpy 폴백: {e!r}''')
            except:
                raise
                raise

        return self._detect_numpy(frame_bgr, timings)

    
    def _detect_numpy(self, frame_bgr, timings = None):
        f = frame_bgr[:FIELD_H, :FIELD_W]
        t0 = time.perf_counter()
        m = self.lutR[f[:, :, 2]]
        (ys, xs) = np.nonzero(m)
        if len(xs):
            enc = _enc(f[ys, xs, 0], f[ys, xs, 1], f[ys, xs, 2])
            idx = np.searchsorted(self.a_colors, enc)
            idx_c = np.minimum(idx, len(self.a_colors) - 1)
            ok = self.a_colors[idx_c] == enc
            ys, xs, cid = (ys[ok], xs[ok], idx_c[ok])
            if len(xs) > MAX_MATCH_PX:
                sub = np.linspace(0, len(xs) - 1, MAX_MATCH_PX).astype(np.int64)
                ys, xs, cid = (ys[sub], xs[sub], cid[sub])
        else:
            cid = np.empty(0, np.int64)
        t1 = time.perf_counter()
        if len(cid):
            cnt = (self.a_start[cid + 1] - self.a_start[cid]).astype(np.int64)
            tot = int(cnt.sum())
            first = self.a_start[cid]
            cum = np.cumsum(cnt)
            item = np.repeat(first, cnt) + (np.arange(tot) - np.repeat(cum - cnt, cnt))
            ti = self.a_t[item]
            ox = np.repeat(xs, cnt) - self.a_ax[item]
            oy = np.repeat(ys, cnt) - self.a_ay[item]
            inb = (ox >= 0) & (oy >= 0) & (ox + self.w[ti] <= FIELD_W) & (oy + self.h[ti] <= FIELD_H)
            ti, ox, oy = (ti[inb], ox[inb], oy[inb])
            key = ti.astype(np.int64) * (FIELD_W * FIELD_H) + oy.astype(np.int64) * FIELD_W + ox
            (_, ui) = np.unique(key, return_index = True)
            ti, ox, oy = (ti[ui], ox[ui], oy[ui])
        else:
            ti = np.empty(0, np.int32)
            ox = oy = np.empty(0, np.int64)
        t2 = time.perf_counter()
        raw = []
        fi16 = f.astype(np.int16)
        order = np.argsort(ti, kind = 'stable')
        ti, ox, oy = (ti[order], ox[order], oy[order])
        bounds = np.searchsorted(ti, np.arange(len(self.tpl) + 1))
        for t in np.unique(ti):
            (s0, s1) = (bounds[t], bounds[t + 1])
            tp = self.tpl[t]
            (oxs, oys) = (ox[s0:s1], oy[s0:s1])
            if len(tp['wgt']) > CASCADE_K:
                topk = np.argsort(-tp['wgt'])[:CASCADE_K]
                Yp = oys[:, None] + tp['py'][topk][None, :]
                Xp = oxs[:, None] + tp['px'][topk][None, :]
                hp = (np.abs(fi16[Yp, Xp] - tp['pcol'][topk][None, :, :]).max(2) <= self.probe_tol).sum(1)
                keep = hp >= CASCADE_PREMIN
                if not keep.any():
                    continue
                (oxs, oys) = (oxs[keep], oys[keep])
            Y = oys[:, None] + tp['py'][None, :]
            X = oxs[:, None] + tp['px'][None, :]
            d = np.abs(fi16[Y, X] - tp['pcol'][None, :, :]).max(axis = 2)
            hit = d <= self.probe_tol
            frac = hit.mean(axis = 1)
            bits = (hit * tp['wgt'][None, :]).sum(axis = 1)
            sc = np.maximum(frac, np.minimum(bits / (self.min_bits * 1.5), 1.0))
            low = tp['py'] >= tp['h'] * 0.55
            n_low = max(1, int(low.sum()))

            frac_low = (hit & low[None, :]).sum(axis = 1) / n_low
            for j in np.nonzero((frac >= self.accept) | (bits >= self.min_bits) & (frac >= self.min_frac))[0]:
                raw.append((float(sc[j]), int(oxs[j]), int(oys[j]), tp['w'], tp['h'], tp['tag'], float(frac_low[j])))
        t3 = time.perf_counter()
        raw.sort(reverse = True)
        out = []
        for sc, x, y, w, h, tag, lowf in raw:
            (cx, cy) = (x + w / 2, y + h / 2)
            if all(((cx - (kx + kw / 2)) ** 2 + (cy - (ky + kh / 2)) ** 2 > 144 for kx, ky, kw, kh, _s, _t, _lf in out)):
                out.append((x, y, w, h, sc, tag, lowf))
        if timings is not None:
            timings.update(prefilter = (t1 - t0) * 1000.0, expand = (t2 - t1) * 1000.0, verify = (t3 - t2) * 1000.0, total = (time.perf_counter() - t0) * 1000.0, cands = len(ti))
        return out

    
    def _ensure_torch(self):
        st = getattr(self, '_torchpk', 'untried')
        if st != 'untried':
            return st
        
        try:
            import torch
            dev = 'cpu'
            
            A = lambda a, dt: torch.as_tensor(np.asarray(a, dt), device = dev)

            T = len(self.tpl)
            P = max((len(t['px']) for t in self.tpl))
            py = np.zeros((T, P), np.int64)
            px = np.zeros((T, P), np.int64)
            pcol = np.zeros((T, P, 3), np.int16)
            wgt = np.zeros((T, P), np.float32)
            low = np.zeros((T, P), bool)
            valid = np.zeros((T, P), bool)
            nprobe = np.zeros(T, np.float32)
            nlow = np.zeros(T, np.float32)
            tk_py = np.zeros((T, CASCADE_K), np.int64)
            tk_px = np.zeros((T, CASCADE_K), np.int64)
            tk_pcol = np.zeros((T, CASCADE_K, 3), np.int16)
            for i, t in enumerate(self.tpl):
                n = len(t['px'])
                nprobe[i] = n
                py[i, :n] = t['py']
                px[i, :n] = t['px']
                pcol[i, :n] = t['pcol']
                wgt[i, :n] = t['wgt']
                valid[i, :n] = True
                lw = t['py'] >= t['h'] * 0.55
                low[i, :n] = lw
                nlow[i] = max(1, int(lw.sum()))
                top = np.argsort(-t['wgt'])[:CASCADE_K]
                kk = len(top)
                tk_py[i, :kk] = t['py'][top]
                tk_px[i, :kk] = t['px'][top]
                tk_pcol[i, :kk] = t['pcol'][top]
            pk = {
                'dev': dev,
                'a_colors': A(self.a_colors, np.int64),
                'a_start': A(self.a_start, np.int64),
                'a_t': A(self.a_t, np.int64),
                'a_ax': A(self.a_ax, np.int64),
                'a_ay': A(self.a_ay, np.int64),
                'lutR': torch.as_tensor(self.lutR, device = dev),
                'w': A(self.w, np.int64),
                'h': A(self.h, np.int64),
                'py': A(py, np.int64),
                'px': A(px, np.int64),
                'pcol': A(pcol, np.int16),
                'wgt': A(wgt, np.float32),
                'low': torch.as_tensor(low, device = dev),
                'valid': torch.as_tensor(valid, device = dev),
                'nprobe': A(nprobe, np.float32),
                'nlow': A(nlow, np.float32),
                **{
                    'tk_py': A(tk_py, np.int64),
                    'tk_px': A(tk_px, np.int64),
                    'tk_pcol': A(tk_pcol, np.int16),
                    'tw': np.array([ t['w'] for t in self.tpl ]),
                    'th': np.array([ t['h'] for t in self.tpl ]),
                    'tags': [ t['tag'] for t in self.tpl ] } }
            self._torchpk = pk
            self.log(f'''[매처] torch(CPU) 가속 경로 활성 — 템플릿 {T}''')
            return pk
        except Exception as e:
            self._torchpk = False
            self.log(f'''[매처] torch 경로 비활성, numpy 사용: {e!r}''')
            return False


    
    def _detect_torch(self, frame_bgr, pk, timings = None):
        import torch
        dev = pk['dev']
        tol = self.probe_tol
        accept = self.accept
        min_bits = self.min_bits
        min_frac = self.min_frac
        t0 = time.perf_counter()
        f = torch.as_tensor(frame_bgr[:FIELD_H, :FIELD_W], device = dev).to(torch.int64)
        mask = pk['lutR'][f[:, :, 2]]
        pts = mask.nonzero(as_tuple = False)
        if pts.numel() == 0:
            return []
        (ys, xs) = (pts[:, 0], pts[:, 1])
        enc = f[ys, xs, 0] | f[ys, xs, 1] << 8 | f[ys, xs, 2] << 16
        idx = torch.clamp(torch.searchsorted(pk['a_colors'], enc), max = pk['a_colors'].numel() - 1)
        ok = pk['a_colors'][idx] == enc
        (ys, xs, cid) = (ys[ok], xs[ok], idx[ok])
        if cid.numel() > MAX_MATCH_PX:
            sub = torch.linspace(0, cid.numel() - 1, MAX_MATCH_PX, device = dev).long()
            (ys, xs, cid) = (ys[sub], xs[sub], cid[sub])
        if cid.numel() == 0:
            return []
        cnt = pk['a_start'][cid + 1] - pk['a_start'][cid]
        tot = int(cnt.sum())
        if tot == 0:
            return []
        first = pk['a_start'][cid]
        cum = torch.cumsum(cnt, 0)
        item = torch.repeat_interleave(first, cnt) + (torch.arange(tot, device = dev) - torch.repeat_interleave(cum - cnt, cnt))
        ti = pk['a_t'][item]
        ox = torch.repeat_interleave(xs, cnt) - pk['a_ax'][item]
        oy = torch.repeat_interleave(ys, cnt) - pk['a_ay'][item]
        inb = (ox >= 0) & (oy >= 0) & (ox + pk['w'][ti] <= FIELD_W) & (oy + pk['h'][ti] <= FIELD_H)
        (ti, ox, oy) = (ti[inb], ox[inb], oy[inb])
        if ti.numel() == 0:
            return []
        key = torch.unique(ti * (FIELD_W * FIELD_H) + oy * FIELD_W + ox)
        ti = key // (FIELD_W * FIELD_H)
        rem = key - ti * (FIELD_W * FIELD_H)
        oy = rem // FIELD_W
        ox = rem - oy * FIELD_W
        fi16 = f.to(torch.int16)
        ncand = int(ti.numel())
        raw = []
        CHUNK = 16384
        for s in range(0, ncand, CHUNK):
            tic = ti[s:s + CHUNK]
            oxc = ox[s:s + CHUNK]
            oyc = oy[s:s + CHUNK]
            Yp = oyc[:, None] + pk['tk_py'][tic]
            Xp = oxc[:, None] + pk['tk_px'][tic]
            hp = ((fi16[Yp, Xp] - pk['tk_pcol'][tic]).abs().amax(dim = 2) <= tol).sum(1)
            kp = hp >= CASCADE_PREMIN
            if not bool(kp.any()):
                continue
            (tic, oxc, oyc) = (tic[kp], oxc[kp], oyc[kp])
            Y = oyc[:, None] + pk['py'][tic]
            X = oxc[:, None] + pk['px'][tic]
            g = fi16[Y, X]
            dd = (g - pk['pcol'][tic]).abs().amax(dim = 2)
            hit = (dd <= tol) & pk['valid'][tic]
            hf = hit.float()
            frac = hf.sum(1) / pk['nprobe'][tic]
            bits = (hf * pk['wgt'][tic]).sum(1)
            sc = torch.maximum(frac, torch.clamp(bits / (min_bits * 1.5), max = 1.0))
            frac_low = (hit & pk['low'][tic]).sum(1).float() / pk['nlow'][tic]
            keep = (frac >= accept) | (bits >= min_bits) & (frac >= min_frac)
            kj = keep.nonzero(as_tuple = False).flatten()
            if kj.numel():
                scj = sc[kj].tolist()
                flj = frac_low[kj].tolist()
                tij = tic[kj].tolist()
                oxj = oxc[kj].tolist()
                oyj = oyc[kj].tolist()
                (tw, th, tags) = (pk['tw'], pk['th'], pk['tags'])
                for a in range(len(scj)):
                    t = tij[a]
                    raw.append((scj[a], oxj[a], oyj[a], int(tw[t]), int(th[t]), tags[t], flj[a]))
        raw.sort(reverse = True)
        out = []
        for sc, x, y, w, h, tag, lowf in raw:
            (cx, cy) = (x + w / 2, y + h / 2)
            if all(((cx - (kx + kw / 2)) ** 2 + (cy - (ky + kh / 2)) ** 2 > 144 for kx, ky, kw, kh, _s, _t, _lf in out)):
                out.append((x, y, w, h, sc, tag, lowf))
        if timings is not None:
            timings.update(total = (time.perf_counter() - t0) * 1000.0, cands = ncand)
        return out


