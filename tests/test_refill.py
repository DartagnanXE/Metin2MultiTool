# -*- coding: utf-8 -*-
"""Pure tests for the auto-refill brain (interface.refill).

Locks the quick-slot key constraint (only 1-4 / F1-F4), the slot->screen maths
(quick-slot + inventory grid, with the window offset), the documented refill
search order (pages I->IV, then row-major), the empty-inventory decision, and
the press-hold-move-release drag sequence. No live window touched.
"""

import os
import types
import unittest

from interface import refill

try:  # numpy/PIL nur fuer die Pixel-/Bild-Tests; der Rest laeuft ohne.
    import numpy as np
    from PIL import Image
    _HAS_DEPS = True
except Exception:  # pragma: no cover
    np = None
    Image = None
    _HAS_DEPS = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _slot(name, row, col):
    return types.SimpleNamespace(state='item', name=name, row=row, col=col)


def _inv(pages):
    return types.SimpleNamespace(pages=pages)


class TestQuickslotKeys(unittest.TestCase):
    def test_only_eight_valid_keys(self):
        for i, k in enumerate(('1', '2', '3', '4', 'f1', 'f2', 'f3', 'f4'), 1):
            self.assertEqual(refill.quickslot_index(k), i)
            self.assertTrue(refill.is_quickslot_key(k))
        self.assertEqual(refill.quickslot_index('F3'), 7)   # case-insensitive

    def test_other_keys_rejected(self):
        for bad in ('5', '9', 'q', 'f5', 'space', '', None):
            self.assertIsNone(refill.quickslot_index(bad))
            self.assertFalse(refill.is_quickslot_key(bad))


class TestScreenMaths(unittest.TestCase):
    def test_quickslot_screen_adds_offset(self):
        base = refill.QUICKSLOT_XY[3]
        self.assertEqual(refill.quickslot_screen(3, 0, 0), base)
        self.assertEqual(refill.quickslot_screen(3, 100, 50),
                         (base[0] + 100, base[1] + 50))

    def test_inventory_slot_screen_uses_grid_and_offset(self):
        # (0,0) centre = origin + half-pitch (+ window offset).
        x0, y0 = refill.inventory_slot_screen(0, 0, 0, 0)
        x1, y1 = refill.inventory_slot_screen(0, 1, 0, 0)   # one column right
        self.assertGreater(x1, x0)
        self.assertEqual(y1, y0)
        # offset is added verbatim.
        xo, yo = refill.inventory_slot_screen(0, 0, 7, 11)
        self.assertEqual((xo - x0, yo - y0), (7, 11))


class TestFindOrder(unittest.TestCase):
    def test_pages_in_order_then_row_major(self):
        inv = _inv({
            'I': [_slot('Carp', 0, 0), _slot('Worm', 2, 3)],
            'II': [_slot('Worm', 0, 0)],
        })
        # Page I scanned before II; within I, row-major -> the (2,3) Worm.
        self.assertEqual(refill.find_first(inv, refill.BAIT_NAMES),
                         ('I', 2, 3))

    def test_returns_none_when_absent(self):
        inv = _inv({'I': [_slot('Carp', 0, 0)]})
        self.assertIsNone(refill.find_first(inv, refill.BAIT_NAMES))

    def test_plan_refill_drag_vs_empty(self):
        inv = _inv({'I': [_slot('Fischpuzzlebox', 1, 2)]})
        self.assertEqual(refill.plan_refill(inv, refill.BOX_NAMES),
                         ('drag', 'I', 1, 2))
        empty = _inv({'I': [_slot('Carp', 0, 0)]})
        self.assertEqual(refill.plan_refill(empty, refill.BOX_NAMES),
                         ('empty',))


class _Recorder:
    def __init__(self):
        self.events = []

    def moveTo(self, x, y):
        self.events.append(('move', x, y))

    def mouseDown(self):
        self.events.append(('down',))

    def mouseUp(self):
        self.events.append(('up',))


class TestDragSequence(unittest.TestCase):
    def test_press_hold_move_release(self):
        rec = _Recorder()
        refill.drag(rec, 10, 20, 110, 70, steps=5, sleep=lambda *_: None)
        ev = rec.events
        self.assertEqual(ev[0], ('move', 10, 20))     # start at source
        self.assertEqual(ev[1], ('down',))            # press
        self.assertEqual(ev[-1], ('up',))             # release last
        moves = [e for e in ev if e[0] == 'move']
        self.assertEqual(moves[-1], ('move', 110, 70))  # ends exactly on target
        self.assertGreaterEqual(len(moves), 6)          # start + 5 steps

    def test_release_even_if_a_move_raises(self):
        class _Boom(_Recorder):
            def moveTo(self, x, y):
                if len(self.events) > 2:
                    raise RuntimeError('boom')
                super().moveTo(x, y)
        rec = _Boom()
        # drag swallows the error but MUST still release the button.
        try:
            refill.drag(rec, 0, 0, 50, 50, steps=4, sleep=lambda *_: None)
        except RuntimeError:
            pass
        self.assertIn(('up',), rec.events)


class _Wincap:
    offset_x = 100
    offset_y = 50

    def get_screenshot(self):
        return None


class _FullRecorder(_Recorder):
    """Recorder that also accepts the tab ``click(x=, y=, button=)`` calls."""
    def click(self, x=None, y=None, button=None):
        self.events.append(('click', x, y))


class TestRefillAbortsOnStop(unittest.TestCase):
    """The heavy refill op must honour a stop predicate at every checkpoint.

    Guarantees the responsiveness contract: a panic-stop (the live loop passes
    the global Stop-Signal as ``should_stop``) aborts the multi-page scan + drag
    quickly with a clear ``'stopped'`` result instead of blocking the loop.
    """

    def test_returns_stopped_immediately_when_already_stopped(self):
        # should_stop truthy from the start -> no scan, no drag, just 'stopped'.
        rec = _Recorder()
        result = refill.refill_from_inventory(
            refill.BAIT_NAMES, (10, 10), inp=rec, wincap=_Wincap(), db=object(),
            sleep=lambda *_: None, should_stop=lambda: True)
        self.assertEqual(result, 'stopped')
        self.assertEqual(rec.events, [])          # nothing happened

    def test_aborts_between_page_switches(self):
        # Drive the real refill with a fake scanner so the page-switch hook runs;
        # flip the stop flag mid-scan -> the op returns 'stopped' after the scan
        # rather than proceeding to the drag.
        from inventory import scanner as scanner_mod
        flag = {'stop': False}

        def fake_scan(*, capture_fn, switch_page_fn, db, calib):
            # The runner calls switch_page_fn per page; we emulate two pages and
            # trip the stop on the first switch.
            switch_page_fn('I')
            flag['stop'] = True
            switch_page_fn('II')
            return types.SimpleNamespace(pages={})

        orig = scanner_mod.scan_inventory
        scanner_mod.scan_inventory = fake_scan
        try:
            rec = _Recorder()
            result = refill.refill_from_inventory(
                refill.BAIT_NAMES, (10, 10), inp=rec, wincap=_Wincap(),
                db=object(), sleep=lambda *_: None,
                should_stop=lambda: flag['stop'])
        finally:
            scanner_mod.scan_inventory = orig
        self.assertEqual(result, 'stopped')

    def test_no_should_stop_is_unchanged_behaviour(self):
        # Without should_stop, a found item drags as before and returns 'dragged'.
        from inventory import scanner as scanner_mod

        def fake_scan(*, capture_fn, switch_page_fn, db, calib):
            slot = types.SimpleNamespace(state='item', name='Worm', row=0, col=0)
            return types.SimpleNamespace(pages={'I': [slot]})

        orig = scanner_mod.scan_inventory
        scanner_mod.scan_inventory = fake_scan
        try:
            rec = _FullRecorder()
            result = refill.refill_from_inventory(
                ('Worm',), (200, 200), inp=rec, wincap=_Wincap(), db=object(),
                sleep=lambda *_: None)
        finally:
            scanner_mod.scan_inventory = orig
        self.assertEqual(result, 'dragged')
        self.assertIn(('down',), rec.events)      # a drag happened
        self.assertIn(('up',), rec.events)

    def test_interrupted_sleep_aborts_before_drag(self):
        # An interruptible sleep that returns False (stop during the nap) right
        # after the scan must abort with 'stopped' before the drag.
        from inventory import scanner as scanner_mod

        def fake_scan(*, capture_fn, switch_page_fn, db, calib):
            slot = types.SimpleNamespace(state='item', name='Worm', row=0, col=0)
            return types.SimpleNamespace(pages={'I': [slot]})

        calls = {'n': 0}

        def stop_sleep(_secs):
            # First post-scan nap (before the drag) reports an interruption.
            calls['n'] += 1
            return False

        orig = scanner_mod.scan_inventory
        scanner_mod.scan_inventory = fake_scan
        try:
            rec = _FullRecorder()
            result = refill.refill_from_inventory(
                ('Worm',), (200, 200), inp=rec, wincap=_Wincap(), db=object(),
                sleep=stop_sleep, should_stop=lambda: False)
        finally:
            scanner_mod.scan_inventory = orig
        self.assertEqual(result, 'stopped')
        self.assertNotIn(('down',), rec.events)   # never started the drag


@unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
class TestQuickslotEmptyDetection(unittest.TestCase):
    """Robuste Leer-Erkennung des Koeder-Quickslots (der Refill-Dauer-Trigger-Bug).

    Kalibriert an live_capture.png (800x601 CLIENT). Der alte ``mean < thr``-Test
    hielt einen vollen, aber DUNKLEN Koeder-Slot (Wurm "47", Patch-Mean ~25) faelsch-
    lich fuer leer -> der Bot legte STAENDIG nach. Die neue Erkennung verlangt
    dunkel UND flach UND ohne helle Icon-Pixel; im Zweifel -> NICHT leer.
    """

    @staticmethod
    def _frame(fill):
        """800x601x3 (H,W,3) uint8 BGR-artiges Vollbild, konstant ``fill``."""
        return np.full((601, 800, 3), fill, dtype=np.uint8)

    @staticmethod
    def _put_icon(frame, slot, value=200, half=7):
        """Malt einen hellen Icon-Block in die Mitte von ``slot`` (1..8)."""
        cx, cy = refill.QUICKSLOT_XY[slot]
        frame[cy - half:cy + half, cx - half:cx + half, :] = value
        return frame

    def test_flat_dark_slot_reads_empty(self):
        # Ein gleichmaessig dunkler (leerer) Slot -> EMPTY fuer alle 8 Slots.
        frame = self._frame(9)
        for slot in range(1, 9):
            self.assertTrue(refill.quickslot_is_empty(frame, slot),
                            'flat-dark slot %d should read empty' % slot)

    def test_bright_icon_slot_reads_occupied(self):
        # Heller Icon-Block in genau einem Slot -> NUR der ist belegt.
        frame = self._put_icon(self._frame(9), 2)
        self.assertFalse(refill.quickslot_is_empty(frame, 2))
        # Nachbarn bleiben leer (kein Uebersprechen).
        self.assertTrue(refill.quickslot_is_empty(frame, 1))
        self.assertTrue(refill.quickslot_is_empty(frame, 3))

    def test_dark_but_textured_icon_reads_occupied(self):
        # Schluesselfall: ein DUNKLES Icon mit ein paar HELLEN Pixeln (wie der
        # Wurm + weisse "47") ist NICHT flach -> belegt, obwohl der Mittelwert
        # niedrig ist. Das ist genau der False-Positive des alten Tests.
        frame = self._frame(9)
        cx, cy = refill.QUICKSLOT_XY[2]
        # Wenige sehr helle Pixel (Stack-Ziffern), Rest dunkel -> niedriger Mean,
        # aber hohe Streuung + helle Icon-Pixel.
        frame[cy:cy + 4, cx - 3:cx + 3, :] = 220
        self.assertFalse(refill.quickslot_is_empty(frame, 2),
                         'a dark icon with bright stack digits must read occupied')

    def test_none_and_bad_input_assume_occupied(self):
        # Kein Bild / Muell -> NIE leer (im Zweifel nicht nachlegen). Wirft nie.
        self.assertFalse(refill.quickslot_is_empty(None, 2))
        self.assertFalse(refill.quickslot_is_empty(np.zeros((5,), np.uint8), 2))
        self.assertFalse(refill.quickslot_is_empty(np.zeros((10, 10), np.uint8), 2))
        # Bild kleiner als die Slot-Koordinate -> degenerierter Patch -> nicht leer.
        self.assertFalse(refill.quickslot_is_empty(self._frame(9)[:50, :50], 8))

    def test_uniform_bright_frame_is_not_empty(self):
        # Ein komplett helles Bild ist NICHT dunkel -> nie leer (kein Refill).
        frame = self._frame(200)
        for slot in range(1, 9):
            self.assertFalse(refill.quickslot_is_empty(frame, slot))

    def test_live_capture_worm_slot_is_occupied(self):
        # Der entscheidende Real-Beleg: live_capture.png (800x601) hat den Wurm
        # "47" in Slot 2 und leere Slots 3..8. Frueher las Slot 2 faelschlich leer.
        path = os.path.join(_ROOT, 'live_capture.png')
        if not os.path.isfile(path):
            self.skipTest('live_capture.png fehlt')
        rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8)
        if rgb.shape[:2] != (601, 800):
            self.skipTest('live_capture.png ist nicht 800x601')
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])  # wie WindowCapture liefert
        # Slot 2 traegt den Koeder -> MUSS belegt sein (kein Refill).
        self.assertFalse(refill.quickslot_is_empty(bgr, 2),
                         'worm-bait slot 2 must NOT read empty (was the bug)')
        # Slot 1 (Werkzeug-Icon) ebenfalls belegt.
        self.assertFalse(refill.quickslot_is_empty(bgr, 1))
        # Die unbenutzten Slots 3..8 sind dunkel/leer.
        for slot in range(3, 9):
            self.assertTrue(refill.quickslot_is_empty(bgr, slot),
                            'unused slot %d should read empty' % slot)


if __name__ == '__main__':
    unittest.main()
