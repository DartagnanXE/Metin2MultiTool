# -*- coding: utf-8 -*-
"""ESC wird nur gedrueckt, wenn das Angel-Minispiel wirklich offen ist.

User-Report 2026-09-10. Bis v1.6.13 drueckte der Abbruch ESC bedingungslos --
mit dem Kommentar "raeumt ein evtl. offenes Minispiel weg". Bei einer NIETE ist
aber keines offen, es hat ja nichts angebissen. Das Live-Log des Testers zeigt
genau das nebeneinander:

    13:25:31 | STATE 3 | WL-DBG kind=niete
    13:25:31 | STATE 3 | Minigame match confidence this cast: 0.33   (Schwelle 0,90)
    13:25:31 | STATE 0 | Whitelist: Niete -> Minispiel abgebrochen (esc)

Ein ESC ins Leere trifft im Client das naechste Fenster: das INVENTAR, das der
Angel-Bot zwingend offen braucht (er oeffnet es nie selbst), oder das
Systemmenue. Und es passiert oft -- im selben Log enden 56 % aller Zyklen im
Abbruch.

FEHLERRICHTUNG (bewusst): lieber ein ESC zu WENIG. Bleibt ein Minispiel
faelschlich offen, laeuft seine eigene Uhr ab, der Koeder-Sensor meldet die
abgelehnte Aktion und der 15-s-Timeout greift -- alles protokolliert. Ein ESC zu
viel schliesst dagegen still das Inventar, und das Koeder-Nachlegen stirbt
unbemerkt.
"""

import os
import unittest
from unittest import mock

import numpy as np

import fishingbot
from tests.test_golden_modal_priority import _Clock, _make_bot

try:
    from PIL import Image
except Exception:                       # pragma: no cover
    Image = None

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Referenzen MIT offenem Minispiel und OHNE -- beide Gruppen aus echten
#: Spiel-Screenshots. Die Werte in den Tests sind gemessen (2026-09-10).
_MIT_MINISPIEL = ('MinispielOffen_user.png', 'thunfisch.png', 'Zander.png')
_OHNE_MINISPIEL = ('inventar_offen_seiteII.png', 'aktion_koeder_befestigt.png',
                   'quickslot_koeder_leer.png', 'GoldenerThunfisch3Optionen.png')


def _shots_present():
    return Image is not None and all(
        os.path.isfile(os.path.join(_REPO, 'FischOCR', n))
        for n in _MIT_MINISPIEL + _OHNE_MINISPIEL)


def _client(name):
    img = np.asarray(Image.open(os.path.join(_REPO, 'FischOCR', name))
                     .convert('RGB'))
    if img.shape[0] > 615:
        img = img[31:, 1:801]
    return img[:, :, ::-1].copy()


@unittest.skipUnless(_shots_present(), 'Referenz-Screenshots fehlen')
class TestErkennungAufEchtenBildern(unittest.TestCase):
    """Die Erkennung auf echten Spiel-Screenshots -- beide Richtungen."""

    def setUp(self):
        self.bot = fishingbot.FishingBot.__new__(fishingbot.FishingBot)

    def test_offenes_minispiel_wird_erkannt(self):
        for name in _MIT_MINISPIEL:
            with self.subTest(shot=name):
                offen, guete = self.bot._minigame_open(_client(name))
                self.assertTrue(offen, 'Guete nur %.3f' % guete)
                self.assertGreater(guete, 0.95)

    def test_ohne_minispiel_wird_nicht_erkannt(self):
        for name in _OHNE_MINISPIEL:
            with self.subTest(shot=name):
                offen, guete = self.bot._minigame_open(_client(name))
                self.assertFalse(offen, 'Guete %.3f' % guete)
                self.assertLess(guete, 0.5, 'zu nah an der Schwelle')

    def test_schwelle_liegt_in_der_luecke(self):
        """Gemessen: offen 0,983-0,992, zu 0,264-0,321. Die Schwelle 0,9 darf
        nicht an einen der Raender rutschen."""
        offen = [self.bot._minigame_open(_client(n))[1] for n in _MIT_MINISPIEL]
        zu = [self.bot._minigame_open(_client(n))[1] for n in _OHNE_MINISPIEL]
        self.assertGreater(min(offen), 0.9)
        self.assertLess(max(zu), 0.9)
        self.assertGreater(min(offen) - max(zu), 0.5, 'Luecke geschrumpft')


class TestDefensiv(unittest.TestCase):
    def test_kein_bild_und_muell_geben_nicht_offen(self):
        bot = fishingbot.FishingBot.__new__(fishingbot.FishingBot)
        for frame in (None, np.zeros((10, 10, 3), np.uint8),
                      np.zeros((601, 800, 3), np.uint8)):
            offen, guete = bot._minigame_open(frame)
            self.assertFalse(offen)
            self.assertGreaterEqual(guete, 0.0)


class _Loop(unittest.TestCase):
    """Treibt den ECHTEN ``runHack`` mit kontrollierter Uhr."""

    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
        self.bot._esc_pending_until = 0.0
        self.keys = []
        self.log = mock.Mock()

        fake_input = mock.Mock()
        fake_input.key.side_effect = lambda k, *a, **kw: self.keys.append(k)
        fake_input.click.side_effect = lambda x, y, **kw: None

        self.minigame = mock.Mock(return_value=False)
        self._patchers = [
            mock.patch.object(fishingbot, 'time', self.clock),
            mock.patch.object(fishingbot, '_input', fake_input),
            mock.patch.object(fishingbot, '_flog', self.log),
            mock.patch.object(fishingbot, 'click_tracker', None),
            mock.patch.object(self.bot, 'detect_minigame', self.minigame),
            mock.patch.object(self.bot, 'detect', return_value=None),
            mock.patch.object(self.bot, '_deliver_minigame_click',
                              side_effect=lambda x, y: None),
            mock.patch.object(self.bot, '_maybe_refill_bait', return_value=None),
            mock.patch.object(self.bot, '_check_bait_feedback',
                              return_value=None),
            mock.patch.object(self.bot, '_on_cycle_end', return_value=None),
            mock.patch.object(self.bot, 'detect_daily_reward',
                              return_value=False),
            mock.patch.object(self.bot, 'detect_golden_confirm',
                              return_value=(False, 0.0, None)),
            mock.patch.object(self.bot, '_apply_whitelist', return_value=False),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])
        self.bot.mount_enabled = False
        self.bot.bait_key = '2'
        self.bot.cast_key = '1'

    def _tick(self, dt=0.05):
        self.clock.advance(dt)
        return self.bot.runHack()

    def _geloggt(self, key):
        from i18n import t
        wanted = t(key)
        return sum(1 for c in self.log.call_args_list
                   if len(c.args) > 1 and c.args[1] == wanted)


class TestEscNurBeiOffenemMinispiel(_Loop):
    """Der Kern des Fixes."""

    def test_kein_esc_wenn_kein_minispiel(self):
        """Der Niete-Fall aus dem Log: nichts offen -> kein Tastendruck."""
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(False, 0.33)):
            how = self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        self.assertEqual(self.keys, [], 'ESC ins Leere gedrueckt')
        self.assertEqual(how, 'kein-minispiel')

    def test_esc_wenn_minispiel_offen(self):
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(True, 0.99)):
            how = self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        self.assertEqual(self.keys, ['esc'])
        self.assertEqual(how, 'esc')

    def test_ohne_bild_wird_nicht_gedrueckt(self):
        """Kein Screenshot -> nicht messbar -> die sichere Richtung."""
        how = self.bot._abort_minigame(None)
        self.assertEqual(self.keys, [])
        self.assertEqual(how, 'kein-minispiel')

    def test_zustand_wird_trotzdem_zurueckgesetzt(self):
        """Ohne ESC muss der Neustart weiterhin greifen -- er haengt am
        Zustand, nicht am Tastendruck."""
        self.bot.state = 3
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(False, 0.2)):
            self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        self.assertEqual(self.bot.state, 0)


class TestNachgeholtesEsc(_Loop):
    """Die Chat-Zeile kann einen Wimpernschlag vor dem Fenster kommen."""

    def _abbruch_ohne_minispiel(self):
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(False, 0.3)):
            self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        self.keys.clear()

    def test_esc_wird_nachgeholt_wenn_das_fenster_doch_aufgeht(self):
        self._abbruch_ohne_minispiel()
        self.minigame.return_value = True
        self._tick(dt=0.5)
        # Neben ESC steht hier die Koeder-Taste: der Abbruch setzt auf State 0
        # und datiert den Timer zurueck, damit SOFORT neu geangelt wird. Das
        # ist gewolltes v1.6.5-Verhalten und darf nicht mitgeprueft werden.
        self.assertIn('esc', self.keys, 'ESC wurde nicht nachgeholt')
        self.assertEqual(self._geloggt('fishing.abort_esc_nachgeholt'), 1)

    def test_nur_einmal_nachgeholt(self):
        self._abbruch_ohne_minispiel()
        self.minigame.return_value = True
        for _ in range(10):
            self._tick(dt=0.1)
        self.assertEqual(self.keys.count('esc'), 1, 'ESC mehrfach nachgeholt')

    def test_nach_ablauf_der_frist_kein_esc_mehr(self):
        self._abbruch_ohne_minispiel()
        self.clock.advance(self.bot.ESC_WATCH_S + 1.0)
        self.minigame.return_value = True
        self._tick(dt=0.1)
        self.assertNotIn('esc', self.keys, 'ESC nach Fristablauf gedrueckt')

    def test_ohne_abbruch_kein_esc(self):
        """Gegenprobe: ein ganz normales Minispiel loest nie ESC aus."""
        self.minigame.return_value = True
        for _ in range(20):
            self._tick(dt=0.1)
        self.assertNotIn('esc', self.keys)


class TestDebugSpur(_Loop):
    """Jede Entscheidung muss im Log stehen -- sonst ist der naechste Report
    wieder nicht auswertbar."""

    def test_gate_zeile_mit_werten(self):
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(False, 0.331)):
            self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        self.assertEqual(self._geloggt('fishing.abort_esc_gate'), 1)
        # Die Zusatzfelder muessen den Messwert tragen.
        felder = [c.kwargs for c in self.log.call_args_list if c.kwargs]
        passend = [f for f in felder if f.get('guete') == '0.331']
        self.assertTrue(passend, 'Guete fehlt im Log: %r' % (felder,))
        self.assertEqual(passend[0]['minispiel'], 'nein')
        self.assertEqual(passend[0]['weg'], 'kein-minispiel')

    def test_gate_zeile_auch_bei_gedruecktem_esc(self):
        with mock.patch.object(self.bot, '_minigame_open',
                               return_value=(True, 0.991)):
            self.bot._abort_minigame(np.zeros((601, 800, 3), np.uint8))
        felder = [c.kwargs for c in self.log.call_args_list if c.kwargs]
        passend = [f for f in felder if f.get('guete') == '0.991']
        self.assertTrue(passend)
        self.assertEqual(passend[0]['minispiel'], 'ja')
        self.assertEqual(passend[0]['weg'], 'esc')


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
