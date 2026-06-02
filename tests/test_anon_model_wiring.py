# -*- coding: utf-8 -*-
"""Run-1 QA: the ANONYMOUS-model WIRING end-to-end (no fakes for the code paths
the spec hinges on).

The payload/anon-name/server pieces are unit-tested elsewhere; this file pins
the GLUE that ties the model together and was previously only mirrored by
stand-in fakes:

  * ``interface.app.lifecycle.LifecycleMixin._telemetry_state`` -- the REAL
    snapshot builder, bound to a tiny harness backed by a REAL ``BotController``
    (real config validation + auto-save). It must:
      - GENERATE + PERSIST a random install_id ONCE on first call (uuid4 hex,
        not device-derived) and REUSE it on every later call;
      - carry that id as the wire ``hwid`` and send WITHOUT requiring a chosen
        username (anonymous always-on counter -- no opt-out);
      - flip ``enabled`` to False ONLY when blocked (``_ranking_banned``), with
        the install_id + url otherwise present;
      - never raise.
  * ``interface.onboarding.needs_onboarding`` -- the only-consent gate: shown
    once, suppressed by a chosen name OR a recorded decision, never raises.
  * The set-name -> clear-name ROUND TRIP through real config: a chosen name is
    the only identifying datum; clearing it returns to '' (the anon fallback the
    server then applies). Pairs the client config truth with the server's
    chosen-or-anon display-name rule so the two stay consistent.
  * The TRANSPARENCY notice exists (a notice, NOT a consent gate) while there is
    NO opt-out flag the user can toggle off.

Headless: imports customtkinter (present on py.exe) but builds NO Tk window --
the mixin method is bound to a plain object, exactly like test_app_controller.
Stdlib unittest + mock.
"""

import unittest
from unittest import mock

try:
    import interface.app as app
    from interface.app.lifecycle import LifecycleMixin
    _IMPORT_OK = True
    _IMPORT_ERR = ''
except Exception as exc:                 # pragma: no cover - env dependent
    _IMPORT_OK = False
    _IMPORT_ERR = repr(exc)

from interface import config as cfgmod
from telemetry import hwid as hwidmod
from telemetry.anon_name import anon_name as client_anon_name


class _FakeApp:
    """Minimal back-talk surface a BotController needs (no Tk).

    ``after`` runs nothing (the debounced save is fine to drop -- we read the
    config straight off the controller), matching test_app_controller's stub."""

    def after(self, _ms, _fn):
        return 'job'

    def after_cancel(self, _job):
        pass

    def sync_controls(self):
        pass

    def flash_saved(self):
        pass


def _make_harness(cfg=None, banned=False, stats=None):
    """A tiny object carrying the REAL _telemetry_state bound to a REAL controller.

    Returns ``(harness, controller)``. The harness exposes exactly what
    ``_telemetry_state`` reads off ``self``: ``controller`` / ``_stats`` /
    ``_install_id`` / ``_ranking_banned``.
    """
    controller = app.BotController(
        _FakeApp(), fishbot=None, puzzlebot=None,
        cfg=cfg if cfg is not None else {})

    class _Harness:
        pass

    h = _Harness()
    h._telemetry_state = LifecycleMixin._telemetry_state.__get__(h)
    h.controller = controller
    h._stats = stats if stats is not None else {
        'fishing_catches': 7, 'puzzles_solved': 3,
        'fishing_runtime_s': 12.0, 'puzzler_runtime_s': 4.0}
    h._install_id = None
    h._ranking_banned = banned
    return h, controller


@unittest.skipUnless(_IMPORT_OK, 'interface.app import failed: ' + _IMPORT_ERR)
class TestTelemetryStateInstallId(unittest.TestCase):
    """The REAL _telemetry_state mints + persists a random install_id once."""

    def test_generates_and_persists_random_install_id_once(self):
        h, ctrl = _make_harness()
        # Config starts with NO id (filled lazily on first snapshot).
        self.assertEqual(ctrl.current_config()['telemetry']['install_id'], '')
        state = h._telemetry_state()
        gen = state['hwid']
        # uuid4 hex: 32 lowercase hex chars, NOT device-derived.
        self.assertEqual(len(gen), 32)
        int(gen, 16)
        # Persisted to the real config via the controller...
        self.assertEqual(ctrl.current_config()['telemetry']['install_id'], gen)
        # ...and cached on the harness for reuse.
        self.assertEqual(h._install_id, gen)
        # A second snapshot returns the SAME id (no regeneration).
        self.assertEqual(h._telemetry_state()['hwid'], gen)

    def test_install_id_is_not_hardware_derived(self):
        # Two independent harnesses (same machine, same run) get DIFFERENT ids ->
        # the id is random per install, never a device fingerprint.
        a, _ = _make_harness()
        b, _ = _make_harness()
        self.assertNotEqual(a._telemetry_state()['hwid'],
                            b._telemetry_state()['hwid'])

    def test_reuses_existing_stored_id(self):
        h, ctrl = _make_harness(
            cfg={'telemetry': {'install_id': 'deadbeef' * 4}})  # 32 chars
        state = h._telemetry_state()
        self.assertEqual(state['hwid'], 'deadbeef' * 4)
        # Untouched in config (already present -> no new mint).
        self.assertEqual(ctrl.current_config()['telemetry']['install_id'],
                         'deadbeef' * 4)


@unittest.skipUnless(_IMPORT_OK, 'interface.app import failed: ' + _IMPORT_ERR)
class TestTelemetryStateAnonymousAlwaysOn(unittest.TestCase):
    """enabled depends only on id+url present AND not blocked; NO username gate."""

    def test_enabled_without_username(self):
        # Anonymous always-on: no chosen name, but a real submit_url default ->
        # the snapshot is enabled and carries an empty username.
        h, _ = _make_harness()
        state = h._telemetry_state()
        self.assertEqual(state['username'], '')
        self.assertTrue(state['hwid'])
        self.assertTrue(state['submit_url'])
        self.assertTrue(state['enabled'])

    def test_blocked_disables_sending(self):
        h, _ = _make_harness(banned=True)
        state = h._telemetry_state()
        # id + url still present, but blocked -> enabled False (the stop-signal).
        self.assertTrue(state['hwid'])
        self.assertTrue(state['submit_url'])
        self.assertFalse(state['enabled'])

    def test_empty_submit_url_disables(self):
        h, _ = _make_harness(cfg={'telemetry': {'submit_url': ''}})
        state = h._telemetry_state()
        # validate() backfills the placeholder default for a blank URL, so force
        # the blank explicitly post-validation to prove the gate.
        with mock.patch.object(
                h.controller, 'current_config',
                return_value={'telemetry': {'submit_url': '',
                                            'install_id': 'a' * 32,
                                            'interval_s': 120},
                              'username': ''}):
            state = h._telemetry_state()
        self.assertFalse(state['enabled'])

    def test_payload_carries_install_id_as_hwid_and_counters(self):
        h, _ = _make_harness(stats={
            'fishing_catches': 9, 'puzzles_solved': 4,
            'fishing_runtime_s': 30.0, 'puzzler_runtime_s': 5.0})
        state = h._telemetry_state()
        p = state['payload']
        self.assertEqual(p['hwid'], state['hwid'])         # id carried as hwid
        self.assertEqual(p['fishing_catches'], 9)
        self.assertEqual(p['puzzles_solved'], 4)
        self.assertEqual(p['username'], '')                # anonymous
        # The four spec counters are present + the version/ts.
        for k in ('fishing_catches', 'puzzles_solved', 'fishing_runtime_s',
                  'puzzler_runtime_s', 'app_version', 'ts'):
            self.assertIn(k, p)

    def test_chosen_name_flows_into_snapshot(self):
        h, _ = _make_harness(cfg={'username': 'Angler'})
        state = h._telemetry_state()
        self.assertEqual(state['username'], 'Angler')
        self.assertEqual(state['payload']['username'], 'Angler')
        # Still enabled (a name does not gate the counter -- it only reveals).
        self.assertTrue(state['enabled'])

    def test_never_raises_on_broken_controller(self):
        class _Boom:
            pass

        h = _Boom()
        h._telemetry_state = LifecycleMixin._telemetry_state.__get__(h)
        # No controller / stats / flags at all -> must fall back, never raise.
        state = h._telemetry_state()
        self.assertFalse(state['enabled'])
        self.assertEqual(state['hwid'], '')
        self.assertEqual(state['payload'], {})


@unittest.skipUnless(_IMPORT_OK, 'interface.app import failed: ' + _IMPORT_ERR)
class TestChosenNameRoundTrip(unittest.TestCase):
    """Set the only-consent name, then clear it -> back to anonymous ''. The
    server's display rule (chosen-or-anon) is pinned against the same id so the
    client truth and the server label stay consistent."""

    def test_set_then_clear_returns_to_anonymous(self):
        h, ctrl = _make_harness()
        install_id = h._telemetry_state()['hwid']

        # Opt-in: choose a name -> it appears in the snapshot.
        ctrl.update_username('TunaKing')
        self.assertEqual(h._telemetry_state()['username'], 'TunaKing')

        # Remove it -> back to anonymous (''); the id is unchanged.
        ctrl.update_username('')
        state = h._telemetry_state()
        self.assertEqual(state['username'], '')
        self.assertEqual(state['hwid'], install_id)

    def test_server_display_name_is_anon_when_name_cleared(self):
        # When the chosen name is blank, the server falls back to the SAME
        # deterministic anon name the client would compute from the id. Pin the
        # cross-package consistency (server copy is import-isolated).
        try:
            from server.app.anon_name import anon_name as server_anon_name
        except Exception:
            self.skipTest('server anon_name unavailable')
        h, _ = _make_harness()
        install_id = h._telemetry_state()['hwid']
        self.assertEqual(server_anon_name(install_id, 'en'),
                         client_anon_name(install_id, 'en'))


@unittest.skipUnless(_IMPORT_OK, 'interface.app import failed: ' + _IMPORT_ERR)
class TestNoUserOptOutButTransparency(unittest.TestCase):
    """There is NO user-toggleable opt-out of the anonymous counter; instead a
    transparency notice is present. The config ``telemetry.enabled`` flag is
    VESTIGIAL: it survives round-trips (back-compat for old config.json) but the
    snapshot NEVER consults it -- so even a stored False keeps sending. The only
    real stop is a server block (``_ranking_banned``)."""

    def test_config_enabled_default_true(self):
        # Absent in config -> defaults True (the vestigial flag's only effect).
        self.assertTrue(cfgmod.validate(cfgmod.DEFAULTS)['telemetry']['enabled'])

    def test_snapshot_ignores_config_enabled_flag(self):
        # Even with telemetry.enabled stored False, the snapshot still computes
        # enabled from (id+url present, not blocked) -- it does NOT read the
        # config flag, so a user cannot opt out by flipping it. This is the real
        # "no opt-out" guarantee.
        h, _ = _make_harness(cfg={'telemetry': {'enabled': False}})
        self.assertTrue(h._telemetry_state()['enabled'])

    def test_transparency_strings_present_both_langs(self):
        from i18n_data import TRANSLATIONS
        for key in ('ui.ranking_transparency', 'ui.onboarding_transparency',
                    'ui.onboarding_whatissent'):
            self.assertIn(key, TRANSLATIONS)
            self.assertTrue(str(TRANSLATIONS[key]['en']).strip())
            self.assertTrue(str(TRANSLATIONS[key]['de']).strip())


@unittest.skipUnless(_IMPORT_OK, 'interface.app import failed: ' + _IMPORT_ERR)
class TestOnboardingGate(unittest.TestCase):
    """needs_onboarding: shown once; a chosen name OR a recorded decision
    suppresses it; malformed config -> False (never crash on startup)."""

    def setUp(self):
        from interface import onboarding
        self.onboarding = onboarding

    def test_shown_when_no_name_and_undecided(self):
        cfg = cfgmod.validate(cfgmod.DEFAULTS)
        self.assertTrue(self.onboarding.needs_onboarding(cfg))

    def test_suppressed_once_decided(self):
        cfg = cfgmod.validate({'telemetry': {'consented': True}})
        self.assertFalse(self.onboarding.needs_onboarding(cfg))

    def test_suppressed_when_name_present(self):
        cfg = cfgmod.validate({'username': 'Bob'})
        self.assertFalse(self.onboarding.needs_onboarding(cfg))

    def test_malformed_config_returns_false(self):
        # A non-dict / hostile config must not raise on the startup path.
        self.assertFalse(self.onboarding.needs_onboarding(None))
        self.assertFalse(self.onboarding.needs_onboarding(12345))


if __name__ == '__main__':
    unittest.main()
