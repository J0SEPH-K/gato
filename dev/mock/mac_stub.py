import sys, types, ctypes
from unittest.mock import MagicMock
class _W:  # fake ctypes.windll: any attribute chain returns callable mocks
    def __getattr__(self, n): return MagicMock(return_value=0)
if not hasattr(ctypes, 'windll'): ctypes.windll = _W()
import ctypes.wintypes as _wt
for m in ('win32gui','win32con','win32api','win32ui','win32process','pythoncom','pywintypes','win32com','win32com.client','windows_capture','webview','psutil','scapy','scapy.all','torch','torch.nn','torch.nn.functional','torchvision','torchvision.transforms','ultralytics','onnxruntime'):
    sys.modules.setdefault(m, MagicMock())
