"""GATO launcher — preflight checks, then hand off to prism.main().

Windows entry point. Keep thin: everything here is fail-fast preflight; the
actual bot logic lives in prism.
"""
import os
import sys

GAME_EXE = "gersang.exe"
MIN_PY = (3, 11)


def _fail(msg: str) -> None:
    print("ERROR: " + msg)
    if os.name == "nt":
        # The packaged app has no console: show the reason instead of exiting silently.
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg, "GATO", 0x10)
        except Exception:
            pass
    sys.exit(1)


def _check_python() -> None:
    if sys.version_info[:2] < MIN_PY:
        _fail(
            "Python %d.%d is too old. This program needs Python %d.%d or newer "
            "(install Python 3.11 64-bit)." % (*sys.version_info[:2], *MIN_PY)
        )
    if os.name != "nt":
        print("WARNING: this program is Windows-only; continuing for testing.")


def _check_admin() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:  # pragma: no cover - Windows only
        print(f"WARNING: could not check administrator rights ({e}).")
        return
    if not is_admin:
        _fail(
            "Administrator rights are required (the bot sends keyboard/mouse "
            "input and reads other processes). Right-click and choose "
            "'Run as administrator'."
        )


def _check_game_window() -> None:
    if os.name != "nt":
        return
    try:
        import psutil

        found = [p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == GAME_EXE]
    except Exception as e:
        print(f"WARNING: could not scan running processes ({e}).")
        return
    if not found:
        _fail(
            f"The game window was not found. Start the game ('{GAME_EXE}') "
            "before starting the bot."
        )


# 거상 only ships 3 fixed windowed-mode resolutions, all 4:3 (confirmed from the
# game's own patch notes): 1024x768 (reference), 1280x960, 1440x1080. Every
# captured frame is scaled to the 1024x768 reference before any pixel/trigger
# check runs, so all three are safe automatically (pure uniform scale, same
# aspect ratio). Fullscreen "화면 맞춤" (fit-to-screen) stretches the content to
# the monitor's real aspect (usually 16:9), which breaks every pixel
# coordinate in this bot silently. Catch that here instead of misclicking.
SUPPORTED_RESOLUTIONS = ((1024, 768), (1280, 960), (1440, 1080))


def _check_game_resolution() -> None:
    if os.name != "nt":
        return
    try:
        import win32con
        import win32gui

        import capture  # noqa: PLC0415

        hwnd = capture.find_window()
        if not hwnd:
            return  # already covered by _check_game_window
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w, h = right - left, bottom - top
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        is_popup_fullscreen = bool(style & win32con.WS_POPUP) and not bool(style & win32con.WS_CAPTION)
    except Exception as e:
        print(f"WARNING: could not check game resolution ({e}).")
        return
    if is_popup_fullscreen:
        _fail(
            "The game is in fullscreen mode. This bot only works in windowed "
            "mode (ESC -> 일반 설정 -> 화면 설정 -> 게임 화면 방식 -> 창 모드), because "
            "fullscreen stretches the image and every button location would be "
            "wrong."
        )
    if (w, h) not in SUPPORTED_RESOLUTIONS:
        _fail(
            f"The game window is {w}x{h}, not one of the 3 supported sizes "
            f"{SUPPORTED_RESOLUTIONS}. In the game: ESC -> 일반 설정 -> 화면 설정 -> "
            "해상도 설정, pick 1024x768, 1280x960 or 1440x1080 (창 모드 only)."
        )


def _check_assets() -> None:
    try:
        import config  # noqa: PLC0415

        paths = set()
        for name in dir(config):
            v = getattr(config, name)
            if isinstance(v, str) and (os.sep in v or "/" in v) and any(
                v.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".onnx", ".pt", ".json")
            ):
                paths.add(v)
        missing = [p for p in sorted(paths) if not os.path.exists(p)]
        if missing:
            _fail("Missing data files (re-copy the program folder intact): " + ", ".join(missing[:10]))
    except ImportError as e:
        _fail(f"Could not load config.py ({e}); the program folder looks incomplete.")
    except Exception as e:
        print(f"WARNING: asset check skipped ({e}).")


def _seed_settings() -> None:
    """First run: copy settings.default.json -> prism_settings.json (never overwrite)."""
    import shutil

    import config

    here = os.path.dirname(os.path.abspath(__file__))
    live = os.path.join(config.BASE_DIR, "prism_settings.json")
    default = os.path.join(here, "settings.default.json")
    if not os.path.exists(live) and os.path.exists(default):
        shutil.copyfile(default, live)
        print("First run: created prism_settings.json from defaults.")


def _selftest() -> int:
    """`Gato.exe --selftest`: import every heavy dependency and run one model inference, write
    selftest.txt next to the app, exit 0/1. Proves a packaged build is complete without the GUI."""
    import time
    import traceback

    here = os.path.dirname(os.path.abspath(__file__))
    # Log next to the exe so the build step can always read it; fall back to the user dir if the
    # program directory happens to be read-only. Written incrementally so a hard crash still leaves
    # evidence of how far the run got.
    log_path = os.path.join(here, "selftest.txt")
    try:
        open(log_path, "a", encoding="utf-8").close()
    except OSError:
        import config as _c

        log_path = os.path.join(_c.BASE_DIR, "selftest.txt")
    log = open(log_path, "w", encoding="utf-8")

    out = []
    ok = True

    def emit(line):
        out.append(line)
        log.write(line + "\n")
        log.flush()

    def step(name, fn):
        nonlocal ok
        t0 = time.time()
        try:
            r = fn()
            emit("PASS %-22s %.1fs %s" % (name, time.time() - t0, r if r is not None else ""))
        except Exception as e:  # noqa: BLE001
            ok = False
            emit("FAIL %-22s %s: %s" % (name, type(e).__name__, e))
            emit(traceback.format_exc(limit=3).rstrip())

    emit("START %s %s" % (sys.version.split()[0], sys.executable))
    step("frozen", lambda: "yes" if getattr(sys, "frozen", False) else "no (running from source)")
    for mod in ("numpy", "cv2", "torch", "torchvision", "ultralytics", "win32gui", "win32api", "webview",
                "windows_capture", "psutil", "scapy.all", "websockets", "cryptography"):
        step("import " + mod, lambda m=mod: __import__(m) and None)
    for mod in ("config", "vision", "detector", "capture", "input", "combat", "brain", "prism"):
        step("module " + mod, lambda m=mod: __import__(m) and None)

    def _yolo():
        import numpy as np
        from ultralytics import YOLO

        path = os.path.join(here, "assets", "models", "jochul", "jochul.pt")
        m = YOLO(path)
        m.predict(source=np.zeros((512, 512, 3), dtype=np.uint8), imgsz=512, verbose=False)
        return os.path.basename(path)

    step("yolo model + predict", _yolo)

    def _assets():
        import config

        missing = [p for p in (config.JOCHUL_MODEL, config.TEXT_MODEL) if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return "models present"

    step("assets", _assets)
    step("ui", lambda: os.path.getsize(os.path.join(here, "ui", "index.html")))
    emit("RESULT " + ("ALL PASS" if ok else "FAILED"))
    log.close()
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv:
        try:
            code = _selftest()
        except Exception:  # noqa: BLE001
            import traceback

            sys.stderr.write(traceback.format_exc())
            code = 1
        sys.exit(code)
    print("GATO launcher: running preflight checks...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    _seed_settings()
    _check_python()
    _check_admin()
    _check_game_window()
    _check_game_resolution()
    _check_assets()
    print("Preflight OK. Starting bot UI...")
    try:
        import prism
    except ModuleNotFoundError as e:
        _fail(
            "A required package is missing: '%s'. Run: py -3.11 -m pip install "
            "-r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu" % e.name
        )

    prism.main()


if __name__ == "__main__":
    main()