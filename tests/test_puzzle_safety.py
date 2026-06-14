"""Headless-Tests fuer die reine Sicherheits-Schicht (puzzle_safety.py).

Keine Bilder, kein numpy-V (die ~12s-Wertiteration wird NICHT angefasst -- die
Funktionen nutzen nur die statischen _FORMS/_PLACE/_occ aus trained_solver).
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import puzzle_safety as ps  # noqa: E402


# Die echten Zentroide aus puzzle.PuzzleBot.PIECE_REF_BGR (hier dupliziert, um
# die GUI-/Bild-Abhaengigkeit von puzzle.py im Headless-Test zu vermeiden).
REFS = {
    4: (37, 65, 250),
    1: (25, 160, 250),
    5: (42, 250, 42),
    3: (250, 250, 25),
    2: (250, 107, 0),
    6: (55, 245, 255),
}


def _empty():
    return [[0] * 6 for _ in range(4)]


class TestCentroidMetrics(unittest.TestCase):
    def test_exact_centroid_zero_distance(self):
        m = ps.centroid_metrics((25, 160, 250), REFS)
        self.assertEqual(m['nearest'], 1)
        self.assertAlmostEqual(m['nearest_dist'], 0.0)
        self.assertGreater(m['margin'], 0)

    def test_nearest_pair_is_1_and_6(self):
        # Dokumentierter Befund: 1<->6 ist das farblich naechste Paar (~90).
        m = ps.centroid_metrics(REFS[1], REFS)
        self.assertEqual(m['nearest'], 1)
        self.assertEqual(m['second'], 6)
        self.assertAlmostEqual(m['second_dist'], 90.28, places=1)

    def test_empty_refs_defensive(self):
        m = ps.centroid_metrics((10, 10, 10), {})
        self.assertIsNone(m['nearest'])
        self.assertEqual(m['dists'], {})


class TestConfidentType(unittest.TestCase):
    def test_clean_reading_accepted(self):
        self.assertEqual(ps.confident_type((25, 160, 250), REFS), 1)

    def test_far_out_of_distribution_rejected(self):
        # Hintergrund-Grau -> kein Kanal nahe einem Zentroid -> None.
        self.assertIsNone(ps.confident_type((31, 34, 36), REFS))

    def test_low_margin_rejected(self):
        # Punkt genau mittig zwischen 1 und 6 -> kleiner Margin -> None.
        mid = tuple((REFS[1][k] + REFS[6][k]) // 2 for k in range(3))
        self.assertIsNone(ps.confident_type(mid, REFS, tol=60, min_margin=30.0))

    def test_small_drift_still_accepted(self):
        # Leichte Drift Richtung eines Kanals, klar bei Typ 1 -> akzeptiert.
        self.assertEqual(ps.confident_type((30, 150, 245), REFS), 1)


class TestFootprint(unittest.TestCase):
    def test_single(self):
        self.assertEqual(ps.footprint(1, (0, 3)), frozenset({(0, 3)}))

    def test_s_piece_matches_log_case(self):
        # Aus dem realen Log: Typ 4 @ (2,2) belegte (2,2),(2,3),(3,3),(3,4).
        self.assertEqual(ps.footprint(4, (2, 2)),
                         frozenset({(2, 2), (2, 3), (3, 3), (3, 4)}))

    def test_out_of_bounds_none(self):
        self.assertIsNone(ps.footprint(2, (3, 0)))  # I-Stein (3 hoch) bei Zeile 3
        self.assertIsNone(ps.footprint(1, (4, 0)))

    def test_unknown_type_none(self):
        self.assertIsNone(ps.footprint(7, (0, 0)))


class TestExpectedBoardAfter(unittest.TestCase):
    def test_places_and_is_immutable(self):
        board = _empty()
        new = ps.expected_board_after(board, 1, (0, 0))
        self.assertEqual(new[0][0], 1)
        self.assertEqual(board[0][0], 0)  # Original unberuehrt

    def test_overlap_returns_none(self):
        board = _empty()
        board[0][0] = 1
        self.assertIsNone(ps.expected_board_after(board, 1, (0, 0)))

    def test_oob_returns_none(self):
        self.assertIsNone(ps.expected_board_after(_empty(), 1, (9, 9)))


class TestVerifyPlacement(unittest.TestCase):
    def test_correct_placement_ok(self):
        prev = _empty()
        actual = ps.expected_board_after(prev, 4, (2, 2))
        r = ps.verify_placement(prev, 4, (2, 2), actual)
        self.assertTrue(r['ok'])
        self.assertEqual(r['severity'], 'ok')

    def test_piece_not_landed_is_critical(self):
        prev = _empty()
        actual = _empty()  # nichts hat sich geaendert -> Stein nicht gelandet
        r = ps.verify_placement(prev, 4, (2, 2), actual)
        self.assertEqual(r['severity'], 'critical')
        self.assertEqual(len(r['missing_footprint']), 4)

    def test_unexpected_extra_cell_is_weak(self):
        prev = _empty()
        actual = ps.expected_board_after(prev, 1, (0, 0))
        actual[3][5] = 1  # fremde Zelle aufgetaucht (Lese-Rauschen?)
        r = ps.verify_placement(prev, 1, (0, 0), actual)
        self.assertEqual(r['severity'], 'weak')
        self.assertIn((3, 5), r['unexpected'])


class TestOnePieceCompletable(unittest.TestCase):
    def test_l_hole_completable_by_type5(self):
        # Genau die Log-Situation: 3 leere Zellen (0,2),(1,2),(1,3) = L-Loch.
        board = [[1, 1, 1, 1, 1, 1],
                 [1, 1, 1, 1, 1, 1],
                 [1, 1, 1, 1, 1, 1],
                 [1, 1, 1, 1, 1, 1]]
        board[0][2] = 0
        board[1][2] = 0
        board[1][3] = 0
        self.assertTrue(ps.one_piece_completable(board))
        self.assertTrue(ps.piece_can_complete(board, 5))   # L fuellt es
        self.assertFalse(ps.piece_can_complete(board, 1))  # Single nicht

    def test_two_isolated_singles_not_completable(self):
        # Nach dem Fehl-Zug: 2 leere Zellen (1,2),(1,3) -> kein Typ fuellt beide.
        board = [[1] * 6 for _ in range(4)]
        board[1][2] = 0
        board[1][3] = 0
        self.assertFalse(ps.one_piece_completable(board))

    def test_full_board_not_completable(self):
        self.assertFalse(ps.one_piece_completable([[1] * 6 for _ in range(4)]))


if __name__ == '__main__':
    unittest.main()
