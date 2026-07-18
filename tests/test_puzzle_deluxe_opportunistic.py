# -*- coding: utf-8 -*-
"""Tests fuer den Modus 'Deluxe SOFORT' (``force_deluxe=True``) + den Magenta-
Miss-Deckel (gegen Endlosschleife bei leerer Deluxe-Box).

'Deluxe SOFORT' setzt die Gold-/Deluxe-Box FRUEH (leeres/fast leeres Brett) auf
ein freies 2x3-Loch, hoechstens EINMAL pro Brett (Monte-Carlo-Optimum, N=200k:
Deluxe sofort aufs leere Brett = bester praktikabler Wert; spaeter/mehrfach
schadet). Frueher (bis v1.4) griff die Deluxe-Nutzung OPPORTUNISTISCH bei JEDEM
2x3-Loch ohne Limit -- das ist hier auf 'max 1x/Brett' verschaerft. Der Kern-
Deckel: das explizite Flag ``_deluxe_used_this_board`` (gesetzt beim Einsatz,
zurueckgesetzt beim Brett-Abschluss), weil ``tetris.board`` beim ersten State 0
eines neuen Bretts noch den VOLLEN Vorgaenger-Zustand traegt (frisch gelesen erst
in State 5) -- ein 'Brett leer'-Test taugt daher nicht.

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


def _empty_board():
    return [[0] * 6 for _ in range(4)]


def _full_board():
    return [[1] * 6 for _ in range(4)]


def _sofort_bot(board=None, **attrs):
    """Bare Bot, vorbereitet fuer die 'Deluxe SOFORT'-Entscheidung.

    Default: alle Bedingungen ERFUELLT (force_deluxe an, 'trained', nicht
    abgeschaltet, in diesem Brett noch nicht genutzt, leeres Brett = freies 2x3).
    Einzelne ``attrs`` ueberschreiben gezielt eine Bedingung fuer den Negativ-Test."""
    b = _bare()
    b.force_deluxe = True
    b.solver_mode = 'trained'
    b._deluxe_disabled = False
    b._deluxe_used_this_board = False
    b.tetris = type('T', (), {'board': _empty_board() if board is None else board})()
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
        b._register_deluxe_result(3)
        self.assertEqual(b._deluxe_miss_streak, 1)

    def test_empty_disables_after_limit_no_refill(self):
        # v1.3: Deluxe-NACHLEGEN entfernt -> ein leerer Deluxe-Slot legt nichts
        # mehr nach; nach dem Miss-Limit wird Deluxe nur abgeschaltet (kein Stop,
        # normales Spiel laeuft weiter).
        b = _bare(_awaiting_deluxe=True,
                  _deluxe_miss_streak=puzzle.DELUXE_MISS_LIMIT - 1)
        result = b._register_deluxe_result(None)
        self.assertTrue(result)                  # war ein Deluxe-Versuch
        self.assertTrue(b._deluxe_disabled)      # abgeschaltet, NICHT nachgelegt
        # Der Bot wird dabei NICHT gestoppt (botting bleibt unberuehrt).
        self.assertFalse(getattr(b, 'botting', False))


class DeluxeSofortTest(unittest.TestCase):
    """'Deluxe SOFORT': frueh auf ein freies 2x3, MAX 1x pro Brett.

    Prueft die reine State-0-Entscheidung ``_should_open_deluxe`` (ohne
    Seiteneffekt) + den Ein-pro-Brett-Deckel ueber ``_deluxe_used_this_board``
    und dessen Reset beim Brett-Abschluss (``_reset_deluxe_board_flag``)."""

    # 1. Leeres Brett + Box-Modus an -> Deluxe wird ausgeloest.
    def test_triggers_on_empty_board(self):
        b = _sofort_bot(board=_empty_board())
        self.assertTrue(b._should_open_deluxe())

    # 2. Schon ein Deluxe in diesem Brett -> KEIN zweiter (auch mit freiem 2x3).
    def test_no_second_deluxe_same_board(self):
        b = _sofort_bot(board=_empty_board(), _deluxe_used_this_board=True)
        self.assertFalse(b._should_open_deluxe())

    # 3. Neues Brett (Flag-Reset beim Abschluss) -> Deluxe wieder moeglich.
    def test_new_board_reenables_after_reset(self):
        b = _sofort_bot(board=_empty_board(), _deluxe_used_this_board=True)
        self.assertFalse(b._should_open_deluxe())
        b._reset_deluxe_board_flag()                 # State 9 / Brett-Abschluss
        self.assertFalse(b._deluxe_used_this_board)
        self.assertTrue(b._should_open_deluxe())

    # 4. force_deluxe=False -> NIE ein Deluxe (byte-stabiles Altverhalten).
    def test_off_never_triggers(self):
        b = _sofort_bot(board=_empty_board(), force_deluxe=False)
        self.assertFalse(b._should_open_deluxe())

    # Gate: nur bei 'KI optimiert' (solver_mode == 'trained').
    def test_requires_trained_solver(self):
        b = _sofort_bot(board=_empty_board(), solver_mode='standard')
        self.assertFalse(b._should_open_deluxe())

    # Gate: nach zu vielen leeren Box-Oeffnungen abgeschaltet -> kein Deluxe.
    def test_disabled_blocks(self):
        b = _sofort_bot(board=_empty_board(), _deluxe_disabled=True)
        self.assertFalse(b._should_open_deluxe())

    # Kein freies 2x3 (volles Brett) -> kein Deluxe, auch wenn sonst alles passt.
    def test_no_free_2x3_no_trigger(self):
        b = _sofort_bot(board=_full_board())
        self.assertFalse(b._should_open_deluxe())

    # Genau EIN Deluxe pro Brett-Zyklus (Trigger -> Flag -> Reset -> Trigger).
    def test_exactly_one_per_board_cycle(self):
        b = _sofort_bot(board=_empty_board())
        self.assertTrue(b._should_open_deluxe())     # Brett 1: erlaubt
        b._deluxe_used_this_board = True             # State 0 setzt das Flag
        self.assertFalse(b._should_open_deluxe())    # kein zweiter im selben Brett
        b._reset_deluxe_board_flag()                 # Brett fertig (State 9)
        self.assertTrue(b._should_open_deluxe())     # Brett 2: wieder erlaubt

    # Defensiv: kaputtes/fehlendes tetris -> False, nie Crash.
    def test_defensive_on_bad_tetris(self):
        b = _sofort_bot(board=_empty_board())
        b.tetris = None
        self.assertFalse(b._should_open_deluxe())


if __name__ == '__main__':
    unittest.main()
