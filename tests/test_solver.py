"""Reine Logik-Tests fuer den Puzzle-Solver (tetris.py + piece.py).

Diese Tests sind bewusst stdlib-only ('unittest', KEIN pytest) und importieren
NUR die Module ohne Fremd-Dependencies:
  - piece.py
  - tetris.py
Sie importieren KEIN puzzle.py / hack.py / windowcapture.py / calibration.py,
da diese numpy / cv2 / win32 / pydirectinput voraussetzen, die unter WSL/Linux
nicht verfuegbar sind.

Die Tests pruefen das gewuenschte ZIEL-Verhalten nach dem Solver-Fix
(P0/P1-Vertrag). Sie duerfen vor dem Fix ROT sein:
  - Vor dem Fix hat Piece keine 'is_valid'-Property und Piece(None).form == None
    -> Crash-Kette A (TypeError 'NoneType is not iterable').
  - Vor dem Fix wirft find_first(Piece(None), ...) einen KeyError "'0'"
    -> Crash-Kette B.
  - Vor dem Fix liefert count_zeros() konstant 8 statt der korrekten Zahl.

Lauf (erst in der QA-Phase): python3 -m unittest tests.test_solver -v
"""

import copy
import os
import sys
import unittest

# Produktivmodule liegen im Repo-Root (eine Ebene ueber tests/). Damit
# 'import piece' / 'import tetris' auch beim direkten Aufruf
# 'python3 -m unittest tests.test_solver' aus beliebigem Verzeichnis
# funktioniert, wird das Repo-Root vorne auf sys.path gelegt.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from piece import Piece  # noqa: E402
from tetris import Tetris  # noqa: E402


# Erwartete Form-Daten der gueltigen Steine 1..6 (Vertrag: bit-identisch
# zum bestehenden, funktionierenden Solver - keine Regression).
VALID_FORMS = {
    1: [[1]],
    2: [[1], [1], [1]],
    3: [[1, 1], [1, 1]],
    4: [[1, 1, 0], [0, 1, 1]],
    5: [[1, 0], [1, 1]],
    6: [[1, 1], [0, 1]],
}

# Ungueltige Stein-"Typen": None und alles ausserhalb 1..6.
INVALID_TYPES = [None, 0, 7, 8, 99, -1]


def empty_board():
    """Frisches leeres 4x6-Board (24 Nullen)."""
    return [[0] * 6 for _ in range(4)]


def full_board():
    """Vollstaendig belegtes 4x6-Board (0 Nullen)."""
    return [[1] * 6 for _ in range(4)]


def half_board():
    """Board mit genau 12 Nullen (obere 2 Reihen voll, untere 2 leer)."""
    return [
        [1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ]


class TestPieceValidity(unittest.TestCase):
    """(1) Ungueltige Pieces duerfen nie crashen und sind is_valid == False."""

    def test_invalid_pieces_do_not_raise_on_construction(self):
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    Piece(t)
                except Exception as exc:  # pragma: no cover - soll nie passieren
                    self.fail(f"Piece({t!r}) hat eine Exception geworfen: {exc!r}")

    def test_invalid_pieces_have_is_valid_false(self):
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                self.assertIs(
                    Piece(t).is_valid,
                    False,
                    f"Piece({t!r}).is_valid sollte False sein",
                )

    def test_invalid_piece_form_is_empty_list_not_none(self):
        # Vertrag: ungueltiger Typ -> form == [] (leere Liste), NICHT None.
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                self.assertEqual(
                    Piece(t).form,
                    [],
                    f"Piece({t!r}).form sollte [] sein (nicht None/sonstiges)",
                )

    def test_invalid_piece_form_is_iterable_without_crash(self):
        # Kern der Crash-Kette A: 'for row in piece.form' darf nicht werfen.
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    rows = [row for row in Piece(t).form]
                except TypeError as exc:  # pragma: no cover
                    self.fail(
                        f"'for row in Piece({t!r}).form' warf TypeError "
                        f"(NoneType not iterable?): {exc!r}"
                    )
                self.assertEqual(rows, [])

    def test_invalid_piece_type_normalized_to_zero(self):
        # Vertrag: unbekannter/None-Typ -> piece_type == 0.
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                self.assertEqual(Piece(t).piece_type, 0)

    def test_valid_pieces_are_valid(self):
        for t in range(1, 7):
            with self.subTest(type=t):
                self.assertIs(Piece(t).is_valid, True)

    def test_valid_pieces_forms_unchanged(self):
        # Regression: Formdaten der gueltigen Steine bit-identisch.
        for t, form in VALID_FORMS.items():
            with self.subTest(type=t):
                self.assertEqual(Piece(t).form, form)

    def test_valid_pieces_keep_piece_type(self):
        for t in range(1, 7):
            with self.subTest(type=t):
                self.assertEqual(Piece(t).piece_type, t)

    def test_specific_examples_from_contract(self):
        # Aus dem Blueprint explizit geforderte Einzelfaelle.
        self.assertIs(Piece(None).is_valid, False)
        self.assertIs(Piece(0).is_valid, False)
        self.assertIs(Piece(4).is_valid, True)
        self.assertEqual(Piece(4).form, [[1, 1, 0], [0, 1, 1]])
        self.assertEqual(Piece(None).form, [])


class TestCountZeros(unittest.TestCase):
    """(3) count_zeros() zaehlt die tatsaechlichen 0-Zellen im 4x6-Board."""

    def test_empty_board_has_24_zeros(self):
        t = Tetris()
        t.board = empty_board()
        self.assertEqual(t.count_zeros(), 24)

    def test_fresh_tetris_has_24_zeros(self):
        # Default-Konstruktor liefert ein leeres Board.
        self.assertEqual(Tetris().count_zeros(), 24)

    def test_full_board_has_0_zeros(self):
        t = Tetris()
        t.board = full_board()
        self.assertEqual(t.count_zeros(), 0)

    def test_half_board_has_12_zeros(self):
        t = Tetris()
        t.board = half_board()
        self.assertEqual(t.count_zeros(), 12)

    def test_count_zeros_is_callable_method(self):
        # Vertrag: count_zeros MUSS mit () aufrufbar sein (kein nacktes Attribut).
        t = Tetris()
        self.assertTrue(callable(t.count_zeros))
        self.assertIsInstance(t.count_zeros(), int)


class TestSolverGuardsInvalidPiece(unittest.TestCase):
    """(2) Solver-Methoden mit ungueltigem Piece -> sicher leer/None/False."""

    def setUp(self):
        self.t = Tetris()

    def test_find_possibles_invalid_returns_empty_list(self):
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    res = self.t.find_possibles(Piece(t))
                except Exception as exc:  # pragma: no cover
                    self.fail(
                        f"find_possibles(Piece({t!r})) warf {exc!r} statt []"
                    )
                self.assertEqual(res, [])

    def test_choose_better_invalid_piece_returns_none(self):
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    res = self.t.choose_better(Piece(t), [[0, 0], [0, 1]])
                except Exception as exc:  # pragma: no cover
                    self.fail(
                        f"choose_better(Piece({t!r}), ...) warf {exc!r} statt None"
                    )
                self.assertIsNone(res)

    def test_choose_better_empty_possibilities_returns_none(self):
        # Auch mit gueltigem Stein, aber leerer Moeglichkeitenliste -> None.
        try:
            res = self.t.choose_better(Piece(3), [])
        except Exception as exc:  # pragma: no cover
            self.fail(f"choose_better(Piece(3), []) warf {exc!r} statt None")
        self.assertIsNone(res)

    def test_insert_piece_invalid_returns_false(self):
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    res = self.t.insert_piece(0, 0, Piece(t))
                except Exception as exc:  # pragma: no cover
                    self.fail(
                        f"insert_piece(0,0,Piece({t!r})) warf {exc!r} statt False"
                    )
                self.assertIs(res, False)

    def test_insert_piece_invalid_does_not_mutate_board(self):
        # Guard muss VOR jeder Board-Mutation greifen.
        before = copy.deepcopy(self.t.board)
        self.t.insert_piece(0, 0, Piece(None))
        self.assertEqual(self.t.board, before)

    def test_verify_insert_piece_invalid_returns_false(self):
        board = empty_board()
        for t in INVALID_TYPES:
            with self.subTest(type=t):
                try:
                    res = self.t.verify_insert_piece(0, 0, Piece(t), board)
                except Exception as exc:  # pragma: no cover
                    self.fail(
                        f"verify_insert_piece(0,0,Piece({t!r}),board) warf "
                        f"{exc!r} statt False"
                    )
                self.assertIs(res, False)


class TestFindFirstCrashVector(unittest.TestCase):
    """Crash-Vektor B: find_first(Piece(None), ...) darf keinen KeyError werfen."""

    def _dictdump(self):
        # Minimaler, aber realistischer Eroeffnungsbuch-Aufbau:
        # 'first' enthaelt nur die gueltigen Schluessel '1'..'6'. Der
        # Schluessel '0' existiert NICHT -> der ungepatchte Code wuerde
        # dictdump['first']['0'] -> KeyError "'0'" werfen.
        first = {}
        for t in range(1, 7):
            first[str(t)] = {"pos": [0, 5], "second": {}}
        return {"first": first}

    def test_find_first_invalid_piece_does_not_raise(self):
        dictdump = self._dictdump()
        for ptype in INVALID_TYPES:
            with self.subTest(type=ptype):
                fresh = Tetris()
                fresh.board = empty_board()
                try:
                    result = fresh.find_first(Piece(ptype), dictdump)
                except Exception as exc:  # pragma: no cover
                    self.fail(
                        f"find_first(Piece({ptype!r}), dictdump) warf {exc!r} "
                        f"(KeyError '0'?) statt sauberem Rueckgabewert"
                    )
                # Vertrag: sauberer Sentinel -> (2, None), keine Platzierung.
                self.assertEqual(result, (2, None))

    def test_find_first_none_dictdump_is_defensive(self):
        # Vertrag: dictdump=None defensiv abfangen (kein TypeError).
        t = Tetris()
        t.board = empty_board()
        try:
            t.find_first(Piece(None), None)
        except Exception as exc:  # pragma: no cover
            self.fail(
                f"find_first(Piece(None), None) warf {exc!r} statt defensiv "
                f"zu behandeln"
            )

    def test_find_first_valid_piece_uses_opening_book(self):
        # Regression: gueltiger Stein liefert weiterhin die Buch-Position.
        t = Tetris()
        t.board = empty_board()
        decision, pos = t.find_first(Piece(2), self._dictdump())
        self.assertEqual(decision, 1)
        self.assertEqual(pos, [0, 5])
        # Nach erstem Treffer ist 'first' gesetzt.
        self.assertEqual(t.first, 2)


class TestValidPiecePlacements(unittest.TestCase):
    """(4) Ein gueltiger Stein bekommt plausible Platzierungen."""

    def setUp(self):
        self.t = Tetris()
        self.t.board = empty_board()

    def test_square_piece_has_placements(self):
        # Typ 3 (2x2-Quadrat) hat keinen Strategie-Filter im find_possibles,
        # ausser dem 3-4-5-Filter (Reihen 0 und 2). Es muss Platzierungen geben.
        possibles = self.t.find_possibles(Piece(3))
        self.assertIsInstance(possibles, list)
        self.assertGreater(len(possibles), 0)
        for pos in possibles:
            self.assertEqual(len(pos), 2)
            x, y = pos
            self.assertIn(x, (0, 2))  # 3-4-5-Strategie: nur Reihe 0 oder 2
            self.assertTrue(0 <= y <= 5)

    def test_piece1_has_placements(self):
        # Typ 1 (1x1) hat keinen Strategiefilter -> alle 24 Felder leer = 24.
        possibles = self.t.find_possibles(Piece(1))
        self.assertEqual(len(possibles), 24)

    def test_each_valid_piece_returns_list(self):
        for ptype in range(1, 7):
            with self.subTest(type=ptype):
                fresh = Tetris()
                fresh.board = empty_board()
                res = fresh.find_possibles(Piece(ptype))
                self.assertIsInstance(res, list)

    def test_choose_better_valid_returns_position_from_possibilities(self):
        piece = Piece(3)
        possibles = self.t.find_possibles(piece)
        chosen = self.t.choose_better(piece, possibles)
        self.assertIsNotNone(chosen)
        self.assertIn(chosen, possibles)

    def test_find_possibles_does_not_mutate_board(self):
        # Vertrag (P2): find_possibles arbeitet auf tiefer Kopie -> Original
        # bleibt unveraendert.
        before = copy.deepcopy(self.t.board)
        self.t.find_possibles(Piece(3))
        self.assertEqual(self.t.board, before)


class TestInsertPieceBoundsAndCollision(unittest.TestCase):
    """(5) insert_piece respektiert Grenzen und Kollisionen."""

    def setUp(self):
        self.t = Tetris()
        self.t.board = empty_board()

    def test_insert_within_bounds_succeeds(self):
        self.assertIs(self.t.insert_piece(0, 0, Piece(3)), True)
        # 2x2-Quadrat oben links gesetzt.
        self.assertEqual(self.t.board[0][0], 1)
        self.assertEqual(self.t.board[0][1], 1)
        self.assertEqual(self.t.board[1][0], 1)
        self.assertEqual(self.t.board[1][1], 1)

    def test_insert_out_of_bounds_vertical_fails(self):
        # Typ 2 ist 3 hoch; bei position_x=2 ragt er ueber Reihe 3 hinaus.
        self.assertIs(self.t.insert_piece(2, 0, Piece(2)), False)

    def test_insert_out_of_bounds_horizontal_fails(self):
        # Typ 3 ist 2 breit; bei position_y=5 ragt er ueber Spalte 5 hinaus.
        self.assertIs(self.t.insert_piece(0, 5, Piece(3)), False)

    def test_insert_out_of_bounds_does_not_mutate_board(self):
        before = copy.deepcopy(self.t.board)
        self.t.insert_piece(0, 5, Piece(3))
        self.assertEqual(self.t.board, before)

    def test_insert_collision_fails(self):
        # Erst ein Quadrat setzen, dann ueberlappend erneut -> Kollision.
        self.assertIs(self.t.insert_piece(0, 0, Piece(3)), True)
        self.assertIs(self.t.insert_piece(0, 0, Piece(3)), False)

    def test_verify_insert_piece_collision_detected(self):
        board = empty_board()
        board[0][0] = 1
        # Quadrat an (0,0) kollidiert mit gesetzter Zelle.
        self.assertIs(
            self.t.verify_insert_piece(0, 0, Piece(3), board), False
        )

    def test_verify_insert_piece_free_cell_ok(self):
        board = empty_board()
        self.assertIs(
            self.t.verify_insert_piece(0, 0, Piece(3), board), True
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
