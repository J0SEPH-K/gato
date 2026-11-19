"""GATO desktop UI — macOS DESIGN PREVIEW ONLY.

This is NOT the production app. prism.py's real Api class talks to the
actual Windows game process (win32gui, ctypes.windll, real combat state) and
cannot run on macOS at all. This file exists solely so Jungjun can open the
exact same ui/index.html on his Mac and see/edit the design without the
Windows PC, by backing every pywebview.api.* call the frontend makes with a
small in-memory stub that returns clean, empty/neutral starting state (not
"realistic fake numbers" -- the whole point of this tool is telling real
data apart from decoration, so it starts at zero/empty everywhere a real
session would, and a few buttons below let Jungjun fill in sample state by
hand to see how populated cards actually look).

Run:
    pip3 install pywebview
    python3 dev/preview_ui.py

Never wire this file's Api into run_gato.py / prism.py. Never point it at
assets/pin_templates or anything game-account-related.
"""
from __future__ import annotations

import os
import time

import webview

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


class PreviewApi:
    """Stands in for prism.py's real Api. Every method mirrors the real
    one's name/shape (see ui/index.html's pywebview.api.* calls) but returns
    local, clearly-synthetic preview state -- nothing here ever touches the
    real game, a real account, or real settings files."""

    def __init__(self):
        self.running = False
        self.battles = 0
        self.sched_active = False
        self.sched = {"cycle": 0, "cycles": 3, "battles": 0, "target": 10, "resting": False, "rest_left": 0}
        self.monster = "건달바의혼"
        self.records = []  # user can add via the "샘플 데이터" preview button in devtools console
        self.kill = []
        self.cfg = {
            "monsters": {
                self.monster: {
                    "squad_counts": [2, 2, 2, 2, 2, 2],
                    "center_move_delay": 1.0,
                    "lead_px": 80,
                    "summon_mode": "none",
                    "multi_retreat": False,
                    "noejeonju": False,
                    "attack_keys": ["3", "4", "5", "6"],
                }
            },
            "categories": ["기타", "월천귀문"],
            "mob_category": {self.monster: "월천귀문"},
            "catalog": [self.monster],
            "current_monster": self.monster,
            "banja_mode": False,
            "gm_chat_msg": "",
            "discord_webhook": "",
            "discord_token": "",
            "discord_channel": "",
            "ntfy_url": "",
            "notify_whisper": True,
            "notify_normal": True,
            "notify_repeat": False,
            "sched_cycles": 3,
            "sched_battles": 10,
            "sched_rest_sec": 600,
            "stamp": "preview-0",
        }
        self._seq = 0
        self._events = []
        self._t0 = time.time()

    # ---- window chrome (no-ops on this preview window) ----
    def win_resize(self, w, h):
        return None

    def win_size_save(self, w, h):
        return None

    def win_minimize(self):
        return None

    def win_close(self):
        os._exit(0)

    # ---- status / polling ----
    def status(self):
        return {
            "running": self.running,
            "window_found": self.running,
            "window_count": 1 if self.running else 0,
            "gato": False,
            "monster": self.monster,
            "fps": 0.0,
            "width": 1024,
            "height": 768,
            "battle_count": self.battles,
            "vision": {"scene": "main" if self.running else "none", "scene_label": "메인화면" if self.running else None, "triggers": [], "whisper": False},
            "clients": [],
            "admin": True,
            "auth": {"ok": False, "label": "미리보기 — 서버 인증 없음", "notice": None},
            "schedule": {"active": self.sched_active, **self.sched},
            "update": {"available": False},
        }

    def tick(self, last_seq, last_chat_seq):
        return {"status": self.status(), "events": [], "chat": []}

    def login(self, auth_id):
        return {"ok": False, "label": "미리보기 — 로그인 비활성"}

    def logout(self):
        return {"label": ""}

    def auth_status(self):
        return {"auth_id": "", "label": "", "banja": False}

    def portrait(self, name):
        return None  # preview deliberately has no real sprite assets bundled

    # ---- config ----
    def get_config(self):
        return self.cfg

    def save_monster_cfg(self, name, patch, stamp):
        self.cfg.setdefault("monsters", {}).setdefault(name, {}).update(patch)
        self.cfg["stamp"] = f"preview-{int(time.time())}"
        return self.cfg

    def save_common(self, common, stamp):
        self.cfg.update(common)
        self.cfg["stamp"] = f"preview-{int(time.time())}"
        return self.cfg

    def set_monster(self, name):
        self.monster = name
        self.cfg["current_monster"] = name
        return None

    # ---- records / kill rank ----
    def appear_records(self):
        return self.records

    def kill_rank(self):
        return self.kill

    def reset_count(self):
        self.battles = 0
        self.records = []
        return self.status()

    # ---- start/stop/schedule (preview: just flips local flags) ----
    def start(self):
        self.running = True
        return self.status()

    def stop(self):
        self.running = False
        return self.status()

    def schedule_start(self, cycles, battles, rest_sec):
        self.sched_active = True
        self.sched = {"cycle": 1, "cycles": cycles, "battles": 0, "target": battles, "resting": False, "rest_left": rest_sec}
        return self.status()

    def schedule_stop(self):
        self.sched_active = False
        return self.status()

    # ---- notification test buttons ----
    def test_webhook(self, url):
        return "미리보기 — 실제 전송 안 함"

    def test_ntfy(self, topic):
        return "미리보기 — 실제 전송 안 함"

    def self_update(self):
        return {"ok": False, "label": "미리보기 — 업데이트 비활성"}


def main():
    api = PreviewApi()
    webview.create_window(
        "Gato_super (macOS 디자인 미리보기)",
        os.path.join(UI_DIR, "index.html"),
        js_api=api,
        width=960,
        height=660,
        min_size=(720, 560),
        background_color="#14110c",
        frameless=False,  # keep real OS chrome on the preview -- the real
                           # app's frameless titlebar + resize grips are
                           # Windows-coded (win32gui) and not meaningful to
                           # preview here; this only affects the window
                           # frame, not ui/index.html's own in-page titlebar
    )
    webview.start(debug=True)


if __name__ == "__main__":
    main()
