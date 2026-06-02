# -*- coding: utf-8 -*-
"""Pure tests for the auto-refill brain (interface.refill).

Locks the quick-slot key constraint (only 1-4 / F1-F4), the slot->screen maths
(quick-slot + inventory grid, with the window offset), the documented refill
search order (pages I->IV, then row-major), the empty-inventory decision, and
the press-hold-move-release drag sequence. No live window touched.
"""

import types
import unittest

from interface import refill


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


if __name__ == '__main__':
    unittest.main()
