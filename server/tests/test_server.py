# -*- coding: utf-8 -*-
"""Server tests runnable WITHOUT the live box.

The DB layer (sqlite, stdlib) is tested unconditionally. The HTTP routes
(schema validation, ban/rate-limit, leaderboard aggregation end-to-end) are
tested via FastAPI's TestClient IF fastapi is installed; otherwise those classes
skip cleanly so CI without server deps still passes.

Run:  python -m pytest server/tests -q
  or: python -m unittest discover -s server/tests
"""

import os
import tempfile
import time
import unittest

from server.app import db

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except Exception:
    _HAS_FASTAPI = False


class TestDB(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db.init_db(os.path.join(self.dir, 't.db'))

    def _sub(self, **over):
        row = {'username': 'u', 'hwid': 'h', 'fishing_catches': 1,
               'puzzles_solved': 0, 'fishing_runtime_s': 1.0,
               'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
               'ts': int(time.time()), 'ip_hash': 'x'}
        row.update(over)
        return row

    def test_aggregates_max_per_identity(self):
        db.insert_submission(self._sub(username='a', hwid='h1',
                                       fishing_catches=10))
        db.insert_submission(self._sub(username='a', hwid='h1',
                                       fishing_catches=25))
        lb = db.leaderboard('all')
        self.assertEqual(lb[0]['username'], 'a')
        self.assertEqual(lb[0]['fishing_catches'], 25)

    def test_last_for_identity_latest_wins_on_ts_tie(self):
        ts = int(time.time())
        db.insert_submission(self._sub(hwid='h1', fishing_catches=5, ts=ts))
        db.insert_submission(self._sub(hwid='h1', fishing_catches=9, ts=ts))
        self.assertEqual(db.last_for_identity('h1')['fishing_catches'], 9)

    def test_block_install_excludes_and_unblock_restores(self):
        # kind='install' removes the installation from the board entirely.
        db.insert_submission(self._sub(username='a', hwid='h1'))
        db.add_ban('install', 'h1', 'x')
        self.assertTrue(db.is_banned('install', 'h1'))
        self.assertEqual(len(db.leaderboard('all')), 0)
        db.remove_ban('install', 'h1')
        self.assertFalse(db.is_banned('install', 'h1'))
        self.assertEqual(len(db.leaderboard('all')), 1)

    def test_hide_name_keeps_row_under_anon_name(self):
        # kind='name' does NOT remove the row -- it blanks the label so the
        # display name falls back to the anonymous funny name.
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='Mallory', hwid='hm',
                                       fishing_catches=3))
        db.add_ban('name', 'Mallory')
        lb = db.leaderboard('all')
        self.assertEqual(len(lb), 1)                  # still on the board
        self.assertEqual(lb[0]['username'], '')       # chosen name blanked
        self.assertEqual(lb[0]['display_name'], anon_name('hm', 'en'))

    def test_no_username_row_shows_anon_name(self):
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='', hwid='hanon',
                                       fishing_catches=4))
        lb = db.leaderboard('all')
        self.assertEqual(lb[0]['display_name'], anon_name('hanon', 'en'))

    def test_clearing_chosen_name_reverts_to_anon(self):
        # Opt-in then opt-out: a user reveals a chosen name, later CLEARS it
        # (client sends username=''). The LATEST submission wins, so the board
        # must revert to the anonymous funny name (spec req 3 / README) -- the
        # earlier revealed name must NOT stick forever.
        from server.app.anon_name import anon_name
        ts = int(time.time())
        db.insert_submission(self._sub(username='RealName123', hwid='hrev',
                                       fishing_catches=10, ts=ts))
        db.insert_submission(self._sub(username='', hwid='hrev',
                                       fishing_catches=12, ts=ts + 1000))
        lb = db.leaderboard('all')
        self.assertEqual(len(lb), 1)
        self.assertEqual(lb[0]['username'], '')                # name un-revealed
        self.assertEqual(lb[0]['display_name'], anon_name('hrev', 'en'))
        # And a self-lookup by the now-removed name no longer maps to the row.
        self.assertIsNone(db.self_rank(username='RealName123'))

    def test_changing_chosen_name_uses_latest(self):
        # A NAME CHANGE (not removal) still surfaces the most-recent chosen name.
        ts = int(time.time())
        db.insert_submission(self._sub(username='OldName', hwid='hchg', ts=ts))
        db.insert_submission(self._sub(username='NewName', hwid='hchg',
                                       ts=ts + 1000))
        self.assertEqual(db.leaderboard('all')[0]['display_name'], 'NewName')

    def test_delete_entries_erasure_by_install(self):
        db.insert_submission(self._sub(hwid='h2'))
        self.assertEqual(db.delete_entries('install', 'h2'), 1)
        self.assertEqual(len(db.leaderboard('all')), 0)

    def test_daily_excludes_old(self):
        old = int(time.time()) - 200_000   # > 24h ago
        db.insert_submission(self._sub(username='old', hwid='ho', ts=old))
        db.insert_submission(self._sub(username='new', hwid='hn'))
        daily = [r['username'] for r in db.leaderboard('daily')]
        self.assertIn('new', daily)
        self.assertNotIn('old', daily)


@unittest.skipUnless(_HAS_FASTAPI, 'fastapi not installed')
class TestNameUniqueness(unittest.TestCase):
    """Chosen names are UNIQUE: the EARLIEST install owns a name; a later install
    with the same name (case-insensitive) falls back to its anonymous funny name
    -- no 'FishLover2' implying a second owner. Server half of the fix; the
    client warns up front via /check_name (db.name_owner)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db.init_db(os.path.join(self.dir, 'u.db'))

    def _sub(self, **over):
        row = {'username': 'u', 'hwid': 'h', 'fishing_catches': 1,
               'puzzles_solved': 0, 'fishing_runtime_s': 1.0,
               'puzzler_runtime_s': 0.0, 'app_version': '1.0.7',
               'ts': int(time.time()), 'ip_hash': 'x'}
        row.update(over)
        return row

    def test_earliest_install_owns_chosen_name(self):
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='FishLover', hwid='h1',
                                       fishing_catches=50, ts=1000))
        db.insert_submission(self._sub(username='FishLover', hwid='h2',
                                       fishing_catches=80, ts=2000))
        lb = db.leaderboard('all')
        by_hwid = {r['hwid']: r['display_name'] for r in lb}
        self.assertEqual(by_hwid['h1'], 'FishLover')              # owner keeps it
        self.assertEqual(by_hwid['h2'], anon_name('h2', 'en'))    # later -> anon
        labels = [r['display_name'] for r in lb]
        self.assertEqual(labels.count('FishLover'), 1)            # exactly once

    def test_ownership_is_case_insensitive(self):
        db.insert_submission(self._sub(username='FishLover', hwid='h1', ts=1000))
        db.insert_submission(self._sub(username='fishlover', hwid='h2', ts=2000))
        by_hwid = {r['hwid']: r['display_name'] for r in db.leaderboard('all')}
        self.assertEqual(by_hwid['h1'], 'FishLover')
        self.assertNotEqual(by_hwid['h2'].casefold(), 'fishlover')

    def test_name_owner_returns_earliest_case_insensitive(self):
        db.insert_submission(self._sub(username='FishLover', hwid='h1', ts=1000))
        db.insert_submission(self._sub(username='FishLover', hwid='h2', ts=2000))
        self.assertEqual(db.name_owner('FishLover'), 'h1')
        self.assertEqual(db.name_owner('FISHLOVER'), 'h1')
        self.assertIsNone(db.name_owner('Unclaimed'))
        self.assertIsNone(db.name_owner(''))

    def test_self_rank_by_name_resolves_to_owner(self):
        db.insert_submission(self._sub(username='FishLover', hwid='h1', ts=1000,
                                       fishing_catches=50))
        db.insert_submission(self._sub(username='FishLover', hwid='h2', ts=2000,
                                       fishing_catches=80))
        row = db.self_rank(username='FishLover')
        self.assertIsNotNone(row)
        self.assertEqual(row['hwid'], 'h1')          # the owner, not the blanked


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ['DB_PATH'] = os.path.join(self.dir, 'r.db')
        os.environ['ADMIN_TOKEN'] = 'secret-token'
        db.init_db(os.environ['DB_PATH'])
        from server.app.main import create_app
        self.client = TestClient(create_app())

    def _payload(self, **over):
        p = {'username': 'bob', 'hwid': 'hbob', 'fishing_catches': 3,
             'puzzles_solved': 1, 'fishing_runtime_s': 5.0,
             'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
             'ts': int(time.time())}
        p.update(over)
        return p

    def test_submit_ok_and_leaderboard(self):
        r = self.client.post('/submit', json=self._payload())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'ok')
        lb = self.client.get('/leaderboard?period=all').json()
        # display name = the chosen name when set.
        self.assertEqual(lb['entries'][0]['username'], 'bob')

    def test_submit_without_username_accepted_anon(self):
        # username is OPTIONAL now: omit it -> 200 + the board shows the anon name.
        from server.app.anon_name import anon_name
        from server.app import routes_leaderboard as rlb
        p = self._payload(hwid='hnouser')
        del p['username']
        r = self.client.post('/submit', json=p)
        self.assertEqual(r.status_code, 200)
        # Clear the 30s top-20 cache so the just-submitted row is visible.
        with rlb._CACHE_LOCK:
            rlb._CACHE.clear()
        lb = self.client.get('/leaderboard?period=all').json()
        names = [e['username'] for e in lb['entries']]
        self.assertIn(anon_name('hnouser', 'en'), names)

    def test_submit_rejects_bad_schema(self):
        bad = self._payload(fishing_catches=-1)   # ge=0 violated
        r = self.client.post('/submit', json=bad)
        self.assertEqual(r.status_code, 422)

    def test_submit_rejects_oversized_username(self):
        r = self.client.post('/submit', json=self._payload(username='x' * 100))
        self.assertEqual(r.status_code, 422)

    def test_blocked_install(self):
        db.add_ban('install', 'hbob', 'test')
        r = self.client.post('/submit', json=self._payload())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['status'], 'banned')

    def test_admin_requires_token(self):
        r = self.client.post('/admin/ban',
                             json={'kind': 'install', 'value': 'z'})
        self.assertIn(r.status_code, (401, 422))   # missing/!match header
        r2 = self.client.post(
            '/admin/ban', headers={'X-Admin-Token': 'secret-token'},
            json={'kind': 'install', 'value': 'z', 'reason': 'x'})
        self.assertEqual(r2.status_code, 200)

    def test_check_name_availability(self):
        # Fresh name -> available.
        r = self.client.get('/check_name?username=Nemere&hwid=hx')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['available'])
        # 'bob' claimed by hbob.
        self.client.post('/submit',
                         json=self._payload(username='bob', hwid='hbob'))
        # A DIFFERENT install asking for 'bob' -> taken (and case-insensitive).
        self.assertFalse(
            self.client.get('/check_name?username=bob&hwid=hother')
            .json()['available'])
        self.assertFalse(
            self.client.get('/check_name?username=BOB&hwid=hother')
            .json()['available'])
        # The OWNER asking for their own name -> available (owner_is_self).
        body = self.client.get('/check_name?username=bob&hwid=hbob').json()
        self.assertTrue(body['available'])
        self.assertTrue(body['owner_is_self'])
        # Empty/whitespace name -> always available (anonymous is allowed).
        self.assertTrue(
            self.client.get('/check_name?username=%20&hwid=hother')
            .json()['available'])

    def test_health(self):
        self.assertEqual(self.client.get('/health').status_code, 200)


if __name__ == '__main__':
    unittest.main()
