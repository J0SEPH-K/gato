# GATO

Auto-hunt macro for 거상 (Gersang). Windows 10/11 x64, Python 3.11, game in windowed mode
at 1024x768, 1280x960 or 1440x1080.

## Install on a new PC

1. Get the repo: `git clone https://github.com/J0SEPH-K/gato.git C:\Gato`
   (or Code -> Download ZIP, extract to `C:\Gato`). Keep the path short, no spaces.
2. Open PowerShell as administrator in that folder and run:

       powershell -ExecutionPolicy Bypass -File install.ps1

   Installs Python 3.11 if missing, creates `.venv`, installs pinned packages (about 10 min, torch is large).
3. Start the game and get the character onto the field.
4. Double-click `run.bat` (asks for administrator).

First launch copies `settings.default.json` to `prism_settings.json`. That file holds your
settings and is git-ignored; never commit it.

## Update

    git pull

## Layout

    run_gato.py      entry point and preflight checks
    prism.py         app window and API for ui/
    brain.py         main loop (scene detection, targeting, clicks, schedule)
    combat.py        battle logic
    detector.py      mob detection (YOLO models, AGF sprite matcher)
    input.py         mouse/keyboard (SendInput, cursor landing check)
    capture.py wgc.py  window capture (Windows Graphics Capture)
    config.py        settings and monster catalogue
    ui/              frontend
    assets/          models, templates, sprites
    docs/            install guide (KR), remote spec
    dev/             macOS UI preview, PyInstaller spec

## Troubleshooting

- Log: `gato_traceback.log` in the install folder.
- "game window not found": start the game first.
- "game window is WxH": switch to one of the three supported windowed sizes.
