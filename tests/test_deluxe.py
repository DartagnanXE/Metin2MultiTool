# -*- coding: utf-8 -*-
"""Tests fuer den DELUXE-Puzzlestein (deluxe.py): Magenta-Erkennung + 2x3-Greedy.

deluxe.py ist bewusst reine Standardbibliothek -> hier direkt importierbar und
testbar (anders als puzzle.py, das pydirectinput/cv2 voraussetzt). Geprueft wird:

  * is_magenta: das Magenta-Deluxe-Fenster trifft das gemessene (251,28,232)
    und seinen Nahbereich, KOLLIDIERT aber mit KEINER der 6 echten Steinfarben
    (PIECE_REF_BGR) und das echte Magenta faellt in KEINES der 6 engen
    single-Fenster (Drift-/Kollisions-Schutz).
  * _classify_piece (single-Pfad, gespiegelt + reale is_magenta): Magenta ->
    Typ 7, die 6 echten Farben bleiben unveraendert -> 1..6, Schwarz -> None.
  * find_free_2x3: erstes freies top-links 2x3-Loch; voll/keins -> None;
    defensiv gegen kaputte Eingaben.

stdlib-only (unittest). Lauf: python3 -m unittest tests.test_deluxe -v
"""

import copy
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import deluxe  # noqa: E402  (reale Produktionslogik, stdlib-only)


# -- Spiegel der 6 echten Steinfarben (muss PuzzleBot.PIECE_REF_BGR gleichen) --
PIECE_REF_BGR = {
    4: (37, 65, 250),
    1: (25, 160, 250),
    5: (42, 250, 42),
    3: (250, 250, 25),
    2: (250, 107, 0),
    6: (55, 245, 255),
}


def classify_single_with_deluxe(bgr):
    """Spiegelt den 'single'-Zweig von PuzzleDetectMixin._classify_piece INKL.
    des vorangestellten realen Magenta-Checks (deluxe.is_magenta -> Typ 7)."""
    b, g, r = bgr
    if deluxe.is_magenta(b, g, r):
        return deluxe.DELUXE_PIECE_TYPE
    if b > 35 and b < 40 and g > 60 and g < 70 and r > 240 and r < 260:
        return 4
    elif b > 20 and b < 30 and g > 150 and g < 170 and r > 240 and r < 260:
        return 1
    elif b > 35 and b < 50 and g > 240 and g < 260 and r > 35 and r < 50:
        return 5
    elif b > 240 and b < 260 and g > 240 and g < 260 and r > 20 and r < 30:
        return 3
    elif b > 240 and b < 260 and g > 100 and g < 115 and r > -10 and r < 10:
        return 2
    elif b > 50 and b < 60 and g > 235 and g < 255 and r > 250 and r < 260:
        return 6
    return None


class TestIsMagenta(unittest.TestCase):
    def test_measured_magenta_is_recognized(self):
        self.assertTrue(deluxe.is_magenta(*deluxe.DELUXE_REF_BGR))
        self.assertTrue(deluxe.is_magenta(251, 28, 232))

    def test_near_magenta_still_recognized(self):
        # +-15 pro Kanal um das Zentrum darf die Erkennung nicht kippen.
        b0, g0, r0 = deluxe.DELUXE_REF_BGR
        for db in (-15, 0, 15):
            for dg in (-15, 0, 15):
                for dr in (-15, 0, 15):
                    bgr = (min(255, max(0, b0 + db)),
                           min(255, max(0, g0 + dg)),
                           min(255, max(0, r0 + dr)))
                    with self.subTest(bgr=bgr):
                        self.assertTrue(deluxe.is_magenta(*bgr))

    def test_six_real_colors_are_not_magenta(self):
        # KEINE der 6 echten Steinfarben darf ins Magenta-Fenster fallen.
        for ptype, ref in PIECE_REF_BGR.items():
            with self.subTest(ptype=ptype, ref=ref):
                self.assertFalse(deluxe.is_magenta(*ref))

    def test_black_and_grey_are_not_magenta(self):
        for bgr in [(0, 0, 0), (50, 50, 50), (128, 128, 128), (255, 255, 255)]:
            with self.subTest(bgr=bgr):
                self.assertFalse(deluxe.is_magenta(*bgr))

    def test_does_not_throw_on_bad_input(self):
        # Defensiv: nicht-numerische Eingabe -> False statt Crash.
        self.assertFalse(deluxe.is_magenta(None, None, None))


class TestClassifyIntegratesDeluxe(unittest.TestCase):
    def test_magenta_maps_to_type_7(self):
        self.assertEqual(classify_single_with_deluxe((251, 28, 232)), 7)
        self.assertEqual(classify_single_with_deluxe(deluxe.DELUXE_REF_BGR), 7)

    def test_six_real_centroids_still_map_to_their_type(self):
        # Der vorangestellte Magenta-Check darf die 6 echten Farben NICHT stoeren.
        for ptype, ref in PIECE_REF_BGR.items():
            with self.subTest(ptype=ptype):
                self.assertEqual(classify_single_with_deluxe(ref), ptype)

    def test_magenta_misses_all_six_tight_windows(self):
        # Ohne den Magenta-Check faellt (251,28,232) durch alle 6 Fenster (None)
        # -> beweist: der neue Typ 7 nimmt keinem bestehenden etwas weg.
        b, g, r = 251, 28, 232
        hit = None
        if b > 35 and b < 40 and g > 60 and g < 70 and r > 240 and r < 260:
            hit = 4
        elif b > 20 and b < 30 and g > 150 and g < 170 and r > 240 and r < 260:
            hit = 1
        elif b > 35 and b < 50 and g > 240 and g < 260 and r > 35 and r < 50:
            hit = 5
        elif b > 240 and b < 260 and g > 240 and g < 260 and r > 20 and r < 30:
            hit = 3
        elif b > 240 and b < 260 and g > 100 and g < 115 and r > -10 and r < 10:
            hit = 2
        elif b > 50 and b < 60 and g > 235 and g < 255 and r > 250 and r < 260:
            hit = 6
        self.assertIsNone(hit)

    def test_black_is_none(self):
        self.assertIsNone(classify_single_with_deluxe((0, 0, 0)))


class TestFindFree2x3(unittest.TestCase):
    @staticmethod
    def _empty():
        return [[0] * 6 for _ in range(4)]

    def test_empty_board_anchors_top_left(self):
        self.assertEqual(deluxe.find_free_2x3(self._empty()), (0, 0))

    def test_full_board_returns_none(self):
        self.assertIsNone(deluxe.find_free_2x3([[1] * 6 for _ in range(4)]))

    def test_finds_hole_after_left_block_is_filled(self):
        # Linke 2x3-Bloecke belegt -> erster freier Anker rueckt nach rechts.
        board = self._empty()
        for i in range(4):
            for j in range(3):
                board[i][j] = 1
        # Spalten 0..2 voll; das erste freie 2x3 beginnt bei Spalte 3.
        self.assertEqual(deluxe.find_free_2x3(board), (0, 3))

    def test_scans_rows_then_columns(self):
        # Obere zwei Zeilen ganz belegt -> Anker muss in Zeile 2 liegen.
        board = self._empty()
        for j in range(6):
            board[0][j] = 1
            board[1][j] = 1
        self.assertEqual(deluxe.find_free_2x3(board), (2, 0))

    def test_no_2x3_fits_returns_none(self):
        # Streumuster, das KEIN volles 2x3-Rechteck frei laesst: jede zweite
        # Spalte belegt -> jede 3-breite Fensterung enthaelt eine belegte Zelle.
        board = self._empty()
        for i in range(4):
            for j in range(0, 6, 2):
                board[i][j] = 1
        self.assertIsNone(deluxe.find_free_2x3(board))

    def test_anchor_keeps_block_in_bounds(self):
        # Der gelieferte Anker (x,y) muss ein 2x3 im 4x6-Brett zulassen.
        board = self._empty()
        board[0][0] = 1  # top-left blockieren -> Anker muss woanders hin
        anchor = deluxe.find_free_2x3(board)
        self.assertIsNotNone(anchor)
        x, y = anchor
        self.assertTrue(0 <= x <= 2 and 0 <= y <= 3)

    def test_does_not_mutate_board(self):
        board = [[(i + j) % 2 for j in range(6)] for i in range(4)]
        snap = copy.deepcopy(board)
        deluxe.find_free_2x3(board)
        self.assertEqual(board, snap)

    def test_defensive_on_bad_input(self):
        self.assertIsNone(deluxe.find_free_2x3(None))
        self.assertIsNone(deluxe.find_free_2x3([]))
        self.assertIsNone(deluxe.find_free_2x3([[0, 0, 0]]))  # zu klein
        self.assertIsNone(deluxe.find_free_2x3('garbage'))


class TestDeluxeForm(unittest.TestCase):
    def test_form_is_full_2x3(self):
        self.assertEqual(len(deluxe.DELUXE_FORM), 6)
        self.assertEqual(set(deluxe.DELUXE_FORM),
                         {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)})

    def test_type_is_disjoint_from_real_pieces(self):
        self.assertNotIn(deluxe.DELUXE_PIECE_TYPE, (1, 2, 3, 4, 5, 6))


if __name__ == '__main__':  # pragma: no cover
    unittest.main(verbosity=2)
