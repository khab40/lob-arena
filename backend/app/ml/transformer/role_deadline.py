"""Wall-clock phase deadlines that cannot extend an enclosing deadline."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import signal
import time

_active_end = ContextVar("role_audit_deadline", default=None)


@contextmanager
def deadline(seconds):
    if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("deadline must be finite and positive")
    now = time.monotonic()
    previous_timer, interval = signal.getitimer(signal.ITIMER_REAL)
    if interval:
        raise ValueError("periodic SIGALRM timers are incompatible with role deadlines")
    parent_end = _active_end.get()
    external_end = now + previous_timer if previous_timer else None
    inherited = [end for end in (parent_end, external_end) if end is not None]
    restore_end = min(inherited) if inherited else None
    end = min([now + seconds, *inherited])
    if end <= time.monotonic():
        raise TimeoutError("role audit exceeded its deadline")

    def expired(*_):
        raise TimeoutError("role audit exceeded its deadline")

    previous_handler = signal.signal(signal.SIGALRM, expired)
    token = _active_end.set(end)
    try:
        signal.setitimer(signal.ITIMER_REAL, max(end - time.monotonic(), 0.000001))
        yield end
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        _active_end.reset(token)
        signal.signal(signal.SIGALRM, previous_handler)
        remaining = restore_end - time.monotonic() if restore_end is not None else 0
        if remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining)
        # Never rearm an expired parent while unwinding: that alarm could interrupt
        # its cleanup and leave our handler installed after the outer context exits.
    if time.monotonic() >= end:
        # A caller that catches the alarm still cannot report normal completion.
        raise TimeoutError("role audit exceeded its deadline")
