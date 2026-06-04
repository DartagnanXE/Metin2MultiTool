# -*- coding: utf-8 -*-
"""Responsiveness/robustness core: the global Stop-Signal + its hotkey daemon.

The bot runs the fishing-/puzzle-tick and every heavy op (open inventory, scan
all four inventory pages, drag a bait, read the chat) in ONE polling loop. A
heavy op therefore BLOCKS that loop -- and with it the in-tick Stop-Hotkey poll
-- so an F6 panic-stop used to be sluggish/unreliable and a wedged heavy op
could hang silently.

This module fixes both, with three small, pure, headless-testable pieces:

  * :class:`StopSignal` -- a thread-safe, flag-based stop request. Simple bool
    reads/writes are atomic under the GIL (no lock needed for correctness); a
    lock only guards the rare callback-list mutation. ``wait(seconds)`` is an
    INTERRUPTIBLE sleep: it naps in tiny slices and returns the instant the flag
    flips, so any heavy op built on it aborts within one slice of a stop.

  * :class:`StopHotkeyWatcher` -- a high-frequency DAEMON thread that polls the
    Stop-Hotkey via ``GetAsyncKeyState`` INDEPENDENTLY of the main loop and of
    any heavy op. On the key's press-edge it (1) sets the StopSignal and (2)
    fires an ``on_stop`` callback -- which clears ``botting`` on both bots -- so
    the stop takes hold in well under 0.2 s no matter what the loop is doing.
    ``win32api`` is SOFT-imported: without it the watcher simply never fires
    (the in-tick poll, kept as a fallback, still works) -> degrades, never
    breaks.

  * :class:`Deadline` -- a monotonic time-budget for a heavy op. ``expired()``
    + the StopSignal give every long action a BOUNDED upper limit and an early
    out, and the call sites log a start line + a clear "exceeded budget" / "aborted
    by stop" line -> the bot never hangs without feedback.

Strictly defensive throughout: nothing here raises into the bot. The whole
machinery is additive -- a default-constructed :class:`StopSignal` is never set
and a watcher that never starts changes no behaviour (byte-stable).
"""

import threading
import time as _time


# Poll period of the hotkey daemon. 5 ms -> the key is sampled ~200x/s, so the
# stop fires far inside the 0.2 s budget while costing a single cheap win32 call
# per slice (negligible CPU). Also the default nap slice of StopSignal.wait, so a
# sleeping heavy op notices a stop within ~5 ms.
POLL_SECONDS = 0.005

# Soft-import win32 exactly like run_loop: present in production, absent headless.
# Missing -> the watcher never fires (no crash); the pure logic stays testable.
try:  # pragma: no cover - pywin32 present in production
    import win32api as _win32api
except Exception:  # pragma: no cover
    _win32api = None


class StopSignal:
    """A thread-safe, flag-based stop request shared loop<->daemon<->heavy ops.

    ``request_stop`` sets it (idempotent), ``clear`` resets it for the next run,
    ``stopped`` reads it. Reads/writes of the single bool are atomic under the
    GIL, so the hot path needs no lock. ``wait`` is an interruptible sleep used
    by heavy ops to stay abortable; ``on_stop`` callbacks let the watcher clear
    ``botting`` the instant the flag flips.
    """

    def __init__(self):
        self._stopped = False
        # Guards only the callback list (mutated rarely, off the hot path). The
        # bool flag itself is touched lock-free (atomic under the GIL).
        self._lock = threading.Lock()
        self._callbacks = []

    @property
    def stopped(self):
        """``True`` once a stop has been requested (until :meth:`clear`)."""
        return self._stopped

    def is_set(self):
        """Alias of :attr:`stopped` (Event-like ergonomics)."""
        return self._stopped

    def clear(self):
        """Reset the flag for a fresh run. Call at START. Wirft nie."""
        self._stopped = False

    def request_stop(self):
        """Set the flag and fire the registered callbacks ONCE per edge.

        Idempotent: a second call while already set does nothing (callbacks fire
        only on the False->True transition). Strictly defensive -- a throwing
        callback is swallowed so a stop can never be blocked by a bad listener.
        """
        if self._stopped:
            return
        self._stopped = True
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

    def add_callback(self, callback):
        """Register a no-arg callable fired once on each stop edge. Wirft nie."""
        if not callable(callback):
            return
        with self._lock:
            self._callbacks.append(callback)

    def wait(self, seconds, slice_seconds=POLL_SECONDS):
        """Interruptible sleep: nap up to ``seconds``, return early on a stop.

        Sleeps in ``slice_seconds`` naps, checking the flag between each, so a
        heavy op that paces itself through this method aborts within one slice of
        a stop request instead of blocking for the full duration. Returns
        ``True`` if it slept the whole time without a stop, ``False`` if a stop
        cut it short. ``seconds <= 0`` returns immediately. Wirft nie.
        """
        try:
            total = float(seconds)
        except (TypeError, ValueError):
            return not self._stopped
        if total <= 0:
            return not self._stopped
        try:
            step = max(0.0005, float(slice_seconds))
        except (TypeError, ValueError):
            step = POLL_SECONDS
        deadline = _time.monotonic() + total
        while True:
            if self._stopped:
                return False
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                return True
            try:
                _time.sleep(min(step, remaining))
            except Exception:
                return not self._stopped


def key_to_vk(key, vk_f1=112):
    """Virtual-Key-Code of a hotkey string (F1-F12 / letter / digit) or ``None``.

    Pure mirror of ``run_loop._key_to_vk`` so the watcher needs no win32 to map a
    key (``vk_f1`` defaults to the real VK_F1=112). Kept here to keep this module
    import-light and self-contained; run_loop stays the single config-facing
    mapper for its own tests.
    """
    k = str(key or '').strip().lower()
    if not k:
        return None
    if k[0] == 'f' and k[1:].isdigit():
        n = int(k[1:])
        if 1 <= n <= 12:
            return vk_f1 + (n - 1)
    if len(k) == 1 and (k.isalpha() or k.isdigit()):
        return ord(k.upper())
    return None


class StopHotkeyWatcher:
    """High-frequency daemon thread that fires the Stop-Hotkey out-of-loop.

    Polls the configured key via ``GetAsyncKeyState`` every :data:`POLL_SECONDS`
    on its OWN daemon thread, so it is unaffected by anything the main loop or a
    heavy op is doing. On the key's press-edge it sets ``signal`` (which clears
    ``botting`` via the signal's callbacks AND aborts any interruptible heavy op)
    -- giving a sub-0.2 s stop regardless of load.

    ``key_provider`` is a no-arg callable returning the current hotkey string
    (read straight from the live config); it is sampled cheaply a few times a
    second, never every poll, so a 200 Hz poll costs one win32 call per slice.
    A ``poll_fn(vk) -> bool`` may be injected for headless tests (default uses
    win32). Without win32 and without an injected ``poll_fn`` the thread is a
    no-op -> the in-tick fallback poll still covers the stop.
    """

    def __init__(self, signal, key_provider, poll_fn=None,
                 poll_seconds=POLL_SECONDS, refresh_every=40):
        self.signal = signal
        self._key_provider = key_provider
        self._poll_fn = poll_fn if poll_fn is not None else _default_poll
        self._poll_seconds = poll_seconds
        # Re-read the key from config every ``refresh_every`` polls (not each one
        # -- the string rarely changes). At 5 ms/poll, 40 -> ~5x/second.
        self._refresh_every = max(1, int(refresh_every))
        self._thread = None
        self._running = False
        self._vk = None
        self._was_down = False     # edge-latch: only fire on the press transition
        self._tick = 0

    # -- lifecycle ---------------------------------------------------------

    def available(self):
        """``True`` if this watcher can actually poll (win32 or an injected fn).

        Lets the caller keep the in-tick fallback poll when the daemon can't run.
        """
        return self._poll_fn is not _noop_poll

    def start(self):
        """Start the daemon thread (idempotent). Wirft nie.

        Daemon=True so it never blocks interpreter shutdown; if polling is
        unavailable it still starts but simply never fires (cheap, harmless).
        """
        if self._running:
            return
        self._running = True
        try:
            self._thread = threading.Thread(
                target=self._run, name='stop-hotkey-watcher', daemon=True)
            self._thread.start()
        except Exception:
            # Could not spawn the thread -> leave it stopped; the in-tick poll
            # remains the safety net. Never raise into startup.
            self._running = False

    def stop(self):
        """Request the daemon thread to exit (joins briefly). Wirft nie."""
        self._running = False
        thread = self._thread
        if thread is not None:
            try:
                thread.join(timeout=0.2)
            except Exception:
                pass

    # -- the poll loop -----------------------------------------------------

    def _refresh_vk(self):
        """(Re)resolve the VK from the provider every ``refresh_every`` polls."""
        if self._tick % self._refresh_every == 0 or self._vk is None:
            try:
                key = self._key_provider() if callable(self._key_provider) else None
            except Exception:
                key = None
            self._vk = key_to_vk(key)
        self._tick += 1

    def poll_once(self):
        """One poll step (also the unit-test entry point). Wirft nie.

        Resolves the VK (throttled), reads the key state and, on the press-edge
        (up->down), requests the stop. Returns ``True`` iff this call fired the
        stop edge (for tests); all errors are swallowed -> the daemon never dies.
        """
        try:
            self._refresh_vk()
            if self._vk is None:
                self._was_down = False
                return False
            down = bool(self._poll_fn(self._vk))
            fired = down and not self._was_down
            self._was_down = down
            if fired:
                self.signal.request_stop()
            return fired
        except Exception:
            return False

    def _run(self):
        """Daemon body: poll until :meth:`stop`. Strictly defensive."""
        while self._running:
            self.poll_once()
            try:
                _time.sleep(self._poll_seconds)
            except Exception:
                break


def _default_poll(vk):
    """Live key poll via win32 (high bit of GetAsyncKeyState = currently down).

    Falls back to the no-op poll when win32 is missing so :meth:`StopHotkeyWatcher
    .available` can report that the daemon can't fire. Wirft nie.
    """
    if _win32api is None:
        return _noop_poll(vk)
    try:
        return bool(_win32api.GetAsyncKeyState(int(vk)) & 0x8000)
    except Exception:
        return False


def _noop_poll(_vk):
    """Sentinel poll used when no real key source exists -> always 'up'."""
    return False


class Deadline:
    """A monotonic time-budget for a single heavy op -- the BOUNDED upper limit.

    Pairs with a :class:`StopSignal` so a heavy op has two ways out: the user's
    stop (signal) and a wall-clock cap (this). ``should_continue`` is the single
    check a heavy op calls between sub-steps; ``reason`` names which limit ended
    it, for a clear log line. Pure + headless (``clock`` injectable). Wirft nie.
    """

    def __init__(self, budget_seconds, signal=None, clock=_time.monotonic):
        self._clock = clock
        try:
            self._budget = float(budget_seconds)
        except (TypeError, ValueError):
            self._budget = 0.0
        self._signal = signal
        self._start = self._safe_now()

    def _safe_now(self):
        try:
            return float(self._clock())
        except Exception:
            return 0.0

    def elapsed(self):
        """Seconds since construction (>= 0). Wirft nie."""
        return max(0.0, self._safe_now() - self._start)

    def expired(self):
        """``True`` once the wall-clock budget is used up (budget>0). Wirft nie."""
        return self._budget > 0 and self.elapsed() >= self._budget

    def stopped(self):
        """``True`` if the attached StopSignal has been set. Wirft nie."""
        return bool(self._signal is not None and self._signal.stopped)

    def should_continue(self):
        """``True`` while the op may keep going (no stop AND within budget)."""
        return not self.stopped() and not self.expired()

    def reason(self):
        """Why the op should end: ``'stop'`` | ``'timeout'`` | ``None``."""
        if self.stopped():
            return 'stop'
        if self.expired():
            return 'timeout'
        return None

    def sleep(self, seconds):
        """Interruptible nap bounded by BOTH the signal and the remaining budget.

        Used by heavy ops in place of ``time.sleep`` so every pause stays
        abortable and inside the budget. Returns ``True`` if it slept fully,
        ``False`` if cut short by a stop or the budget. Wirft nie.
        """
        try:
            want = float(seconds)
        except (TypeError, ValueError):
            return self.should_continue()
        if self._budget > 0:
            want = min(want, max(0.0, self._budget - self.elapsed()))
        if self._signal is not None:
            return self._signal.wait(want)
        # No signal -> still honour the budget via a short plain nap.
        if want <= 0:
            return not self.expired()
        try:
            _time.sleep(want)
        except Exception:
            pass
        return not self.expired()


# A single shared, never-set signal used as the DEFAULT on bots/engines so the
# opt-in wiring stays byte-stable: when nobody injects a real signal, heavy ops
# see a flag that is never set and a watcher that never started -> unchanged
# behaviour. The live RunLoop injects ONE real StopSignal across the app.
NULL_SIGNAL = StopSignal()


__all__ = [
    'StopSignal', 'StopHotkeyWatcher', 'Deadline',
    'key_to_vk', 'POLL_SECONDS', 'NULL_SIGNAL',
]
