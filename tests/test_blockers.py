"""Regressionstests fuer die zwei vom Code-Review gefundenen Blocker.

Diese Tests sichern die Nachbesserung ab, damit die Fehler nicht zurueckkehren:

  Blocker A (CRITICAL): Das Eroeffnungsbuch (pieces_second.json) muss beim
    LEEREN Startbrett greifen, nicht beim vollen. Die Bedingung in
    puzzle.set_puzzle_state war invertiert. Der testbare Seam ist jetzt
    Tetris.is_opening_position() (leeres Brett -> True).

  Blocker B (HIGH): Der Positions-Selbstcheck (calibration.validate_puzzle_region)
    darf ein LEGITIM leeres Brett NICHT als Fehlposition werten (das stoppte
    den Bot bei jedem Puzzle-Start). Form/Groesse-Fehler muessen aber weiter
    erkannt werden.

stdlib-only (unittest), importiert nur tetris/piece/calibration -- alle ohne
cv2/win32/pydirectinput, also unter WSL/Linux lauffaehig.

Lauf: python3 -m unittest tests.test_blockers -v
"""

import json
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from piece import Piece  # noqa: E402
from tetris import Tetris  # noqa: E402
import calibration  # noqa: E402


def _empty_board():
    return [[0] * 6 for _ in range(4)]


def _full_board():
    return [[1] * 6 for _ in range(4)]


# --- Blocker A -----------------------------------------------------------

class TestOpeningBookActivation(unittest.TestCase):
    """Blocker A: leeres Brett -> Eroeffnungsbuch aktiv, volles Brett -> nicht."""

    def setUp(self):
        with open(os.path.join(_REPO_ROOT, 'pieces_second.json')) as fh:
            self.book = json.load(fh)

    def test_is_opening_position_true_on_empty_board(self):
        t = Tetris()
        t.board = _empty_board()
        self.assertIs(t.is_opening_position(), True)

    def test_is_opening_position_false_on_full_board(self):
        t = Tetris()
        t.board = _full_board()
        self.assertIs(t.is_opening_position(), False)

    def test_is_opening_position_false_on_partial_board(self):
        t = Tetris()
        board = _empty_board()
        board[1][3] = 1  # genau eine Zelle belegt
        t.board = board
        self.assertIs(t.is_opening_position(), False)

    def test_book_consulted_when_first_is_zero(self):
        # first=0 == 'leeres Startbrett' (so setzt es is_opening_position jetzt).
        # find_first muss dann das Buch konsultieren -> nie der normale Solver(3).
        decisions = []
        for typ in range(1, 7):
            t = Tetris()
            t.first = 0
            t.second = 0
            decision, _pos = t.find_first(Piece(typ), self.book)
            decisions.append(decision)
        self.assertTrue(all(d in (1, 2) for d in decisions),
                        'first=0 muss das Buch konsultieren, nie decision=3; '
                        'erhalten: {}'.format(decisions))
        self.assertIn(1, decisions,
                      'Eroeffnungsbuch liefert fuer KEINEN Stein eine Position '
                      '-> Buch ist (immer noch) toter Code')

    def test_book_skipped_when_board_not_empty(self):
        # Brett nicht leer -> first/second gesetzt -> normaler Solver (3).
        t = Tetris()
        t.first = 1
        t.second = 1
        decision, pos = t.find_first(Piece(2), self.book)
        self.assertEqual(decision, 3)
        self.assertIsNone(pos)

    def test_find_first_survives_corrupt_book(self):
        # .get()-Haertung: unvollstaendiges Buch -> (2, None) statt KeyError.
        t = Tetris()
        t.first = 0
        decision, pos = t.find_first(Piece(2), {'first': {}})
        self.assertEqual((decision, pos), (2, None))


# --- Blocker B -----------------------------------------------------------

def _make_crop(height, width, bgr):
    """Verschachtelte (H, B, 3)-Liste -> calibration laeuft ohne numpy."""
    return [[list(bgr) for _ in range(width)] for _ in range(height)]


class TestCalibrationEmptyBoardValid(unittest.TestCase):
    """Blocker B: leeres, korrekt positioniertes Brett -> ok=True."""

    def test_empty_dark_board_is_valid(self):
        crop = _make_crop(170, 260, (10, 10, 10))  # dunkelgrau, korrekte Groesse
        res = calibration.validate_puzzle_region(crop)
        self.assertTrue(res.ok,
                        'Leeres Brett darf NICHT als Fehlposition gelten. '
                        'reasons={!r}'.format(res.reasons))
        self.assertEqual(res.reasons, [])

    def test_pure_black_correct_size_is_valid(self):
        crop = _make_crop(170, 260, (0, 0, 0))
        res = calibration.validate_puzzle_region(crop)
        self.assertTrue(res.ok, 'reasons={!r}'.format(res.reasons))

    def test_empty_board_emits_advisory(self):
        # Inhalts-Hinweis vorhanden (fuer Debug-Konsole), aber nicht blockierend.
        crop = _make_crop(170, 260, (10, 10, 10))
        res = calibration.validate_puzzle_region(crop)
        self.assertIn('advisories', res.details)
        self.assertTrue(len(res.details['advisories']) >= 1)

    def test_wrong_size_is_still_rejected(self):
        # Echte Fehlpositionierung/Aufloesung -> Feature wirkt weiterhin.
        crop = _make_crop(100, 100, (40, 80, 120))
        res = calibration.validate_puzzle_region(crop)
        self.assertFalse(res.ok)
        self.assertTrue(res.reasons)

    def test_none_crop_is_rejected(self):
        res = calibration.validate_puzzle_region(None)
        self.assertFalse(res.ok)

    def test_filled_board_is_valid(self):
        # Korrekt positioniertes, belegtes Brett -> ok.
        crop = _make_crop(170, 260, (200, 120, 60))
        res = calibration.validate_puzzle_region(crop)
        self.assertTrue(res.ok, 'reasons={!r}'.format(res.reasons))


if __name__ == '__main__':  # pragma: no cover
    unittest.main(verbosity=2)
