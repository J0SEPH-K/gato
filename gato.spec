# gato.spec -- PyInstaller recipe for the one-folder app dist\Gato\Gato.exe
# Build (on Windows, from the repo root, with the project's .venv):
#     .venv\Scripts\python -m PyInstaller gato.spec --noconfirm --clean
# build_windows.ps1 runs this and then wraps the folder into GatoSetup.exe (Inno Setup).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = (
    ['win32timezone', 'clr', 'clr_loader', 'pythonnet', 'webview.platforms.winforms',
     'windows_capture', 'scapy.all', 'websockets', 'cryptography']
    # modules the app imports lazily or by name
    + ['agf', 'autosupply', 'captcha', 'chat', 'remote_link', 'agent_link', 'second_pw', 'sniffer', 'traders_ctl',
       'watchdog', 'sprite_match', 'notify', 'net', 'dpi', 'wgc']
    # YOLO checkpoints unpickle classes from these packages at load time
    + collect_submodules('ultralytics')
)

datas = [
    ('ui', 'ui'),
    ('assets', 'assets'),
    ('settings.default.json', '.'),
] + collect_data_files('ultralytics')

a = Analysis(
    ['run_gato.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib.tests', 'pytest', 'IPython', 'notebook'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Gato',
    icon='assets/app.ico',
    console=False,        # no terminal window: it is a desktop app
    uac_admin=True,       # needs admin for input and capture: UAC prompt is in the manifest
)
coll = COLLECT(exe, a.binaries, a.datas, name='Gato')
