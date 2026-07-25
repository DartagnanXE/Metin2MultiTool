# -*- coding: utf-8 -*-
"""Tests fuer die ECHO-KLICK-SPERRE (User-Report 2026-07-25 "der Char laeuft vor").

BEFUND, auf dem die Sperre beruht (zwei Live-Logs, 10 vollstaendige Runden):
der LETZTE Klick einer Runde springt im Median nur 4,6 px gegenueber seinem
Vorgaenger, alle uebrigen Klicks 48,6 px (Faktor 10,5); 8/10 Runden enden mit
einem Sprung <= 10 px bei 0,42-0,59 s Abstand, und 0,2-1,2 s spaeter meldet der
Bot "Minigame finished". Der Fisch haengt dort schon am Haken -- die Uhr rendert
waehrend der Fang-Animation weiter (Konfidenz 0,99), also greift der bestehende
Uhr-Re-Check NICHT und der Nachzuegler faellt durchs Overlay in die Welt.

Getestet wird ``_deliver_minigame_click``/``_is_echo_click`` direkt: Zustellung,
Unterdrueckung, Radius-/Zeit-Grenzen, Fail-Safe-Richtung, Runden-Reset und eine
datengetriebene Regression auf den echten Log-Koordinaten.
"""

import math
import unittest
from unittest import mock

import numpy as np

import fishingbot


class _Clock:
    def __init__(self, t=500.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += float(dt)


def _make_bot(clock):
    """Minimaler Bot fuer den Klick-Zustellpfad (kein Fenster, kein Capture)."""
    b = fishingbot.FishingBot.__new__(fishingbot.FishingBot)
    b._last_click_pos = None
    b._last_click_time = 0.0
    b._bite_seen_this_cycle = True
    b._casts_without_bite = 0
    b._best_minigame_conf = 0.99
    return b


class _GuardHarness(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.bot = _make_bot(self.clock)
        self.delivered = []

        fake_input = mock.Mock()
        fake_input.click.side_effect = (
            lambda x, y, button='left', tag='other':
            self.delivered.append((x, y)))

        self._patchers = [
            mock.patch.object(fishingbot, 'time', self.clock),
            mock.patch.object(fishingbot, '_input', fake_input),
            mock.patch.object(fishingbot, 'click_tracker', None),
            # Uhr-Re-Check neutral: er darf hier nie der Grund fuers Blocken sein.
            mock.patch.object(self.bot, '_minigame_recheck_gone',
                              return_value=False),
            mock.patch.dict('os.environ', {}, clear=False),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])
        # Schalter explizit auf Default AN -- keine Abhaengigkeit von der Umgebung.
        import os
        os.environ.pop('M2FB_ECHO_GUARD', None)

    def click(self, x, y, after=0.0):
        self.clock.advance(after)
        return self.bot._deliver_minigame_click(x, y)


class TestEchoSuppression(_GuardHarness):
    def test_first_click_is_delivered(self):
        self.assertTrue(self.click(200, 200))
        self.assertEqual(self.delivered, [(200, 200)])

    def test_echo_on_same_spot_is_suppressed(self):
        self.assertTrue(self.click(200, 200))
        # 2 px weiter, 0,5 s spaeter -- exakt das Log-Muster (12:49 4 und 12:49 5).
        self.assertFalse(self.click(198, 200, after=0.5))
        self.assertEqual(self.delivered, [(200, 200)],
                         'Der Nachzuegler darf NICHT zugestellt werden.')

    def test_distant_click_within_window_is_delivered(self):
        self.assertTrue(self.click(200, 200))
        # Median-Sprung der legitimen Klicks liegt bei ~49 px.
        self.assertTrue(self.click(249, 200, after=0.4))
        self.assertEqual(len(self.delivered), 2)

    def test_same_spot_after_window_is_delivered(self):
        """Ein wirklich ruhender Fisch wird weiter nachgeklickt -- die Sperre
        darf nicht dauerhaft blockieren."""
        self.assertTrue(self.click(200, 200))
        self.assertTrue(self.click(200, 200,
                                   after=fishingbot.FishingBot.FISH_ECHO_WINDOW_S
                                   + 0.01))
        self.assertEqual(len(self.delivered), 2)

    def test_radius_boundary(self):
        r = fishingbot.FishingBot.FISH_ECHO_RADIUS_PX
        self.assertTrue(self.click(200, 200))
        self.assertFalse(self.click(200 + r, 200, after=0.3),
                         'Genau auf dem Radius zaehlt als Echo.')
        self.assertTrue(self.click(200 + r + 1, 200, after=0.3),
                        'Einen Pixel ausserhalb wird zugestellt.')

    def test_suppressed_click_does_not_become_the_new_reference(self):
        """Nur ZUGESTELLTE Klicks setzen den Bezugspunkt -- sonst koennte sich
        die Sperre an ihren eigenen unterdrueckten Klicks entlanghangeln."""
        self.click(200, 200)
        self.click(202, 200, after=0.4)          # unterdrueckt
        self.assertEqual(self.bot._last_click_pos, (200, 200))
        self.assertAlmostEqual(self.bot._last_click_time, 500.0, places=3)


class TestGuardIsFailSafe(_GuardHarness):
    def test_env_switch_off_restores_old_behaviour(self):
        import os
        os.environ['M2FB_ECHO_GUARD'] = '0'
        self.addCleanup(lambda: os.environ.pop('M2FB_ECHO_GUARD', None))
        self.assertTrue(self.click(200, 200))
        self.assertTrue(self.click(200, 200, after=0.3),
                        'Mit ausgeschaltetem Schalter wird wie frueher geklickt.')

    def test_broken_state_never_blocks(self):
        """Im Zweifel klicken: kaputte Werte duerfen einen Fang nie verhindern."""
        self.bot._last_click_pos = ('kaputt', None)
        self.assertFalse(self.bot._is_echo_click(200, 200))

    def test_no_predecessor_never_blocks(self):
        self.bot._last_click_pos = None
        self.assertFalse(self.bot._is_echo_click(200, 200))


class TestRoundReset(_GuardHarness):
    def test_cycle_end_clears_the_reference(self):
        """Der erste Klick der naechsten Runde darf nie am Vorgaenger haengen."""
        self.click(200, 200)
        with mock.patch.object(fishingbot, '_flog'), \
                mock.patch.object(fishingbot, 't', lambda *a, **k: 'x'):
            self.bot._on_cycle_end()
        self.assertIsNone(self.bot._last_click_pos)
        self.assertTrue(self.click(200, 200, after=0.1))


class TestRealLogRegression(_GuardHarness):
    """Datengetrieben: die echten Klickfolgen aus den beiden User-Logs.

    Jede Runde = die geloggten (wall_sekunde, client_x, client_y). Erwartung:
    der TERMINALE Nachzuegler wird unterdrueckt, die legitimen Spruenge nicht.
    """

    # 8 der 10 Runden enden mit einem Sprung <= 10 px; die zwei uebrigen
    # (28,3 px / 29,0 px) sind bewusst NICHT betroffen -- sie liegen klar
    # ausserhalb des Radius und muessen zugestellt werden.
    RUNDEN = {
        '12:18 B': [(31.506, 240, 224), (31.852, 240, 136), (32.654, 229, 149),
                    (33.078, 230, 133), (33.489, 224, 132), (33.909, 183, 184),
                    (34.327, 180, 187)],
        '12:18 C': [(37.249, 211, 224), (38.073, 216, 144), (38.906, 187, 183),
                    (39.408, 182, 196), (40.508, 184, 183), (40.935, 186, 186)],
        '12:18 D': [(46.014, 298, 185), (46.355, 251, 253), (47.200, 203, 235),
                    (48.351, 162, 187), (48.693, 191, 235), (49.981, 206, 166),
                    (50.408, 204, 196), (50.996, 204, 186)],
        '12:49 1': [(12.384, 204, 140), (12.707, 276, 180), (13.743, 262, 162),
                    (14.742, 236, 199), (15.259, 238, 205)],
        '12:49 4': [(41.682, 248, 263), (42.216, 266, 258), (43.531, 214, 197),
                    (43.892, 285, 164), (44.330, 258, 177), (45.326, 286, 158),
                    (45.848, 284, 158)],
        '12:49 5': [(51.209, 246, 120), (51.880, 223, 123), (52.240, 197, 226),
                    (53.126, 250, 216), (53.865, 304, 188), (54.311, 302, 188)],
        '12:49 6': [(57.280, 297, 158), (57.629, 218, 123), (59.163, 215, 131),
                    (59.506, 287, 183), (60.639, 308, 194), (61.229, 303, 194)],
        '12:49 7': [(65.138, 208, 153), (67.267, 193, 138), (67.764, 204, 141),
                    (68.188, 270, 207), (69.374, 283, 228), (69.810, 280, 226)],
    }

    def _replay(self, klicks):
        """Spielt eine Runde ab; gibt die Zustell-Entscheidungen zurueck."""
        self.bot._last_click_pos = None
        self.bot._last_click_time = 0.0
        self.clock.t = klicks[0][0]
        out = []
        for i, (wall, x, y) in enumerate(klicks):
            self.clock.t = wall
            out.append(self.bot._deliver_minigame_click(x, y))
        return out

    def test_terminal_echo_is_suppressed_in_every_affected_round(self):
        betroffen = 0
        for name, klicks in self.RUNDEN.items():
            with self.subTest(runde=name):
                sprung = math.hypot(klicks[-1][1] - klicks[-2][1],
                                    klicks[-1][2] - klicks[-2][2])
                res = self._replay(klicks)
                if sprung <= fishingbot.FishingBot.FISH_ECHO_RADIUS_PX:
                    betroffen += 1
                    self.assertFalse(
                        res[-1],
                        '%s: der End-Echo-Klick (%.1f px) muss unterdrueckt '
                        'werden' % (name, sprung))
        self.assertEqual(betroffen, 8,
                         'Alle 8 gemessenen End-Echos muessen erfasst sein.')

    def test_legitimate_clicks_stay_mostly_untouched(self):
        """Die Sperre darf den Angel-Betrieb nicht abwuergen: nur der Nachzuegler
        (und im Ausnahmefall ein sehr enger Zwischenklick) darf wegfallen."""
        gesamt = weg = 0
        for klicks in self.RUNDEN.values():
            res = self._replay(klicks)
            gesamt += len(res) - 1          # ohne den terminalen Echo-Klick
            weg += sum(1 for r in res[:-1] if r is False)
        self.assertLessEqual(
            weg / float(gesamt), 0.10,
            'Hoechstens 10 %% der NICHT-terminalen Klicks duerfen die Sperre '
            'ausloesen (gemessen: %d von %d).' % (weg, gesamt))


class TestClickDiagnostics(_GuardHarness):
    """Der Debug-Log muss sagen WANN und WARUM geklickt wurde -- sonst laesst
    sich am naechsten User-Log nicht entscheiden, ob die Sperre richtig liegt."""

    def _flog_calls(self):
        return [c for c in self.flog.call_args_list]

    def setUp(self):
        super(TestClickDiagnostics, self).setUp()
        self.flog = mock.MagicMock()
        p = mock.patch.object(fishingbot, '_flog', self.flog)
        p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch.object(fishingbot, 't', lambda *a, **k: 'Fish clicked')
        p2.start()
        self.addCleanup(p2.stop)

    def test_delivered_click_logs_path_and_confidence(self):
        self.bot._last_detect_info = {'grund': 'vorhalt', 'conf': 0.83,
                                      'dist': 41.0, 'velo': 612.0,
                                      'ref_alter': 0.07}
        self.click(200, 200)
        fields = self._flog_calls()[-1].kwargs
        self.assertEqual(fields['grund'], 'vorhalt')
        self.assertEqual(fields['conf'], '0.83')
        self.assertEqual(fields['velo'], '612')
        self.assertEqual(fields['dist'], '41.0')
        self.assertEqual(fields['ref_alter'], '0.07')

    def test_second_click_logs_distance_and_age_of_predecessor(self):
        self.bot._last_detect_info = {'grund': 'ruht', 'conf': 0.91}
        self.click(200, 200)
        self.click(260, 200, after=0.4)
        fields = self._flog_calls()[-1].kwargs
        self.assertEqual(fields['abstand_vorher'], '60.0')
        self.assertEqual(fields['t_vorher'], '0.40')

    def test_suppressed_echo_also_logs_why(self):
        self.bot._last_detect_info = {'grund': 'ruht', 'conf': 0.95}
        self.click(200, 200)
        self.click(202, 200, after=0.5)
        fields = self._flog_calls()[-1].kwargs
        self.assertEqual(fields['grund'], 'ruht')
        self.assertEqual(fields['abstand_vorher'], '2.0')
        self.assertEqual(fields['t_vorher'], '0.50')

    def test_missing_detect_info_never_breaks_the_click(self):
        self.bot._last_detect_info = None
        self.assertTrue(self.click(200, 200))
        self.assertEqual(self._flog_calls()[-1].kwargs['grund'], '?')

    def test_round_summary_counts_paths_and_suppressions(self):
        self.bot._last_detect_info = {'grund': 'ruht'}
        self.click(200, 200)
        self.click(202, 200, after=0.4)          # Echo -> unterdrueckt
        self.click(300, 200, after=0.4)          # legitim
        with mock.patch.object(fishingbot, 't', lambda *a, **k: 'x'):
            self.bot._on_cycle_end()
        bilanz = [c for c in self._flog_calls()
                  if c.args[1] == 'Klick-Bilanz dieser Runde'][-1].kwargs
        self.assertEqual(bilanz['geklickt-ruht'], '2')
        self.assertEqual(bilanz['unterdrueckt-echo'], '1')
        self.assertEqual(self.bot._click_stats, {},
                         'Bilanz wird pro Runde zurueckgesetzt.')


class TestDetectRecordsItsReason(unittest.TestCase):
    """``detect`` muss den gewaehlten Pfad hinterlegen -- ohne sein Verhalten
    (Rueckgabewerte) zu aendern."""

    def _bot(self):
        b = fishingbot.FishingBot.__new__(fishingbot.FishingBot)
        b.FISH_RANGE = 74
        b.FISH_VELO_PREDICT = 30
        needle = mock.MagicMock()
        needle.shape = (10, 10)          # needle_h, needle_w
        b.needle_img = needle
        b.fish_pos_x = b.fish_pos_y = b.fish_last_time = None
        b._last_detect_info = None
        return b

    @staticmethod
    def _img():
        """Echter Crop -- detect() liest ``haystack_img.shape`` direkt."""
        return np.zeros((226, 280, 3), dtype=np.uint8)

    def test_missing_template_is_recorded(self):
        b = self._bot()
        with mock.patch('fishing_detect._match_template_max',
                        return_value=(False, 0.0, (0, 0))):
            self.assertIsNone(b.detect(self._img()))
        self.assertEqual(b._last_detect_info['grund'], 'vorlage-fehlt')

    def test_weak_match_is_recorded_as_no_fish(self):
        b = self._bot()
        with mock.patch('fishing_detect._match_template_max',
                        return_value=(True, 0.3, (0, 0))), \
                mock.patch('fishing_detect.cv'):
            self.assertIsNone(b.detect(self._img()))
        self.assertEqual(b._last_detect_info['grund'], 'kein-fisch')
        self.assertAlmostEqual(b._last_detect_info['conf'], 0.3)

    def test_first_sighting_is_recorded(self):
        b = self._bot()
        needle = mock.MagicMock()
        needle.shape = (10, 10)
        b.needle_img = needle
        with mock.patch('fishing_detect._match_template_max',
                        return_value=(True, 0.9, (50, 50))), \
                mock.patch('fishing_detect.cv'):
            self.assertIsNone(b.detect(self._img()))
        self.assertEqual(b._last_detect_info['grund'], 'erster-fund')
        self.assertIsNotNone(b.fish_last_time)

    def test_resting_target_is_recorded_and_still_returns_the_click(self):
        b = self._bot()
        needle = mock.MagicMock()
        needle.shape = (10, 10)
        b.needle_img = needle
        b.fish_pos_x, b.fish_pos_y = 55.0, 55.0
        b.fish_last_time = 1.0
        with mock.patch('fishing_detect._match_template_max',
                        return_value=(True, 0.95, (50, 50))), \
                mock.patch('fishing_detect.cv'), \
                mock.patch('fishing_detect.time', return_value=2.0):
            res = b.detect(self._img())
        self.assertEqual(res, (55.0, 55.0, True))
        self.assertEqual(b._last_detect_info['grund'], 'ruht')
        self.assertEqual(b._last_detect_info['velo'], 0.0)


if __name__ == '__main__':
    unittest.main()
