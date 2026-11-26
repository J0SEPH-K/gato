# gato.spec -- PyInstaller recipe for the one-folder app dist\Gato\Gato.exe
# Build (on Windows, from the repo root, with the project's .venv):
#     .venv\Scripts\python -m PyInstaller gato.spec --noconfirm --clean
# build_windows.ps1 runs this and then wraps the folder into GatoSetup.exe (Inno Setup).
#
# collect_submodules() spawns an isolated child interpreter to walk a package. Under Wine that
# child dies ("unimplemented function ucrtbase.dll.crealf") and takes the whole build down with
# it, so the two big walks are precomputed into hidden_modules.txt instead. Regenerate it with
#     python dev/tools/gen_hidden_modules.py
# against the build interpreter whenever ultralytics or numpy is upgraded.
import os
import sys

# ultralytics' import graph nests deep enough to blow the default stack while PyInstaller
# walks it (RecursionError, "about 115 nested imports"). Raise the ceiling as the message says.
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

from PyInstaller.utils.hooks import collect_data_files
import PyInstaller.building.build_main as _bm

# PyInstaller talks to an isolated child interpreter over anonymous pipes for several helpers
# (hook discovery, module collection). Under Wine the write handle's flush fails with
# "OSError: [Errno 22] Invalid argument", so every such call dies. Hook discovery only returns
# directories contributed by installed hook entry points, so stub it out and name the directory
# it would have returned explicitly -- the community hooks in pyinstaller-hooks-contrib are not
# optional: hook-cv2 is what sets cv2's module_collection_mode to 'py', without which the frozen
# cv2 package re-imports itself out of the PYZ archive and dies with "recursion is detected".
_bm.discover_hook_directories = lambda: []
_CONTRIB_HOOKS = os.path.join(sys.prefix, 'Lib', 'site-packages',
                              '_pyinstaller_hooks_contrib', 'hooks', 'stdhooks')
_HOOKPATH = [os.path.join(os.path.abspath(SPECPATH), 'buildhooks')]
if os.path.isdir(_CONTRIB_HOOKS):
    _HOOKPATH.append(_CONTRIB_HOOKS)

# The isolated child interpreter itself dies under Wine (the ucrtbase crealf abort), so anything
# routed through it raises EOFError from readline(). Run those helpers inline instead: they are
# plain functions whose whole point is to return data, and isolation only exists to keep their
# imports out of the parent namespace. For a one-shot build that is not worth a subprocess.
import PyInstaller.isolated as _isolated
import PyInstaller.isolated._parent as _iso


class _InlinePython:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, function, *args, **kwargs):
        return function(*args, **kwargs)


def _inline_call(function, *args, **kwargs):
    return function(*args, **kwargs)


for _m in (_iso, _isolated):
    _m.Python = _InlinePython
    _m.call = _inline_call

# A spec is exec'd, not imported, so __file__ does not exist. PyInstaller injects SPECPATH.
_HERE = os.path.abspath(SPECPATH)


def _precomputed(name):
    p = os.path.join(_HERE, 'hidden_modules.txt')
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and (line == name or line.startswith(name + '.')):
                out.append(line)
    return out


hidden = (
    ['win32timezone', 'clr', 'clr_loader', 'pythonnet', 'webview.platforms.winforms',
     'windows_capture', 'scapy.all', 'websockets', 'cryptography']
    # modules the app imports lazily or by name
    + ['agf', 'autosupply', 'captcha', 'chat', 'remote_link', 'agent_link', 'update', 'second_pw', 'sniffer', 'traders_ctl',
       'watchdog', 'sprite_match', 'notify', 'net', 'dpi', 'wgc']
    # YOLO checkpoints unpickle classes from these packages at load time
    + _precomputed('ultralytics')
    # numpy 2.x moved its C internals under numpy._core; PyInstaller's hook misses
    # the private exception module on some numpy builds, so the frozen exe dies
    # with "No module named 'numpy._core._exceptions'". Collect them explicitly.
    + _precomputed('numpy._core')
)

# cv2 is imported by a dozen modules but its contrib hook collects nothing under Wine:
# collect_dynamic_libs('cv2') returns an empty list, so the frozen exe came out with no
# cv2.pyd and no ffmpeg backend at all. Name the extension and its ffmpeg DLL explicitly.
_CV2DIR = os.path.join(sys.prefix, 'Lib', 'site-packages', 'cv2')
binaries = []
if os.path.isdir(_CV2DIR):
    binaries += [(os.path.join(_CV2DIR, f), 'cv2')
                 for f in os.listdir(_CV2DIR)
                 if f.endswith(('.pyd', '.dll'))]
    # cv2/__init__.py execs config.py at import to locate cv2.pyd; without it the frozen
    # import fails with "OpenCV loader: missing configuration file". The contrib hook collects
    # these as data, but its collect_data_files() also comes back empty under Wine.
    for _f in ('config.py', 'config-3.py', 'load_config_py3.py'):
        _p = os.path.join(_CV2DIR, _f)
        if os.path.exists(_p):
            binaries.append((_p, 'cv2'))

_SP = os.path.join(sys.prefix, 'Lib', 'site-packages')

# Wheels ship their private runtime DLLs in sibling `<pkg>.libs` directories (numpy.libs holds
# the hashed msvcp140 build that numpy's .pyd links against). PyInstaller resolves those through
# the DLL search path, which under Wine does not include them, so the build warns
# "lib not found: msvcp140-<hash>.dll" and the frozen numpy dies with
# "DLL load failed while importing _multiarray_umath". Collect every *.libs directory verbatim.
if os.path.isdir(_SP):
    for _d in sorted(os.listdir(_SP)):
        _libs = os.path.join(_SP, _d)
        if _d.endswith('.libs') and os.path.isdir(_libs):
            binaries += [(os.path.join(_libs, _f), _d)
                         for _f in os.listdir(_libs) if _f.lower().endswith('.dll')]

datas = [
    ('ui', 'ui'),
    ('assets', 'assets'),
    ('settings.default.json', '.'),
    ('VERSION', 'res'),
] + collect_data_files('ultralytics')

# pkg_resources' runtime hook imports jaraco.text, which reads a data file at import time
# ("Lorem ipsum.txt"). setuptools vendors jaraco under setuptools/_vendor, and PyInstaller's
# hook for it does not collect that .txt, so the frozen exe dies in the pkg_resources rthook
# before main() ever runs. Ship the vendored tree as data.
_JARACO = os.path.join(_SP, 'setuptools', '_vendor', 'jaraco')
if os.path.isdir(_JARACO):
    for _root, _dirs, _files in os.walk(_JARACO):
        _rel = os.path.relpath(_root, _JARACO)
        _dest = 'jaraco' if _rel == '.' else os.path.join('jaraco', _rel)
        for _f in _files:
            if _f.endswith('.txt'):
                datas.append((os.path.join(_root, _f), _dest))

a = Analysis(
    ['run_gato.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    # buildhooks/ overrides PyInstaller's hook-matplotlib, which imports matplotlib (aborts
    # under Wine) just to ask for its data directory.
    hookspath=_HOOKPATH,
    runtime_hooks=[],
    # matplotlib used to be excluded: importing it aborted the build with ucrtbase.dll.crealf and
    # Analysis.assemble() imports every collected package in one process to scan for DLLs, so one
    # bad package killed the build. The native ucrtbase runtime fixed that, and ultralytics imports
    # matplotlib on plain `import ultralytics`, so the frozen exe died with "No module named
    # 'matplotlib'" at the YOLO step. Included again; only dev-only packages stay excluded.
    excludes=['tkinter', 'pytest', 'IPython', 'notebook'],
    noarchive=False,
)
# The repo-root file VERSION is a 7-byte text file. python311.dll imports VERSION.dll, and the
# app directory is on the DLL search path, so PyInstaller resolves that import to the text file
# and freezes it as version.dll. A text file is not a PE image, so the exe dies at startup with
# c000012f (bad image). Drop the tiny entry and pin the real system DLL instead. Size is the
# discriminator: no genuine version.dll is under 4 KB.
_SYSVER = os.path.join(os.environ.get('SystemRoot', r'C:\windows'), 'system32', 'version.dll')
a.binaries = [b for b in a.binaries
              if not (os.path.basename(b[0]).lower() == 'version.dll'
                      and os.path.exists(b[1]) and os.path.getsize(b[1]) < 4096)]
if os.path.exists(_SYSVER):
    a.binaries.append(('version.dll', _SYSVER, 'BINARY'))

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
