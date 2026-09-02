# -*- coding: utf-8 -*-
"""Der OK-Knopf des Goldenen Thunfischs wird ZUVERLAESSIG gedrueckt.

User-Report 2026-08-18: "irgendwie drueckt er doch nicht drauf, beim ersten Mal
hats geklappt, jetzt die letzten Male gar nicht mehr -- also auf das 2. Popup".

Zwei UNABHAENGIGE Ursachen, beide gemessen statt vermutet:

1. FENSTER-VERANKERUNG (Steuerfluss). ``_golden_confirm_hard`` ist die absolute
   Obergrenze einer Golden-Episode. Gesetzt wurde sie bis v1.6.11 an der
   Bedingung ``now >= _hard`` -- die aber AUCH das Sicherheitsnetz im
   Minispiel-Timeout stellt, zu einem voellig unabhaengigen Zeitpunkt. Kam der
   Thunfisch innerhalb dieser 45 s, galt seine Flanke als "laeuft schon" und das
   Klick-Fenster wurde per ``min(now+10, _hard)`` auf den Rest zusammengekuerzt.
   Am echten ``runHack`` nachgestellt: Timeout bei t=0, Optionsfenster bei t=44
   -> Fenster 1,0 s statt 10 s, Server-Antwort bei t=46, OK NIE gedrueckt --
   obwohl der Dialog sauber erkannt wurde. Genau das Muster "mal geht es, mal
   nicht".

2. SZENEN-ABHAENGIGE SCHWELLE (Erkennung). Der Leisten-Check verlangte eine
   Helligkeit von 50..110 -- kalibriert an den drei Referenzen (65,7 / 79,3 /
   84,7). Die Leiste ist aber HALBTRANSPARENT, ihre Helligkeit folgt der Szene
   dahinter. Gemessen: schon +45 Helligkeit (andere Angelstelle / Tageszeit)
   liess 3 von 3 Referenzen durchfallen -- perfekt erkannter Knopf, kein Klick.

Beide Tests pinnen den Fix; die Fenster-Tests fahren den ECHTEN ``runHack``.
"""

import os
import unittest
from unittest import mock

import numpy as np

import fishing_detect as fd
import fishingbot

from tests.test_golden_modal_priority import (_Clock, _client_bgr, _make_bot,
                                              _shots_present)

_POSITIVE = ('GoldenThunfischBuffBestaetigen.png',
             'GoldenerThunfischAuswahlbestätigen.png',
             'GoldenerThunfischEntwischtBestaetigen.png',
             # Nutzer-Report 2026-09-02: Gildenname ueber dem OK (Bonus) und
             # die Entwischt-Meldung desselben Laufs -- beides echte Dialoge.
             'GoldenerThunfischBonus_user2.png',
             'GoldenerThunfischEntwischtNass_user2.png')

# Erwartete Knopf-Mitte je Referenz (Client-Koordinaten) -- der Dialog WANDERT,
# seine Hoehe haengt am Meldungstext.
_PUNKT = {'GoldenThunfischBuffBestaetigen.png': (403, 202),
          'GoldenerThunfischAuswahlbestätigen.png': (403, 250),
          'GoldenerThunfischEntwischtBestaetigen.png': (403, 266),
          'GoldenerThunfischBonus_user2.png': (403, 250),
          'GoldenerThunfischEntwischtNass_user2.png': (403, 266)}


class _Fenster(unittest.TestCase):
    """Treibt den echten ``runHack`` mit kontrollierter Uhr."""

    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
        self.bot._golden_daily_seen = 0.0
        self.clicks = []

        fake_input = mock.Mock()
        fake_input.click.side_effect = (
            lambda x, y, button='left', tag='other':
            self.clicks.append((tag, x, y)))

        self._patchers = [
            mock.patch.object(fishingbot, 'time', self.clock),
            mock.patch.object(fishingbot, '_input', fake_input),
            mock.patch.object(fishingbot, 'click_tracker', None),
            mock.patch.object(self.bot, 'detect_minigame', return_value=True),
            mock.patch.object(self.bot, 'detect', return_value=None),
            mock.patch.object(self.bot, '_deliver_minigame_click',
                              side_effect=lambda x, y: None),
            mock.patch.object(self.bot, '_maybe_refill_bait', return_value=None),
            mock.patch.object(self.bot, '_check_bait_feedback',
                              return_value=None),
            mock.patch.object(self.bot, '_on_cycle_end', return_value=None),
            mock.patch.object(self.bot, '_apply_whitelist', return_value=False),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])

    def _tick(self, daily=False, confirm=None):
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=daily), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  return_value=(confirm or (False, 0.0, None))):
            return self.bot.runHack()

    def _timeout(self):
        """Einen echten Minispiel-Timeout ausloesen (arm't das Sicherheitsnetz)."""
        self.clock.advance(0.001)   # runHack rechnet FPS = 1/dt
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 16.0
        self._tick()

    def _tags(self):
        return [tag for tag, _x, _y in self.clicks]


class TestFensterNachTimeout(_Fenster):
    """DER KERN DES FIXES -- der nachgestellte Fehlerfall."""

    def test_ok_kommt_auch_wenn_kurz_vorher_ein_timeout_lief(self):
        self._timeout()
        self.clock.advance(44.0)
        self.bot.state = 3
        self.bot.timer_action = self.clock()
        self._tick(daily=True)                      # Optionsfenster
        self.clock.advance(2.0)
        self._tick(confirm=(True, 0.9, (403, 266)))  # Server-Antwort
        self.assertIn('confirm', self._tags(),
                      'Bestaetigungsdialog stand, aber OK wurde nicht gedrueckt')

    def test_options_klick_bekommt_immer_das_volle_fenster(self):
        self._timeout()
        self.clock.advance(44.0)
        self.bot.state = 3
        self.bot.timer_action = self.clock()
        self._tick(daily=True)
        self.assertAlmostEqual(
            self.bot._golden_confirm_until - self.clock(),
            self.bot.GOLDEN_CONFIRM_WAIT_S, places=6,
            msg='ein fremdes Ereignis hat das Klick-Fenster gekuerzt')

    def test_ok_kommt_auch_ohne_vorheriges_timeout(self):
        """Gegenprobe: der einfache Fall darf nicht kaputtgehen."""
        self._tick(daily=True)
        self.clock.advance(2.0)
        self._tick(confirm=(True, 0.9, (403, 250)))
        self.assertIn('confirm', self._tags())


class TestDeckelBleibtDicht(_Fenster):
    """Die Backstops, die den Fix nicht aufweichen darf."""

    def test_klebendes_optionsfenster_verlaengert_die_deadline_nicht(self):
        """Ein dauerhaft schwarzer Bildrand (Lade-/Teleport-Screen) darf die
        harte Obergrenze NICHT endlos vor sich herschieben."""
        self._tick(daily=True)
        erste = self.bot._golden_confirm_hard
        for _ in range(20):
            self.clock.advance(1.0)     # < GOLDEN_EPISODE_GAP_S -> gleiche Episode
            self._tick(daily=True)
        self.assertEqual(self.bot._golden_confirm_hard, erste,
                         'die harte Deadline wurde weitergeschoben')

    def test_neue_episode_nach_echter_pause_setzt_zurueck(self):
        self._tick(daily=True)
        self.bot._golden_confirm_clicks = 4
        erste = self.bot._golden_confirm_hard
        self.clock.advance(self.bot.GOLDEN_EPISODE_GAP_S + 1.0)
        self._tick(daily=True)
        self.assertGreater(self.bot._golden_confirm_hard, erste)
        self.assertEqual(self.bot._golden_confirm_clicks, 0)

    def test_klick_deckel_haelt_einen_klebenden_dialog_an(self):
        """Klebt der Dialog (Klick wirkt nicht), endet die Episode nach dem
        Deckel -- statt 60x/s auf dieselbe Stelle zu haemmern.

        Der Bot bleibt dabei bewusst in State 0 (Angel-Uhr eingefroren), damit
        kein Minispiel-Timeout dazwischenfunkt: der zieht naemlich absichtlich
        eine NEUE Episode auf (siehe der Test darunter)."""
        self._tick(daily=True)
        self.bot.state = 0
        for _ in range(40):
            self.clock.advance(1.5)     # > Cooldown, damit jeder Klick zaehlen darf
            self.bot.timer_action = self.clock()     # keine State-Wechsel
            self._tick(confirm=(True, 0.9, (403, 266)))
        self.assertLessEqual(self._tags().count('confirm'),
                             self.bot.GOLDEN_CONFIRM_MAX_CLICKS)

    def test_sicherheitsnetz_darf_es_spaeter_neu_versuchen(self):
        """BEWUSST so: der Deckel begrenzt EINE Episode, nicht den ganzen Lauf.

        Bleibt eine Meldung stehen, oeffnet das Sicherheitsnetz im
        Minispiel-Timeout spaeter ein neues Fenster und der Bot versucht es
        erneut -- sonst haenge er fuer immer hinter einem Dialog, den niemand
        wegklickt. Aufgeben ist hier die schlechtere Richtung."""
        self._tick(daily=True)
        self.bot.state = 0
        for _ in range(10):
            self.clock.advance(1.5)
            self.bot.timer_action = self.clock()
            self._tick(confirm=(True, 0.9, (403, 266)))
        vorher = self._tags().count('confirm')
        self.assertEqual(vorher, self.bot.GOLDEN_CONFIRM_MAX_CLICKS)

        self._timeout()                 # neues Fenster, frisches Budget
        self.clock.advance(1.5)
        self._tick(confirm=(True, 0.9, (403, 266)))
        self.assertGreater(self._tags().count('confirm'), vorher)


@unittest.skipUnless(_shots_present(), 'Referenz-Screenshots fehlen')
class TestErkennungUeberlebtDieSzene(unittest.TestCase):
    """Der Leisten-Check darf nicht an der Szenen-Helligkeit haengen.

    Die Dialog-Leiste ist halbtransparent -- eine andere Angelstelle oder
    Tageszeit verschiebt ihre Helligkeit. Gemessen mit dem ALTEN Fenster
    (50..110): schon +45 liess alle drei Referenzen durchfallen.
    """

    def _varianten(self, img):
        return (
            ('original', img),
            ('heller +45', np.clip(img.astype(np.int16) + 45, 0, 255)
             .astype(np.uint8)),
            ('heller x1.5', np.clip(img.astype(np.float32) * 1.5, 0, 255)
             .astype(np.uint8)),
            ('dunkler -35', np.clip(img.astype(np.int16) - 35, 0, 255)
             .astype(np.uint8)),
        )

    def test_knopf_wird_in_jeder_helligkeit_gefunden(self):
        for name in _POSITIVE:
            img = _client_bgr(name)
            for label, variante in self._varianten(img):
                with self.subTest(shot=name, szene=label):
                    found, _score, point = fd.golden_confirm_find(variante)
                    self.assertTrue(found, 'nicht erkannt')
                    # Seit v1.6.13 ist der Klick an der Leisten-Geometrie
                    # verankert, nicht am OK-Text: bis 3 px Versatz auf der
                    # 20 px hohen Leiste sind derselbe Knopf.
                    ex = _PUNKT[name]
                    self.assertLessEqual(
                        abs(point[0] - ex[0]) + abs(point[1] - ex[1]), 6,
                        'Klickpunkt %s nicht auf dem Knopf um %s' % (point, ex))

    def test_weiteres_fenster_erzeugt_keine_neuen_fehltreffer(self):
        """Gegenprobe: kein Nicht-Dialog darf jetzt als Dialog gelten."""
        ordner = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'FischOCR')
        for datei in sorted(os.listdir(ordner)):
            if not datei.endswith('.png') or datei in _POSITIVE:
                continue
            pfad = os.path.join(ordner, datei)
            try:
                img = _client_bgr(datei)
            except Exception:                       # pragma: no cover
                continue
            if img.shape[0] < 100 or not os.path.isfile(pfad):
                continue
            with self.subTest(shot=datei):
                found, score, _pt = fd.golden_confirm_find(img)
                self.assertFalse(found,
                                 '%s gilt faelschlich als Dialog (%.4f)'
                                 % (datei, score))

    def test_schwelle_bleibt_in_der_luecke(self):
        """Die NCC-Schwelle ist der eigentliche Unterscheider -- sie bleibt
        zwischen dem schwaechsten Positiv und dem staerksten Negativ."""
        self.assertGreater(fd.GOLDEN_OK_NCC_MIN, 0.60)
        self.assertLess(fd.GOLDEN_OK_NCC_MIN, 0.78)


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
