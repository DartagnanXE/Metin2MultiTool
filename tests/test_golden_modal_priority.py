# -*- coding: utf-8 -*-
"""Der Goldene Thunfisch hat Vorrang -- seine Dialoge muessen IMMER weggeklickt
werden (User-Report 2026-08-17).

Der Tester schickte zwei Bilder: das Optionsfenster (Freilassen / Aufschneiden /
Als Koeder benutzen) und die Meldung danach, die noch mit OK bestaetigt werden
muss. Letztere blieb stehen.

Die Erkennung war NICHT die Ursache -- sie trifft den Knopf auf allen drei
Referenz-Meldungen sicher (siehe ``TestErkennungAufDenEchtenBildern``). Die
Ursache lag in der REIHENFOLGE innerhalb eines Frames: Die Angel-Whitelist stand
vor dem Golden-Block und steigt bei einem Abbruch mit ``return`` aus dem Frame
aus. Stand in genau diesem Frame ein Dialog, wurde kein Klick gesendet. Und
Abbrueche sind haeufig -- jede Niete bricht ab (im Live-Log des Testers 56 % der
Zyklen).

Diese Tests pinnen beides: dass die Erkennung auf den ECHTEN Bildern greift, und
dass der Golden-Block laeuft, egal was die Whitelist entscheidet.
"""

import os
import unittest
from unittest import mock

import numpy as np

import fishingbot

try:
    from PIL import Image
except Exception:                       # pragma: no cover
    Image = None

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Die Referenz-Screenshots liegen in FischOCR/ -- der Ordner ist bewusst NICHT
# im Repo (.gitignore, mehrere hundert KB je Bild). Ohne sie werden die
# bildgestuetzten Tests uebersprungen statt zu scheitern; dasselbe Muster nutzt
# test_golden_confirm.py.
_SHOTS = ('GoldenerThunfischAuswahlbestätigen.png',
          'GoldenThunfischBuffBestaetigen.png',
          'GoldenerThunfischEntwischtBestaetigen.png',
          'GoldenerThunfisch3Optionen.png',
          'GoldenerThunfisch3Optionen2.png')


def _shots_present():
    return Image is not None and all(
        os.path.isfile(os.path.join(_REPO_ROOT, 'FischOCR', n))
        for n in _SHOTS)


def _client_bgr(name):
    """Referenz-Shot als BGR-Client-Array (Vollfenster -> Rand/Titel weg)."""
    img = np.asarray(Image.open(os.path.join(_REPO_ROOT, 'FischOCR',
                                             name)).convert('RGB'))
    if img.shape[0] > 615:
        img = img[31:, 1:]
    return img[:, :, ::-1].copy()


class _Clock:
    def __init__(self, t=1000.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += float(dt)


class _Cap:
    offset_x = 10
    offset_y = 20

    def __init__(self, shot):
        self._shot = shot

    def get_screenshot(self):
        return self._shot


class _Hsv:
    def apply_hsv_filter(self, _img):
        h = fishingbot.FishingBot.FISH_WINDOW_SIZE[1]
        w = fishingbot.FishingBot.FISH_WINDOW_SIZE[0]
        return np.zeros((h, w, 3), dtype=np.uint8)


def _make_bot(clock, shot=None):
    b = fishingbot.FishingBot.__new__(fishingbot.FishingBot)
    if shot is None:
        shot = np.zeros((601, 800, 3), dtype=np.uint8)
    b.wincap = _Cap(shot)
    b.hsv_filter = _Hsv()
    b.loop_time = clock() - 0.001
    b.state = 3
    b.timer_action = clock()
    b.timer_mouse = clock() - 1.0
    b.initial_time = clock()
    b.end_time_enable = False
    b.end_time = 10 ** 9
    b.golden_tuna_action = 3
    b._bite_seen_this_cycle = False
    b.mount_enabled = False
    b.FISH_RANGE = 1000
    b._golden_confirm_until = 0.0
    b._golden_confirm_hard = 0.0
    b._last_confirm_click = 0.0
    b._golden_suppress_until = 0.0
    b._golden_confirm_clicks = 0
    b._golden_last_scan = 0.0
    return b


@unittest.skipUnless(_shots_present(), 'Referenz-Screenshots fehlen')
class TestErkennungAufDenEchtenBildern(unittest.TestCase):
    """Die Bilderkennung auf den ECHTEN Referenzen -- inklusive der neuen
    Meldung aus dem Report ("... der goldene Thunfisch entwischt ...").

    Gemessen 2026-08-17: die drei Bestaetigungs-Meldungen liegen bei 0,80 /
    0,81 / 1,00, die staerkste Verwechslung (Optionsfenster, offenes Inventar,
    normale Angel-Szenen) bei 0,57. Die Schwelle 0,70 sitzt in der Luecke --
    dieser Test haelt sie dort fest.
    """

    def test_alle_drei_meldungen_werden_erkannt(self):
        import fishing_detect as fd
        for name in ('GoldenerThunfischAuswahlbestätigen.png',
                     'GoldenThunfischBuffBestaetigen.png',
                     'GoldenerThunfischEntwischtBestaetigen.png'):
            with self.subTest(shot=name):
                found, score, point = fd.golden_confirm_find(_client_bgr(name))
                self.assertTrue(found, '%s wurde nicht erkannt' % name)
                self.assertGreaterEqual(score, 0.75)
                self.assertIsNotNone(point)

    def test_klickpunkt_sitzt_auf_dem_knopf(self):
        """Der Dialog WANDERT (die Hoehe haengt am Meldungstext) -- geklickt
        wird der Fund, nie eine Konstante. Hier gemessen: y=250 / 202 / 266."""
        import fishing_detect as fd
        erwartet = {
            'GoldenerThunfischAuswahlbestätigen.png': (403, 250),
            'GoldenThunfischBuffBestaetigen.png': (403, 202),
            'GoldenerThunfischEntwischtBestaetigen.png': (403, 266),
        }
        for name, (ex, ey) in erwartet.items():
            with self.subTest(shot=name):
                _f, _s, point = fd.golden_confirm_find(_client_bgr(name))
                self.assertLessEqual(abs(point[0] - ex), 3)
                self.assertLessEqual(abs(point[1] - ey), 3)

    def test_optionsfenster_ist_kein_bestaetigungsdialog(self):
        """Beide Fenster haben dieselbe graue Knopfleiste -- nur der OK-Text
        unterscheidet sie. Ein Fehltreffer hier wuerde mitten ins
        Optionsfenster klicken."""
        import fishing_detect as fd
        for name in ('GoldenerThunfisch3Optionen.png',
                     'GoldenerThunfisch3Optionen2.png'):
            with self.subTest(shot=name):
                self.assertFalse(
                    fd.golden_confirm_present(_client_bgr(name)))

    def test_der_options_klick_trifft_die_leiste(self):
        """Die drei Felder liegen im Vollbild bei y=254..278 / 286..310 /
        318..342. Die Klick-Konstanten (Client + 31) muessen darin liegen --
        sonst geht der Klick ins Leere und der Dialog bleibt offen."""
        felder = {1: (254, 278), 2: (286, 310), 3: (318, 342)}
        for feld, (oben, unten) in felder.items():
            with self.subTest(feld=feld):
                y_voll = fishingbot.FishingBot.GOLDEN_TUNA_Y[feld] + 31
                self.assertGreater(y_voll, oben)
                self.assertLess(y_voll, unten)


class _FrameHarness(unittest.TestCase):
    """Treibt den ECHTEN ``runHack`` mit kontrollierter Uhr."""

    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
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
            mock.patch.object(self.bot, 'detect', return_value=(1.0, 1.0, True)),
            mock.patch.object(self.bot, '_deliver_minigame_click',
                              side_effect=lambda x, y: None),
            mock.patch.object(self.bot, '_maybe_refill_bait',
                              return_value=None),
            mock.patch.object(self.bot, '_check_bait_feedback',
                              return_value=None),
            mock.patch.object(self.bot, '_on_cycle_end', return_value=None),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])

    def _tick(self, daily=False, confirm=None, whitelist_abbruch=False):
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=daily), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  return_value=(confirm or (False, 0.0, None))), \
                mock.patch.object(self.bot, '_apply_whitelist',
                                  return_value=whitelist_abbruch):
            return self.bot.runHack()

    def _tags(self):
        return [tag for tag, _x, _y in self.clicks]


class TestDialogSchlaegtWhitelist(_FrameHarness):
    """DER KERN DES FIXES.

    Bis v1.6.10 stand die Whitelist vor dem Golden-Block. Brach sie ab, verliess
    ``runHack`` den Frame -- und der Dialog blieb unangetastet.
    """

    def test_options_klick_kommt_trotz_whitelist_abbruch(self):
        self._tick(daily=True, whitelist_abbruch=True)
        self.assertIn('daily', self._tags(),
                      'Optionsfenster stand, aber es wurde nicht geklickt')

    def test_ok_klick_kommt_trotz_whitelist_abbruch(self):
        self.bot._golden_confirm_until = self.clock() + 10.0
        self.bot._golden_confirm_hard = self.clock() + 40.0
        self._tick(confirm=(True, 0.9, (403, 266)), whitelist_abbruch=True)
        self.assertIn('confirm', self._tags(),
                      'Bestaetigungsdialog stand, aber OK wurde nicht geklickt')

    def test_ok_klick_geht_auf_den_fund_plus_offset(self):
        self.bot._golden_confirm_until = self.clock() + 10.0
        self.bot._golden_confirm_hard = self.clock() + 40.0
        self._tick(confirm=(True, 0.9, (403, 266)))
        self.assertIn(('confirm', 403 + self.bot.wincap.offset_x,
                       266 + self.bot.wincap.offset_y), self.clicks)

    def test_whitelist_pausiert_solange_ein_dialog_steht(self):
        """Ein Abbruch wuerde ESC druecken und sofort neu auswerfen -- in ein
        offenes Fenster hinein, wo der Client die Aktion ohnehin ablehnt."""
        gerufen = []
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=True), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  return_value=(False, 0.0, None)), \
                mock.patch.object(self.bot, '_apply_whitelist',
                                  side_effect=lambda s: gerufen.append(1)):
            self.bot.runHack()
        self.assertEqual(gerufen, [],
                         'Whitelist lief, obwohl ein Dialog stand')

    def test_ohne_dialog_entscheidet_die_whitelist_weiterhin(self):
        """Gegenprobe -- der Vorrang darf die Whitelist nicht dauerhaft
        stilllegen."""
        gerufen = []
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=False), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  return_value=(False, 0.0, None)), \
                mock.patch.object(self.bot, '_apply_whitelist',
                                  side_effect=lambda s: gerufen.append(1)):
            self.bot.runHack()
        self.assertEqual(gerufen, [1])


class TestDialogketteUndDeckel(_FrameHarness):
    """Der Server schickt teils mehrere Meldungen -- alle muessen weg, aber ein
    klebender Dialog darf nicht endlos angeklickt werden."""

    def _fenster_auf(self):
        self.bot._golden_confirm_until = self.clock() + 10.0
        self.bot._golden_confirm_hard = self.clock() + 40.0

    def test_mehrere_dialoge_werden_nacheinander_bestaetigt(self):
        self._fenster_auf()
        for _ in range(3):
            self._tick(confirm=(True, 0.9, (403, 266)))
            self.clock.advance(self.bot.GOLDEN_CONFIRM_CLICK_COOLDOWN_S + 0.1)
        self.assertEqual(self._tags().count('confirm'), 3)

    def test_klick_deckel_stoppt_einen_klebenden_dialog(self):
        self._fenster_auf()
        for _ in range(self.bot.GOLDEN_CONFIRM_MAX_CLICKS + 4):
            self._tick(confirm=(True, 0.9, (403, 266)))
            self.clock.advance(self.bot.GOLDEN_CONFIRM_CLICK_COOLDOWN_S + 0.1)
        self.assertEqual(self._tags().count('confirm'),
                         self.bot.GOLDEN_CONFIRM_MAX_CLICKS)

    def test_neue_episode_setzt_den_deckel_zurueck(self):
        """Sonst waere der Bot nach sechs Klicks fuer immer taub."""
        self.bot._golden_confirm_clicks = self.bot.GOLDEN_CONFIRM_MAX_CLICKS
        self.bot._golden_confirm_hard = self.clock() - 1.0   # Episode vorbei
        self._tick(daily=True)
        self.assertEqual(self.bot._golden_confirm_clicks, 0)

    def test_suche_ist_gedrosselt(self):
        """Die Vollbild-Suche kostet 4,7 ms -- ungedrosselt waere das rund ein
        Viertel der Frame-Zeit, solange das Fenster offen ist."""
        self._fenster_auf()
        suchen = []
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=False), \
                mock.patch.object(self.bot, 'detect_golden_confirm',
                                  side_effect=lambda s: (
                                      suchen.append(1) or (False, 0.0, None))), \
                mock.patch.object(self.bot, '_apply_whitelist',
                                  return_value=False):
            for _ in range(20):
                self.bot.runHack()
                self.clock.advance(0.01)        # 20 Frames in 0,2 s
        self.assertLessEqual(len(suchen), 2,
                             'Suche lief ungedrosselt bei jedem Frame')

    def test_erkennungsfehler_kippt_den_loop_nicht(self):
        """Defensiv: eine Ausnahme in der Erkennung darf das Angeln nicht
        beenden."""
        self._fenster_auf()
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               side_effect=RuntimeError('kaputt')), \
                mock.patch.object(self.bot, '_apply_whitelist',
                                  return_value=False):
            self.bot.runHack()          # darf nicht werfen


class TestSicherheitsnetzImTimeout(_FrameHarness):
    """Fuer den Fall, dass nie ein Such-Fenster aufgezogen wurde.

    Der Bestaetigungs-Dialog wird sonst nur nach einem erkannten Options-Klick
    gesucht. Klickt der Nutzer die Option selbst, oder laeuft das Fenster ab,
    bevor der Server antwortet, bliebe die Meldung fuer immer stehen.
    """

    def test_timeout_oeffnet_ein_suchfenster(self):
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 16.0     # Minispiel-Timeout faellig
        self._tick()
        self.assertGreater(self.bot._golden_confirm_until, self.clock(),
                           'Timeout hat kein Suchfenster geoeffnet')

    def test_ok_wird_danach_gedrueckt(self):
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 16.0
        self._tick()                                     # Netz spannt sich
        self.clock.advance(0.5)
        self._tick(confirm=(True, 0.9, (403, 266)))
        self.assertIn('confirm', self._tags())

    def test_wiederkehrender_timeout_verlaengert_nicht_endlos(self):
        """Sonst haelt ein Bot, der aus anderen Gruenden haengt, die Episode
        ewig offen -- und mit ihr die gedrosselte Suche."""
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 16.0
        self._tick()
        erste_deadline = self.bot._golden_confirm_hard
        self.clock.advance(1.0)
        self.bot.state = 3
        self.bot.timer_action = self.clock() - 16.0
        self._tick()
        self.assertEqual(self.bot._golden_confirm_hard, erste_deadline)


class TestEchtesBildImLoop(_FrameHarness):
    """End-to-End auf dem ECHTEN Screenshot des Testers -- ohne gestubbte
    Erkennung. Das ist der Beweis, dass die Taste gefunden UND gedrueckt wird."""

    @unittest.skipUnless(_shots_present(), 'Referenz-Screenshots fehlen')
    def test_ok_wird_auf_dem_echten_screenshot_gedrueckt(self):
        shot = _client_bgr('GoldenerThunfischEntwischtBestaetigen.png')
        self.bot.wincap = _Cap(shot)
        self.bot._golden_confirm_until = self.clock() + 10.0
        self.bot._golden_confirm_hard = self.clock() + 40.0
        with mock.patch.object(self.bot, '_apply_whitelist', return_value=True):
            self.bot.runHack()
        confirm = [c for c in self.clicks if c[0] == 'confirm']
        self.assertEqual(len(confirm), 1,
                         'OK wurde auf dem echten Bild nicht gedrueckt')
        _tag, x, y = confirm[0]
        self.assertEqual((x, y), (403 + self.bot.wincap.offset_x,
                                  266 + self.bot.wincap.offset_y))


if __name__ == '__main__':
    unittest.main()
