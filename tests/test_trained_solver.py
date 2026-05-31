"""Schnelle, headless Tests fuer den KI-optimiert-Solver (trained_solver.py).

Die exakte V-Tabelle (~12 s) wird hier NICHT berechnet -- stattdessen wird
``trained_solver._V`` mit einer kontrollierten Mock-Tabelle belegt, sodass nur
die choose_placement-LOGIK (gueltige/optimale Lage, Verwerfen-Vertrag,
Immutabilitaet, Guards) geprueft wird. Reine stdlib + numpy.
"""

import copy
import os
import sys
import unittest

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import trained_solver as ts  # noqa: E402


class _Piece:
    def __init__(self, t):
        self.piece_type = t


class TestGeometryHelpers(unittest.TestCase):
    def test_idx_corners(self):
        self.assertEqual(ts._idx(0, 0), 0)
        self.assertEqual(ts._idx(3, 5), 23)

    def test_occ(self):
        board = [[0] * 6 for _ in range(4)]
        board[0][0] = 1
        board[3][5] = 1
        self.assertEqual(ts._occ(board), (1 << 0) | (1 << 23))

    def test_single_has_24_placements(self):
        self.assertEqual(len(ts._PLACE[1]), 24)

    def test_placement_masks_match_form_size_and_in_bounds(self):
        for t in range(1, 7):
            for (x, y, m) in ts._PLACE[t]:
                self.assertEqual(bin(m).count('1'), len(ts._FORMS[t]))
                self.assertEqual(m & ~((1 << 24) - 1), 0)


class TestChoosePlacement(unittest.TestCase):
    def setUp(self):
        # Mock-Wertfunktion: ueberall teuer -> 'verbessern' gezielt steuerbar.
        ts._V = np.full(1 << 24, 100.0, dtype=np.float32)

    def tearDown(self):
        ts._V = None

    def test_invalid_piece_type_returns_none(self):
        board = [[0] * 6 for _ in range(4)]
        for t in (None, 0, 7, 99, -1):
            self.assertIsNone(ts.choose_placement(board, _Piece(t)))

    def test_none_board_returns_none(self):
        self.assertIsNone(ts.choose_placement(None, _Piece(3)))

    def test_no_improvement_burns(self):
        board = [[0] * 6 for _ in range(4)]
        self.assertIsNone(ts.choose_placement(board, _Piece(1)))

    def test_picks_the_improving_placement(self):
        board = [[0] * 6 for _ in range(4)]
        m = 1 << ts._idx(2, 3)  # Single an (2,3)
        ts._V[m] = 1.0
        self.assertEqual(ts.choose_placement(board, _Piece(1)), (2, 3))

    def test_returns_valid_in_bounds_anchor(self):
        board = [[0] * 6 for _ in range(4)]
        x0, y0, m = ts._PLACE[3][7]
        ts._V[m] = 0.5
        xy = ts.choose_placement(board, _Piece(3))
        self.assertEqual(xy, (x0, y0))
        self.assertTrue(0 <= xy[0] <= 3 and 0 <= xy[1] <= 5)

    def test_full_board_returns_none(self):
        board = [[1] * 6 for _ in range(4)]
        for t in range(1, 7):
            self.assertIsNone(ts.choose_placement(board, _Piece(t)))

    def test_respects_occupied_cells(self):
        board = [[0] * 6 for _ in range(4)]
        board[2][3] = 1
        ts._V[1 << ts._idx(2, 3)] = 0.1  # billige, aber belegte Lage
        self.assertIsNone(ts.choose_placement(board, _Piece(1)))

    def test_board_not_mutated(self):
        board = [[(i * 6 + j) % 2 for j in range(6)] for i in range(4)]
        snap = copy.deepcopy(board)
        ts.choose_placement(board, _Piece(3))
        self.assertEqual(board, snap)


if __name__ == '__main__':
    unittest.main(verbosity=2)
