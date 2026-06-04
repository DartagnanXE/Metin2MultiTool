# -*- coding: utf-8 -*-
"""The responsiveness core: StopSignal + StopHotkeyWatcher + Deadline.

Locks the flag-based stop semantics (atomic set/clear, edge-once callbacks),
the interruptible sleep (returns the instant the flag flips), the daemon-thread
hotkey watcher (press-edge only, VK throttled-refresh, no-op without a key
source) and the time-budget Deadline (stop OR timeout, interruptible naps).
Headless: a fake poll_fn + injectable clock replace win32/wall-clock; the live
GetAsyncKeyState path is exercised only via run_loop's own tests.
"""

import time
import unittest

import stop_signal as ss


class TestStopSignalFlag(unittest.TestCase):
    def test_default_not_set(self):
        sig = ss.StopSignal()
        self.assertFalse(sig.stopped)
        self.assertFalse(sig.is_set())

    def test_request_sets_and_clear_resets(self):
        sig = ss.StopSignal()
        sig.request_stop()
        self.assertTrue(sig.stopped)
        sig.clear()
        self.assertFalse(sig.stopped)

    def test_callbacks_fire_once_per_edge(self):
        sig = ss.StopSignal()
        hits = []
        sig.add_callback(lambda: hits.append(1))
        sig.request_stop()
        sig.request_stop()          # idempotent -> no second fire
        self.assertEqual(hits, [1])
        # After a clear, the next stop edge fires again.
        sig.clear()
        sig.request_stop()
        self.assertEqual(hits, [1, 1])

    def test_throwing_callback_does_not_block_stop(self):
        sig = ss.StopSignal()
        def boom():
            raise RuntimeError('nope')
        good = []
        sig.add_callback(boom)
        sig.add_callback(lambda: good.append(1))
        sig.request_stop()          # must not raise; good cb still runs
        self.assertTrue(sig.stopped)
        self.assertEqual(good, [1])

    def test_non_callable_callback_ignored(self):
        sig = ss.StopSignal()
        sig.add_callback(None)
        sig.add_callback(42)
        sig.request_stop()          # must not raise
        self.assertTrue(sig.stopped)


class TestInterruptibleWait(unittest.TestCase):
    def test_wait_returns_true_when_uninterrupted(self):
        sig = ss.StopSignal()
        self.assertTrue(sig.wait(0.01, slice_seconds=0.002))

    def test_wait_zero_returns_immediately(self):
        sig = ss.StopSignal()
        self.assertTrue(sig.wait(0))
        sig.request_stop()
        self.assertFalse(sig.wait(0))

    def test_wait_aborts_fast_on_stop(self):
        sig = ss.StopSignal()
        # Flip the flag from another thread mid-wait; the wait must bail in well
        # under the requested 5 s (within a slice or two).
        import threading
        threading.Timer(0.02, sig.request_stop).start()
        t0 = time.monotonic()
        result = sig.wait(5.0, slice_seconds=0.005)
        dt = time.monotonic() - t0
        self.assertFalse(result)
        self.assertLess(dt, 0.5)

    def test_already_stopped_wait_is_false(self):
        sig = ss.StopSignal()
        sig.request_stop()
        self.assertFalse(sig.wait(1.0))


class TestKeyToVk(unittest.TestCase):
    def test_function_keys_and_letters(self):
        self.assertEqual(ss.key_to_vk('f6'), 117)
        self.assertEqual(ss.key_to_vk('F1'), 112)
        self.assertEqual(ss.key_to_vk('q'), ord('Q'))
        self.assertEqual(ss.key_to_vk('5'), ord('5'))

    def test_invalid_keys_none(self):
        for bad in ('', None, 'f0', 'f13', 'ctrl', 'esc', '!'):
            self.assertIsNone(ss.key_to_vk(bad))


class TestHotkeyWatcher(unittest.TestCase):
    def _watcher(self, key='f6', initial_down=False):
        state = {'down': initial_down}
        def poll(_vk):
            return state['down']
        w = ss.StopHotkeyWatcher(ss.StopSignal(), lambda: key, poll_fn=poll,
                                 refresh_every=1)
        return w, state

    def test_press_edge_fires_stop(self):
        w, state = self._watcher()
        self.assertFalse(w.poll_once())          # up -> no fire
        self.assertFalse(w.signal.stopped)
        state['down'] = True
        self.assertTrue(w.poll_once())           # up->down edge fires
        self.assertTrue(w.signal.stopped)

    def test_holding_does_not_refire(self):
        w, state = self._watcher()
        state['down'] = True
        self.assertTrue(w.poll_once())           # edge
        # The flag is now set; subsequent held polls report no NEW edge.
        self.assertFalse(w.poll_once())
        self.assertFalse(w.poll_once())

    def test_release_then_press_is_new_edge(self):
        w, state = self._watcher()
        state['down'] = True
        self.assertTrue(w.poll_once())
        w.signal.clear()
        state['down'] = False
        self.assertFalse(w.poll_once())          # released
        state['down'] = True
        self.assertTrue(w.poll_once())           # new press edge

    def test_invalid_key_never_fires(self):
        w, state = self._watcher(key='not-a-key')
        state['down'] = True
        self.assertFalse(w.poll_once())
        self.assertFalse(w.signal.stopped)

    def test_throwing_poll_fn_swallowed(self):
        def boom(_vk):
            raise RuntimeError('x')
        w = ss.StopHotkeyWatcher(ss.StopSignal(), lambda: 'f6', poll_fn=boom,
                                 refresh_every=1)
        self.assertFalse(w.poll_once())          # must not raise

    def test_throwing_key_provider_swallowed(self):
        def boom():
            raise RuntimeError('x')
        w = ss.StopHotkeyWatcher(ss.StopSignal(), boom,
                                 poll_fn=lambda _vk: True, refresh_every=1)
        self.assertFalse(w.poll_once())          # VK unresolved -> no fire

    def test_noop_watcher_reports_unavailable(self):
        # No poll_fn injected + no win32 in CI -> available() is False so the
        # caller keeps the in-tick fallback. (If win32 IS present, it's True --
        # either way the call must not raise.)
        w = ss.StopHotkeyWatcher(ss.StopSignal(), lambda: 'f6')
        self.assertIn(w.available(), (True, False))

    def test_start_stop_thread_lifecycle(self):
        # The daemon thread must actually pick up a key-down and fire, then stop.
        state = {'down': False}
        w = ss.StopHotkeyWatcher(ss.StopSignal(), lambda: 'f6',
                                 poll_fn=lambda _vk: state['down'],
                                 poll_seconds=0.002, refresh_every=1)
        w.start()
        try:
            state['down'] = True
            t0 = time.monotonic()
            while not w.signal.stopped and time.monotonic() - t0 < 1.0:
                time.sleep(0.005)
            self.assertTrue(w.signal.stopped)
        finally:
            w.stop()


class TestDeadline(unittest.TestCase):
    def _clock(self):
        box = {'t': 0.0}
        return box, (lambda: box['t'])

    def test_within_budget_continues(self):
        box, clock = self._clock()
        d = ss.Deadline(1.0, clock=clock)
        self.assertTrue(d.should_continue())
        self.assertIsNone(d.reason())

    def test_timeout_expires(self):
        box, clock = self._clock()
        d = ss.Deadline(1.0, clock=clock)
        box['t'] = 1.5
        self.assertTrue(d.expired())
        self.assertFalse(d.should_continue())
        self.assertEqual(d.reason(), 'timeout')

    def test_stop_signal_ends_first(self):
        box, clock = self._clock()
        sig = ss.StopSignal()
        d = ss.Deadline(10.0, signal=sig, clock=clock)
        self.assertTrue(d.should_continue())
        sig.request_stop()
        self.assertTrue(d.stopped())
        self.assertFalse(d.should_continue())
        self.assertEqual(d.reason(), 'stop')

    def test_zero_budget_never_times_out(self):
        box, clock = self._clock()
        d = ss.Deadline(0, clock=clock)
        box['t'] = 99999.0
        self.assertFalse(d.expired())            # budget<=0 -> only stop ends it

    def test_sleep_honours_stop(self):
        sig = ss.StopSignal()
        d = ss.Deadline(5.0, signal=sig)
        import threading
        threading.Timer(0.02, sig.request_stop).start()
        t0 = time.monotonic()
        self.assertFalse(d.sleep(5.0))
        self.assertLess(time.monotonic() - t0, 0.5)

    def test_elapsed_monotonic(self):
        box, clock = self._clock()
        d = ss.Deadline(5.0, clock=clock)
        box['t'] = 2.0
        self.assertAlmostEqual(d.elapsed(), 2.0, places=6)


class TestNullSignal(unittest.TestCase):
    def test_null_signal_is_never_set(self):
        # The default sentinel must stay unset across the suite (byte-stable
        # opt-in). It is shared, so we only assert it is not set here.
        self.assertFalse(ss.NULL_SIGNAL.stopped)


if __name__ == '__main__':
    unittest.main()
