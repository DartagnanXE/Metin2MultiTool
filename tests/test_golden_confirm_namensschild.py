# -*- coding: utf-8 -*-
"""Der OK-Dialog wird auch dann gedrueckt, wenn ein Namensschild ueber dem
"OK" steht -- und der Angel-Loop faehrt nicht in den offenen Dialog hinein.

User-Log 2026-09-02 (v1.6.12), Auszug:

    13:25:46 | STATE 0 | KLICK ... tag=daily        <- Optionsfenster geklickt
    13:25:46 | STATE 1 | Bait set (key 2)           <- SOFORT weitergeangelt
    13:25:46 | STATE 2 | Cast out (key 1)
    13:25:52 | STATE 0 | No bite ...                <- alle 6 s, Dialog steht
    (keine einzige Zeile "Bestaetigen-OK")

Drei Befunde, alle gemessen:

1. ERKENNUNG. Auf dem Screenshot des Nutzers kommt der OK-Knopf nur auf 0,68
   (Schwelle 0,70): der Gildenname der eigenen Figur steht in Pink quer ueber
   dem "OK". Die Figur steht mittig, der Dialog ist halbtransparent, und der
   Client zeichnet Namensschilder DARUEBER. Die ENDEN der 280 px breiten Leiste
   erreicht kein Schild -- sie tragen 0,937 / 0,787. Dazu die feste Geometrie
   (Rahmen bei x 49..53 / y 149, hellste flache Zeile in schildfreien Spalten)
   als zweiter, template-freier Pfad auf Wunsch des Nutzers ("mach die festen
   Koordinaten besser").
2. ANGEL-AUTOMAT. Nach dem Options-Klick lief die State-Maschine sofort weiter
   -- Koeder und Wurf in den offenen Dialog. Jetzt pausiert sie, solange ein
   Dialog steht (Evidenz + 3 s Grace).
3. SICHERHEITSNETZ. Das Netz im 15-s-Timeout griff nie: steht ein Dialog,
   erscheint kein Minispiel, und der 5-s-Zweig "Kein Biss" feuert zuerst. Das
   Netz haengt jetzt auch dort.

Dazu EINE Diagnosezeile, wenn ein erwarteter Dialog nicht gefunden wurde --
bis v1.6.12 blieb genau dieser Fall im Log unsichtbar.
"""

import os
import unittest
from unittest import mock

import cv2 as cv
import numpy as np

import fishing_detect as fd
import fishingbot

from tests.test_golden_modal_priority import _Clock, _make_bot

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Der Screenshot des Nutzers (Bonus-Meldung, Gildenname ueber dem OK) und die
# Entwischt-Meldung aus demselben Report. Beide liegen -- wie alle Referenzen --
# im gitignorierten FischOCR/; ohne sie werden die Bildtests uebersprungen.
_USER_BONUS = 'GoldenerThunfischBonus_user2.png'
_USER_NASS = 'GoldenerThunfischEntwischtNass_user2.png'
_OPTIONS = 'GoldenerThunfisch3Optionen.png'
_POSITIVE = {
    _USER_BONUS: (403, 250),
    _USER_NASS: (403, 266),
    'GoldenThunfischBuffBestaetigen.png': (403, 202),
    'GoldenerThunfischAuswahlbestätigen.png': (403, 250),
    'GoldenerThunfischEntwischtBestaetigen.png': (403, 266),
}


def _shot(name):
    return os.path.join(_REPO_ROOT, 'FischOCR', name)


def _shots_present():
    return all(os.path.isfile(_shot(n)) for n in list(_POSITIVE) + [_OPTIONS])


def _client_bgr(name):
    """Referenz als BGR-Client-Array. Der Nutzer-Shot ist 801 statt 802 px
    breit -- der Rand wird ueber die Hoehe erkannt, nicht ueber die Breite."""
    raw = cv.imread(_shot(name), cv.IMREAD_UNCHANGED)
    h, w = raw.shape[:2]
    if h == 632 and w >= 801:
        raw = raw[31:632, 1:801]
    return np.ascontiguousarray(raw[:, :, :3])


def _gray(name):
    return cv.cvtColor(_client_bgr(name), cv.COLOR_BGR2GRAY)


def _auf_dem_knopf(point, erwartet, toleranz=6):
    return point is not None and \
        abs(point[0] - erwartet[0]) + abs(point[1] - erwartet[1]) <= toleranz


@unittest.skipUnless(_shots_present(), 'Referenz-Screenshots fehlen')
class TestNamensschildUeberDemOK(unittest.TestCase):
    """Der Fall aus dem Log: Knopf-Template unter der Schwelle, Enden tragen."""

    def test_nutzer_screenshot_wird_erkannt(self):
        found, score, point = fd.golden_confirm_find(_client_bgr(_USER_BONUS))
        self.assertTrue(found, 'der Screenshot des Nutzers wird nicht erkannt')
        self.assertTrue(_auf_dem_knopf(point, _POSITIVE[_USER_BONUS]), point)

    def test_knopf_template_allein_haette_versagt(self):
        """Dokumentiert die Ursache: das OK-Template liegt unter der Schwelle."""
        werte = fd.golden_confirm_scores(_client_bgr(_USER_BONUS))
        self.assertLess(werte['knopf'], fd.GOLDEN_OK_NCC_MIN)
        self.assertGreaterEqual(min(werte['links'], werte['rechts']),
                                fd.GOLDEN_BAR_END_NCC_MIN)

    def test_enden_pfad_findet_alle_dialoge(self):
        for name, erwartet in _POSITIVE.items():
            with self.subTest(shot=name):
                found, score, point, detail = fd.golden_bar_ends_find(_gray(name))
                self.assertTrue(found, detail)
                self.assertTrue(_auf_dem_knopf(point, erwartet), point)

    def test_feste_geometrie_findet_alle_dialoge_allein(self):
        """Der Rueckfall ohne Template traegt fuer sich -- so, wie der Nutzer
        es wollte: faellt die Bilderkennung aus, hilft die feste Lage."""
        for name, erwartet in _POSITIVE.items():
            with self.subTest(shot=name):
                found, _k, point, detail = fd.golden_fixed_geometry_find(
                    _gray(name))
                self.assertTrue(found, detail)
                self.assertLessEqual(abs(point[1] - erwartet[1]), 4, point)
                self.assertEqual(point[0], fd.GOLDEN_BAR_CENTER_X)

    def test_optionsfenster_ist_kein_bestaetigungs_dialog(self):
        """Gleicher Rahmen, gleiche flachen Balken -- aber schwarze Ecke.
        Ein Treffer dort waere ein Klick ZWISCHEN die Optionsfelder."""
        g = _gray(_OPTIONS)
        self.assertFalse(fd.golden_fixed_geometry_find(g)[0])
        self.assertFalse(fd.golden_bar_ends_find(g)[0])
        self.assertFalse(fd.golden_confirm_find(_client_bgr(_OPTIONS))[0])

    def test_rahmen_trennt_dialog_von_szene(self):
        links, oben = fd.golden_panel_frame(_gray(_USER_BONUS))
        self.assertGreater(min(links, oben), fd.GOLDEN_FRAME_MIN)
        links, oben = fd.golden_panel_frame(_gray('thunfisch.png'))
        self.assertLess(max(links, oben), fd.GOLDEN_FRAME_MIN / 3)

    def test_alle_nicht_dialoge_bleiben_negativ(self):
        ordner = os.path.join(_REPO_ROOT, 'FischOCR')
        for datei in sorted(os.listdir(ordner)):
            if not datei.endswith('.png') or datei in _POSITIVE:
                continue
            img = _client_bgr(datei)
            if img.shape[0] < 500:
                continue
            with self.subTest(shot=datei):
                found, score, _pt = fd.golden_confirm_find(img)
                self.assertFalse(found, 'Fehltreffer %.3f' % score)


class TestDefensiv(unittest.TestCase):
    def test_winzige_und_leere_frames(self):
        for frame in (None, np.zeros((40, 40, 3), np.uint8),
                      np.zeros((601, 800, 3), np.uint8)):
            self.assertEqual(fd.golden_confirm_find(frame)[0], False)
        werte = fd.golden_confirm_scores(np.zeros((40, 40, 3), np.uint8))
        self.assertIn('knopf', werte)


class _Loop(unittest.TestCase):
    """Treibt den echten ``runHack`` mit kontrollierter Uhr und Log-Mock."""

    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
        self.bot._golden_daily_seen = 0.0
        self.bot._golden_expect_confirm = False
        self.clicks = []
        self.keys = []
        self.log = mock.Mock()

        fake_input = mock.Mock()
        fake_input.click.side_effect = (
            lambda x, y, button='left', tag='other':
            self.clicks.append((tag, x, y)))
        fake_input.key.side_effect = lambda k, *a, **kw: self.keys.append(k)

        self.minigame = mock.Mock(return_value=True)
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
            mock.patch.object(self.bot, '_fire_on_catch', return_value=None),
            mock.patch.object(self.bot, '_apply_whitelist', return_value=False),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])
        self.bot.bait_key = '2'
        self.bot.cast_key = '1'
        self.bot.bait_time = 0.5
        self.bot.throw_time = 0.5
        self.bot.game_time = 0.5
        self.bot._roll_deadline = lambda base: base

    def _tick(self, daily=False, confirm=None, dt=0.05):
        self.clock.advance(dt)
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=daily), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  return_value=(confirm or (False, 0.0, None))):
            return self.bot.runHack()

    def _logged(self, key_text):
        from i18n import t
        wanted = t(key_text)
        return sum(1 for c in self.log.call_args_list
                   if len(c.args) > 1 and c.args[1] == wanted)


class TestAutomatPausiertBeiDialog(_Loop):
    """Befund 2 aus dem Log: Koeder und Wurf in derselben Sekunde wie der
    Options-Klick. Jetzt: kein Tastendruck, solange der Dialog steht."""

    def test_kein_koeder_und_kein_wurf_waehrend_das_optionsfenster_steht(self):
        self.bot.state = 0
        self.bot.timer_action = self.clock() - 10.0     # Koedern waere faellig
        for _ in range(20):
            self._tick(daily=True)
        self.assertEqual(self.keys, [], 'Tasten in den offenen Dialog gedrueckt')
        self.assertIn('daily', [c[0] for c in self.clicks])

    def test_kein_tastendruck_waehrend_der_ok_dialog_steht(self):
        self.bot.state = 0
        self.bot.timer_action = self.clock() - 10.0
        self._tick(daily=True)
        for _ in range(20):
            self._tick(confirm=(True, 0.9, (403, 250)))
        self.assertEqual(self.keys, [])
        self.assertIn('confirm', [c[0] for c in self.clicks])

    def test_nach_dem_dialog_geht_es_weiter(self):
        """Kein Deadlock: ist der Dialog weg, koedert der Bot nach der Grace."""
        self.bot.state = 0
        self.bot.timer_action = self.clock() - 10.0
        self._tick(daily=True)
        for _ in range(5):
            self._tick(dt=1.0)          # Grace 3 s laeuft ab
        self.assertIn('2', self.keys, 'nach dem Dialog wurde nie gekoedert')


class TestSicherheitsnetzImKeinBissZweig(_Loop):
    """Befund 3: das Netz haengt jetzt an dem Zweig, der wirklich feuert."""

    def test_kein_biss_oeffnet_ein_suchfenster(self):
        self.minigame.return_value = False
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 6.0      # > 5 s, kein Minispiel
        self.bot._bite_seen_this_cycle = False
        self._tick()
        self.assertGreater(self.bot._golden_confirm_until, self.clock(),
                           '"Kein Biss" hat kein Suchfenster geoeffnet')

    def test_ok_wird_danach_gedrueckt_auch_ohne_gesehenes_optionsfenster(self):
        self.minigame.return_value = False
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 6.0
        self.bot._bite_seen_this_cycle = False
        self._tick()                                    # -> "Kein Biss"
        self._tick(confirm=(True, 0.9, (403, 266)), dt=0.5)
        self.assertIn('confirm', [c[0] for c in self.clicks])

    def test_wiederholte_kein_biss_runden_verlaengern_nicht_endlos(self):
        self.minigame.return_value = False
        self.bot._bite_seen_this_cycle = False
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 6.0
        self._tick()
        erstes = self.bot._golden_confirm_until
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 6.0
        self._tick(dt=1.0)
        self.assertEqual(self.bot._golden_confirm_until, erstes)


class TestDiagnosezeile(_Loop):
    """Ein erwarteter, aber nicht gefundener Dialog hinterlaesst GENAU eine
    Zeile mit den Teilwerten -- nicht null (wie bis v1.6.12), nicht viele."""

    def test_genau_eine_zeile_wenn_erwartet_und_nicht_gefunden(self):
        self._tick(daily=True)
        self.assertTrue(self.bot._golden_expect_confirm)
        for _ in range(15):
            self._tick(dt=1.0)          # Fenster (10 s) laeuft ohne Fund ab
        self.assertEqual(self._logged('fishing.golden_confirm_missed'), 1)
        self.assertFalse(self.bot._golden_expect_confirm)

    def test_keine_zeile_wenn_ok_geklickt_wurde(self):
        self._tick(daily=True)
        self._tick(confirm=(True, 0.9, (403, 250)), dt=1.0)
        for _ in range(15):
            self._tick(dt=1.0)
        self.assertEqual(self._logged('fishing.golden_confirm_missed'), 0)

    def test_keine_zeile_fuer_ein_reines_sicherheitsnetz_fenster(self):
        """Das Netz oeffnet nach jedem "Kein Biss" ein Fenster -- ohne
        Erwartung. Dort darf nichts geloggt werden, sonst waere es Spam."""
        self.minigame.return_value = False
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 6.0
        self.bot._bite_seen_this_cycle = False
        self._tick()
        for _ in range(15):
            self.bot.state = 0
            self.bot.timer_action = self.clock()
            self._tick(dt=1.0)
        self.assertEqual(self._logged('fishing.golden_confirm_missed'), 0)


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
