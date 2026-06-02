# -*- coding: utf-8 -*-
"""Run-1 QA: server API in-process tests (no live box).

Extends server/tests/test_server.py. The DB-layer cases run unconditionally; the
HTTP cases use FastAPI's TestClient when fastapi is installed (else skip). This
file targets the spec's explicit asks:

  * SUBMIT VALIDATION rejects bad / oversized / IMPLAUSIBLE input (422), and the
    implausible-jump guard (_implausible) is unit-tested directly + end-to-end.
  * LEADERBOARD SHAPE: the response envelope {period, entries[]} with ranked,
    aggregated rows; period query is constrained to all|daily.
  * BAN / DELETE: a banned identity is told to stop (403) and excluded from the
    board; admin delete performs GDPR erasure; unban restores.
  * RATE-LIMIT logic: the in-process limiter both as a unit (_rate_limited) and
    end-to-end (the N+1-th submit in a window -> 429).
  * GDPR: the raw IP is never stored -- only a salted hash.

Run:  python -m pytest server/tests -q
"""

import os
import tempfile
import time
import unittest

from server.app import db
from server.app import routes_submit as rs

try:
    from server.app import routes_leaderboard as rlb
except Exception:                       # fastapi may be absent
    rlb = None


def _reset_server_state():
    """Clear all in-process module state so tests don't leak into each other:
    the rate-limit buckets AND the leaderboard response cache (30 s TTL)."""
    with rs._RATE_LOCK:
        rs._HITS.clear()
    if rlb is not None:
        with rlb._CACHE_LOCK:
            rlb._CACHE.clear()

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except Exception:
    _HAS_FASTAPI = False


# ---------------------------------------------------------------------------
# Pure DB / guard units (no HTTP, always run)
# ---------------------------------------------------------------------------
class TestImplausibleGuard(unittest.TestCase):
    """rs._implausible: first submit always ok; huge jumps vs last -> reject."""

    class _P:                       # tiny payload stand-in (attr access)
        def __init__(self, c=0, p=0, fr=0.0, pr=0.0):
            self.fishing_catches = c
            self.puzzles_solved = p
            self.fishing_runtime_s = fr
            self.puzzler_runtime_s = pr

    def test_first_submit_never_implausible(self):
        self.assertFalse(rs._implausible(self._P(c=10 ** 6), None))

    def test_small_increment_ok(self):
        last = {'fishing_catches': 100, 'puzzles_solved': 0,
                'fishing_runtime_s': 0.0, 'puzzler_runtime_s': 0.0}
        self.assertFalse(rs._implausible(self._P(c=150), last))

    def test_huge_catch_jump_rejected(self):
        last = {'fishing_catches': 0, 'puzzles_solved': 0,
                'fishing_runtime_s': 0.0, 'puzzler_runtime_s': 0.0}
        self.assertTrue(
            rs._implausible(self._P(c=rs.MAX_DELTA_COUNT + 1), last))

    def test_huge_runtime_jump_rejected(self):
        last = {'fishing_catches': 0, 'puzzles_solved': 0,
                'fishing_runtime_s': 0.0, 'puzzler_runtime_s': 0.0}
        self.assertTrue(
            rs._implausible(self._P(fr=rs.MAX_DELTA_RUNTIME_S + 1), last))

    def test_decrease_is_not_implausible(self):
        # A lower value than last (e.g. reset) is not a forbidden *jump*.
        last = {'fishing_catches': 500, 'puzzles_solved': 0,
                'fishing_runtime_s': 0.0, 'puzzler_runtime_s': 0.0}
        self.assertFalse(rs._implausible(self._P(c=10), last))


class TestRateLimiterUnit(unittest.TestCase):
    def setUp(self):
        _reset_server_state()
        self._orig_max = rs.RATE_MAX

    def tearDown(self):
        rs.RATE_MAX = self._orig_max
        _reset_server_state()

    def test_allows_up_to_max_then_blocks(self):
        rs.RATE_MAX = 3
        key = 'hwid:test'
        self.assertFalse(rs._rate_limited(key))   # 1
        self.assertFalse(rs._rate_limited(key))   # 2
        self.assertFalse(rs._rate_limited(key))   # 3
        self.assertTrue(rs._rate_limited(key))    # 4 -> blocked

    def test_separate_keys_independent(self):
        rs.RATE_MAX = 1
        self.assertFalse(rs._rate_limited('hwid:a'))
        self.assertFalse(rs._rate_limited('hwid:b'))   # different key, allowed
        self.assertTrue(rs._rate_limited('hwid:a'))    # a now blocked

    def test_ip_hash_is_not_raw_ip(self):
        h = rs._hash_ip('203.0.113.7')
        self.assertNotIn('203.0.113.7', str(h))
        self.assertEqual(len(h), 64)               # sha256 hex

    def test_sweep_evicts_stale_keys(self):
        # Stale buckets (no timestamp within the window) must be globally
        # evicted so a rotating-identity attacker cannot grow the map unbounded.
        with rs._RATE_LOCK:
            rs._HITS.clear()
            old = time.time() - (rs.RATE_WINDOW_S + 100)
            rs._HITS['ip:1.1.1.1'] = [old, old]          # all expired
            rs._HITS['hwid:stale'] = [old]               # expired
            rs._HITS['ip:2.2.2.2'] = [time.time()]       # fresh -> kept
            rs._sweep_locked(time.time())
            keys = set(rs._HITS)
        self.assertIn('ip:2.2.2.2', keys)
        self.assertNotIn('ip:1.1.1.1', keys)
        self.assertNotIn('hwid:stale', keys)

    def test_periodic_sweep_bounds_map(self):
        # Drive many DISTINCT keys (each allowed once) with a tiny window so the
        # periodic sweep prunes them -> the map stays bounded, not 1 entry/key.
        orig_w, orig_every = rs.RATE_WINDOW_S, rs._SWEEP_EVERY
        try:
            rs.RATE_WINDOW_S = 0          # every bucket is immediately stale
            rs._SWEEP_EVERY = 50
            with rs._RATE_LOCK:
                rs._HITS.clear()
                rs._calls_since_sweep = 0
            for i in range(5000):
                rs._rate_limited('hwid:id-{}'.format(i))
            self.assertLessEqual(len(rs._HITS), rs._SWEEP_EVERY)
        finally:
            rs.RATE_WINDOW_S, rs._SWEEP_EVERY = orig_w, orig_every
            with rs._RATE_LOCK:
                rs._HITS.clear()


class _FakeReq:
    """Minimal Request stand-in: only .headers (dict-like) + .client are read."""

    class _Client:
        def __init__(self, host):
            self.host = host

    def __init__(self, headers=None, peer='198.51.100.9'):
        # Starlette headers are case-insensitive; mimic with lower-cased keys.
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = self._Client(peer) if peer else None


class TestClientIPAntiSpoof(unittest.TestCase):
    """_client_ip must not trust a forged left-most X-Forwarded-For."""

    def test_prefers_x_real_ip(self):
        req = _FakeReq(headers={'X-Real-IP': '203.0.113.5',
                                'X-Forwarded-For': '1.2.3.4, 203.0.113.5'})
        self.assertEqual(rs._client_ip(req), '203.0.113.5')

    def test_forged_leftmost_xff_is_ignored(self):
        # Attacker sends a spoofed left-most entry; nginx appends the real peer
        # on the RIGHT. With no X-Real-IP we must take the right-most hop.
        req = _FakeReq(headers={
            'X-Forwarded-For': '6.6.6.6, 203.0.113.5'}, peer=None)
        ip = rs._client_ip(req)
        self.assertEqual(ip, '203.0.113.5')
        self.assertNotEqual(ip, '6.6.6.6')

    def test_falls_back_to_socket_peer(self):
        req = _FakeReq(headers={}, peer='198.51.100.9')
        self.assertEqual(rs._client_ip(req), '198.51.100.9')

    def test_spoofed_ip_does_not_change_hashed_record(self):
        # The stored ip_hash must reflect the REAL ip (X-Real-IP), so a rotating
        # left-most XFF cannot pick the stored value or dodge the per-IP limit.
        a = _FakeReq(headers={'X-Real-IP': '203.0.113.5',
                              'X-Forwarded-For': 'aaaa, 203.0.113.5'})
        b = _FakeReq(headers={'X-Real-IP': '203.0.113.5',
                              'X-Forwarded-For': 'bbbb, 203.0.113.5'})
        self.assertEqual(rs._client_ip(a), rs._client_ip(b))
        self.assertEqual(rs._hash_ip(rs._client_ip(a)),
                         rs._hash_ip(rs._client_ip(b)))


class TestDBLeaderboardShape(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db.init_db(os.path.join(self.dir, 'lb.db'))

    def _sub(self, **over):
        row = {'username': 'u', 'hwid': 'h', 'fishing_catches': 1,
               'puzzles_solved': 0, 'fishing_runtime_s': 1.0,
               'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
               'ts': int(time.time()), 'ip_hash': 'x'}
        row.update(over)
        return row

    def test_rows_ranked_and_ordered(self):
        db.insert_submission(self._sub(username='low', hwid='h1',
                                       fishing_catches=5))
        db.insert_submission(self._sub(username='high', hwid='h2',
                                       fishing_catches=50))
        lb = db.leaderboard('all')
        self.assertEqual([r['username'] for r in lb], ['high', 'low'])
        self.assertEqual(lb[0]['rank'], 1)
        self.assertEqual(lb[1]['rank'], 2)

    def test_row_has_all_counter_fields(self):
        db.insert_submission(self._sub(username='a', hwid='h1'))
        row = db.leaderboard('all')[0]
        for k in ('username', 'fishing_catches', 'puzzles_solved',
                  'fishing_runtime_s', 'puzzler_runtime_s', 'rank'):
            self.assertIn(k, row)

    def test_delete_then_unblock_roundtrip(self):
        db.insert_submission(self._sub(username='a', hwid='h1'))
        db.add_ban('install', 'h1', 'spam')
        self.assertEqual(len(db.leaderboard('all')), 0)
        self.assertEqual(db.remove_ban('install', 'h1'), 1)
        self.assertEqual(len(db.leaderboard('all')), 1)
        self.assertEqual(db.delete_entries('install', 'h1'), 1)
        self.assertEqual(len(db.leaderboard('all')), 0)

    def test_display_name_anon_for_blank_username(self):
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='', hwid='hblank'))
        row = db.leaderboard('all')[0]
        self.assertEqual(row['username'], '')
        self.assertEqual(row['display_name'], anon_name('hblank', 'en'))

    def test_hidden_name_masked_but_row_kept(self):
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='Eve', hwid='heve'))
        db.add_ban('name', 'Eve')
        self.assertIn('Eve', db.hidden_names())
        rows = db.leaderboard('all')
        self.assertEqual(len(rows), 1)                # still on the board
        self.assertEqual(rows[0]['display_name'], anon_name('heve', 'en'))

    def test_everyone_ranked_mixed_chosen_and_anonymous(self):
        # Core model guarantee in ONE board: EVERY install appears (none dropped
        # for lacking a name); a row WITH a chosen name shows it, a row WITHOUT
        # one shows the deterministic anon name. Ranked together by catches.
        from server.app.anon_name import anon_name
        db.insert_submission(self._sub(username='Named', hwid='hnamed',
                                       fishing_catches=30))
        db.insert_submission(self._sub(username='', hwid='hanon1',
                                       fishing_catches=20))
        db.insert_submission(self._sub(username='   ', hwid='hanon2',
                                       fishing_catches=10))   # blank -> anon
        rows = db.leaderboard('all')
        # All three installs are present (everyone appears).
        self.assertEqual(len(rows), 3)
        by_hwid = {r['hwid']: r for r in rows}
        # Chosen name shown for the opted-in row.
        self.assertEqual(by_hwid['hnamed']['display_name'], 'Named')
        # Anonymous funny name for both no-name rows (deterministic from the id).
        self.assertEqual(by_hwid['hanon1']['display_name'],
                         anon_name('hanon1', 'en'))
        self.assertEqual(by_hwid['hanon2']['display_name'],
                         anon_name('hanon2', 'en'))
        # Ranked by catches desc -> Named(30) #1, hanon1(20) #2, hanon2(10) #3.
        self.assertEqual([r['hwid'] for r in rows],
                         ['hnamed', 'hanon1', 'hanon2'])
        self.assertEqual([r['rank'] for r in rows], [1, 2, 3])


class TestSelfRankAndTop20(unittest.TestCase):
    """CS1: top-20 slice + the requesting identity's TRUE rank over the full
    aggregated board (looked up by hwid first, then username), plus tie-break."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db.init_db(os.path.join(self.dir, 'lb.db'))

    def _sub(self, **over):
        row = {'username': 'u', 'hwid': 'h', 'fishing_catches': 1,
               'puzzles_solved': 0, 'fishing_runtime_s': 1.0,
               'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
               'ts': int(time.time()), 'ip_hash': 'x'}
        row.update(over)
        return row

    def _seed_25(self):
        # 25 identities; catches DESCENDING with the username so 'u01' has the
        # MOST catches (rank 1) ... 'u25' the FEWEST (rank 25). hwid != username.
        for i in range(1, 26):
            db.insert_submission(self._sub(
                username='u{:02d}'.format(i), hwid='hw{:02d}'.format(i),
                fishing_catches=(26 - i) * 10, puzzles_solved=i))

    def test_top20_is_exactly_20_ordered_by_catches(self):
        self._seed_25()
        lb = db.leaderboard('all', limit=20)
        self.assertEqual(len(lb), 20)
        catches = [r['fishing_catches'] for r in lb]
        self.assertEqual(catches, sorted(catches, reverse=True))
        self.assertEqual(lb[0]['username'], 'u01')   # most catches
        self.assertEqual(lb[0]['rank'], 1)
        self.assertEqual(lb[19]['rank'], 20)

    def test_self_rank_for_25th_by_hwid(self):
        self._seed_25()
        # u25 has the fewest catches -> rank 25; resolve by its HWID.
        me = db.self_rank(hwid='hw25')
        self.assertIsNotNone(me)
        self.assertEqual(me['rank'], 25)
        self.assertEqual(me['username'], 'u25')
        self.assertEqual(me['fishing_catches'], 10)

    def test_self_rank_resolves_by_hwid_even_with_wrong_username(self):
        self._seed_25()
        # Passing a username that does NOT exist must be overridden by the hwid.
        me = db.self_rank(hwid='hw25', username='not-a-real-name')
        self.assertIsNotNone(me)
        self.assertEqual(me['username'], 'u25')
        self.assertEqual(me['rank'], 25)

    def test_self_rank_by_username_when_no_hwid(self):
        self._seed_25()
        me = db.self_rank(username='u13')
        self.assertIsNotNone(me)
        self.assertEqual(me['rank'], 13)

    def test_tie_break_equal_catches_higher_puzzles_first(self):
        # Two identities, SAME catches; the one with more puzzles ranks first.
        db.insert_submission(self._sub(username='lowp', hwid='hl',
                                       fishing_catches=100, puzzles_solved=1))
        db.insert_submission(self._sub(username='highp', hwid='hh',
                                       fishing_catches=100, puzzles_solved=9))
        lb = db.leaderboard('all', limit=20)
        self.assertEqual([r['username'] for r in lb], ['highp', 'lowp'])
        self.assertEqual(db.self_rank(hwid='hh')['rank'], 1)
        self.assertEqual(db.self_rank(hwid='hl')['rank'], 2)

    def test_tie_break_full_chain_username_breaks_final_tie(self):
        # Full 3-level tie-break: equal catches AND equal puzzles -> username ASC
        # is the deterministic final key. Insert OUT of alphabetical order to
        # prove the ORDER BY (not insertion order) decides; ranks are 1..3.
        for name, h in (('charlie', 'h1'), ('alice', 'h2'), ('bob', 'h3')):
            db.insert_submission(self._sub(username=name, hwid=h,
                                           fishing_catches=100, puzzles_solved=5))
        lb = db.leaderboard('all', limit=20)
        self.assertEqual([r['username'] for r in lb],
                         ['alice', 'bob', 'charlie'])
        self.assertEqual([r['rank'] for r in lb], [1, 2, 3])
        # self_rank agrees with the board's deterministic order.
        self.assertEqual(db.self_rank(hwid='h2')['rank'], 1)   # alice
        self.assertEqual(db.self_rank(hwid='h3')['rank'], 2)   # bob
        self.assertEqual(db.self_rank(hwid='h1')['rank'], 3)   # charlie

    def test_tie_break_is_stable_across_repeated_aggregations(self):
        # The deterministic ORDER BY must yield the SAME rank on every call (the
        # client relies on a stable self-rank between the top-20 fetch and the
        # self lookup). Identical scores, queried twice -> identical ranking.
        for name, h in (('beta', 'hb'), ('alpha', 'ha'), ('gamma', 'hg')):
            db.insert_submission(self._sub(username=name, hwid=h,
                                           fishing_catches=7, puzzles_solved=2))
        first = [r['username'] for r in db.leaderboard('all', limit=20)]
        second = [r['username'] for r in db.leaderboard('all', limit=20)]
        self.assertEqual(first, second)
        self.assertEqual(first, ['alpha', 'beta', 'gamma'])

    def test_self_rank_none_for_unknown_identity(self):
        self._seed_25()
        self.assertIsNone(db.self_rank(hwid='nope'))
        self.assertIsNone(db.self_rank(username='ghost'))
        self.assertIsNone(db.self_rank())            # no identity at all

    def test_self_rank_none_for_blocked_install(self):
        self._seed_25()
        db.add_ban('install', 'hw10')    # hw10 blocked -> excluded from board
        self.assertIsNone(db.self_rank(hwid='hw10'))
        # And the board now has 24 rows max for the top-20 slice.
        self.assertEqual(len(db.leaderboard('all', limit=100)), 24)

    def test_anon_name_vector_matches_client(self):
        # SHARED EN vector: pins the server anon_name to the client copy so the
        # two import-isolated generators can never drift. The SAME (id->EN name)
        # pairs are asserted by the client test (tests/test_anon_name.py).
        from server.app.anon_name import anon_name
        vector = {
            'install-aaaa': 'MightyBass#1350',
            'install-bbbb': 'LuckyCrab#0300',
            '0123456789abcdef0123456789abcdef': 'NimbleTrout#9239',
            'zzz': 'NimblePerch#2426',
        }
        for install_id, expected in vector.items():
            self.assertEqual(anon_name(install_id, 'en'), expected)


# ---------------------------------------------------------------------------
# HTTP route tests (need fastapi)
# ---------------------------------------------------------------------------
@unittest.skipUnless(_HAS_FASTAPI, 'fastapi not installed')
class TestSubmitValidationHTTP(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ['DB_PATH'] = os.path.join(self.dir, 'r.db')
        os.environ['ADMIN_TOKEN'] = 'secret-token'
        db.init_db(os.environ['DB_PATH'])
        _reset_server_state()
        from server.app.main import create_app
        self.client = TestClient(create_app())

    def _payload(self, **over):
        p = {'username': 'bob', 'hwid': 'hbob', 'fishing_catches': 3,
             'puzzles_solved': 1, 'fishing_runtime_s': 5.0,
             'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
             'ts': int(time.time())}
        p.update(over)
        return p

    def test_rejects_negative_count(self):
        self.assertEqual(
            self.client.post('/submit',
                             json=self._payload(fishing_catches=-1)).status_code,
            422)

    def test_rejects_over_max_count(self):
        self.assertEqual(
            self.client.post(
                '/submit',
                json=self._payload(fishing_catches=10 ** 12)).status_code, 422)

    def test_rejects_oversized_hwid(self):
        self.assertEqual(
            self.client.post('/submit',
                             json=self._payload(hwid='h' * 200)).status_code,
            422)

    def test_rejects_oversized_app_version(self):
        self.assertEqual(
            self.client.post(
                '/submit',
                json=self._payload(app_version='v' * 200)).status_code, 422)

    def test_blank_username_accepted_anonymous(self):
        # Anonymous model: a blank/absent username is VALID (the row shows the
        # anon name). It is normalised to '' and stored, returning 200.
        self.assertEqual(
            self.client.post('/submit',
                             json=self._payload(username='   ')).status_code,
            200)

    def test_missing_username_accepted_anonymous(self):
        p = self._payload(hwid='hmiss')
        del p['username']
        self.assertEqual(self.client.post('/submit', json=p).status_code, 200)

    def test_rejects_missing_field(self):
        bad = self._payload()
        del bad['ts']
        self.assertEqual(self.client.post('/submit', json=bad).status_code, 422)

    def test_rejects_future_ts_over_2100(self):
        self.assertEqual(
            self.client.post('/submit',
                             json=self._payload(ts=5_000_000_000)).status_code,
            422)

    def test_implausible_jump_rejected_end_to_end(self):
        # Seed a low baseline, then submit an enormous jump -> 422.
        self.assertEqual(
            self.client.post('/submit',
                             json=self._payload(fishing_catches=1)).status_code,
            200)
        big = self._payload(fishing_catches=rs.MAX_DELTA_COUNT + 5)
        r = self.client.post('/submit', json=big)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['detail'], 'implausible_jump')


@unittest.skipUnless(_HAS_FASTAPI, 'fastapi not installed')
class TestLeaderboardAndBanHTTP(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ['DB_PATH'] = os.path.join(self.dir, 'r.db')
        os.environ['ADMIN_TOKEN'] = 'secret-token'
        db.init_db(os.environ['DB_PATH'])
        _reset_server_state()
        from server.app.main import create_app
        self.client = TestClient(create_app())

    def _payload(self, **over):
        p = {'username': 'bob', 'hwid': 'hbob', 'fishing_catches': 3,
             'puzzles_solved': 1, 'fishing_runtime_s': 5.0,
             'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
             'ts': int(time.time())}
        p.update(over)
        return p

    def test_leaderboard_envelope_shape(self):
        self.client.post('/submit', json=self._payload())
        lb = self.client.get('/leaderboard?period=all').json()
        self.assertEqual(lb['period'], 'all')
        self.assertIsInstance(lb['entries'], list)
        entry = lb['entries'][0]
        for k in ('rank', 'username', 'fishing_catches', 'puzzles_solved',
                  'fishing_runtime_s', 'puzzler_runtime_s'):
            self.assertIn(k, entry)
        self.assertEqual(entry['rank'], 1)

    def test_leaderboard_rejects_bad_period(self):
        self.assertEqual(
            self.client.get('/leaderboard?period=weekly').status_code, 422)

    def test_leaderboard_self_envelope_by_hwid(self):
        # Seed 25 identities (r01 most catches ... r25 fewest) directly in the DB
        # (the per-IP rate limiter would 429 the 6th+ HTTP submit from the single
        # TestClient peer); then ask for the board AS r25 by HWID over HTTP ->
        # entries<=20 + self with the true rank 25.
        now = int(time.time())
        for i in range(1, 26):
            db.insert_submission({
                'username': 'r{:02d}'.format(i), 'hwid': 'rh{:02d}'.format(i),
                'fishing_catches': (26 - i) * 10, 'puzzles_solved': i,
                'fishing_runtime_s': 1.0, 'puzzler_runtime_s': 0.0,
                'app_version': '1.0.5', 'ts': now, 'ip_hash': 'x'})
        lb = self.client.get('/leaderboard?period=all&hwid=rh25').json()
        self.assertEqual(lb['period'], 'all')
        self.assertLessEqual(len(lb['entries']), 20)
        self.assertIsNotNone(lb['self'])
        self.assertEqual(lb['self']['rank'], 25)
        self.assertEqual(lb['self']['username'], 'r25')
        # r25 is outside the top-20, so it is NOT in entries.
        self.assertNotIn('r25', [e['username'] for e in lb['entries']])

    def test_leaderboard_self_null_without_identity(self):
        self.client.post('/submit', json=self._payload())
        lb = self.client.get('/leaderboard?period=all').json()
        self.assertIsNone(lb['self'])

    def test_leaderboard_rejects_oversized_hwid_query(self):
        self.assertEqual(
            self.client.get(
                '/leaderboard?hwid=' + 'h' * 200).status_code, 422)

    def test_blocked_install_told_to_stop(self):
        db.add_ban('install', 'hbob', 'cheating')
        r = self.client.post('/submit', json=self._payload())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['status'], 'banned')

    def test_hidden_name_still_submits_but_label_masked(self):
        # A hidden NAME does NOT stop submits (only the label is moderated): the
        # submit returns 200 and the row stays on the board under the anon name.
        from server.app.anon_name import anon_name
        db.add_ban('name', 'bob')
        r = self.client.post('/submit', json=self._payload(hwid='hbobhide'))
        self.assertEqual(r.status_code, 200)         # NOT 403
        lb = self.client.get('/leaderboard?period=all').json()
        names = [e['username'] for e in lb['entries']]
        self.assertIn(anon_name('hbobhide', 'en'), names)
        self.assertNotIn('bob', names)               # the hidden label is gone

    def test_admin_delete_erases_entries_by_install(self):
        self.client.post('/submit', json=self._payload(hwid='herase'))
        r = self.client.post(
            '/admin/delete', headers={'X-Admin-Token': 'secret-token'},
            json={'kind': 'install', 'value': 'herase'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['deleted_rows'], 1)

    def test_admin_unblock_restores_board(self):
        self.client.post('/submit', json=self._payload(username='z', hwid='hz'))
        self.client.post('/admin/ban',
                         headers={'X-Admin-Token': 'secret-token'},
                         json={'kind': 'install', 'value': 'hz',
                               'reason': 'x'})
        # blocked -> excluded
        self.assertEqual(
            len(self.client.get('/leaderboard?period=all').json()['entries']), 0)
        self.client.post('/admin/unban',
                         headers={'X-Admin-Token': 'secret-token'},
                         json={'kind': 'install', 'value': 'hz'})
        # restored (cache TTL is 30s; force a fresh period to avoid the cache)
        self.assertGreaterEqual(
            len(self.client.get(
                '/leaderboard?period=daily').json()['entries']), 1)

    def test_admin_rejects_unknown_kind(self):
        # The old vocabulary ('hwid'/'username') is no longer accepted.
        r = self.client.post('/admin/ban',
                             headers={'X-Admin-Token': 'secret-token'},
                             json={'kind': 'hwid', 'value': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_admin_delete_requires_token(self):
        r = self.client.post('/admin/delete',
                             headers={'X-Admin-Token': 'wrong'},
                             json={'kind': 'install', 'value': 'x'})
        self.assertEqual(r.status_code, 401)


@unittest.skipUnless(_HAS_FASTAPI, 'fastapi not installed')
class TestRateLimitHTTP(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ['DB_PATH'] = os.path.join(self.dir, 'r.db')
        os.environ['ADMIN_TOKEN'] = 'secret-token'
        db.init_db(os.environ['DB_PATH'])
        _reset_server_state()
        self._orig_max = rs.RATE_MAX
        rs.RATE_MAX = 3
        from server.app.main import create_app
        self.client = TestClient(create_app())

    def tearDown(self):
        rs.RATE_MAX = self._orig_max
        _reset_server_state()

    def test_n_plus_one_in_window_is_429(self):
        payload = {'username': 'rl', 'hwid': 'hrl', 'fishing_catches': 1,
                   'puzzles_solved': 0, 'fishing_runtime_s': 1.0,
                   'puzzler_runtime_s': 0.0, 'app_version': '1.0.5',
                   'ts': int(time.time())}
        codes = [self.client.post('/submit', json=payload).status_code
                 for _ in range(4)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3], 429)
        self.assertEqual(
            self.client.post('/submit', json=payload).json()['detail'],
            'rate_limited')

    def test_oversized_body_413(self):
        # Content-Length over MAX_BODY_BYTES -> early 413 from the middleware.
        big = 'x' * 9000
        r = self.client.post(
            '/submit', content=big,
            headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 413)


if __name__ == '__main__':
    unittest.main()
