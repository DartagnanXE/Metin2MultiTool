# -*- coding: utf-8 -*-
"""Characterization tests for the puzzle.py glue (sampling / classify / diagnose).

tetris.py + piece.py (the pure solver) already have deep tests. This file pins
the CURRENT behaviour of the PuzzleBot GLUE that wires the vision sampling to the
solver -- the code a behaviour-preserving split of puzzle.py must keep stable:

  * ``_sample_cell_bgr`` -- 'single' returns the EXACT pixel (byte-stable), and
    'multi' returns the per-channel patch mean (clamped at the edges).
  * ``_classify_piece`` -- 'single' uses the six tight BGR windows (None on a
    miss); 'multi' returns the nearest reference colour (never None for a valid
    colour).
  * ``_is_valid_piece_color`` -- the tolerance check used by the board diagnosis.
  * ``_diagnose_board`` -- the {valid, empty, garbage} census over the 24 cells.
  * ``set_to_begin`` -- the per-run reset of offset / key_points / state (with
    the WindowCapture + log + file IO patched out).

Headless: puzzle.py imports cleanly under py.exe; the glue methods touch only
numpy arrays + the geometry helpers -- no window, no input. We use ``__new__`` to
get a bare instance and set the few attributes each method reads.
"""

import unittest
from unittest import mock

import numpy as np

import puzzle


def _bare_bot(color_mode='single', color_patch=3):
    bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
    bot.color_mode = color_mode
    bot.color_patch = color_patch
    bot.board_size = puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE
    return bot


class TestSampleCellBgrSingle(unittest.TestCase):
    def test_single_is_exact_pixel(self):
        bot = _bare_bot('single')
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        img[5, 4] = (10, 20, 30)
        self.assertEqual(bot._sample_cell_bgr(img, 4, 5), (10, 20, 30))

    def test_single_returns_int_tuple(self):
        bot = _bare_bot('single')
        img = np.full((4, 4, 3), 7, dtype=np.uint8)
        b, g, r = bot._sample_cell_bgr(img, 1, 1)
        self.assertIsInstance(b, int)
        self.assertEqual((b, g, r), (7, 7, 7))


class TestSampleCellBgrMulti(unittest.TestCase):
    def test_multi_is_patch_mean(self):
        bot = _bare_bot('multi', 3)
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        img[4:7, 3:6] = (30, 60, 90)        # 3x3 block centred on (4,5)
        self.assertEqual(bot._sample_cell_bgr(img, 4, 5), (30, 60, 90))

    def test_multi_mean_mixed_values(self):
        bot = _bare_bot('multi', 3)
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        # Centre cell (4,5) plus neighbours: half 0, half 100 -> rounded-down mean.
        img[4:7, 3:6, 0] = 0
        img[5, 4, 0] = 90                    # one bright pixel among nine
        b, _g, _r = bot._sample_cell_bgr(img, 4, 5)
        self.assertEqual(b, 10)             # 90 / 9 = 10 (int)

    def test_multi_clamps_at_edge(self):
        # At a corner the patch is clipped to the image; must not raise/index OOB.
        bot = _bare_bot('multi', 3)
        img = np.full((10, 10, 3), 50, dtype=np.uint8)
        self.assertEqual(bot._sample_cell_bgr(img, 0, 0), (50, 50, 50))


class TestClassifyPieceSingle(unittest.TestCase):
    """The six tight BGR windows, byte-stable to get_new_piece_color."""

    def setUp(self):
        self.bot = _bare_bot('single')

    def test_each_reference_colour_classifies(self):
        cases = {
            (37, 65, 250): 4,
            (25, 160, 250): 1,
            (42, 250, 42): 5,
            (250, 250, 25): 3,
            (250, 107, 0): 2,
            (55, 245, 255): 6,
        }
        for bgr, expected in cases.items():
            self.assertEqual(self.bot._classify_piece(bgr), expected, bgr)

    def test_black_is_none(self):
        self.assertIsNone(self.bot._classify_piece((0, 0, 0)))

    def test_off_window_colour_is_none(self):
        # Just outside every window -> no match.
        self.assertIsNone(self.bot._classify_piece((100, 100, 100)))


class TestClassifyPieceMulti(unittest.TestCase):
    """Nearest-reference: never None for a colour; closest centroid wins."""

    def setUp(self):
        self.bot = _bare_bot('multi')

    def test_exact_reference_nearest(self):
        self.assertEqual(self.bot._classify_piece((37, 65, 250)), 4)

    def test_near_reference_snaps(self):
        # A small drift around type 1's centroid still classifies as 1.
        self.assertEqual(self.bot._classify_piece((28, 162, 248)), 1)

    def test_black_snaps_to_a_type_not_none(self):
        # multi is nearest-colour: black is not None here (the SEPARATE black
        # guard lives in get_new_piece_color, not in _classify_piece).
        self.assertEqual(self.bot._classify_piece((0, 0, 0)), 5)


class TestIsValidPieceColor(unittest.TestCase):
    def setUp(self):
        self.bot = _bare_bot()

    def test_reference_colour_is_valid(self):
        self.assertTrue(self.bot._is_valid_piece_color(37, 65, 250))

    def test_black_is_invalid(self):
        self.assertFalse(self.bot._is_valid_piece_color(0, 0, 0))

    def test_within_tolerance_is_valid(self):
        # Default tol=45; +40 on each channel of a reference still passes.
        self.assertTrue(self.bot._is_valid_piece_color(37 + 40, 65 + 40, 250 - 40))

    def test_outside_tolerance_is_invalid(self):
        self.assertFalse(self.bot._is_valid_piece_color(150, 150, 150))


class TestDiagnoseBoard(unittest.TestCase):
    def test_all_black_is_all_empty(self):
        bot = _bare_bot('single')
        black = np.zeros((170, 260, 3), dtype=np.uint8)
        self.assertEqual(bot._diagnose_board(black),
                         {'valid': 0, 'empty': 24, 'garbage': 0})

    def test_census_counts_to_24(self):
        bot = _bare_bot('single')
        img = np.zeros((170, 260, 3), dtype=np.uint8)
        d = bot._diagnose_board(img)
        self.assertEqual(d['valid'] + d['empty'] + d['garbage'], 24)

    def test_garbage_when_occupied_but_not_piece_colour(self):
        bot = _bare_bot('single')
        # Fill bright grey everywhere (occupied, but no real piece colour) -> all
        # 24 cells count as garbage.
        img = np.full((170, 260, 3), 150, dtype=np.uint8)
        d = bot._diagnose_board(img)
        self.assertEqual(d['empty'], 0)
        self.assertEqual(d['garbage'], 24)
        self.assertEqual(d['valid'], 0)

    def test_diagnose_never_raises_on_small_image(self):
        bot = _bare_bot('single')
        tiny = np.zeros((2, 2, 3), dtype=np.uint8)
        # Out-of-range cell reads are caught internally -> returns a dict.
        d = bot._diagnose_board(tiny)
        self.assertEqual(set(d), {'valid', 'empty', 'garbage'})


class TestDetectEndGame(unittest.TestCase):
    """End game must mean the board is FULL (no empty cells) -- only then does
    the reward chest appear. Regression guard for the "stops after every piece"
    bug: the old single-pixel get-piece check read dark right after a placement
    and falsely reported 'end game', running the chest/stop path on a partial
    board.
    """

    def test_empty_board_is_not_end_game(self):
        bot = _bare_bot('single')
        black = np.zeros((170, 260, 3), dtype=np.uint8)      # 24 empty cells
        self.assertFalse(bot.detect_end_game(black))

    def test_partial_board_is_not_end_game(self):
        bot = _bare_bot('single')
        img = np.zeros((170, 260, 3), dtype=np.uint8)
        img[:, :130] = (37, 65, 250)        # left cells a piece colour, right empty
        self.assertGreater(bot._diagnose_board(img)['empty'], 0)
        self.assertFalse(bot.detect_end_game(img))

    def test_full_board_is_end_game(self):
        bot = _bare_bot('single')
        full = np.zeros((170, 260, 3), dtype=np.uint8)
        full[:] = (37, 65, 250)             # every cell a valid piece colour
        self.assertEqual(bot._diagnose_board(full)['empty'], 0)
        self.assertTrue(bot.detect_end_game(full))


class TestSetToBeginReset(unittest.TestCase):
    """Per-run reset of offset / key_points / state (IO + capture patched out)."""

    def _begin(self, bot, dictdump='{}'):
        stub_cap = type('C', (), {'offset_x': 0, 'offset_y': 0})
        with mock.patch.object(puzzle, 'WindowCapture',
                               lambda *a, **k: stub_cap()), \
                mock.patch.object(puzzle.log, 'configure',
                                  lambda *a, **k: None), \
                mock.patch.object(puzzle.log, 'section', lambda *a, **k: None), \
                mock.patch('builtins.open',
                           mock.mock_open(read_data=dictdump)):
            bot.set_to_begin({})

    def test_offset_reset_to_default(self):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        bot.puzzle_offset = (1, 1)
        bot.key_points = {'color': [9, 9]}
        bot.state = 5
        self._begin(bot)
        self.assertEqual(bot.puzzle_offset,
                         puzzle.PuzzleBot.PUZZLE_WINDOW_POSITION)
        self.assertEqual(bot.key_points, {})
        self.assertEqual(bot.state, 0)

    def test_dictdump_loaded(self):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        self._begin(bot, dictdump='{"a": 1}')
        self.assertEqual(bot.dictdump, {'a': 1})


class TestOpeningPositionGate(unittest.TestCase):
    """set_puzzle_state couples to Tetris.is_opening_position for the book move.

    We assert the gate the glue relies on directly (no window needed)."""

    def test_empty_board_is_opening(self):
        from tetris import Tetris
        t = Tetris()
        t.board = [[0] * 6 for _ in range(4)]
        self.assertTrue(t.is_opening_position())

    def test_nonempty_board_is_not_opening(self):
        from tetris import Tetris
        t = Tetris()
        t.board = [[0] * 6 for _ in range(4)]
        t.board[0][0] = 1
        self.assertFalse(t.is_opening_position())


class _FakeWincap:
    """Minimal stand-in for WindowCapture (only the click offsets are read)."""

    def __init__(self, offset_x, offset_y):
        self.offset_x = offset_x
        self.offset_y = offset_y


class TestButtonClickMethods(unittest.TestCase):
    """Pin the EXACT screen (x, y, button) of the three one-shot click helpers.

    press_comfirm / press_comfirm_cake / throw_pice each map a board reference
    point (via the geometry accessor + optional key_points override) into screen
    coordinates ``int(point + puzzle_offset + wincap.offset)`` and click. These
    are not otherwise unit-tested (they need a live window), so this nails their
    output -- any behaviour-preserving deduplication must keep it identical.
    """

    def _bot(self, key_points=None, offset=(270, 227), wincap=(1000, 500),
             board_size=None):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        bot.board_size = board_size or puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE
        bot.key_points = key_points or {}
        bot.puzzle_offset = offset
        bot.wincap = _FakeWincap(*wincap)
        return bot

    def _expected(self, bot, accessor, kp_name):
        import geometry
        cx, cy = accessor(bot.board_size, bot.key_points.get(kp_name))
        return (int(cx + bot.puzzle_offset[0] + bot.wincap.offset_x),
                int(cy + bot.puzzle_offset[1] + bot.wincap.offset_y))

    def _capture_click(self, fn):
        calls = []
        with mock.patch.object(puzzle.pydirectinput, 'click',
                               lambda **kw: calls.append(kw)):
            fn()
        self.assertEqual(len(calls), 1)
        return calls[0]

    def test_press_comfirm_left_at_confirm_point(self):
        import geometry
        bot = self._bot()
        call = self._capture_click(bot.press_comfirm)
        ex, ey = self._expected(bot, geometry.confirm_point, 'confirm')
        self.assertEqual((call['x'], call['y'], call['button']), (ex, ey, 'left'))

    def test_throw_pice_right_at_confirm_point(self):
        import geometry
        bot = self._bot()
        call = self._capture_click(bot.throw_pice)
        ex, ey = self._expected(bot, geometry.confirm_point, 'confirm')
        self.assertEqual((call['x'], call['y'], call['button']), (ex, ey, 'right'))

    def test_press_comfirm_cake_left_at_cake_point(self):
        import geometry
        bot = self._bot()
        call = self._capture_click(bot.press_comfirm_cake)
        ex, ey = self._expected(bot, geometry.cake_point, 'cake')
        self.assertEqual((call['x'], call['y'], call['button']), (ex, ey, 'left'))

    def test_keypoint_override_is_honoured(self):
        import geometry
        # A 'confirm' override must shift both confirm-based clicks identically.
        bot = self._bot(key_points={'confirm': (40, 55)})
        ex, ey = self._expected(bot, geometry.confirm_point, 'confirm')
        c1 = self._capture_click(bot.press_comfirm)
        c2 = self._capture_click(bot.throw_pice)
        self.assertEqual((c1['x'], c1['y']), (ex, ey))
        self.assertEqual((c2['x'], c2['y']), (ex, ey))

    def test_scaled_board_size_scales_points(self):
        import geometry
        # Non-reference board size exercises the geometry scaling path.
        bot = self._bot(board_size=(520, 340))
        call = self._capture_click(bot.press_comfirm_cake)
        ex, ey = self._expected(bot, geometry.cake_point, 'cake')
        self.assertEqual((call['x'], call['y']), (ex, ey))


class TestCellClickHelpers(unittest.TestCase):
    """Pin the board-CELL screen point + click used by play_game/_place_deluxe.

    The placement paths (trained / opening-book / greedy / deluxe) each turned a
    chosen board cell ``(i, j)`` into screen coordinates
    ``int(geometry.cell_point(i, j, board_size) + puzzle_offset + wincap.offset)``
    and clicked it POSITIONALLY (``pydirectinput.click(x, y)``, no button kwarg).
    These helpers (``_cell_screen_point`` / ``_click_cell``) deduplicate that
    arithmetic; this test nails the EXACT output so the extraction stays
    byte-identical (the placement paths themselves need a live window).
    """

    def _bot(self, offset=(270, 227), wincap=(1000, 500), board_size=None):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        bot.board_size = board_size or puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE
        bot.puzzle_offset = offset
        bot.wincap = _FakeWincap(*wincap)
        return bot

    def _expected(self, bot, i, j):
        import geometry
        cx, cy = geometry.cell_point(i, j, bot.board_size)
        return (int(cx + bot.puzzle_offset[0] + bot.wincap.offset_x),
                int(cy + bot.puzzle_offset[1] + bot.wincap.offset_y))

    def test_cell_screen_point_matches_inlined_formula(self):
        bot = self._bot()
        for (i, j) in ((0, 0), (3, 5), (2, 4)):
            self.assertEqual(bot._cell_screen_point(i, j),
                             self._expected(bot, i, j), (i, j))

    def test_cell_screen_point_scales_with_board_size(self):
        bot = self._bot(board_size=(520, 340))
        self.assertEqual(bot._cell_screen_point(3, 5), self._expected(bot, 3, 5))

    def test_click_cell_clicks_positionally_at_cell_point(self):
        bot = self._bot()
        calls = []
        with mock.patch.object(puzzle.pydirectinput, 'click',
                               lambda *a, **kw: calls.append((a, kw))):
            bot._click_cell(2, 4)
        # Exactly the inlined call shape: two positional args, no kwargs.
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(kwargs, {})
        self.assertEqual(args, self._expected(bot, 2, 4))


class TestColorReadRetry(unittest.TestCase):
    """State 4 liest die Stein-Farbe WIEDERHOLT (frisches Capture pro Frame)
    statt einen zu frueh gelesenen Hintergrund-Frame sofort zu verwerfen.

    Live-Befund 2026-06-10: ~0.1-0.3s nach dem Stein-Holen war der Stein oft
    noch nicht gerendert -> der Einmal-Read las Hintergrund-Grau, new_piece
    wurde None und JEDER Stein ging sofort in den Verwerfen-Pfad (State 7/8).
    """

    def _bot(self, crop, retry_until):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        bot.board_size = puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE
        bot.key_points = {}
        bot.puzzle_offset = (270, 227)
        bot.wincap = _FakeWincap(1000, 500)
        bot.color_mode = 'single'
        bot.state = 4
        bot.timer_action = 0.0            # timep laengst abgelaufen
        bot.new_piece = 'sentinel'
        bot._color_read_announced = False
        bot._color_retry_until = retry_until
        bot.get_image = lambda: crop      # statt Live-Capture
        return bot

    def _black_crop(self):
        w, h = puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE
        return np.zeros((h, w, 3), dtype=np.uint8)

    def _blue_crop(self):
        import geometry
        crop = self._black_crop()
        x, y = geometry.color_sample(puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE)
        crop[y, x] = (255, 74, 0)         # live gemessenes Stein-Blau (BGR)
        return crop

    def test_miss_during_retry_stays_in_state4(self):
        from time import time as _now
        bot = self._bot(self._black_crop(), retry_until=_now() + 60)
        bot.runHack()
        self.assertEqual(bot.state, 4)            # kein Verwerfen-Uebergang
        self.assertEqual(bot.new_piece, 'sentinel')  # nichts ueberschrieben

    def test_miss_after_deadline_falls_through_to_discard_path(self):
        bot = self._bot(self._black_crop(), retry_until=0.0)  # abgelaufen
        bot.runHack()
        self.assertEqual(bot.state, 5)
        self.assertIsNone(bot.new_piece)          # bestehender Verwerfen-Pfad

    def test_blue_piece_detected_during_retry(self):
        # Deckt zugleich das verbreiterte BLAU-Fenster (g 60..130) end-to-end:
        # (255, 74, 0) fiel mit dem alten 100..115-Fenster durch.
        from time import time as _now
        bot = self._bot(self._blue_crop(), retry_until=_now() + 60)
        bot.runHack()
        self.assertEqual(bot.state, 5)
        self.assertEqual(bot.new_piece, 2)


class TestClassifyPieceTolerant(unittest.TestCase):
    """Toleranz-Fallback: eindeutiger Zentroid-Treffer oder None."""

    def _bot(self):
        bot = puzzle.PuzzleBot.__new__(puzzle.PuzzleBot)
        return bot

    def test_drifted_blue_classifies(self):
        # Live gemessen 2026-06-10; lag ausserhalb des alten engen Fensters.
        self.assertEqual(self._bot()._classify_piece_tolerant((255, 74, 0)), 2)

    def test_drifted_orange_classifies(self):
        # Nahe Zentroid 1 (25,160,250), aber ausserhalb des g>150-Fensters.
        self.assertEqual(self._bot()._classify_piece_tolerant((25, 135, 250)), 1)

    def test_dark_background_is_none(self):
        self.assertIsNone(self._bot()._classify_piece_tolerant((31, 34, 36)))

    def test_mid_gray_garbage_is_none(self):
        self.assertIsNone(self._bot()._classify_piece_tolerant((100, 100, 100)))

    def test_magenta_is_deluxe(self):
        import deluxe
        # Ein Magenta-Wert aus dem Deluxe-Fenster -> Typ 7, nie einer der 6.
        b, g, r = 230, 30, 230
        if deluxe.is_magenta(b, g, r):
            self.assertEqual(self._bot()._classify_piece_tolerant((b, g, r)),
                             deluxe.DELUXE_PIECE_TYPE)


class TestTolerantFallbackWiring(TestColorReadRetry):
    """Ein gedrifteter (gerenderter) Stein wird SOFORT erkannt -- noch
    waehrend des Retry-Fensters, ohne die 2s abzuwarten."""

    def _drifted_crop(self):
        import geometry
        crop = self._black_crop()
        x, y = geometry.color_sample(puzzle.PuzzleBot.PUZZLE_WINDOW_SIZE)
        crop[y, x] = (25, 135, 250)   # nahe Zentroid 1, ausserhalb Fenster
        return crop

    def test_drifted_piece_recognized_during_retry(self):
        from time import time as _now
        bot = self._bot(self._drifted_crop(), retry_until=_now() + 60)
        bot.runHack()
        self.assertEqual(bot.state, 5)
        self.assertEqual(bot.new_piece, 1)


if __name__ == '__main__':
    unittest.main()
