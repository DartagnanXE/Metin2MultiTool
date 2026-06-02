# -*- coding: utf-8 -*-
"""Run-1 QA: ranking-tab DATA handling (interface/ranking_view.py).

The ranking view is mostly Tk, but its data-shaping + branching logic is pure
and load-bearing, so we test it WITHOUT a Tk root by:
  * driving the real ``refresh_leaderboard`` / ``_on_board`` branches with a
    fake ``app`` (a plain object) and patching only the Tk-touching sinks
    (``_set_notice`` / ``_clear_board`` / ``_render_board``) to record calls;
  * exercising ``_hms`` directly.

Asserted behaviour (the view is now LEADERBOARD-ONLY: no local-stats block, no
runtimes, no fish-event info):
  * banned state -> the banned notice, board cleared, NO network worker spawned;
  * telemetry OFF -> the telemetry-off notice, board cleared, no worker;
  * opt-in ON -> a loading notice + a worker thread is started;
  * Refresh submits the user's stats OUT-OF-BAND *before* fetching the board;
  * ``_on_board`` accepts the new {'entries':[...], 'self':{...}} envelope plus
    the legacy {'all':[...]} / {'daily':[...]} fallbacks, and ignores
    non-dict / empty payloads with the right notice;
  * a row's catches read from 'fishing_catches' or legacy 'catches', puzzles
    from 'puzzles_solved', rank from 'rank' (fallback to position), and the
    user's own row is detected for the "your rank" notice;
  * REPLACE-20-WITH-SELF: when self.rank > 20 the 20th displayed row becomes the
    user's own row (real rank, highlighted); a self inside the top-20 is not
    duplicated;
  * ``_hms`` formats seconds as HH:MM:SS and clamps garbage/negatives.

Headless: ranking_view imports under py.exe (customtkinter present); we never
construct widgets.
"""

import threading
import unittest
from unittest import mock

from interface import ranking_view as rv


class _FakeBody:
    """Stand-in for the Tk board frame: only winfo_children() is used here."""

    def winfo_children(self):
        return []


class _FakeController:
    def __init__(self, cfg):
        self._cfg = cfg

    def current_config(self):
        return self._cfg


class _FakeApp:
    """Minimal stand-in for the CTk app the view reads from."""

    def __init__(self, cfg, banned=False):
        self.controller = _FakeController(cfg)
        self._ranking_banned = banned
        self._install_id = 'hwid-test'
        self._stats = {'fishing_catches': 1, 'puzzles_solved': 0,
                       'fishing_runtime_s': 0.0, 'puzzler_runtime_s': 0.0}
        self.after_calls = []

    def _telemetry_state(self):
        # Anonymous always-on: 'enabled' means "id+url present, not blocked".
        tele = self.controller.current_config().get('telemetry', {})
        return {
            'enabled': bool(self._install_id) and not self._ranking_banned,
            'username': str(self.controller.current_config().get(
                'username', '') or ''),
            'hwid': self._install_id,
            'submit_url': tele.get('submit_url', 'https://x/submit'),
            'interval_s': 120,
            'payload': {'username': 'bob', 'hwid': self._install_id,
                        'fishing_catches': 1},
        }

    def after(self, delay, fn):
        # Run synchronously so worker results are observable in-test.
        self.after_calls.append(delay)
        fn()


def _cfg(enabled=False, username='', leaderboard_url='https://x/leaderboard'):
    return {
        'telemetry': {'enabled': enabled, 'leaderboard_url': leaderboard_url,
                      'submit_url': 'https://x/submit'},
        'username': username,
        'events': {'windows': [], 'warn_minutes': 0},
    }


class TestHms(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(rv._hms(0), '00:00:00')

    def test_h_m_s(self):
        self.assertEqual(rv._hms(3661), '01:01:01')

    def test_minutes_seconds(self):
        self.assertEqual(rv._hms(125), '00:02:05')

    def test_negative_clamped(self):
        self.assertEqual(rv._hms(-50), '00:00:00')

    def test_garbage_safe(self):
        self.assertEqual(rv._hms('nope'), '00:00:00')

    def test_large_value(self):
        self.assertEqual(rv._hms(36000), '10:00:00')


class TestRefreshGating(unittest.TestCase):
    def setUp(self):
        # Patch the Tk sinks for the whole class; record notices + board clears.
        self.notices = []
        self.cleared = []
        self.rendered = []
        self._p = [
            mock.patch.object(rv, '_set_notice',
                              lambda app, text: self.notices.append(text)),
            mock.patch.object(rv, '_clear_board',
                              lambda app: self.cleared.append(True)),
            # The out-of-band submit must never reach the network in this suite.
            mock.patch.object(rv, '_submit_current_stats', lambda app: None),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_banned_shows_notice_and_no_worker(self):
        app = _FakeApp(_cfg(enabled=True, username='bob'), banned=True)
        with mock.patch.object(threading, 'Thread',
                               side_effect=AssertionError('no worker')) as th:
            rv.refresh_leaderboard(app)
        self.assertEqual(th.call_count, 0)
        self.assertTrue(self.cleared)
        # The last notice is the banned message.
        from i18n import t
        self.assertIn(t('ui.ranking_banned'), self.notices)

    def test_anonymous_no_name_still_loads_board(self):
        # Always-on model: even with NO chosen name the board loads (a worker is
        # spawned + a loading notice shown). There is no telemetry-off state.
        app = _FakeApp(_cfg(enabled=True, username=''))
        started = {}

        class _FakeThread:
            def __init__(self, target=None, name=None, daemon=None):
                started['target'] = target

            def start(self):
                started['started'] = True

        with mock.patch.object(threading, 'Thread', _FakeThread):
            rv.refresh_leaderboard(app)
        self.assertTrue(started.get('started'))
        from i18n import t
        self.assertIn(t('ui.leaderboard_loading'), self.notices)

    def test_loads_worker_and_loading_notice_with_name(self):
        app = _FakeApp(_cfg(enabled=True, username='bob'))
        started = {}

        class _FakeThread:
            def __init__(self, target=None, name=None, daemon=None):
                started['target'] = target
                started['daemon'] = daemon

            def start(self):
                started['started'] = True

        with mock.patch.object(threading, 'Thread', _FakeThread):
            rv.refresh_leaderboard(app)
        self.assertTrue(started.get('started'))
        self.assertTrue(started.get('daemon'))
        from i18n import t
        self.assertIn(t('ui.leaderboard_loading'), self.notices)


class TestOutOfBandSubmit(unittest.TestCase):
    """Refresh must POST the user's current stats BEFORE fetching the board so
    the user's own row already reflects current data. We run the worker inline
    (a fake Thread that calls target() synchronously) and record the call order
    of the patched ``post_submit`` + ``fetch_leaderboard``."""

    def setUp(self):
        # This class MOCKS the network (post_submit/fetch), so it must exercise
        # the REAL out-of-band submit path -> drop the conftest M2FB_NO_TELEMETRY
        # guard for the duration of these tests (restored in tearDown so other
        # App-building tests stay protected from hitting the live server).
        import os
        self._saved_no_tel = os.environ.pop('M2FB_NO_TELEMETRY', None)
        self.calls = []
        self._p = [
            mock.patch.object(rv, '_set_notice', lambda app, text: None),
            mock.patch.object(rv, '_clear_board', lambda app: None),
            mock.patch.object(rv, '_on_board',
                              lambda app, data, username: None),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        import os
        if self._saved_no_tel is not None:
            os.environ['M2FB_NO_TELEMETRY'] = self._saved_no_tel

    def test_submit_runs_before_fetch_on_worker(self):
        from telemetry import client as tclient
        app = _FakeApp(_cfg(enabled=True, username='bob'))

        class _InlineThread:
            def __init__(self, target=None, name=None, daemon=None):
                self._target = target

            def start(self):
                self._target()          # run the worker body synchronously

        recorder = self.calls
        with mock.patch.object(
                tclient, 'post_submit',
                lambda url, payload, *a, **k: recorder.append('submit')), \
             mock.patch.object(
                tclient, 'fetch_leaderboard',
                lambda url, *a, **k: recorder.append('fetch') or {}), \
             mock.patch.object(threading, 'Thread', _InlineThread):
            rv.refresh_leaderboard(app)

        self.assertEqual(self.calls, ['submit', 'fetch'])

    def test_url_carries_identity_query(self):
        from telemetry import client as tclient
        app = _FakeApp(_cfg(enabled=True, username='bob'))
        seen = {}

        class _InlineThread:
            def __init__(self, target=None, name=None, daemon=None):
                self._target = target

            def start(self):
                self._target()

        with mock.patch.object(tclient, 'post_submit',
                               lambda *a, **k: None), \
             mock.patch.object(
                tclient, 'fetch_leaderboard',
                lambda url, *a, **k: seen.update(url=url) or {}), \
             mock.patch.object(threading, 'Thread', _InlineThread):
            rv.refresh_leaderboard(app)

        self.assertIn('hwid=hwid-test', seen['url'])
        self.assertIn('username=bob', seen['url'])

    def test_explicit_refresh_forces_cache_bypass(self):
        # The Refresh button passes force=True so the fetch right AFTER the
        # out-of-band submit bypasses the 30s client cache (otherwise the user's
        # own row would lag the stats they just submitted). Auto-load (default)
        # leaves force=False so rapid tab re-opens still hit the cache.
        from telemetry import client as tclient
        app = _FakeApp(_cfg(enabled=True, username='bob'))
        seen = {}

        class _InlineThread:
            def __init__(self, target=None, name=None, daemon=None):
                self._target = target

            def start(self):
                self._target()

        def _capture_force(url, *a, **k):
            seen['force'] = k.get('force', False)
            return {}

        with mock.patch.object(tclient, 'post_submit', lambda *a, **k: None), \
             mock.patch.object(tclient, 'fetch_leaderboard', _capture_force), \
             mock.patch.object(threading, 'Thread', _InlineThread):
            rv.refresh_leaderboard(app, force=True)
            self.assertTrue(seen['force'])
            seen.clear()
            rv.refresh_leaderboard(app)                 # auto-load default
            self.assertFalse(seen['force'])


class TestOnBoardShapes(unittest.TestCase):
    def setUp(self):
        self.notices = []
        self.rendered = []
        self._p = [
            mock.patch.object(rv, '_set_notice',
                              lambda app, text: self.notices.append(text)),
            mock.patch.object(rv, '_clear_board', lambda app: None),
            mock.patch.object(
                rv, '_render_board',
                lambda app, entries, username, self_row=None:
                self.rendered.append((list(entries), username, self_row))),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_entries_key_preferred(self):
        rv._on_board(_FakeApp(_cfg()),
                     {'entries': [{'username': 'a', 'fishing_catches': 9}],
                      'all': [{'username': 'x'}]}, 'a')
        self.assertEqual(len(self.rendered), 1)
        entries, user, self_row = self.rendered[0]
        self.assertEqual(entries[0]['username'], 'a')
        self.assertEqual(user, 'a')

    def test_all_key_used_when_no_entries(self):
        rv._on_board(_FakeApp(_cfg()),
                     {'all': [{'username': 'a', 'fishing_catches': 9}],
                      'daily': [{'username': 'd'}]}, 'a')
        self.assertEqual(self.rendered[0][0][0]['username'], 'a')

    def test_daily_key_used_when_no_all(self):
        rv._on_board(_FakeApp(_cfg()),
                     {'daily': [{'username': 'd', 'fishing_catches': 3}]}, '')
        self.assertEqual(self.rendered[0][0][0]['username'], 'd')

    def test_self_passed_through(self):
        rv._on_board(
            _FakeApp(_cfg()),
            {'entries': [{'username': 'a', 'fishing_catches': 9}],
             'self': {'rank': 5, 'username': 'me', 'fishing_catches': 2,
                      'puzzles_solved': 1}}, 'me')
        self.assertEqual(self.rendered[0][2]['rank'], 5)

    def test_non_dict_payload_failed_notice(self):
        rv._on_board(_FakeApp(_cfg()), None, '')
        from i18n import t
        self.assertIn(t('ui.leaderboard_fetch_failed'), self.notices)
        self.assertEqual(self.rendered, [])

    def test_empty_entries_empty_notice(self):
        rv._on_board(_FakeApp(_cfg()), {'all': []}, '')
        from i18n import t
        self.assertIn(t('ui.leaderboard_empty'), self.notices)
        self.assertEqual(self.rendered, [])


class _RowRecorder:
    """Shared helper: patches _board_row with the new 6-arg signature + a stub
    board body, recording (row, rank, name, catches, puzzles, header, mine)."""

    def start(self, testcase):
        testcase.rows = []
        testcase.notices = []
        testcase._p = [
            mock.patch.object(
                rv, '_board_row',
                lambda body, row, rank, name, catches, puzzles, header=False,
                mine=False: testcase.rows.append(
                    (row, rank, name, catches, puzzles, header, mine))),
            mock.patch.object(rv, '_set_notice',
                              lambda app, text: testcase.notices.append(text)),
        ]
        for p in testcase._p:
            p.start()

    def stop(self, testcase):
        for p in testcase._p:
            p.stop()


def _app_with_body():
    app = _FakeApp(_cfg())
    app._rank_board_body = _FakeBody()
    return app


class TestRowExtraction(unittest.TestCase):
    """Per-row field extraction inside _render_board, asserted against the real
    function via a recording _board_row (now 6-arg: +puzzles)."""

    def setUp(self):
        _RowRecorder().start(self)

    def tearDown(self):
        _RowRecorder().stop(self)

    def test_catches_and_puzzles_from_entry(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'a', 'fishing_catches': 42,
                           'puzzles_solved': 7, 'rank': 1}], 'a')
        # rows[0] is the header; rows[1] the data row.
        data = self.rows[1]
        self.assertEqual(data[2], 'a')        # name
        self.assertEqual(data[3], '42')       # catches
        self.assertEqual(data[4], '7')        # puzzles
        self.assertEqual(data[1], '1')        # rank
        self.assertTrue(data[6])              # mine == True (own row)

    def test_catches_legacy_key_fallback(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'b', 'catches': 7}], 'other')
        data = self.rows[1]
        self.assertEqual(data[3], '7')
        self.assertEqual(data[4], '0')        # puzzles default 0
        self.assertFalse(data[6])             # not the user's row

    def test_rank_falls_back_to_position(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'x'}, {'username': 'y'}], '')
        # Two data rows after the header; ranks default to 1 and 2.
        self.assertEqual(self.rows[1][1], '1')
        self.assertEqual(self.rows[2][1], '2')

    def test_caps_at_top_n_rows(self):
        entries = [{'username': 'u{}'.format(i), 'fishing_catches': i}
                   for i in range(50)]
        rv._render_board(_app_with_body(), entries, '')
        # 1 header + TOP_N data rows max.
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), rv.TOP_N)

    def test_own_rank_notice_emitted(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'me', 'fishing_catches': 5, 'rank': 3}],
                         'me')
        from i18n import t
        self.assertIn(t('ui.leaderboard_your_rank', rank=3), self.notices)


class TestPuzzlesColumn(unittest.TestCase):
    def setUp(self):
        _RowRecorder().start(self)

    def tearDown(self):
        _RowRecorder().stop(self)

    def test_header_has_puzzles_column(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'a', 'fishing_catches': 1}], '')
        from i18n import t
        header = self.rows[0]
        self.assertTrue(header[5])                    # header flag
        self.assertEqual(header[4], t('ui.stats_puzzles'))

    def test_puzzles_value_rendered(self):
        rv._render_board(_app_with_body(),
                         [{'username': 'a', 'fishing_catches': 1,
                           'puzzles_solved': 99}], '')
        self.assertEqual(self.rows[1][4], '99')


class TestSelfRankReplacement(unittest.TestCase):
    """Replace-20-with-self: a self with rank > 20 replaces the 20th visible row
    (real rank, highlighted); a self inside the top-20 is not duplicated."""

    def setUp(self):
        _RowRecorder().start(self)

    def tearDown(self):
        _RowRecorder().stop(self)

    def _top20(self):
        return [{'username': 'u{:02d}'.format(i),
                 'fishing_catches': (21 - i), 'puzzles_solved': 0, 'rank': i}
                for i in range(1, 21)]

    def test_self_beyond_top20_replaces_row20(self):
        self_row = {'rank': 147, 'username': 'me', 'fishing_catches': 5,
                    'puzzles_solved': 2}
        rv._render_board(_app_with_body(), self._top20(), 'me',
                         self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 20)          # still exactly 20 rows
        last = data_rows[-1]                           # the 20th displayed row
        self.assertEqual(last[1], '147')              # real rank shown
        self.assertEqual(last[2], 'me')               # the user's name
        self.assertEqual(last[3], '5')                # the user's catches
        self.assertTrue(last[6])                      # highlighted (mine)
        # 'me' appears exactly once (not duplicated anywhere).
        self.assertEqual(sum(1 for r in data_rows if r[2] == 'me'), 1)
        # The original 20th entry (u20) was pushed out.
        self.assertNotIn('u20', [r[2] for r in data_rows])
        from i18n import t
        self.assertIn(t('ui.leaderboard_your_rank', rank=147), self.notices)

    def test_self_inside_top20_not_duplicated(self):
        # The user is u05 (already visible at rank 5). self.rank == 5 (<=20):
        # no injection, highlight the existing row, no duplicate.
        top = self._top20()
        self_row = {'rank': 5, 'username': 'u05', 'fishing_catches': 16,
                    'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'u05', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 20)
        self.assertEqual(sum(1 for r in data_rows if r[2] == 'u05'), 1)
        mine_rows = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine_rows), 1)
        self.assertEqual(mine_rows[0][1], '5')        # rank 5, highlighted

    def test_no_self_falls_back_to_username_highlight(self):
        # Old-server path: no 'self' in the envelope -> highlight by username.
        top = self._top20()
        rv._render_board(_app_with_body(), top, 'u07', self_row=None)
        data_rows = [r for r in self.rows if not r[5]]
        mine_rows = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine_rows), 1)
        self.assertEqual(mine_rows[0][2], 'u07')

    def test_self_at_exactly_rank20_is_not_injected(self):
        # Boundary: only a rank STRICTLY > TOP_N replaces the 20th row. A self at
        # exactly rank 20 who is already the 20th visible entry stays put (no
        # injection, no duplicate), highlighted in place.
        top = self._top20()                       # u20 sits at rank 20
        self_row = {'rank': 20, 'username': 'u20', 'fishing_catches': 1,
                    'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'u20', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 20)
        self.assertIn('u20', [r[2] for r in data_rows])   # not pushed out
        self.assertEqual(sum(1 for r in data_rows if r[2] == 'u20'), 1)
        mine = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0][1], '20')

    def test_self_with_unparseable_rank_does_not_inject_or_crash(self):
        # A malformed self.rank (non-numeric) must NOT trigger injection (we only
        # inject when we KNOW rank > TOP_N) and must never raise. The board still
        # renders the plain top-20; the bogus self is simply ignored.
        top = self._top20()
        self_row = {'rank': 'not-a-number', 'username': 'ghost',
                    'fishing_catches': 5, 'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'ghost', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 20)
        # No injected 'ghost' row (it was outside the visible names + unparseable).
        self.assertNotIn('ghost', [r[2] for r in data_rows])
        self.assertEqual([r[2] for r in data_rows][-1], 'u20')  # u20 retained

    def test_self_beyond_top20_with_short_board_still_surfaces_rank(self):
        # Defensive hardening: a (buggy/garbage) server reports self.rank > 20 but
        # returns a board SHORTER than 20 entries -> the self row cannot be
        # injected into a non-existent 20th slot, but the user must STILL learn
        # their real rank via the notice (instead of seeing nothing about
        # themselves). With a correct, full-board server this is unreachable.
        from i18n import t
        short = [{'username': 'u{:02d}'.format(i),
                  'fishing_catches': (6 - i), 'puzzles_solved': 0, 'rank': i}
                 for i in range(1, 6)]                 # only 5 rows
        self_row = {'rank': 147, 'username': 'me', 'fishing_catches': 5,
                    'puzzles_solved': 2}
        rv._render_board(_app_with_body(), short, 'me', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 5)            # board stays as-is
        self.assertNotIn('me', [r[2] for r in data_rows])  # not injected
        # The real rank is surfaced in the notice regardless.
        self.assertIn(t('ui.leaderboard_your_rank', rank=147), self.notices)

    def test_self_inside_top20_under_different_display_name_highlights(self):
        # HWID-resolved self whose server 'username' differs from the locally typed
        # name: the row matching the SELF rank (server-resolved by install id) is
        # the one highlighted. Here the local box says 'typo', the server self is
        # rank 9 (u09) -- rank-authoritative match wins over the typed name.
        top = self._top20()
        self_row = {'rank': 9, 'username': 'u09', 'fishing_catches': 12,
                    'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'typo', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        mine = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0][2], 'u09')       # highlighted by self-rank
        self.assertEqual(mine[0][1], '9')

    def test_duplicate_chosen_name_only_self_rank_row_highlighted(self):
        # Two installs picked the SAME chosen name 'Bob' and both are visible.
        # The server resolved THIS caller to rank 12 by install id, so ONLY the
        # rank-12 'Bob' is highlighted -- not both (no double-highlight).
        top = [{'username': 'Bob' if i in (3, 12) else 'u{:02d}'.format(i),
                'fishing_catches': (21 - i), 'puzzles_solved': 0, 'rank': i}
               for i in range(1, 21)]
        self_row = {'rank': 12, 'username': 'Bob', 'fishing_catches': 9,
                    'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'Bob', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        mine = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine), 1)            # exactly one, not two
        self.assertEqual(mine[0][1], '12')        # the rank-12 Bob
        # Both 'Bob' rows still render (only one is marked as the caller).
        self.assertEqual(sum(1 for r in data_rows if r[2] == 'Bob'), 2)

    def test_fresh_self_rank_in_window_but_absent_from_stale_cache_notice(self):
        # Breakthrough submit lands the caller at rank <= TOP_N, but the server's
        # cached top-20 is STALE and does not yet contain them. No injection
        # (rank not > TOP_N) and no name/rank match in the cached slice, yet the
        # caller must STILL see their real rank in the notice (was previously
        # empty for ~30s). The board renders the stale top-20 unchanged.
        from i18n import t
        top = self._top20()                        # ranks 1..20, no 'me'
        self_row = {'rank': 1, 'username': 'me', 'fishing_catches': 999,
                    'puzzles_solved': 0}
        rv._render_board(_app_with_body(), top, 'me', self_row=self_row)
        data_rows = [r for r in self.rows if not r[5]]
        self.assertEqual(len(data_rows), 20)       # stale board unchanged
        self.assertNotIn('me', [r[2] for r in data_rows])  # not injected
        mine = [r for r in data_rows if r[6]]
        self.assertEqual(len(mine), 0)             # nothing falsely highlighted
        # The authoritative rank is surfaced regardless of the stale slice.
        self.assertIn(t('ui.leaderboard_your_rank', rank=1), self.notices)


class TestOnBoardSelfTypeGuard(unittest.TestCase):
    """``_on_board`` must only forward a DICT 'self'; a malformed self (list,
    string, number) is dropped to None so the render path never injects garbage.
    """

    def setUp(self):
        self.captured = []
        self._p = [
            mock.patch.object(rv, '_set_notice', lambda app, text: None),
            mock.patch.object(rv, '_clear_board', lambda app: None),
            mock.patch.object(
                rv, '_render_board',
                lambda app, entries, username, self_row=None:
                self.captured.append(self_row)),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_non_dict_self_dropped(self):
        rv._on_board(_FakeApp(_cfg()),
                     {'entries': [{'username': 'a', 'fishing_catches': 1}],
                      'self': ['not', 'a', 'dict']}, 'a')
        self.assertEqual(self.captured, [None])

    def test_dict_self_forwarded(self):
        rv._on_board(_FakeApp(_cfg()),
                     {'entries': [{'username': 'a', 'fishing_catches': 1}],
                      'self': {'rank': 7, 'username': 'a'}}, 'a')
        self.assertEqual(self.captured[0]['rank'], 7)


class TestCompactRowsFit(unittest.TestCase):
    """Compact rows so all TOP_N(=20) + the replace-20-by-self row fit the fixed
    608px window WITHOUT a scrollbar (the old size=11 fit only ~13 of 20).

    Pure pins on the module constants + the row COUNT (we never build Tk, so the
    pixel fit itself is verified by the GUI smoke / a manual eyeball; these
    assertions document + lock the compact intent)."""

    def test_row_font_size_constant_is_compact(self):
        # <= 9 keeps 20+self in 608px; the constant exists so this pins without Tk.
        self.assertTrue(hasattr(rv, 'ROW_FONT_SIZE'))
        self.assertLessEqual(rv.ROW_FONT_SIZE, 9)
        self.assertGreaterEqual(rv.ROW_FONT_SIZE, 8)   # still readable

    def test_row_height_constant_is_tight(self):
        self.assertTrue(hasattr(rv, 'ROW_HEIGHT'))
        self.assertLessEqual(rv.ROW_HEIGHT, 16)        # tight, uniform rows
        self.assertGreater(rv.ROW_HEIGHT, 0)

    def test_render_25_entries_produces_header_plus_top_n_rows(self):
        # 1 header + exactly TOP_N data rows -> they all fit (no scroll).
        _RowRecorder().start(self)
        try:
            entries = [{'username': 'u{}'.format(i), 'fishing_catches': 50 - i}
                       for i in range(25)]
            rv._render_board(_app_with_body(), entries, '')
            data_rows = [r for r in self.rows if not r[5]]
            self.assertEqual(len(data_rows), rv.TOP_N)
            self.assertEqual(len(self.rows), 1 + rv.TOP_N)   # header + 20
        finally:
            _RowRecorder().stop(self)


class TestEntryFieldsExtraction(unittest.TestCase):
    """Direct coverage of the per-row field extractor (used by _render_board)."""

    def test_fishing_catches_preferred_over_legacy(self):
        name, catches, puzzles, rank = rv._entry_fields(
            {'username': 'a', 'fishing_catches': 42, 'catches': 1,
             'puzzles_solved': 3, 'rank': 4})
        self.assertEqual((name, catches, puzzles, rank), ('a', 42, 3, 4))

    def test_legacy_catches_when_no_fishing_catches(self):
        _name, catches, puzzles, rank = rv._entry_fields(
            {'username': 'b', 'catches': 9})
        self.assertEqual((catches, puzzles, rank), (9, 0, None))

    def test_missing_username_placeholder(self):
        name, _c, _p, _r = rv._entry_fields({'fishing_catches': 1})
        self.assertEqual(name, '?')

    def test_garbage_row_is_benign(self):
        self.assertEqual(rv._entry_fields('nope'), ('?', 0, 0, None))
        self.assertEqual(rv._entry_fields(None), ('?', 0, 0, None))


if __name__ == '__main__':
    unittest.main()
