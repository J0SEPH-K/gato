"""Single-instance guard: a second Gato must close the older twin and take the mutex,
never run alongside it. Runs on any OS against a fake kernel32.
    python dev/test_single_instance.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import single_instance

fails = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)


class FakeK32:
    """kernel32 stand-in: the mutex is 'held' while `held` is true."""

    def __init__(self, held=False, releases_after=1):
        self.held = held
        self.releases_after = releases_after
        self.closed = 0
        self.created = 0
        self.last_error = 0
        self.names = []

    def CreateMutexW(self, _attr, _owner, name):
        self.created += 1
        self.names.append(name)
        self.last_error = single_instance.ERROR_ALREADY_EXISTS if self.held else 0
        return 0x100 + self.created

    def GetLastError(self):
        return self.last_error

    def CloseHandle(self, _h):
        self.closed += 1


# 1) nobody holds the mutex -> first instance runs, nothing closed
k = FakeK32(held=False)
h, busy, closed = single_instance.acquire(k32=k, tries=3, delay=0)
check('first instance takes the mutex', busy is False and closed == 0, (busy, closed))
check('first instance returns a handle', bool(h), h)
check('first instance creates the mutex exactly once', k.created == 1, k.created)
check('the mutex name is the documented one', k.names == [single_instance.MUTEX_NAME], k.names)
check('a first instance closes nothing', k.closed == 0, k.closed)

# 2) a live twin that exits on the first reap -> we take it and report it
closed_calls = []

def reap_then_release():
    closed_calls.append(1)
    k.held = False  # the twin exits and the OS frees the mutex


k = FakeK32(held=True, releases_after=1)
h, busy, closed = single_instance.acquire(k32=k, tries=6, delay=0, close_others=reap_then_release)
check('a second instance is NOT told it is a duplicate once the twin exits', busy is False, busy)
check('a second instance asked the twin to close', closed == 1 and len(closed_calls) == 1, (closed, closed_calls))
check('the twin is reaped exactly once', k.closed == 1, k.closed)

# 3) a twin that never exits -> we give up and report already_running (caller exits)
k = FakeK32(held=True)
h, busy, closed = single_instance.acquire(k32=k, tries=4, delay=0, close_others=lambda: None)
check('a stuck twin ends with already_running', busy is True, busy)
check('a stuck twin is retried `tries` times', closed == 4, closed)
check('every retry drops our own stale handle', k.closed == 4, k.closed)

# 4) no kernel32 at all (macOS mock) -> no-op, first instance
h, busy, closed = single_instance.acquire(k32=None, tries=2, delay=0)
check('no win32 layer is a no-op first instance', busy is False and closed == 0 and h == 0, (h, busy, closed))

# 5) a throwing CreateMutexW must not kill startup


class Broken:
    def CreateMutexW(self, *a):
        raise OSError('boom')


h, busy, closed = single_instance.acquire(k32=Broken(), tries=2, delay=0)
check('a broken kernel32 still lets the app start', busy is False, busy)

# 6) a raising close_others must not abort the handover
k = FakeK32(held=True)
state = {'n': 0}


def bad_close():
    state['n'] += 1
    if state['n'] >= 2:
        k.held = False
    raise RuntimeError('nope')


h, busy, closed = single_instance.acquire(k32=k, tries=5, delay=0, close_others=bad_close)
check('a failing close_others still hands the mutex over', busy is False, busy)

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
