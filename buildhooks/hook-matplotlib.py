# Overrides PyInstaller's stock hook-matplotlib, which does
#
#     @isolated.decorate
#     def mpl_data_dir():
#         import matplotlib
#         return matplotlib.get_data_path()
#
# Importing matplotlib aborts the process under Wine/Rosetta (unimplemented
# ucrtbase.dll.crealf), so the build dies while loading that hook. Here the data directory
# is located without executing matplotlib: importlib.util.find_spec only reads metadata.
import importlib.util
import os

datas = []
binaries = []

_spec = importlib.util.find_spec('matplotlib')
if _spec and _spec.origin:
    _data = os.path.join(os.path.dirname(_spec.origin), 'mpl-data')
    if os.path.isdir(_data):
        datas.append((_data, 'matplotlib/mpl-data'))
    # delvewheel-vendored DLLs (matplotlib >= 3.7 wheels); copying them is enough, the
    # load-order file is only needed by ancient pythons / Anaconda.
    _libs = os.path.join(os.path.dirname(os.path.dirname(_spec.origin)), 'matplotlib.libs')
    if os.path.isdir(_libs):
        for _f in os.listdir(_libs):
            if _f.lower().endswith('.dll'):
                binaries.append((os.path.join(_libs, _f), '.'))
