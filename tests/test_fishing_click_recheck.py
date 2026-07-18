# -*- coding: utf-8 -*-
"""ANGEL-FIX: Re-Check unmittelbar vor dem Minispiel-Fischklick.

Problem (analysiert, hohe Konfidenz): Der Minispiel-Fischklick wird ~0,1-0,3 s
NACH dem ``detected_end``/Uhr-NCC-Gate physisch zugestellt. Endet das Minispiel
genau in diesem Fenster, traefe der Linksklick die Wasserflaeche dahinter -> der
Char laeuft ins Wasser.

Fix: UNMITTELBAR vor dem physischen Klick nochmal auf einem FRISCHEN Screenshot
die Uhr-NCC-Logik (dieselbe Schwelle >0.9 wie ``detect_minigame``) pruefen. KLAR
'Uhr weg' -> Klick UNTERDRUECKEN + ueber den Tracker als ``SUPPRESSED: minigame-
weg`` loggen. FAIL-SAFE: jede Unsicherheit (Schalter aus, kein Screenshot,
Exception, nicht auswertbarer NCC) -> Klick NORMAL ausfuehren ('im Zweifel
klicken'), damit ein legitimer Fang NIE faelschlich verhindert wird.

Getestet (rot->gruen):
  (a) Minispiel VOR dem Klick weg           -> Klick unterdrueckt + geloggt.
  (b) Minispiel noch aktiv                   -> Klick normal ausgefuehrt.
  (c) Schalter M2FB_MINIGAME_RECHECK=0       -> immer klicken (Altverhalten,
                                                KEIN Extra-Screenshot).
  (d) detect/Match unsicher oder Exception   -> Klick ausgefuehrt (fail-safe).
"""

import os
import unittest
from unittest import mock

import numpy as np

import debuglog
import click_tracker
import fishingbot


def _bare_bot():
    """FishingBot OHNE __init__ (kein Capture/Needle-Work) -- wie in
    test_fishingbot_logic._bare_bot."""
    return fishingbot.FishingBot.__new__(fishingbot.FishingBot)


def _frame():
    """Vollbild gross genug fuer den Uhr-Crop (FISH_WINDOW_POSITION + _SIZE)."""
    pos = fishingbot.FishingBot.FISH_WINDOW_POSITION
    size = fishingbot.FishingBot.FISH_WINDOW_SIZE
    h = pos[1] + size[1] + 8
    w = pos[0] + size[0] + 8
    return np.zeros((h, w, 3), np.uint8)


class _Capture:
    """Faengt alle debuglog-Zeilen ueber eine additive Senke ab."""

    def __init__(self):
        self.lines = []
        debuglog.log.add_sink(self._sink)

    def _sink(self, line):
        self.lines.append(line)

    def close(self):
        debuglog.log.remove_sink(self._sink)

    @property
    def text(self):
        return '\n'.join(self.lines)


class TestMinigameRecheckGone(unittest.TestCase):
    """``_minigame_recheck_gone`` -- die Fail-safe-Entscheidungslogik.

    ``_match_template_max`` wird gemockt, damit die ENTSCHEIDUNG (Schwelle,
    ok-Flag, Fail-safe) praezise geprueft wird -- die cv2-Match-Numerik selbst
    ist in test_fishingbot_logic (TestMatchTemplateMax/TestDetectMinigame)
    abgedeckt.
    """

    def _bot(self, screenshot=None, raises=False):
        bot = _bare_bot()
        bot.needle_img_clock = np.zeros((10, 10, 3), np.uint8)
        cap = mock.Mock()
        if raises:
            cap.get_screenshot.side_effect = RuntimeError('kein Fenster')
        else:
            cap.get_screenshot.return_value = screenshot
        bot.wincap = cap
        return bot

    def test_switch_off_never_rechecks_and_clicks(self):
        # (c) M2FB_MINIGAME_RECHECK=0 -> alter Zustand: KEIN frischer Screenshot,
        # immer klicken (Re-Check komplett aus).
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '0'}):
            self.assertFalse(bot._minigame_recheck_gone())
        bot.wincap.get_screenshot.assert_not_called()

    def test_minigame_clearly_gone_suppresses(self):
        # (a) Uhr-Score klar unter der Schwelle -> Minispiel weg -> unterdruecken.
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(True, 0.30, (0, 0))):
            self.assertTrue(bot._minigame_recheck_gone())

    def test_minigame_still_active_clicks(self):
        # (b) Uhr-Score ueber der Schwelle -> Minispiel aktiv -> normal klicken.
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(True, 0.97, (0, 0))):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_threshold_is_same_as_detect_minigame(self):
        # Gleiche/gleich strenge Schwelle wie detect_minigame (>0.9 = 'aktiv').
        # Exakt 0.9 gilt (wie dort) NICHT als 'aktiv' -> weg -> unterdruecken.
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(True, 0.90, (0, 0))):
            self.assertTrue(bot._minigame_recheck_gone())
        # Minimal darueber (0.9001) ist 'aktiv' -> klicken.
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(True, 0.9001, (0, 0))):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_uncertain_match_ok_false_clicks(self):
        # (d) ok=False (Form-/Typ-/Vorlagen-Problem) = UNSICHER -> fail-safe klicken.
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(False, 0.0, (0, 0))):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_no_screenshot_clicks(self):
        # (d) kein frischer Screenshot (None) -> fail-safe klicken.
        bot = self._bot(screenshot=None)
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_capture_exception_clicks(self):
        # (d) get_screenshot wirft -> fail-safe klicken (nie crashen).
        bot = self._bot(raises=True)
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_match_exception_clicks(self):
        # (d) Match/Crop wirft unerwartet -> fail-safe klicken.
        bot = self._bot(screenshot=_frame())
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  side_effect=ValueError('boom')):
            self.assertFalse(bot._minigame_recheck_gone())

    def test_default_switch_is_on(self):
        # Ohne Env-Var: Default AN -> ein frischer Screenshot WIRD geholt.
        bot = self._bot(screenshot=_frame())
        env = dict(os.environ)
        env.pop('M2FB_MINIGAME_RECHECK', None)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(fishingbot, '_match_template_max',
                                  return_value=(True, 0.97, (0, 0))):
            bot._minigame_recheck_gone()
        bot.wincap.get_screenshot.assert_called_once()

    def test_crop_geometry_is_the_clock_window(self):
        # Der Re-Check bewertet GENAU den Uhr-Crop (FISH_WINDOW_SIZE) des frischen
        # Frames -- dieselbe Geometrie wie runHack/detect_end_img.
        bot = self._bot(screenshot=_frame())
        seen = {}

        def _cap(crop, needle):
            seen['shape'] = tuple(crop.shape[:2])
            return (True, 0.97, (0, 0))

        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '1'}), \
                mock.patch.object(fishingbot, '_match_template_max', _cap):
            bot._minigame_recheck_gone()
        sx, sy = bot.FISH_WINDOW_SIZE
        self.assertEqual(seen['shape'], (sy, sx))   # (H, W) = (SIZE_y, SIZE_x)


class TestDeliverMinigameClick(unittest.TestCase):
    """``_deliver_minigame_click`` -- Klick unterdruecken vs. normal klicken."""

    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)
        click_tracker.set_enabled(True)   # Singleton scharf (Default, defensiv)

    def test_suppressed_when_gone_no_click_and_logged(self):
        # (a) Minispiel weg -> KEIN physischer Klick + SUPPRESSED-Logzeile.
        bot = _bare_bot()
        fake_input = mock.Mock()
        with mock.patch.object(fishingbot, '_input', fake_input), \
                mock.patch.object(bot, '_minigame_recheck_gone',
                                  return_value=True):
            clicked = bot._deliver_minigame_click(123, 456)
        self.assertFalse(clicked)
        fake_input.click.assert_not_called()
        self.assertIn('SUPPRESSED', self.cap.text)
        self.assertIn('minigame-weg', self.cap.text)

    def test_clicks_when_active(self):
        # (b) Minispiel aktiv -> normaler Klick (Form unveraendert, tag=minigame).
        bot = _bare_bot()
        fake_input = mock.Mock()
        with mock.patch.object(fishingbot, '_input', fake_input), \
                mock.patch.object(bot, '_minigame_recheck_gone',
                                  return_value=False):
            clicked = bot._deliver_minigame_click(123, 456)
        self.assertTrue(clicked)
        fake_input.click.assert_called_once_with(123, 456, tag='minigame')
        self.assertNotIn('SUPPRESSED', self.cap.text)

    def test_switch_off_always_clicks_byte_identical(self):
        # (c) Schalter=0 -> immer klicken, KEIN Extra-Screenshot, keine
        # Unterdrueckung: byte-identisch zum Altverhalten.
        bot = _bare_bot()
        bot.wincap = mock.Mock()
        bot.needle_img_clock = np.zeros((10, 10, 3), np.uint8)
        fake_input = mock.Mock()
        with mock.patch.dict(os.environ, {'M2FB_MINIGAME_RECHECK': '0'}), \
                mock.patch.object(fishingbot, '_input', fake_input):
            clicked = bot._deliver_minigame_click(10, 20)
        self.assertTrue(clicked)
        fake_input.click.assert_called_once_with(10, 20, tag='minigame')
        bot.wincap.get_screenshot.assert_not_called()
        self.assertNotIn('SUPPRESSED', self.cap.text)


if __name__ == '__main__':
    unittest.main()
