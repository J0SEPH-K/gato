# Auto-restart (2026-11-21)

The bot now restarts itself after any stop IT decided on its own (a false no-fight timeout, the
window vanishing, a kill trigger, a jochul/jamun failure, a revive failure, a bad battle result,
"scene changed" suspicion). An explicit stop never auto-restarts: F3/F4/F10, the panel stop button,
a Discord stop command, schedule completion, logout, self-update, closing the window. A lost
server-auth connection IS treated as automatic (reconnect attempt), since that is usually transient.

Mechanism: `Brain._auto_restart` (bool) is set by whichever stop path fires -
`Brain.stop()` (explicit) always clears it; `_stop_now(reason)` always sets it; `_stop_bot(reason,
user_requested=False)` sets it unless the caller passes `user_requested=True` (prism.py's
`stop_grace()` defaults to `True`, i.e. panel/Discord stops, and explicitly passes `False` only for
the auth-lost case). `_loop()`'s finally block checks the flag after logging "구동 정지" and, if
eligible, waits `AUTO_RESTART_DELAY_SEC` (10 s) then calls the `on_auto_restart` callback, which in
prism.py is `Api._auto_restart_bot` - the SAME `Api.start()` sequence F3 runs (auth check, window
focus, engine start, brain start), not just `brain.start()` alone.

Safety cap: `AUTO_RESTART_MAX_IN_WINDOW` (4) restarts per `AUTO_RESTART_WINDOW_SEC` (600 s / 10 min).
Past that it logs a "반복 정지 의심, 수동 확인 필요" message and stops retrying, so a real persistent
bug surfaces instead of crash-looping forever.

Test: `dev/test_auto_restart.py` - flag logic for every stop path, plus one full end-to-end run
through the REAL loop (simulated vanished window -> the loop's own no-frame timeout -> `_stop_now`
-> the finally block -> the restart callback actually fires), and the crash-loop cap.
