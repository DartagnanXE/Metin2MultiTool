# -*- coding: utf-8 -*-
"""Nach den Thunfisch-Fenstern wird das Inventar neu geordnet.

User-Wunsch 2026-09-10: "nach dem der goldene Thunfisch kam ist das Inventar
meist etwas verschoben -- sobald die Fenster weg sind mit 0,3 s Delay 2x I
drücken, damit das Inventar sich neu korrekt ordnet."

WARUM DAS ZAEHLT: Der Bot rechnet mit FESTEN Slot-Pixeln. Verschiebt sich das
Inventar-Fenster, greift das Koeder-Nachlegen an die alte Stelle -- also ins
Leere, ohne dass jemand etwas merkt.

Zweimal die Taste stellt den ALTEN ZUSTAND wieder her: zu -> auf -> zu, bzw.
auf -> zu -> auf. Nur die Lage wird korrigiert. Deshalb ist es auch dann
unschaedlich, wenn das Inventar gerade geschlossen war.

Der zweite Druck laeuft ueber einen Zeitstempel, NICHT ueber ``sleep`` -- der
Angel-Loop darf nicht 0,3 s stehenbleiben (die Tester haben zweimal Tempo
gemeldet).
"""

import unittest
from unittest import mock

import numpy as np

import fishingbot
from tests.test_golden_modal_priority import _Clock, _make_bot


class _Loop(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
        self.bot._golden_daily_seen = 0.0
        self.bot._golden_seen_any = False
        self.bot._inv_reorder_second_at = 0.0
        self.bot._esc_pending_until = 0.0
        self.bot.inventory_key = 'i'
        self.bot.inventar_neu_ordnen = True
        self.keys = []

        fake_input = mock.Mock()
        fake_input.key.side_effect = lambda k, *a, **kw: self.keys.append(k)
        fake_input.click.side_effect = lambda x, y, **kw: None

        self._patchers = [
            mock.patch.object(fishingbot, 'time', self.clock),
            mock.patch.object(fishingbot, '_input', fake_input),
            mock.patch.object(fishingbot, 'click_tracker', None),
            mock.patch.object(self.bot, 'detect_minigame', return_value=False),
            mock.patch.object(self.bot, 'detect', return_value=None),
            mock.patch.object(self.bot, '_deliver_minigame_click',
                              side_effect=lambda x, y: None),
            mock.patch.object(self.bot, '_maybe_refill_bait', return_value=None),
            mock.patch.object(self.bot, '_check_bait_feedback',
                              return_value=None),
            mock.patch.object(self.bot, '_on_cycle_end', return_value=None),
            mock.patch.object(self.bot, '_apply_whitelist', return_value=False),
            mock.patch.object(self.bot, 'detect_golden_confirm',
                              return_value=(False, 0.0, None)),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])
        self.bot.mount_enabled = False
        self.bot.bait_key = '2'
        self.bot.cast_key = '1'
        # State 0 mit frischem Timer -> der Automat loest keine eigenen Tasten aus
        self.bot.state = 0

    def _tick(self, daily=False, dt=0.05):
        self.clock.advance(dt)
        self.bot.timer_action = self.clock() + 999   # keine State-Wechsel
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=daily):
            return self.bot.runHack()

    def _i_druecke(self):
        return [k for k in self.keys if k == 'i']


class TestNeuordnungNachDenFenstern(_Loop):
    def test_zwei_druecke_nachdem_das_fenster_weg_ist(self):
        self._tick(daily=True)              # Optionsfenster steht
        self.assertEqual(self._i_druecke(), [], 'zu frueh gedrueckt')
        self._tick(daily=False, dt=4.0)     # Fenster weg (Grace vorbei)
        self.assertEqual(len(self._i_druecke()), 1, 'erster Druck fehlt')
        # Der zweite kommt erst nach der Wartezeit.
        self._tick(dt=0.1)
        self.assertEqual(len(self._i_druecke()), 1, 'zweiter Druck zu frueh')
        self._tick(dt=0.3)
        self.assertEqual(len(self._i_druecke()), 2, 'zweiter Druck fehlt')

    def test_abstand_entspricht_der_vorgabe(self):
        self._tick(daily=True)
        self._tick(daily=False, dt=4.0)
        geplant = self.bot._inv_reorder_second_at - self.clock()
        self.assertAlmostEqual(geplant, self.bot.INVENTAR_NEUORDNEN_DELAY_S,
                               places=6)
        self.assertAlmostEqual(self.bot.INVENTAR_NEUORDNEN_DELAY_S, 0.3,
                               places=6)

    def test_genau_zweimal_nicht_oefter(self):
        self._tick(daily=True)
        self._tick(daily=False, dt=4.0)
        for _ in range(40):
            self._tick(dt=0.2)
        self.assertEqual(len(self._i_druecke()), 2,
                         'Taste wurde mehr als zweimal gedrueckt')

    def test_der_loop_wird_nicht_angehalten(self):
        """Der zweite Druck laeuft ueber einen Zeitstempel -- kein sleep im
        Angel-Loop, sonst kostet jede Thunfisch-Episode 0,3 s Angelzeit."""
        with mock.patch('time.sleep') as geschlafen:
            self._tick(daily=True)
            self._tick(daily=False, dt=4.0)
            self._tick(dt=0.4)
        self.assertEqual(geschlafen.call_count, 0, 'der Loop hat geschlafen')

    def test_nutzt_die_eingestellte_taste(self):
        self.bot.inventory_key = 'b'
        self._tick(daily=True)
        self._tick(daily=False, dt=4.0)
        self._tick(dt=0.4)
        self.assertEqual([k for k in self.keys if k == 'b'].__len__(), 2)

    def test_schalter_aus_druckt_nichts(self):
        self.bot.inventar_neu_ordnen = False
        self._tick(daily=True)
        self._tick(daily=False, dt=4.0)
        self._tick(dt=0.4)
        self.assertEqual(self._i_druecke(), [])

    def test_ohne_thunfisch_passiert_nichts(self):
        """Gegenprobe: im Normalbetrieb darf die Taste nie kommen."""
        for _ in range(30):
            self._tick(daily=False, dt=0.2)
        self.assertEqual(self._i_druecke(), [])

    def test_auch_nach_einem_bestaetigungs_dialog(self):
        """Nicht nur das Optionsfenster zaehlt -- auch ein OK-Dialog allein
        verschiebt das Inventar."""
        self.bot._golden_confirm_until = self.clock() + 10.0
        self.bot._golden_confirm_hard = self.clock() + 40.0
        with mock.patch.object(self.bot, 'detect_golden_confirm',
                               return_value=(True, 0.99, (403, 250))):
            self._tick()
        self.assertTrue(self.bot._golden_seen_any, 'Dialog nicht vermerkt')
        self.bot._golden_confirm_until = 0.0
        self.bot._golden_suppress_until = 0.0
        self._tick(dt=4.0)
        self.assertEqual(len(self._i_druecke()), 1)

    def test_zweite_episode_ordnet_erneut(self):
        for runde in range(2):
            self._tick(daily=True)
            self._tick(daily=False, dt=4.0)
            self._tick(dt=0.4)
        self.assertEqual(len(self._i_druecke()), 4,
                         'zweite Episode hat nicht neu geordnet')

    def test_fehler_beim_druecken_kippt_den_loop_nicht(self):
        with mock.patch.object(fishingbot._input, 'key',
                               side_effect=RuntimeError('boom')):
            self._tick(daily=True)
            self._tick(daily=False, dt=4.0)     # darf nicht werfen
        self.assertEqual(self.bot._inv_reorder_second_at, 0.0)


class TestVoreinstellung(unittest.TestCase):
    def test_default_ist_an(self):
        from interface.config.defaults import DEFAULTS
        self.assertTrue(DEFAULTS['fishing']['inventar_neu_ordnen'])

    def test_validierung(self):
        from interface.config.validate import validate
        self.assertTrue(validate({})['fishing']['inventar_neu_ordnen'])
        self.assertFalse(validate({'fishing': {'inventar_neu_ordnen': False}})
                         ['fishing']['inventar_neu_ordnen'])


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
