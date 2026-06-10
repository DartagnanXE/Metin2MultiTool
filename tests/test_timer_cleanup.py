# -*- coding: utf-8 -*-
"""Zeitlimit-Aktion 'cleanup' (Inventar-Cleanup + Auto-Neustart) -- Verdrahtung.

Headless auf den test_run_loop_stop-Fakes: gepinnt wird die RunLoop-Seite
(WANN der Cleanup angestossen wird) + die Config-Validierung. Die after()-
State-Machine selbst (views_inventory._cleanup_tick) braucht Tk und wird vom
Windows-GUI-Smoke mit abgedeckt.

  * Zeitlimit + timer_action='cleanup' + ANGEL-Lauf -> _start_timer_cleanup
    wird geplant, Grund = run.reason_time_limit_cleanup, close_on_timer_expire
    wird uebersprungen (Cleanup impliziert Weiterlaufen).
  * timer_action='stop' (Default) -> historisches Verhalten, KEIN Cleanup.
  * PUZZLE-Lauf -> nie Cleanup (der Ablauf ist ein Angel-Feature).
  * Stop-Signal (F6/Button) -> _cancel_timer_cleanup wird gerufen (ein
    wartender Countdown stirbt mit).
"""

import time
import unittest

import run_loop

from tests.test_run_loop_stop import _Bot, _FakeApp, _FakeController


class _CleanupApp(_FakeApp):
    """_FakeApp + Aufzeichnung der after()-Callbacks und Cancel-Aufrufe."""

    def __init__(self):
        super().__init__()
        self.scheduled = []
        self.cleanup_cancelled = 0

    def after(self, ms, fn=None):
        if fn is not None:
            self.scheduled.append(fn)

    def _start_timer_cleanup(self):
        pass

    def _cancel_timer_cleanup(self):
        self.cleanup_cancelled += 1

    def scheduled_names(self):
        return [getattr(f, '__name__', str(f)) for f in self.scheduled]


def _make_loop(timer_action='stop', close_on_expire=False):
    from interface import config as cfgmod
    cfg = cfgmod.validate(cfgmod.DEFAULTS)
    cfg['fishing']['timer_action'] = timer_action
    cfg['window']['close_on_timer_expire'] = close_on_expire
    app = _CleanupApp()
    fish, puzz = _Bot(), _Bot()
    app.controller = _FakeController(app, fish, puzz, cfg)
    loop = run_loop.RunLoop(app)
    return loop, app, fish, puzz


class TestTimerActionConfig(unittest.TestCase):
    def test_default_is_stop(self):
        from interface import config as cfgmod
        self.assertEqual(cfgmod.validate({})['fishing']['timer_action'], 'stop')

    def test_cleanup_round_trips(self):
        from interface import config as cfgmod
        cfg = cfgmod.validate({'fishing': {'timer_action': 'cleanup'}})
        self.assertEqual(cfg['fishing']['timer_action'], 'cleanup')

    def test_garbage_falls_back_to_stop(self):
        from interface import config as cfgmod
        cfg = cfgmod.validate({'fishing': {'timer_action': 'nonsense'}})
        self.assertEqual(cfg['fishing']['timer_action'], 'stop')


class TestCleanupArming(unittest.TestCase):
    def _expire(self, loop, fish_active=True):
        loop.controller.running = True
        (loop.fishbot if fish_active else loop.puzzlebot).botting = True
        loop._stop_deadline = time.time() - 1
        loop.tick()

    def test_fishing_cleanup_schedules_start(self):
        loop, app, fish, _ = _make_loop(timer_action='cleanup')
        self._expire(loop)
        self.assertIn('_start_timer_cleanup', app.scheduled_names())
        from i18n import t
        self.assertIn(t('run.reason_time_limit_cleanup'), app.notified)
        self.assertFalse(fish.botting)

    def test_stop_mode_keeps_historic_behaviour(self):
        loop, app, fish, _ = _make_loop(timer_action='stop')
        self._expire(loop)
        self.assertNotIn('_start_timer_cleanup', app.scheduled_names())
        from i18n import t
        self.assertIn(t('run.reason_time_limit_reached'), app.notified)

    def test_puzzle_run_never_cleans_up(self):
        loop, app, _, puzz = _make_loop(timer_action='cleanup')
        self._expire(loop, fish_active=False)
        self.assertNotIn('_start_timer_cleanup', app.scheduled_names())
        self.assertFalse(puzz.botting)

    def test_cleanup_overrides_close_on_expire(self):
        # Beide gesetzt: Cleanup gewinnt (Weiterlaufen), die App schliesst NICHT
        # (_on_close wuerde via after() geplant -> darf nicht erscheinen).
        loop, app, fish, _ = _make_loop(timer_action='cleanup',
                                        close_on_expire=True)
        self._expire(loop)
        names = app.scheduled_names()
        self.assertIn('_start_timer_cleanup', names)
        self.assertNotIn('_on_close', names)


class TestStopSignalCancelsCleanup(unittest.TestCase):
    def test_signal_calls_cancel(self):
        loop, app, fish, _ = _make_loop(timer_action='cleanup')
        loop.stop_signal.request_stop()
        loop.tick()
        self.assertEqual(app.cleanup_cancelled, 1)


if __name__ == '__main__':
    unittest.main()
