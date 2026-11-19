# Source Generated with Decompyle++
# File: captcha.pyc (Python 3.11)

import cv2
import numpy as np
import torch
import torch.nn as nn
IMG_H = 64
(REF_W, REF_H) = (1024, 768)
TEXT_REGION = (379, 280, 642, 370)
JAMUN_LEN = 5
CHAR_CONF_MIN = 0.8

def crop_text(frame):
    (h, w) = frame.shape[:2]
    (x0, y0, x1, y1) = TEXT_REGION
    if (w, h) != (REF_W, REF_H):
        sy = h / REF_H
        sx = w / REF_W
        y0 = round(y0 * sy)
        x0 = round(x0 * sx)
        y1 = round(y1 * sy)
        x1 = round(x1 * sx)
    return frame[y0:y1, x0:x1]


class _CRNN(nn.Module):
    
    def __init__(self, n_channels, n_classes, n_hidden=256):
        super().__init__()
        
        def block(cin, cout, k = 3, s = 1, p = 1, do = 0.1):
            return nn.Sequential(nn.Conv2d(cin, cout, k, s, p), nn.BatchNorm2d(cout), nn.ReLU(True), nn.Dropout2d(do))

        self.cnn = nn.Sequential(block(n_channels, 64, do = 0.05), nn.MaxPool2d(2, 2), block(64, 128, do = 0.05), nn.MaxPool2d(2, 2), block(128, 256), block(256, 256), nn.MaxPool2d((2, 2), (2, 1), (0, 1)), block(256, 512, do = 0.15), block(512, 512, do = 0.15), nn.MaxPool2d((2, 2), (2, 1), (0, 1)), block(512, 512, 2, 1, 0, do = 0.15))
        self.rnn1 = nn.LSTM(512, n_hidden, bidirectional = True)
        self.rnn2 = nn.LSTM(2 * n_hidden, n_hidden, bidirectional = True)
        self.fc = nn.Linear(2 * n_hidden, n_classes)

    
    def forward(self, x):
        conv = self.cnn(x)
        if conv.size(2) > 1:
            conv = torch.mean(conv, 2, keepdim = True)
        conv = conv.squeeze(2).permute(2, 0, 1)
        (rec, _) = self.rnn1(conv)
        (rec, _) = self.rnn2(rec)
        return self.fc(rec)

    __classcell__ = None


class TextReader:
    
    def __init__(self, ckpt_path):
        self.ckpt_path = ckpt_path
        self.model = None
        self.alphabet = ''
        self.ready = False
        self.last_step_conf = 0

    
    def preload(self):
        ckpt = torch.load(self.ckpt_path, map_location = 'cpu', weights_only = True)
        self.alphabet = ckpt['alphabet']
        model = _CRNN(1, len(self.alphabet) + 1)
        model.load_state_dict(ckpt['state_dict'])
        model.eval()
        self.model = model
        self.ready = True

    
    def read(self, crop_bgr):
        if not self.ready:
            return ('', 0)
        if crop_bgr.ndim == 3:
            gray = cv2.cvtColor(crop_bgr, cv2.COLOR_RGB2GRAY)
        else:
            gray = crop_bgr
        (h, w) = gray.shape
        new_w = max(12, int(round(w * IMG_H / float(h))))
        gray = cv2.resize(gray, (new_w, IMG_H), interpolation = cv2.INTER_AREA)
        x = (gray.astype(np.float32) / 255 - 0.5) / 0.5
        x = torch.from_numpy(x)[(None, None)]
        with torch.no_grad():
            logits = self.model(x)
        return self._greedy(logits)

    
    def _greedy(self, logits):
        lp = logits.log_softmax(2)
        probs_full = lp.exp()[:, 0]
        (vals, idx) = lp.max(2)
        seq = idx[:, 0].tolist()
        probs = vals[:, 0].exp().tolist()
        prev = None
        segs = []
        for t, c in enumerate(seq):
            if c != 0:
                if c != prev:
                    segs.append([
                        self.alphabet[c - 1],
                        probs[t],
                        [
                            t]])
                else:
                    segs[-1][1] = max(segs[-1][1], probs[t])
                    segs[-1][2].append(t)
            prev = c
        
        def _text_conf(ss):
            steps = []
            margins = []
            for _, _, ts in ss:
                for t in ts:
                    p = probs[t]
                    steps.append(p)
                    row = probs_full[t].clone()
                    row[0] = 0
                    row[seq[t]] = 0
                    rival = float(row.max())
                    margins.append(p / (p + rival) if p + rival > 0 else 1.0)
            conf = float(np.exp(np.mean(np.log(np.clip(margins, 1e-09, 1.0))))) if margins else 0
            if steps:
                conf = conf * float(np.exp(np.mean(np.log(steps))))
            self.last_step_conf = conf
            return (''.join((s[0] for s in ss)).strip().upper(), conf)

        strong = [ s for s in segs if s[1] >= CHAR_CONF_MIN ]
        if len(strong) == JAMUN_LEN and len(strong) != len(segs):
            return _text_conf(strong)
        return _text_conf(segs)


