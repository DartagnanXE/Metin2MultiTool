# -*- coding: utf-8 -*-
"""Tests fuer die OPPORTUNISTISCHE Deluxe-Nutzung (loest die starre Reservat-
Strategie ab) + den Magenta-Miss-Deckel (gegen Endlosschleife bei falsch-positiver
Box-Zahl-OCR).

Headless: bare ``__new__``-Instanz + Mocks (kein Fenster), wie test_puzzle_glue.
"""

import unittest
from unittest import mock

import deluxe
import puzzle


def _bare(**attrs):
    b = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
    b.state = 0
    b.wincap = type('W', (), {'get_screenshot': lambda self=None: object()})()
    b._awaiting_deluxe = False
    b._deluxe_miss_streak = 0
    b._deluxe_disabled = False
    for k, v in attrs.items():
        setattr(b, k, v)
    return b


class DeluxeCountTest(unittest.TestCase):
    def test_count_returns_raw_int(self):
        b = _bare()
        with mock.patch.object(deluxe, 'read_deluxe_count', return_value=5):
            self.assertEqual(b._deluxe_count(), 5)

    def test_count_zero_on_error(self):
        b = _bare()
        with mock.patch.object(deluxe, 'read_deluxe_count',
                               side_effect=RuntimeError):
            self.assertEqual(b._deluxe_count(), 0)

    def test_available_is_count_ge_1(self):
        b = _bare()
        with mock.patch.object(deluxe, 'read_deluxe_count', return_value=1):
            self.assertTrue(b._read_deluxe_available())
        with mock.patch.object(deluxe, 'read_deluxe_count', return_value=0):
            self.assertFalse(b._read_deluxe_available())


class DeluxeGuardTest(unittest.TestCase):
    def test_not_awaiting_is_noop(self):
        b = _bare(_awaiting_deluxe=False)
        self.assertFalse(b._register_deluxe_result(None))
        self.assertEqual(b._deluxe_miss_streak, 0)
        self.assertFalse(b._deluxe_disabled)

    def test_magenta_resets_streak(self):
        b = _bare(_awaiting_deluxe=True, _deluxe_miss_streak=1)
        result = b._register_deluxe_result(deluxe.DELUXE_PIECE_TYPE)
        self.assertTrue(result)                 # war ein Deluxe-Versuch
        self.assertEqual(b._deluxe_miss_streak, 0)
        self.assertFalse(b._awaiting_deluxe)
        self.assertFalse(b._deluxe_disabled)

    def test_no_magenta_increments_miss(self):
        b = _bare(_awaiting_deluxe=True)
        result = b._register_deluxe_result(None)
        self.assertTrue(result)
        self.assertEqual(b._deluxe_miss_streak, 1)
        self.assertFalse(b._awaiting_deluxe)
        self.assertFalse(b._deluxe_disabled)     # noch unter dem Limit

    def test_disables_after_limit(self):
        b = _bare(_awaiting_deluxe=True,
                  _deluxe_miss_streak=puzzle.DELUXE_MISS_LIMIT - 1)
        b._register_deluxe_result(None)          # erreicht das Limit
        self.assertTrue(b._deluxe_disabled)

    def test_normal_piece_also_counts_as_miss(self):
        # Ein normaler 1-6 nach Deluxe-Open ist KEIN Magenta -> Fehlversuch.
        b = _bare(_awaiting_deluxe=True)
        with mock.patch.object(puzzle.PuzzleBot, '_box_refill_active',
                               return_value=False):
            b._register_deluxe_result(3)
        self.assertEqual(b._deluxe_miss_streak, 1)


class DeluxeReactiveRefillTest(unittest.TestCase):
    """Neue reaktive Regel: leerer Deluxe-Slot -> nachlegen (falls aktiv) statt
    OCR; kein Bot-Stopp; nach Erschoepfung Deluxe abschalten."""

    def test_empty_with_refill_active_refills_and_resets(self):
        b = _bare(_awaiting_deluxe=True, _deluxe_refill_tries=0)
        with mock.patch.object(puzzle.PuzzleBot, '_box_refill_active',
                               return_value=True), \
             mock.patch.object(puzzle.PuzzleBot, '_maybe_refill_deluxe_box',
                               return_value=True) as rf:
            result = b._register_deluxe_result(None)
        self.assertTrue(result)
        rf.assert_called_once()
        self.assertEqual(b._deluxe_refill_tries, 1)
        self.assertEqual(b._deluxe_miss_streak, 0)   # frische Box -> reset
        self.assertFalse(b._deluxe_disabled)

    def test_refill_capped_then_disables(self):
        b = _bare(_awaiting_deluxe=True,
                  _deluxe_refill_tries=puzzle.DELUXE_REFILL_MAX,
                  _deluxe_miss_streak=puzzle.DELUXE_MISS_LIMIT - 1)
        with mock.patch.object(puzzle.PuzzleBot, '_box_refill_active',
                               return_value=True), \
             mock.patch.object(puzzle.PuzzleBot, '_maybe_refill_deluxe_box',
                               return_value=True) as rf:
            b._register_deluxe_result(None)
        rf.assert_not_called()              # Cap erreicht -> kein Nachlegen mehr
        self.assertTrue(b._deluxe_disabled)  # stattdessen abgeschaltet

    def test_refill_returns_false_disables_after_limit(self):
        b = _bare(_awaiting_deluxe=True,
                  _deluxe_miss_streak=puzzle.DELUXE_MISS_LIMIT - 1)
        with mock.patch.object(puzzle.PuzzleBot, '_box_refill_active',
                               return_value=True), \
             mock.patch.object(puzzle.PuzzleBot, '_maybe_refill_deluxe_box',
                               return_value=False):
            b._register_deluxe_result(None)
        self.assertTrue(b._deluxe_disabled)


if __name__ == '__main__':
    unittest.main()
