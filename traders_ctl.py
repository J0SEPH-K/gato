# Source Generated with Decompyle++
# File: traders_ctl.pyc (Python 3.11)

import ctypes
import re
import time
from ctypes import wintypes
import uiautomation as auto

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

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
EXE = 'gersang.exe'
_SPI_SETSCREENREADER = 71
_SPIF_SENDCHANGE = 2
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# CreateToolhelp32Snapshot returns a 64-bit HANDLE. Without restype ctypes truncates it to
# a 32-bit int and the next call dies with ArgumentError "Don't know how to convert
# parameter 1". Declare the signatures once.
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32First.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_kernel32.Process32First.restype = wintypes.BOOL
_kernel32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_kernel32.Process32Next.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

# The enum callbacks receive a raw HWND; without argtypes ctypes cannot convert it and
# raises ArgumentError "Don't know how to convert parameter 1" on the first user32 call.
_user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.EnumChildWindows.argtypes = [wintypes.HWND, _EnumProc, wintypes.LPARAM]
_user32.EnumChildWindows.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]


def _enable_screen_reader():
    _user32.SystemParametersInfoW(_SPI_SETSCREENREADER, 1, None, _SPIF_SENDCHANGE)


def _pid_by_exe(name_lower):
    TH32CS_SNAPPROCESS = 2
    
    class PE32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_void_p),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260)]

    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    pid = None
    if _kernel32.Process32First(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.decode('cp949', 'replace').lower() == name_lower:
                pid = pe.th32ProcessID
                break
            if not _kernel32.Process32Next(snap, ctypes.byref(pe)):
                break
    _kernel32.CloseHandle(snap)
    return pid

TAB_CLIENT = '🎮 클라이언트'
TAB_CHAT = '💬 채팅'
TAB_BATTLE = '채팅 및 전투'
SUBTAB_BATTLE = '⚔️ 전투 분석'
BTN_ANALYZE_START = '분석 시작'
BTN_ANALYZE_PAUSE = '일시정지'
BTN_ANALYZE_RESUME = '재개'
OTP_ENTER_BTN = '인증'
OTP_WIN_TITLE = '거상 로그인'
OTP_FIELD_ID = 'GSotpNo'
OTP_OK_ID = 'btn_Send'
MAIN_WIN_TITLE = '고상 트레이더스'
LAUNCH_NAMES = ('게임실행', '게임 실행', '실행')
MAX_DEPTH = 40

class TradersError(Exception):
    pass


def _windows(pid):
    out = []
    def cb(hwnd, _):
        wp = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
        if wp.value == pid:
            cls = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, cls, 256)
            ttl = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, ttl, 256)
            out.append((hwnd, cls.value, ttl.value))
        return True
    _user32.EnumWindows(_EnumProc(cb), 0)
    return out


def _child_of_class(parent, cls_name):
    hit = [
        None]
    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == cls_name:
            hit[0] = hwnd
            return False
        return True
    _user32.EnumChildWindows(parent, _EnumProc(cb), 0)
    return hit[0]


def _tree(title_prefix, child_cls):
    pid = _pid_by_exe(EXE)
    if not pid:
        raise TradersError('고트가 실행 중이 아닙니다')
    _enable_screen_reader()
    for hwnd, cls, ttl in _windows(pid):
        if cls == 'Tauri Window' and ttl.startswith(title_prefix):
            ch = _child_of_class(hwnd, child_cls)
            if ch:
                root = auto.ControlFromHandle(ch)
                if root:
                    return root
                continue
    return None


def _root():
    root = _tree(MAIN_WIN_TITLE, 'Chrome_WidgetWin_0')
    if not root:
        raise TradersError('고트 본 창을 찾을 수 없습니다 (최소화됐거나 구조 변경)')
    return root


def _otp_root():
    return _tree(OTP_WIN_TITLE, 'Chrome_RenderWidgetHostHWND')


def _by_automation_id(root, aid):
    hits = _walk(root, lambda n, name, ctrl: (n.AutomationId or '') == aid)
    return hits[0] if hits else None


def _walk(node, want, depth = 0, out = None):
    if out is None:
        out = []
    if depth > MAX_DEPTH:
        return out
    try:
        name = (node.Name or '').strip()
        ctrl = node.ControlTypeName
    except Exception:
        return out

    
    try:
        if want(node, name, ctrl):
            out.append(node)
    except Exception:
        pass

    
    try:
        for c in node.GetChildren():
            _walk(c, want, depth + 1, out)
    except Exception:
        pass

    return out


def _invokable(node):
    
    try:
        return node.GetInvokePattern() is not None
    except Exception:
        return False



def _enabled(node):
    
    try:
        return bool(node.IsEnabled)
    except Exception:
        return True


_COM_MSG = {
    0x80040200: '버튼이 비활성 상태입니다 (이미 실행 중이거나 조건 미충족)',
    0x80040201: '요소가 사라졌습니다 (화면이 바뀜)',
    0x80040202: '클릭 지점을 찾을 수 없습니다',
    0x80040204: '이 요소는 해당 동작을 지원하지 않습니다' }

def _buttons_named(root, needle):
    return _walk(root, lambda n, name, ctrl: ctrl == 'ButtonControl' and needle in name and _invokable(n))


def _invoke(node):
    if not _enabled(node):
        raise TradersError(_COM_MSG[0x80040200])
    
    try:
        node.GetInvokePattern().Invoke()
        return None
    except Exception as e:
        hr = getattr(e, 'hresult', None)
        if hr is None and getattr(e, 'args', None) and isinstance(e.args[0], int):
            hr = e.args[0]
        msg = _COM_MSG.get(hr) if isinstance(hr, int) else None
        if msg:
            raise TradersError(msg)
        raise TradersError(f'''버튼 실행 실패: {type(e).__name__}: {e}''')



def ensure_tab(root, needle):
    if _ui_label(needle) == '클라이언트' and _client_page_ready(root):
        return True
    button = _tab_button(root, needle)
    if not button:
        return False
    _invoke(button)
    time.sleep(0.4)
    return True


def _ui_label(value):
    if not value:
        return re.sub('\\s+', ' ', re.sub('^[^0-9A-Za-z가-힣]+', '', '')).strip()


def _tab_button(root, needle):
    target = _ui_label(needle)
    if target == '클라이언트':
        aliases = ('클라이언트',)
    elif target in ('채팅', '채팅 및 전투', '인게임'):
        aliases = ('인게임', '채팅 및 전투', '채팅')
    elif target == '전투 분석':
        aliases = ('전투 분석',)
    else:
        aliases = (target,)
    
    def matches(node, name, ctrl, alias):
        if ctrl not in ('ButtonControl', 'TabItemControl') or not _invokable(node):
            return False
        labels = [name]
        try:
            if node.HelpText:
                labels.append(node.HelpText)
        except Exception:
            pass
        for label in labels:
            label = _ui_label(label)
            if label == alias:
                return True
            if alias in ('채팅', '채팅 및 전투') and re.fullmatch(re.escape(alias) + '\\s*\\d+\\+?', label):
                return True
        return False


    for hits in aliases:
        visible = []
        for b in hits:
            try:
                if not b.IsOffscreen:
                    visible.append(b)
            except Exception:
                continue
        if not visible:
            visible = hits
        if visible:
            return visible[0]
    return None


def _client_page_ready(root):
    actions = None
    return ((_ui_label(button.Name) in actions for slot, button in _scan_slots(root, '') if slot > 0))


def _button_exact(root, name):
    hits = _walk(root, lambda n, nm, ctrl: ctrl == 'ButtonControl' and nm == name and _invokable(n))
    return hits[0] if hits else None


def battle_analysis_state(root=None):
    if not root:
        root = _root()
    if _button_exact(root, BTN_ANALYZE_PAUSE):
        return 'running'
    if _button_exact(root, BTN_ANALYZE_RESUME):
        return 'paused'
    if _button_exact(root, BTN_ANALYZE_START):
        return 'idle'
    return 'unknown'


def open_battle_analysis(root=None):
    if not root:
        root = _root()
    if battle_analysis_state(root) != 'unknown':
        return root
    if not ensure_tab(root, TAB_BATTLE):
        raise TradersError("'인게임/채팅 및 전투' 탭 버튼을 찾지 못했습니다")
    root = _root()
    if battle_analysis_state(root) != 'unknown':
        return root
    sub = _tab_button(root, SUBTAB_BATTLE)
    if not sub:
        raise TradersError("'전투 분석' 하위 탭을 찾지 못했습니다")
    _invoke(sub)
    time.sleep(0.6)
    root = _root()
    if battle_analysis_state(root) == 'unknown':
        raise TradersError('전투 분석 탭 전환 후 분석 상태를 확인하지 못했습니다')
    return root


def ensure_battle_analysis(log):
    root = open_battle_analysis()
    state = battle_analysis_state(root)
    if state == 'running':
        return '전투 분석 이미 진행 중'
    if state == 'unknown':
        raise TradersError('전투 분석 상태를 읽지 못했습니다 (고트 화면 확인 필요)')
    label = BTN_ANALYZE_RESUME
    btn = _button_exact(root, label)
    if not btn:
        raise TradersError(f'''\'{label}\' 버튼을 찾지 못했습니다''')
    _invoke(btn)
    time.sleep(0.9)
    state = battle_analysis_state()
    if state == 'running':
        return None
    verb = '재개' if state == 'idle' else '재개'
    return f'''전투 분석 {verb} 눌렀으나 상태 미확인'''

STAT_LABELS = ('전투 횟수', '시간당 전투횟수', '평균 전투', 'EXP/시간', '드랍/시간', '누적 총수익', '상대/시간', '총 획득 경험치', '포만감')
STAT_LABEL_ALIASES = {
    '시간당 전투 횟수': '시간당 전투횟수',
    '평균 전투 시간': '평균 전투',
    '처치한 몬스터 수': '처치한 몬스터 수' }
LABEL_INCOME = '누적 총수익'
LABEL_INCOME_HOUR = '시간당 수익'
STAT_SPAN_MAX = 6
STAT_SPAN = {
    '포만감': 2 }

def _texts_in_order(root):
    out = []
    _walk(root, lambda n, nm, ctrl: bool(nm) and ctrl == 'TextControl', out=out)
    return out


def _join(parts_by_label):
    out = { }
    for label, parts in parts_by_label.items():
        if label != LABEL_INCOME:
            out[label] = ' '.join(parts).strip()
            continue
        hourly = [ p for p in parts if p.endswith('/시간') ]
        out[label] = ' '.join((p for p in parts if p.endswith('/시간'))).strip()
        if hourly:
            out[LABEL_INCOME_HOUR] = hourly[-1][:-len('/시간')].strip()
    return out


def read_battle_stats(root = None):
    texts = _texts_in_order(root or _root())
    marks = [ (i, STAT_LABEL_ALIASES.get(t, t)) for i, t in enumerate(texts) if t in STAT_LABEL_ALIASES ]
    out = { }
    for k, (i, label) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(texts)
        end = min(end, i + 1 + STAT_SPAN.get(label, STAT_SPAN_MAX))
        parts = [ t for t in texts[i + 1:end] if t ]
        if label == '포만감':
            parts = parts[:1] + [ p for p in parts[1:2] if p.startswith('/') ]
        if label not in out:
            out[label] = parts
    return _join(out)


def battle_stats(log):
    root = open_battle_analysis()
    return {
        'state': battle_analysis_state(root),
        'stats': read_battle_stats(root) }
