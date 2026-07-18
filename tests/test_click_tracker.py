# -*- coding: utf-8 -*-
"""Tests fuer den ms-genauen Klick-/Move-Tracker (Debug-Diagnose Angelbot).

Zweck des Trackers: JEDER physische Maus-Klick (beide Backends) wird
millisekunden-genau + mit Kontext in die Debug-Logdatei geschrieben, damit ein
"Char laeuft ins Wasser"-Vorfall meldbar wird. WICHTIG (hier mitgeprueft): reines
Logging -- KEIN Klick wird veraendert/unterdrueckt/verschoben.

Kernpunkte:
  * Klick-Event wird mit allen Feldern geloggt (ms-Zeit, button, tag,
    client+screen coord).
  * STRAY-CLICK: LINKS-Klick ohne sauberes Minispiel-Gate erzeugt eine WARN-Zeile.
  * ``tag`` wird durch die Klick-Signatur beider Backends durchgereicht.
  * Der Klick selbst verhaelt sich unveraendert (Recorder-Mock bekommt exakt
    dieselben moveTo/click-Aufrufe wie vorher).
  * OFFSET_STALE (Fenster verschoben) wird erkannt + gedrosselt (GetWindowRect
    nicht bei jedem Klick, nur LINKS + Throttle).
"""

import time
import unittest
from unittest import mock

import debuglog
import click_tracker


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

    def stray_lines(self):
        return [ln for ln in self.lines if 'STRAY-CLICK' in ln]


def _fresh():
    """Isolierte Tracker-Instanz (nicht das Modul-Singleton)."""
    t = click_tracker.ClickTracker()
    t.configure(enabled=True)
    return t


class TestRecordFields(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_click_logged_with_all_fields(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=100, offset_y=50)
        t.record('left', 400, 237, tag='daily')
        txt = self.cap.text
        self.assertIn('KLICK', txt)
        self.assertIn('tag=daily', txt)
        self.assertIn('btn=LINKS', txt)
        self.assertIn('screen=400,237', txt)
        # client = screen - gespeicherter Offset (400-100, 237-50)
        self.assertIn('client=300,187', txt)
        # ms-Zeit (monoton) + Delta-t Screenshot->Klick vorhanden
        self.assertIn('dt_ms=', txt)
        self.assertIn('t_ms=', txt)

    def test_right_click_is_never_stray(self):
        t = _fresh()
        t.mark_tick(state=1, offset_x=0, offset_y=0)
        t.record('right', 300, 300, tag='focus')
        self.assertEqual(self.cap.stray_lines(), [])
        self.assertIn('btn=RECHTS', self.cap.text)

    def test_client_coord_unknown_without_offset(self):
        t = _fresh()
        # ohne mark_tick/Offset -> client unbekannt, aber kein Crash + Zeile da.
        t.record('left', 10, 20, tag='minigame')
        self.assertIn('client=?', self.cap.text)


class TestStrayDetection(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_untagged_left_click_is_stray(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=0, offset_y=0)
        t.record('left', 500, 500, tag='other')
        self.assertTrue(self.cap.stray_lines())
        self.assertIn('!!! STRAY-CLICK !!!', self.cap.text)

    def test_clean_minigame_click_is_not_stray(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=0, offset_y=0, detected_end=True)
        t.record('left', 200, 200, tag='minigame')
        self.assertEqual(self.cap.stray_lines(), [])

    def test_minigame_click_without_detected_end_is_stray(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=0, offset_y=0, detected_end=False)
        t.record('left', 200, 200, tag='minigame')
        self.assertTrue(self.cap.stray_lines())
        self.assertIn('Gate', self.cap.text)

    def test_minigame_click_in_wrong_state_is_stray(self):
        t = _fresh()
        t.mark_tick(state=0, offset_x=0, offset_y=0, detected_end=True)
        t.record('left', 200, 200, tag='minigame')
        self.assertTrue(self.cap.stray_lines())

    def test_late_minigame_dispatch_is_stray(self):
        t = _fresh()
        t.configure(stray_dt_ms=10.0)
        t.mark_tick(state=3, offset_x=0, offset_y=0, detected_end=True)
        # Tick-Referenz kuenstlich weit in die Vergangenheit -> grosses Delta-t.
        t._tick_perf_ms -= 1000.0
        t.record('left', 200, 200, tag='minigame')
        self.assertTrue(self.cap.stray_lines())
        self.assertIn('Timing-Miss', self.cap.text)

    def test_gated_ui_tags_not_stray(self):
        t = _fresh()
        t.mark_tick(state=2, offset_x=0, offset_y=0)
        t.record('left', 399, 269, tag='daily')
        t.record('left', 399, 301, tag='confirm')
        self.assertEqual(self.cap.stray_lines(), [])

    def test_set_gate_updates_detected_end(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=0, offset_y=0, detected_end=None)
        t.set_gate(True)
        t.record('left', 200, 200, tag='minigame')
        self.assertEqual(self.cap.stray_lines(), [])


class TestOffsetStale(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_moved_window_flags_offset_stale_and_stray(self):
        t = _fresh()
        # gespeicherter Offset (108,130); Fenster hat sich bewegt -> live-Rect
        # ergibt (20+8, 20+30)=(28,50) != gespeichert -> stale.
        t.mark_tick(state=3, offset_x=108, offset_y=130, detected_end=True)
        t.configure(get_rect=lambda: (20, 20, 820, 620), cropped=(8, 30),
                    stale_interval_ms=0.0)
        t.record('left', 200, 200, tag='minigame')
        self.assertIn('OFFSET_STALE', self.cap.text)
        # trotz sauberem Minispiel-Gate: verschobenes Fenster -> STRAY.
        self.assertTrue(self.cap.stray_lines())

    def test_unmoved_window_no_stale(self):
        t = _fresh()
        # live-Rect (100,100) + cropped(8,30) = (108,130) == gespeicherter Offset.
        t.mark_tick(state=3, offset_x=108, offset_y=130, detected_end=True)
        t.configure(get_rect=lambda: (100, 100, 900, 700), cropped=(8, 30),
                    stale_interval_ms=0.0)
        t.record('left', 200, 200, tag='minigame')
        self.assertNotIn('OFFSET_STALE', self.cap.text)
        self.assertEqual(self.cap.stray_lines(), [])

    def test_getwindowrect_only_left_and_throttled(self):
        calls = {'n': 0}

        def rect():
            calls['n'] += 1
            return (0, 0, 800, 600)

        t = _fresh()
        t.mark_tick(state=3, offset_x=8, offset_y=30, detected_end=True)
        # grosser Throttle -> innerhalb des Fensters nur EIN echter Rect-Call.
        t.configure(get_rect=rect, cropped=(8, 30), stale_interval_ms=100000.0)
        t.record('right', 1, 1, tag='focus')     # Rechtsklick: KEIN Rect-Call
        self.assertEqual(calls['n'], 0)
        t.record('left', 2, 2, tag='minigame')   # erster Links-Klick misst
        t.record('left', 3, 3, tag='minigame')   # zweiter: aus Cache (Throttle)
        self.assertEqual(calls['n'], 1)

    def test_bad_get_rect_never_raises(self):
        def boom():
            raise RuntimeError('kein Fenster')

        t = _fresh()
        t.mark_tick(state=3, offset_x=0, offset_y=0, detected_end=True)
        t.configure(get_rect=boom, cropped=(8, 30), stale_interval_ms=0.0)
        # darf nicht werfen; Zeile wird trotzdem geschrieben (nicht als stale).
        t.record('left', 5, 5, tag='minigame')
        self.assertIn('KLICK', self.cap.text)
        self.assertNotIn('OFFSET_STALE', self.cap.text)


class TestEnableSwitch(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_disabled_emits_nothing(self):
        t = _fresh()
        t.set_enabled(False)
        t.record('left', 1, 1, tag='other')
        self.assertEqual(self.cap.lines, [])

    def test_env_off_disables_by_default(self):
        with mock.patch.dict('os.environ', {'M2FB_CLICK_TRACKER': '0'}):
            t = click_tracker.ClickTracker()
        t.record('left', 1, 1, tag='other')
        self.assertEqual(self.cap.lines, [])


class TestDirectBackendTagPassthrough(unittest.TestCase):
    """fishingbot._DirectBackend.click: ``tag`` additiv; der physische
    pydirectinput-Klick bleibt FORM-EXAKT (bestehende Assertions unveraendert)."""

    def test_left_click_form_unchanged_with_tag(self):
        import fishingbot
        fake = mock.Mock()
        with mock.patch.object(fishingbot, 'pydirectinput', fake):
            fishingbot._DirectBackend().click(10, 20, tag='minigame')
        # Genau EIN Klick, Form (x=,y=) OHNE button-kwarg (Default 'left').
        fake.click.assert_called_once_with(x=10, y=20)

    def test_right_click_form_unchanged_with_tag(self):
        import fishingbot
        fake = mock.Mock()
        with mock.patch.object(fishingbot, 'pydirectinput', fake):
            fishingbot._DirectBackend().click(10, 20, button='right', tag='focus')
        fake.click.assert_called_once_with(x=10, y=20, button='right')

    def test_default_tag_is_other_and_call_unchanged(self):
        import fishingbot
        fake = mock.Mock()
        with mock.patch.object(fishingbot, 'pydirectinput', fake):
            fishingbot._DirectBackend().click(5, 6)      # ohne tag
        fake.click.assert_called_once_with(x=5, y=6)


class _FakeInput:
    """Protokolliert Input-Aufrufe (wie in test_cursor_client)."""

    def __init__(self):
        self.log = []
        self.PAUSE = None

    def moveTo(self, x, y):
        self.log.append(('moveTo', x, y))

    def click(self, button='left'):
        self.log.append(('click', button))

    def mouseUp(self, button='left'):
        self.log.append(('mouseUp', button))

    def mouseDown(self, button='left'):
        self.log.append(('mouseDown', button))


class TestCursorClientTagPassthrough(unittest.TestCase):
    """CursorClient.click / LeasedInput.click: ``tag`` additiv; die physische
    Burst-Sequenz (moveTo/click) bleibt byte-identisch."""

    def _client(self, inp, needs_activation=False):
        import cursor_client as cc
        return cc.CursorClient(
            idx=0, hwnd=42, to_screen=lambda x, y: (x, y),
            acquire=lambda i, h: None, release=lambda i: None,
            inp=inp, foreground_fn=lambda: 42, activate_fn=lambda h: None,
            stop_check=lambda: False, sleep=lambda s: None,
            needs_activation=needs_activation)

    def test_click_sequence_unchanged_with_tag(self):
        inp = _FakeInput()
        c = self._client(inp)
        c.click(7, 8, tag='minigame')
        # Exakt die Legacy-Sequenz (Finding #1 Neutralisierung + moveTo + click).
        self.assertEqual(inp.log, [
            ('mouseUp', 'left'), ('mouseUp', 'right'),
            ('moveTo', 7, 8), ('click', 'left'),
            ('mouseUp', 'left'), ('mouseUp', 'right')])

    def test_leased_input_forwards_tag_to_tracker(self):
        import cursor_client as cc
        cap = _Capture()
        self.addCleanup(cap.close)
        inp = _FakeInput()
        be = cc.LeasedInput(self._client(inp))
        be.click(300, 400, button='left', tag='minigame')
        # tag hat den Tracker erreicht (ueber das Modul-Singleton).
        self.assertIn('tag=minigame', cap.text)
        # und die physische Sequenz ist unveraendert vorhanden.
        self.assertIn(('moveTo', 300, 400), inp.log)
        self.assertIn(('click', 'left'), inp.log)


class TestRefillTagClassification(unittest.TestCase):
    """Koeder-/Inventar-Refill-Klicks (``tag='refill'``) sind gegatete UI-Klicks
    (bewegen den Char nicht) -> NIE STRAY. Ein echter ungegateter Welt-Linksklick
    (``tag='other'``) bleibt STRAY."""

    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_refill_left_click_is_not_stray(self):
        t = _fresh()
        t.mark_tick(state=0, offset_x=0, offset_y=0)
        t.record('left', 110, 70, tag='refill')
        self.assertEqual(self.cap.stray_lines(), [])
        self.assertIn('tag=refill', self.cap.text)

    def test_ungated_world_left_click_still_stray(self):
        t = _fresh()
        t.mark_tick(state=0, offset_x=0, offset_y=0)
        t.record('left', 400, 300, tag='other')
        self.assertTrue(self.cap.stray_lines())


class TestSuppressedLogging(unittest.TestCase):
    """``record_suppressed`` schreibt eine greppbare ``SUPPRESSED: <grund>``-Zeile
    (der ANGEL-FIX hat einen Welt-Klick verhindert). Reines Logging, wirft nie."""

    def setUp(self):
        self.cap = _Capture()
        self.addCleanup(self.cap.close)

    def test_suppressed_line_emitted_with_reason(self):
        t = _fresh()
        t.mark_tick(state=3, offset_x=100, offset_y=50, detected_end=True)
        t.record_suppressed(400, 237, tag='minigame', reason='minigame-weg')
        txt = self.cap.text
        self.assertIn('SUPPRESSED: minigame-weg', txt)
        self.assertIn('tag=minigame', txt)
        self.assertIn('screen=400,237', txt)
        self.assertIn('client=300,187', txt)   # screen - gespeicherter Offset

    def test_disabled_emits_nothing(self):
        t = _fresh()
        t.set_enabled(False)
        t.record_suppressed(1, 1)
        self.assertEqual(self.cap.lines, [])

    def test_module_shim_is_safe(self):
        # Modul-Ebene: record_suppressed wirft nie (auch ohne configure/mark_tick).
        click_tracker.record_suppressed(5, 6, tag='minigame', reason='minigame-weg')


class TestNeverRaises(unittest.TestCase):
    def test_record_without_configure_is_safe(self):
        t = click_tracker.ClickTracker()
        # kein configure/mark_tick -> darf nicht werfen.
        t.record('left', 1, 2)
        t.record('right', 3, 4, tag='focus')

    def test_module_shims_are_safe(self):
        # Modul-Ebene: record_click/mark_tick/set_gate/configure werfen nie.
        click_tracker.configure(enabled=True)
        click_tracker.mark_tick(state=3, offset_x=0, offset_y=0)
        click_tracker.set_gate(True)
        click_tracker.record_click('left', 1, 1, tag='minigame')


if __name__ == '__main__':
    unittest.main()
