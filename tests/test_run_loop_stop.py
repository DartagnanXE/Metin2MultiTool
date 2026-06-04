# -*- coding: utf-8 -*-
"""RunLoop <-> Stop-Signal wiring: the responsiveness contract.

The daemon-thread hotkey watcher and the heavy-op abort are pure (covered by
test_stop_signal); here we lock how :class:`run_loop.RunLoop` GLUES them in:

  * the stop-signal callback clears ``botting`` on BOTH bots (the daemon path),
  * a tick consumes a daemon-set signal -> announces the hotkey stop + reason,
  * a UI/button stop (on_stop) sets the signal to abort a heavy op but stays
    SILENT in the tick (no spurious "hotkey" reason),
  * on_start clears a stale signal so a fresh run is not killed instantly,
  * the fishbot gets the shared signal injected for its refill op.

Built on lightweight fakes (no Tk window / no win32) so it runs headless.
"""

import unittest

import run_loop
import stop_signal


class _Bot:
    def __init__(self):
        self.botting = False
        self.state = 0
        self.stop_signal = None
        self.wincap = None
        self.began = None

    def runHack(self):
        return None

    def set_to_begin(self, values):
        self.began = values


class _FakeApp:
    """Minimal stand-in for interface.app.App used by RunLoop."""
    def __init__(self):
        self._stats = None
        self._stats_save_hook = None
        self.notified = []
        self.synced = 0

    def after(self, ms, fn=None):
        return None

    def after_cancel(self, job):
        pass

    def notify_stop(self, reason):
        self.notified.append(reason)

    def sync_button(self):
        self.synced += 1

    class _LP:
        def pump(self):
            pass
    log_panel = _LP()

    def _maybe_show_rating_prompt(self):
        pass


class _FakeController:
    def __init__(self, app, fishbot, puzzlebot, cfg):
        self.app = app
        self.fishbot = fishbot
        self.puzzlebot = puzzlebot
        self._cfg = cfg
        self.mode = 'fishing'
        self.running = False
        self.on_start = None
        self.on_stop = None
        self.set_running_calls = []

    def current_config(self):
        return self._cfg

    def collect_values(self):
        return {}

    def set_running(self, running):
        self.running = bool(running)
        self.set_running_calls.append(self.running)
        if not self.running:
            self.fishbot.botting = False
            self.puzzlebot.botting = False


def _make_loop():
    from interface import config as cfgmod
    cfg = cfgmod.validate(cfgmod.DEFAULTS)
    app = _FakeApp()
    fish, puzz = _Bot(), _Bot()
    app.controller = _FakeController(app, fish, puzz, cfg)
    loop = run_loop.RunLoop(app)
    return loop, app, fish, puzz


class TestStopSignalCallback(unittest.TestCase):
    def test_callback_clears_both_bots(self):
        loop, app, fish, puzz = _make_loop()
        fish.botting = True
        puzz.botting = True
        loop._on_stop_signal()
        self.assertFalse(fish.botting)
        self.assertFalse(puzz.botting)
        self.assertTrue(loop._hotkey_fired)

    def test_signal_request_fires_callback_via_add(self):
        # After wire-style registration, setting the signal clears botting -- this
        # is exactly the daemon -> botting path, exercised without a thread.
        loop, app, fish, puzz = _make_loop()
        loop.stop_signal.add_callback(loop._on_stop_signal)
        fish.botting = True
        loop.stop_signal.request_stop()
        self.assertFalse(fish.botting)


class TestTickConsumesSignal(unittest.TestCase):
    def test_daemon_stop_announces_with_reason(self):
        loop, app, fish, puzz = _make_loop()
        loop.controller.running = True
        fish.botting = True
        # Simulate the REAL daemon path: register the botting-clear callback,
        # then the watcher sets the signal (which fires the callback).
        loop.stop_signal.add_callback(loop._on_stop_signal)
        loop.stop_signal.request_stop()
        self.assertTrue(loop.stop_signal.stopped)
        self.assertFalse(fish.botting)       # callback cleared botting
        self.assertTrue(loop._hotkey_fired)
        loop.tick()
        # Tick consumed the signal, fell back to START and announced the reason.
        self.assertFalse(loop.stop_signal.stopped)
        self.assertFalse(loop._hotkey_fired)
        from i18n import t
        self.assertIn(t('run.reason_stop_hotkey'), app.notified)

    def test_signal_fired_mid_tick_attributes_hotkey_reason(self):
        # The daemon fires F6 DURING runHack (a heavy op): botting is cleared and
        # the signal set mid-tick. The same tick must still attribute the hotkey
        # reason (not the generic 'stopped, see console' fallback).
        loop, app, fish, puzz = _make_loop()
        loop.controller.running = True
        fish.botting = True
        loop.stop_signal.add_callback(loop._on_stop_signal)

        def runHack_that_gets_stopped():
            # Simulate F6 landing while this heavy op runs.
            loop.stop_signal.request_stop()
            return None
        fish.runHack = runHack_that_gets_stopped

        loop.tick()
        from i18n import t
        self.assertIn(t('run.reason_stop_hotkey'), app.notified)
        self.assertNotIn(t('run.reason_stopped_see_console'), app.notified)
        self.assertFalse(loop.stop_signal.stopped)   # consumed

    def test_button_stop_is_silent(self):
        loop, app, fish, puzz = _make_loop()
        loop.controller.running = True
        fish.botting = True
        # on_stop = UI button: clears botting + sets signal (to abort heavy op),
        # but must NOT set the hotkey marker.
        loop.on_stop()
        self.assertTrue(loop.stop_signal.stopped)
        self.assertFalse(loop._hotkey_fired)
        loop.tick()
        self.assertFalse(loop.stop_signal.stopped)
        from i18n import t
        # Silent: the hotkey reason is never announced for a button stop.
        self.assertNotIn(t('run.reason_stop_hotkey'), app.notified)


class TestOnStartResetsSignal(unittest.TestCase):
    def test_on_start_clears_stale_signal_and_injects(self):
        loop, app, fish, puzz = _make_loop()
        loop.stop_signal.request_stop()      # stale flag from a previous stop
        loop._hotkey_fired = True
        loop.on_start()
        self.assertFalse(loop.stop_signal.stopped)
        self.assertFalse(loop._hotkey_fired)
        # The shared signal is injected into the fishbot for the refill op.
        self.assertIs(fish.stop_signal, loop.stop_signal)
        self.assertTrue(fish.botting)        # fishing mode -> fishbot armed


class TestWatcherLifecycle(unittest.TestCase):
    def test_start_stop_watcher_is_defensive(self):
        loop, app, fish, puzz = _make_loop()
        # Must not raise even though win32 may be absent (no-op watcher then).
        loop.start_stop_watcher()
        self.assertIsNotNone(loop._stop_watcher)
        loop._stop_watcher.stop()

    def test_current_stop_key_defaults_f6(self):
        loop, app, fish, puzz = _make_loop()
        self.assertEqual(loop._current_stop_key(), 'f6')


if __name__ == '__main__':
    unittest.main()
