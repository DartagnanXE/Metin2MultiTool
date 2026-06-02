# -*- coding: utf-8 -*-
"""Pure tests for telemetry.payload + telemetry.hwid (no network/threads).

Only the PURE layers are exercised: build_submit/clamp_payload (schema keys,
length caps, numeric coercion, deterministic ts from injected now) and the
RANDOM install-id module (new_install_id is a unique uuid4 hex; ensure_install_id
generates+persists once via an injected getter/setter; the get_hwid shim is a
process-stable RANDOM id -- NOT a machine hash). Stdlib unittest.
"""

import unittest
from datetime import datetime, timezone

from telemetry import payload, hwid


class TestNewInstallId(unittest.TestCase):
    def test_uuid4_hex_shape(self):
        i = hwid.new_install_id()
        self.assertEqual(len(i), 32)
        int(i, 16)                       # uuid4 hex -> valid hex (raises if not)
        self.assertTrue(all(c in '0123456789abcdef' for c in i))

    def test_unique_across_calls(self):
        ids = {hwid.new_install_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)  # random -> (practically) all distinct

    def test_no_hardware_derivation_api(self):
        # The retired hardware-hash API must be GONE (no fingerprint remains).
        for gone in ('compute_hwid', '_read_machine_guid', '_read_volume_serial'):
            self.assertFalse(hasattr(hwid, gone),
                             '{} must be retired'.format(gone))


class TestEnsureInstallId(unittest.TestCase):
    def test_generates_and_persists_once(self):
        store = {'id': ''}
        got = hwid.ensure_install_id(
            lambda: store['id'], lambda v: store.__setitem__('id', v))
        self.assertTrue(got)
        self.assertEqual(store['id'], got)           # persisted via the setter
        # Second call returns the STORED id (no regeneration).
        again = hwid.ensure_install_id(lambda: store['id'], lambda v: None)
        self.assertEqual(again, got)

    def test_blank_or_invalid_triggers_generation(self):
        for start in ('', '   ', None):
            store = {'id': start}
            got = hwid.ensure_install_id(
                lambda: store['id'], lambda v: store.__setitem__('id', v))
            self.assertTrue(got and len(got) == 32)

    def test_never_raises_on_failing_callbacks(self):
        def boom():
            raise RuntimeError('getter down')

        def boom_set(_v):
            raise RuntimeError('setter down')

        # Must still return a usable in-memory id so a submit can go out.
        got = hwid.ensure_install_id(boom, boom_set)
        self.assertEqual(len(got), 32)

    def test_caps_overlong_stored_id(self):
        store = {'id': 'a' * 500}
        got = hwid.ensure_install_id(lambda: store['id'], lambda v: None)
        self.assertLessEqual(len(got), hwid.INSTALL_ID_MAXLEN)


class TestGetHwidShim(unittest.TestCase):
    def test_process_stable_random_id(self):
        # Compat shim: bounded, process-stable. NOT a machine hash.
        a = hwid.get_hwid()
        b = hwid.get_hwid()
        self.assertEqual(a, b)
        self.assertTrue(0 < len(a) <= hwid.INSTALL_ID_MAXLEN)
        int(a, 16)                       # opaque hex


class TestBuildSubmit(unittest.TestCase):
    def _stats(self, **over):
        base = {'fishing_catches': 5, 'puzzles_solved': 2,
                'fishing_runtime_s': 12.5, 'puzzler_runtime_s': 3.0}
        base.update(over)
        return base

    def test_schema_keys_exact(self):
        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        p = payload.build_submit('bob', 'abc123', self._stats(), '1.0.5', now)
        self.assertEqual(set(p), {
            'username', 'hwid', 'fishing_catches', 'puzzles_solved',
            'fishing_runtime_s', 'puzzler_runtime_s', 'app_version', 'ts'})

    def test_values_carried(self):
        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        p = payload.build_submit('bob', 'abc', self._stats(), '1.0.5', now)
        self.assertEqual(p['username'], 'bob')
        self.assertEqual(p['fishing_catches'], 5)
        self.assertEqual(p['app_version'], '1.0.5')

    def test_deterministic_ts_from_aware_now(self):
        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        p = payload.build_submit('bob', 'abc', self._stats(), '1.0.5', now)
        self.assertEqual(p['ts'], int(now.timestamp()))

    def test_ts_from_epoch_number(self):
        p = payload.build_submit('bob', 'abc', self._stats(), '1.0.5', 1700000000)
        self.assertEqual(p['ts'], 1700000000)

    def test_username_capped(self):
        long = 'x' * 200
        p = payload.build_submit(long, 'abc', self._stats(), '1.0.5', 0)
        self.assertEqual(len(p['username']), payload.USERNAME_MAXLEN)

    def test_negative_counts_clamped(self):
        p = payload.build_submit('bob', 'abc',
                                 self._stats(fishing_catches=-9,
                                             fishing_runtime_s=-1.0),
                                 '1.0.5', 0)
        self.assertEqual(p['fishing_catches'], 0)
        self.assertEqual(p['fishing_runtime_s'], 0.0)

    def test_garbage_stats_safe(self):
        p = payload.build_submit('bob', 'abc',
                                 {'fishing_catches': 'NaN',
                                  'fishing_runtime_s': 'oops'}, '1.0.5', 0)
        self.assertEqual(p['fishing_catches'], 0)
        self.assertEqual(p['fishing_runtime_s'], 0.0)

    def test_build_from_non_dict_stats(self):
        p = payload.build_submit('bob', 'abc', None, '1.0.5', 0)
        self.assertEqual(p['fishing_catches'], 0)
        self.assertEqual(p['puzzles_solved'], 0)

    def test_never_raises(self):
        # totally hostile inputs
        p = payload.build_submit(object(), object(), object(), object(),
                                 object())
        self.assertIn('username', p)
        self.assertEqual(p['ts'], 0)


class TestClampPayload(unittest.TestCase):
    def test_idempotent(self):
        p = payload.build_submit('bob', 'abc',
                                 {'fishing_catches': 3}, '1.0.5', 100)
        self.assertEqual(payload.clamp_payload(p), p)

    def test_huge_count_clamped(self):
        p = payload.clamp_payload({'fishing_catches': 10 ** 12})
        self.assertEqual(p['fishing_catches'], 100_000_000)

    def test_non_dict_returns_defaults(self):
        p = payload.clamp_payload('not a dict')
        self.assertEqual(p['fishing_catches'], 0)
        self.assertEqual(p['username'], '')


if __name__ == '__main__':
    unittest.main()
