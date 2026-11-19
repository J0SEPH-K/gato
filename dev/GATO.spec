# GATO.spec — packages run_gato.py into a real double-clickable Gato.exe
# with its own icon (assets/app.ico), instead of "run a Python script from
# a terminal". This is scaffolding only -- PyInstaller must actually run on
# Windows (with the project's real venv active, torch/ultralytics/pywin32
# installed) to produce a working exe; it cannot be cross-built from macOS.
#
# Build on the Windows PC, from C:\Gato, with the venv active:
#   py -3.11 -m pip install pyinstaller
#   py -3.11 -m PyInstaller GATO.spec --noconfirm
# Output: dist\Gato\Gato.exe
#
# Test before trusting it: run dist\Gato\Gato.exe directly (not through
# run_gato.py) and confirm the window opens with the real icon in the
# taskbar -- PyInstaller onedir builds commonly miss a data file on the
# first try (ui/, assets/, fonts) and fail with a blank window or a
# FileNotFoundError, not a cryptic error, so it's a quick instant check.

block_cipher = None

a = Analysis(
    ['run_gato.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('ui', 'ui'),                     # webview frontend (index.html, fonts/)
        ('assets', 'assets'),             # pin keypad + idle-warning CV templates, app.ico
        ('prism_settings.json', '.'),     # default settings template
    ],
    hiddenimports=[
        'win32timezone',  # pywin32 frozen-app gotcha: not auto-detected by PyInstaller
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Gato',
    icon='assets/app.ico',
    console=False,       # no terminal window -- real app behavior
    uac_admin=True,       # the bot requires admin rights (input.py ensure_admin) --
                           # bake the UAC prompt into the exe manifest instead of
                           # making the user right-click "run as administrator"
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    name='Gato',
)
