"""Integrations-Tests fuer die Haertungs-Verdrahtung in puzzle.py.

puzzle.py importiert Windows-only Module (pydirectinput, win32* via
windowcapture). Die werden hier VOR dem Import gestubbt, damit die reine
Glue-Logik (Finish-Fix, Safe-Fail, Closed-Loop-Arming, Plausibilitaet) auch
headless gegen den ECHTEN Code laeuft -- nicht nur gegen puzzle_safety.
"""

import os
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _install_stubs():
    pdi = types.ModuleType('pydirectinput')
    pdi.PAUSE = 0
    for fn in ('click', 'moveTo', 'press', 'keyDown', 'keyUp'):
        setattr(pdi, fn, lambda *a, **k: None)
    sys.modules['pydirectinput'] = pdi
    for name in ('win32gui', 'win32ui', 'win32con'):
        sys.modules.setdefault(name, types.ModuleType(name))


_install_stubs()

import puzzle          # noqa: E402
import trained_solver  # noqa: E402
from tetris import Tetris  # noqa: E402
from piece import Piece  # noqa: E402


def _bare_bot():
    bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
    bot.solver_mode = 'trained'
    bot.force_deluxe = False
    bot.verify_placements = True
    bot.board_plausibility = True
    bot.state = 5
    bot.end = False
    bot.botting = True
    bot._discard_streak = 0
    bot._expected_board = None
    bot._expected_meta = None
    bot._last_board_garbage = 0
    bot.tetris = Tetris()
    return bot


def _l_hole_board():
    # 3 leere Zellen (0,2),(1,2),(1,3) = das per L-Stein (Typ 5) in EINEM Zug
    # fuellbare Loch aus dem realen Log.
    b = [[1] * 6 for _ in range(4)]
    b[0][2] = 0
    b[1][2] = 0
    b[1][3] = 0
    return b


class TestFinishFix(unittest.TestCase):
    """Finish-Modus ENTFERNT (2026-06-17, Nutzer-Vorgabe "perfekt, keine Grenzen,
    minimale Steine"): immer die beweisbar optimale Policy (per Monte-Carlo
    bestaetigt: erreicht V[leer]=15.57, 0 Steckenbleiber/50k). Der Finish-Modus
    legte fragmentierende Steine (V steigt) und verbrauchte ~22% MEHR Steine."""

    def _finish_flag(self, board, new_piece, streak):
        bot = _bare_bot()
        bot.tetris.board = board
        bot.new_piece = new_piece
        bot._discard_streak = streak
        captured = {}

        def fake_choose(board_arg, piece, finish=False, reservat=None):
            captured['finish'] = finish
            return None

        with mock.patch.object(trained_solver, 'choose_placement', fake_choose):
            bot.play_game()
        return captured['finish']

    def test_finish_always_off_regardless_of_streak_and_piece(self):
        # Egal welcher Stein / wie hoch der Streak: play_game ruft den Solver IMMER
        # mit finish=False (kein erzwungenes Legen suboptimaler Steine mehr).
        for streak in (0, 1, 3, 5, 10, 30, 59):
            for piece in (1, 5):
                self.assertFalse(
                    self._finish_flag(_l_hole_board(), piece, streak),
                    'Stein %d, Streak %d: finish muss aus sein' % (piece, streak))

    def test_optimal_policy_discards_fragmenting_single(self):
        # ECHTER Solver: ein Monomino auf das 1-Zug-L-Loch wird VERWORFEN (None),
        # statt es zu fragmentieren (V 6 -> 12 waere schlechter).
        self.assertIsNone(
            trained_solver.choose_placement(_l_hole_board(), Piece(1), finish=False))

    def test_optimal_policy_places_completing_piece(self):
        # ECHTER Solver: der komplettierende L-Stein (Typ 5) wird platziert.
        self.assertIsNotNone(
            trained_solver.choose_placement(_l_hole_board(), Piece(5), finish=False))


class TestSafeFail(unittest.TestCase):
    """⑥ Dauer-Verwerfen ohne Platzierung -> sauberer Stop."""

    def test_stop_at_discard_limit(self):
        bot = _bare_bot()
        bot.tetris.board = [[0] * 6 for _ in range(4)]  # leer -> nicht 1-Zug-komplettierbar
        bot.new_piece = 1
        bot._discard_streak = puzzle.DISCARD_STOP_LIMIT - 1

        def fake_choose(*a, **k):
            return None

        with mock.patch.object(trained_solver, 'choose_placement', fake_choose):
            bot.play_game()
        self.assertEqual(bot._discard_streak, puzzle.DISCARD_STOP_LIMIT)
        self.assertFalse(bot.botting)

    def test_no_stop_before_limit(self):
        bot = _bare_bot()
        bot.tetris.board = [[0] * 6 for _ in range(4)]
        bot.new_piece = 1
        bot._discard_streak = 2
        with mock.patch.object(trained_solver, 'choose_placement',
                               lambda *a, **k: None):
            bot.play_game()
        self.assertTrue(bot.botting)


class TestClosedLoopArming(unittest.TestCase):
    """① Nach einer Platzierung wird das Soll gemerkt; Verify loggt Abweichungen."""

    def test_arm_then_verify_detects_missing_piece(self):
        bot = _bare_bot()
        bot.tetris.board = [[0] * 6 for _ in range(4)]
        # Arming spiegelt das Brett VOR dem Einsetzen + Stein/Anker.
        bot._arm_placement_verify(4, (2, 2))
        self.assertIsNotNone(bot._expected_board)
        # Ist-Brett: der Stein ist NICHT gelandet (alles leer) -> critical-Log.
        actual = [[0] * 6 for _ in range(4)]
        with mock.patch.object(puzzle.log, 'snapshot') as snap:
            bot._verify_last_placement(actual)
        self.assertTrue(snap.called)
        extra = snap.call_args.kwargs.get('extra', '')
        self.assertIn('critical', extra)

    def test_correct_placement_logs_nothing(self):
        bot = _bare_bot()
        bot.tetris.board = [[0] * 6 for _ in range(4)]
        bot._arm_placement_verify(1, (0, 0))
        actual = [[0] * 6 for _ in range(4)]
        actual[0][0] = 1  # Stein korrekt gelandet
        with mock.patch.object(puzzle.log, 'snapshot') as snap:
            bot._verify_last_placement(actual)
        self.assertFalse(snap.called)


class TestBoardSuspicious(unittest.TestCase):
    """④ Garbage-Schwelle markiert die Brett-Lesung als verdaechtig."""

    def test_threshold(self):
        bot = _bare_bot()
        bot._last_board_garbage = puzzle.BOARD_MAX_GARBAGE
        self.assertTrue(bot._board_suspicious())
        bot._last_board_garbage = puzzle.BOARD_MAX_GARBAGE - 1
        self.assertFalse(bot._board_suspicious())

    def test_disabled_flag(self):
        bot = _bare_bot()
        bot.board_plausibility = False
        bot._last_board_garbage = 99
        self.assertFalse(bot._board_suspicious())


if __name__ == '__main__':
    unittest.main()
