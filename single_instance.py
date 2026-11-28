"""Single-instance guard: only one Gato may run on a PC at a time.

Why this exists: nothing stopped a second Gato. The silent-install path launched the app from
BOTH ends (the updater's detached script started the exe, and the installer's [Run] section did
too), so every self-update left two processes alive. Both attach to the game, both click, and
they fight each other for z-order -- so every click pays the full failed foreground-steal ladder
and the macro looks slow, which reads as a timing bug rather than a duplicate install.

The guard is a named kernel mutex. A second instance notices ERROR_ALREADY_EXISTS, closes the
older twin (so the survivor is always the newest build), waits for the mutex to be released by
that process's exit, and then runs normally. No window, no dialog: an operator who double-clicks
the desktop icon twice still ends up with exactly one app.

Windows-only by nature; on macOS/Linux `acquire()` is a no-op that reports "first instance" so
mock flows and unit tests run unchanged.

win32 functions are passed in (`k32`) rather than imported here so the module stays importable
on a Mac and testable with a fake layer.
"""
from __future__ import annotations

import os
import time

MUTEX_NAME = 'Global\\GatoSuperSingleInstance'
ERROR_ALREADY_EXISTS = 183


def _real_k32():
    """The real kernel32, or None when this is not Windows."""
    if os.name != 'nt':
        return None
    import ctypes

    return ctypes.windll.kernel32


def _create(k32):
    """(handle, already_running).

    CreateMutexW signals a pre-existing name through GetLastError, but GetLastError is
    thread-local and any call in between clobbers it -- so read it immediately, and let
    `use_last_error` do the capture where the platform supports it.
    """
    try:
        handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    except Exception:
        return 0, False
    try:
        already = k32.GetLastError() == ERROR_ALREADY_EXISTS
    except Exception:
        already = False
    return handle or 0, already


def acquire(k32=None, tries=12, delay=0.5, close_others=None):
    """Take the single-instance mutex; (handle, already_running, closed_other).

    `already_running` is True only when another instance still held the mutex after every
    retry -- the caller should then exit. `closed_other` counts how many times we asked an
    older twin to close, which is what makes a slow handover visible in the log instead of
    looking like a hang.

    The handle is intentionally not closed: it must live for the whole process, and the OS
    releases the mutex when the process dies (that release is what the waiting twin watches).
    """
    if k32 is None:
        k32 = _real_k32()
    if k32 is None:
        return 0, False, 0  # macOS mock: nothing to guard

    handle, busy = _create(k32)
    if not busy:
        return handle, False, 0

    closed = 0
    for _ in range(max(1, tries)):
        # Our handle refers to the existing mutex; drop it so the twin's exit can free the
        # name, then reap the twin and try again.
        try:
            k32.CloseHandle(handle)
        except Exception:
            pass
        if close_others is not None:
            try:
                close_others()
            except Exception:
                pass
            closed += 1
        time.sleep(delay)
        handle, busy = _create(k32)
        if not busy:
            return handle, False, closed
    return handle, True, closed
