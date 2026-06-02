# -*- coding: utf-8 -*-
"""The 30-minute periodic GitHub update re-check + banner idempotency.

Locks: (1) the startup check ALSO arms a 30-min repeat that re-checks and
re-arms itself; (2) across those repeats the banner pops only ONCE per distinct
version and never re-nags a version the user dismissed -- while the version
label always reflects the newest find. GUI widgets are stubbed so it runs
headless.
"""

import types
import unittest

from interface.app.update_banner import UpdateBannerMixin, UPDATE_RECHECK_MS


class _Info:
    def __init__(self, tag):
        self.tag = tag


class _FakeApp(UpdateBannerMixin):
    def __init__(self):
        self.after_calls = []
        self.checks = 0
        self.pops = []            # tags for which the banner was made visible
        self._update_info = None
        self._update_banner = None

    # -- scheduling / check seams --
    def after(self, ms, fn):
        self.after_calls.append((ms, fn))

    def _start_one_update_check(self):
        self.checks += 1

    # -- GUI seams stubbed --
    def _highlight_version_update(self, info):
        pass

    def _refresh_update_banner_text(self):
        pass

    def _build_update_banner(self):
        app = self
        self._update_banner = types.SimpleNamespace(
            grid=lambda: app.pops.append(app._update_info.tag),
            grid_remove=lambda: None)
        self._update_btn = types.SimpleNamespace(configure=lambda **k: None)


class TestPeriodicSchedule(unittest.TestCase):
    def test_kickoff_runs_check_and_arms_30min_repeat(self):
        app = _FakeApp()
        app._kick_off_update_check()
        self.assertEqual(app.checks, 1)
        self.assertTrue(any(ms == UPDATE_RECHECK_MS for ms, _ in app.after_calls))

    def test_periodic_rechecks_and_reschedules_itself(self):
        app = _FakeApp()
        app._periodic_update_check()
        self.assertEqual(app.checks, 1)
        ms, fn = app.after_calls[-1]
        self.assertEqual(ms, UPDATE_RECHECK_MS)
        fn()                                   # fire the scheduled tick
        self.assertEqual(app.checks, 2)        # re-checked
        self.assertEqual(app.after_calls[-1][0], UPDATE_RECHECK_MS)  # re-armed


class TestBannerIdempotency(unittest.TestCase):
    def test_same_version_pops_once_over_repeats(self):
        app = _FakeApp()
        info = _Info('v1.0.6')
        app._show_update_banner(info)
        app._show_update_banner(info)          # a later 30-min repeat, same find
        self.assertEqual(app.pops, ['v1.0.6'])

    def test_dismissed_version_does_not_renag_but_newer_does(self):
        app = _FakeApp()
        app._show_update_banner(_Info('v1.0.6'))
        app._on_update_dismiss()               # user closes it
        app._show_update_banner(_Info('v1.0.6'))   # 30-min repeat, same version
        self.assertEqual(app.pops, ['v1.0.6'])     # not re-popped
        app._show_update_banner(_Info('v1.0.7'))   # a NEWER release appears
        self.assertEqual(app.pops, ['v1.0.6', 'v1.0.7'])  # pops again


if __name__ == '__main__':
    unittest.main()
