# -*- coding: utf-8 -*-
"""Flow-Tests fuer den Golden-Tuna-Bestaetigungs-Zweig in ``runHack``.

Deckt die Live-Bug-Fixes vom 2026-07-22 ab (User-Report):

  1. FAIL-SAFE AUS: ``pydirectinput.FAILSAFE`` muss nach dem fishingbot-Import
     ``False`` sein -- sonst killt ein transientes (0,0)-Cursor-Lesen die ganze
     Session (``FailSafeException`` -> "Stop due to exception").
  2. MEHRERE Bestaetigungs-Dialoge: der Server schickt teils 2+ Dialoge
     nacheinander. Nach jedem OK-Klick wird das Warte-Fenster VERLAENGERT (bis
     zur harten Deadline), damit auch der 2./3. Dialog abgeraeumt wird.
  3. COOLDOWN: zwei OK-Klicks liegen mind. ``GOLDEN_CONFIRM_CLICK_COOLDOWN_S``
     auseinander (kein 60x/s-Hammer auf denselben Dialog).
  4. WELTKLICK-SPERRE: solange das Bestaetigungs-Fenster aktiv ist, wird KEIN
     Minispiel-/Weltklick gesendet (sonst Klick hinter den Dialog -> Char laeuft
     vor).

Der echte ``runHack`` wird mit kontrollierter Uhr (``fishingbot.time``) und
gestubbten Erkennungs-Methoden getrieben; nur ``_input``/``_deliver_minigame_
click`` werden zum Mitschreiben ersetzt. Headless lauffaehig (numpy + cv2 aus
dem Bundle; kein echter Klick).
"""

import unittest
from unittest import mock

import numpy as np

import fishingbot


class _Clock:
    """Kontrollierbare, waehrend eines Aufrufs KONSTANTE Uhr."""

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


def _make_bot(clock):
    b = fishingbot.FishingBot.__new__(fishingbot.FishingBot)
    b.wincap = _Cap(np.zeros((601, 800, 3), dtype=np.uint8))
    b.hsv_filter = _Hsv()
    b.loop_time = clock() - 0.001          # >0 Abstand -> keine Div/0 im FPS-putText
    b.state = 3
    b.timer_action = clock()               # frisch -> keine State-Transition
    b.timer_mouse = clock() - 1.0          # alt -> Klick-Gate (>0.3) offen
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
    return b


class _RunHackHarness(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock(1000.0)
        self.bot = _make_bot(self.clock)
        self.clicks = []               # (tag, x, y) aller _input.click-Aufrufe
        self.world_clicks = []         # (x, y) der zugestellten Minispiel-Klicks

        fake_input = mock.Mock()
        fake_input.click.side_effect = (
            lambda x, y, button='left', tag='other':
            self.clicks.append((tag, x, y)))

        # Patches, die fuer JEDEN runHack-Aufruf gelten.
        self._patchers = [
            mock.patch.object(fishingbot, 'time', self.clock),
            mock.patch.object(fishingbot, '_input', fake_input),
            mock.patch.object(fishingbot, 'click_tracker', None),
            mock.patch.object(self.bot, '_apply_whitelist', return_value=False),
            mock.patch.object(self.bot, 'detect_minigame', return_value=True),
            mock.patch.object(self.bot, 'detect',
                              return_value=(150.0, 120.0, True)),
            mock.patch.object(
                self.bot, '_deliver_minigame_click',
                side_effect=lambda x, y: self.world_clicks.append((x, y))),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])

    def _run(self, daily=False, confirm=None):
        """Ein runHack-Tick mit gewaehltem daily/confirm-Erkennungsausgang.

        confirm: None -> kein Dialog; sonst (found, score, point).
        """
        with mock.patch.object(self.bot, 'detect_daily_reward',
                               return_value=daily), \
                mock.patch.object(
                    self.bot, 'detect_golden_confirm',
                    return_value=(confirm or (False, 0.0, None))):
            self.bot.runHack()


class TestFailsafeDisabled(unittest.TestCase):
    def test_failsafe_is_off_after_import(self):
        # Der Import von fishingbot MUSS die pydirectinput-Fail-Safe abschalten.
        self.assertIs(fishingbot.pydirectinput.FAILSAFE, False)


class TestDailyOpensWindow(_RunHackHarness):
    def test_daily_click_arms_window_and_hard_deadline(self):
        t0 = self.clock()
        self._run(daily=True)
        # Options-Klick auf Feld 3 in Client-Koordinaten (offset + Konstante).
        self.assertIn(
            ('daily',
             self.bot.wincap.offset_x + self.bot.GOLDEN_TUNA_X,
             self.bot.wincap.offset_y + self.bot.GOLDEN_TUNA_Y[3]),
            self.clicks)
        self.assertAlmostEqual(self.bot._golden_confirm_until,
                               t0 + self.bot.GOLDEN_CONFIRM_WAIT_S)
        self.assertAlmostEqual(self.bot._golden_confirm_hard,
                               t0 + self.bot.GOLDEN_CONFIRM_MAX_S)

    def test_no_world_click_while_daily_and_confirm_window(self):
        # Beim daily-Frame selbst darf kein Weltklick zugestellt werden.
        self._run(daily=True)
        self.assertEqual(self.world_clicks, [])


class TestWorldClickSuppression(_RunHackHarness):
    def test_world_click_fires_without_modal(self):
        # Keine Modal-Evidenz + Sperre abgelaufen -> Minispielklick geht raus.
        self.bot._golden_suppress_until = 0.0
        self._run(daily=False, confirm=None)
        self.assertEqual(len(self.world_clicks), 1)

    def test_world_click_suppressed_by_active_grace(self):
        # Sperre aktiv (juengste Modal-Evidenz) -> KEIN Weltklick (Char-Vorlauf-Fix).
        self.bot._golden_suppress_until = self.clock() + 2.0
        self._run(daily=False, confirm=None)
        self.assertEqual(self.world_clicks, [])

    def test_daily_popup_suppresses_and_arms_grace(self):
        # Popup steht diesen Frame -> Weltklick unterdrueckt + Grace scharf.
        t0 = self.clock()
        self._run(daily=True, confirm=None)
        self.assertEqual(self.world_clicks, [])
        self.assertAlmostEqual(self.bot._golden_suppress_until,
                               t0 + self.bot.GOLDEN_SUPPRESS_GRACE_S)

    def test_confirm_found_arms_grace(self):
        # Dialog diesen Frame erkannt -> Grace aufgefrischt (auch ohne OK-Klick).
        self.bot._golden_confirm_until = self.clock() + 5.0
        self.bot._last_confirm_click = self.clock()   # Cooldown blockt OK-Klick
        t0 = self.clock()
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        self.assertEqual(self.world_clicks, [])       # trotzdem gesperrt
        self.assertAlmostEqual(self.bot._golden_suppress_until,
                               t0 + self.bot.GOLDEN_SUPPRESS_GRACE_S)

    # --- Regression fuer den Red-Team-HIGH (2026-07-22) -------------------
    def test_lingering_click_window_alone_does_not_suppress(self):
        # KERN DES FIXES: ein noch offenes Klick-Fenster (_golden_confirm_until)
        # OHNE aktuelle Modal-Evidenz darf das Angeln NICHT blockieren. Vorher
        # haing die Sperre am Klick-Fenster -> ein spurioeser/klebender daily-
        # False-Positive stallte 10-25s. Jetzt: Sperre abgelaufen -> Klick geht.
        self.bot._golden_confirm_until = self.clock() + 30.0   # weit offen
        self.bot._golden_confirm_hard = self.clock() + 30.0
        self.bot._golden_suppress_until = 0.0                  # keine Evidenz
        self._run(daily=False, confirm=None)
        self.assertEqual(len(self.world_clicks), 1)

    def test_suppression_expires_after_grace_without_evidence(self):
        # Nach einem daily-Frame laeuft die Sperre GRACE Sekunden spaeter aus,
        # wenn keine neue Evidenz kommt -> Angeln nimmt selbst wieder auf
        # (kein Dauer-Stall bei transientem Schwarz-Frame).
        self._run(daily=True, confirm=None)          # armt Grace
        self.assertEqual(self.world_clicks, [])
        self.clock.advance(self.bot.GOLDEN_SUPPRESS_GRACE_S + 0.2)
        self.bot.timer_mouse = self.clock() - 1.0    # Klick-Gate wieder offen
        self._run(daily=False, confirm=None)         # keine Evidenz mehr
        self.assertEqual(len(self.world_clicks), 1)  # Angeln laeuft wieder


class TestConfirmClicksAndExtension(_RunHackHarness):
    def _arm(self):
        self.bot._golden_confirm_until = self.clock() + 5.0
        self.bot._golden_confirm_hard = self.clock() + self.bot.GOLDEN_CONFIRM_MAX_S
        self.bot._last_confirm_click = 0.0

    def test_confirm_clicks_found_button_and_extends_window(self):
        self._arm()
        t0 = self.clock()
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        # OK auf die GEFUNDENE Knopf-Mitte (Client = offset + point).
        self.assertIn(('confirm',
                       self.bot.wincap.offset_x + 100,
                       self.bot.wincap.offset_y + 150), self.clicks)
        self.assertAlmostEqual(self.bot._last_confirm_click, t0)
        # Fenster verlaengert (min aus t0+WAIT und harter Deadline).
        self.assertAlmostEqual(
            self.bot._golden_confirm_until,
            min(t0 + self.bot.GOLDEN_CONFIRM_WAIT_S,
                self.bot._golden_confirm_hard))

    def test_cooldown_blocks_second_immediate_click(self):
        self._arm()
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        n_after_first = len([c for c in self.clicks if c[0] == 'confirm'])
        # Nur 0.2s spaeter (< Cooldown) -> KEIN zweiter Klick.
        self.clock.advance(0.2)
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        n_after_second = len([c for c in self.clicks if c[0] == 'confirm'])
        self.assertEqual(n_after_first, 1)
        self.assertEqual(n_after_second, 1)

    def test_second_dialog_confirmed_after_cooldown(self):
        self._arm()
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        # Nach dem Cooldown kommt der ZWEITE Dialog -> wird ebenfalls geklickt.
        self.clock.advance(self.bot.GOLDEN_CONFIRM_CLICK_COOLDOWN_S + 0.1)
        self._run(daily=False, confirm=(True, 0.95, (120, 160)))
        confirms = [c for c in self.clicks if c[0] == 'confirm']
        self.assertEqual(len(confirms), 2)
        self.assertIn(('confirm',
                       self.bot.wincap.offset_x + 120,
                       self.bot.wincap.offset_y + 160), confirms)

    def test_extension_never_exceeds_hard_deadline(self):
        # Harte Deadline schon fast erreicht -> Verlaengerung wird gekappt.
        self.bot._golden_confirm_until = self.clock() + 2.0
        self.bot._golden_confirm_hard = self.clock() + 0.5
        self.bot._last_confirm_click = 0.0
        self._run(daily=False, confirm=(True, 0.95, (100, 150)))
        self.assertAlmostEqual(self.bot._golden_confirm_until,
                               self.bot._golden_confirm_hard)


if __name__ == '__main__':
    unittest.main()
