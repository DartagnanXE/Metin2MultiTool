# -*- coding: utf-8 -*-
"""Der Koeder-Regelkreis: merkt der Bot, ob sein Tastendruck angekommen ist?

Bis v1.6.5 hat der Bot den Koeder-Tastendruck gesendet und Erfolg ANGENOMMEN.
Lehnt der Client ab ("Du kannst diese Aktion nicht ausfuehren, waehrend du
angelst."), warf er ohne Koeder aus und meldete danach "Kein Biss" -- der
Fehler war unsichtbar. Diese Datei sichert die drei Bausteine des Gegenmittels:

  1. :func:`fishing_chat.read_action_feedback` -- liest die Client-Antwort
     (gegen ECHTE Screenshots vom 2026-08-06, wie die uebrigen Chat-Tests).
  2. :func:`interface.refill.find_first` -- fasst nur SICHERE Treffer an.
  3. ``FishingBot._check_bait_feedback`` -- reagiert auf eine Ablehnung.

(2) und (3) sind reine Logik und laufen IMMER (auch ohne Screenshots/numpy);
(1) skippt sauber, wenn die Referenzbilder fehlen.
"""

import os
import unittest

try:
    import numpy as np
    from PIL import Image
    _HAS_DEPS = True
except Exception:                       # pragma: no cover - headless ohne Deps
    _HAS_DEPS = False

import fishing_chat as fc


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_FISCH_DIR = os.path.join(_ROOT, 'FischOCR')

# Ground Truth: Dateiname -> erwartete Rueckmeldung.
_EXPECTED_FEEDBACK = {
    'aktion_koeder_befestigt.png': fc.BAITED,    # "... als Koeder am Haken befestigt."
    'aktion_koeder_getauscht.png': fc.BAITED,    # "Du tauschst den aktuellen Koeder ..."
    'aktion_blockiert_angeln.png': fc.BLOCKED,   # "... waehrend du angelst."
    'quickslot_koeder_195.png': fc.NONE,         # kein Chat-Text -> keine Aussage
    'quickslot_koeder_leer.png': fc.NONE,
}


def _shots_present():
    return _HAS_DEPS and all(
        os.path.isfile(os.path.join(_FISCH_DIR, f)) for f in _EXPECTED_FEEDBACK)


def _load_bgr(path):
    """PNG -> BGR uint8 (genau das, was WindowCapture liefert)."""
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


@unittest.skipUnless(_shots_present(), 'numpy/PIL oder die Referenz-Screenshots fehlen')
class TestActionFeedbackRealShots(unittest.TestCase):
    """Jede echte Client-Antwort muss korrekt gelesen werden."""

    @classmethod
    def setUpClass(cls):
        fc.reset_template_cache()

    def test_every_shot_reads_correctly(self):
        failures = []
        for fname, expected in sorted(_EXPECTED_FEEDBACK.items()):
            got, _sig = fc.read_action_feedback(
                _load_bgr(os.path.join(_FISCH_DIR, fname)))
            if got != expected:
                failures.append('%s -> %r (erwartet %r)' % (fname, got, expected))
        self.assertEqual(failures, [], 'Falsch gelesen:\n' + '\n'.join(failures))

    def test_blocked_shot_is_recognised(self):
        """Der Kernfall -- ohne ihn bleibt der Bot blind."""
        got, sig = fc.read_action_feedback(
            _load_bgr(os.path.join(_FISCH_DIR, 'aktion_blockiert_angeln.png')))
        self.assertEqual(got, fc.BLOCKED)
        self.assertIsNotNone(sig)

    def test_same_line_yields_the_same_fingerprint(self):
        """Grundlage der Doppelwertungs-Sperre: gleiche Zeile -> gleiche Kennung."""
        path = os.path.join(_FISCH_DIR, 'aktion_blockiert_angeln.png')
        _a, sig_a = fc.read_action_feedback(_load_bgr(path))
        _b, sig_b = fc.read_action_feedback(_load_bgr(path))
        self.assertEqual(sig_a, sig_b)

    def test_different_lines_yield_different_fingerprints(self):
        _a, sig_a = fc.read_action_feedback(
            _load_bgr(os.path.join(_FISCH_DIR, 'aktion_blockiert_angeln.png')))
        _b, sig_b = fc.read_action_feedback(
            _load_bgr(os.path.join(_FISCH_DIR, 'aktion_koeder_befestigt.png')))
        self.assertNotEqual(sig_a, sig_b)

    def test_bite_messages_never_read_as_blocked(self):
        """Kein Fehlalarm auf den gelabelten Biss-/Niete-Zeilen.

        Ein erfundenes "blockiert" wuerde einen ueberfluessigen Koeder-Druck
        ausloesen -- billig, aber es soll trotzdem nicht passieren.
        """
        others = [f for f in os.listdir(_FISCH_DIR)
                  if f.lower().endswith('.png') and f not in _EXPECTED_FEEDBACK]
        wrong = []
        for fname in sorted(others):
            got, _sig = fc.read_action_feedback(
                _load_bgr(os.path.join(_FISCH_DIR, fname)))
            if got == fc.BLOCKED:
                wrong.append(fname)
        self.assertEqual(wrong, [], 'faelschlich BLOCKED: %r' % (wrong,))

    def test_read_hook_unaffected_by_the_new_template(self):
        """Das neue 'nicht'-Template darf die Biss-Erkennung nicht stoeren."""
        res = fc.read_hook(_load_bgr(os.path.join(_FISCH_DIR, 'Lachs.png')))
        self.assertEqual(res.kind, fc.FISH)
        self.assertEqual(res.name, 'Lachs')
        # Die Blockade-Zeile ist fuer die Biss-Erkennung weiterhin "nichts".
        blocked = fc.read_hook(
            _load_bgr(os.path.join(_FISCH_DIR, 'aktion_blockiert_angeln.png')))
        self.assertEqual(blocked.kind, fc.NONE)


class _Slot(object):
    """Minimaler SlotResult-Ersatz fuer die find_first-Tests."""

    def __init__(self, name, row, col, distance, state='item'):
        self.name = name
        self.row = row
        self.col = col
        self.distance = distance
        self.state = state


class _Inv(object):
    def __init__(self, pages):
        self.pages = pages


class TestFindFirstOnlyTouchesSureHits(unittest.TestCase):
    """Der Bot darf nur ANFASSEN, was sicher erkannt ist."""

    def test_sure_hit_is_returned(self):
        from interface.refill import find_first
        inv = _Inv({'I': [_Slot('Worm', 0, 1, 0.16)]})
        self.assertEqual(find_first(inv, ('Worm',)), ('I', 0, 1))

    def test_uncertain_hit_is_skipped(self):
        """Der real gemessene Fall: Bronze-Abzeichen als 'Worm', Distanz 29,5.

        Frueher haette der Bot es in den Koeder-Slot gezogen, sobald der echte
        Stapel leer war; jetzt gilt der Beutel ehrlich als koederlos.
        """
        from interface.refill import find_first
        inv = _Inv({'I': [_Slot('Worm', 0, 3, 29.49)]})
        self.assertIsNone(find_first(inv, ('Worm',)))

    def test_sure_hit_wins_over_uncertain_one(self):
        from interface.refill import find_first
        inv = _Inv({'I': [_Slot('Worm', 0, 3, 29.49),
                          _Slot('Worm', 0, 1, 0.16)]})
        self.assertEqual(find_first(inv, ('Worm',)), ('I', 0, 1))

    def test_slot_without_distance_still_works(self):
        """Aeltere/fremde Slot-Objekte ohne Distanz-Feld bleiben nutzbar."""
        from interface.refill import find_first

        class _Bare(object):
            state, name, row, col = 'item', 'Worm', 2, 2

        self.assertEqual(find_first(_Inv({'I': [_Bare()]}), ('Worm',)), ('I', 2, 2))

    def test_threshold_is_the_matchers_sure_hit_bound(self):
        from interface.refill import REFILL_MAX_DISTANCE
        from inventory.constants import MATCH_THRESHOLD, MARGIN_PRIMARY_MAX_DIST
        self.assertEqual(REFILL_MAX_DISTANCE, MATCH_THRESHOLD)
        # Sonst waere die Verschaerfung wirkungslos.
        self.assertLess(REFILL_MAX_DISTANCE, MARGIN_PRIMARY_MAX_DIST)


class _Bot(object):
    """Nachbau des Bot-Zustands, den _check_bait_feedback anfasst."""

    from fishingbot import FishingBot as _FB
    _check_bait_feedback = _FB._check_bait_feedback
    _BAIT_FEEDBACK_WINDOW_S = _FB._BAIT_FEEDBACK_WINDOW_S
    _BAIT_RETRY_WAIT_S = _FB._BAIT_RETRY_WAIT_S
    _BAIT_BLOCKED_WARN_AT = _FB._BAIT_BLOCKED_WARN_AT

    def __init__(self, state=1, pending=None):
        import time as _t
        self.state = state
        self._bait_pending_since = _t.time() if pending is None else pending
        self._bait_ok = 0
        self._bait_blocked = 0
        self._bait_blocked_streak = 0
        self._bait_last_feedback_sig = None
        self.timer_action = 0.0


class TestBaitFeedbackLoop(unittest.TestCase):
    """Die Reaktion auf die Client-Antwort."""

    def setUp(self):
        import fishingbot
        self._bot_mod = fishingbot
        self._orig = fishingbot._fc

    def tearDown(self):
        self._bot_mod._fc = self._orig

    def _with_feedback(self, value, sig='zeile-1'):
        """fishing_chat durch einen Stub ersetzen, der ``value`` meldet."""
        class _Stub(object):
            BAITED = fc.BAITED
            BLOCKED = fc.BLOCKED
            NONE = fc.NONE

            @staticmethod
            def read_action_feedback(_shot):
                return value, sig

        self._bot_mod._fc = _Stub

    def test_confirmed_bait_only_counts(self):
        self._with_feedback(fc.BAITED)
        bot = _Bot(state=1)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_ok, 1)
        self.assertEqual(bot._bait_blocked, 0)
        self.assertEqual(bot.state, 1)            # Ablauf unveraendert
        self.assertEqual(bot._bait_pending_since, 0.0)

    def test_blocked_bait_goes_back_to_state_zero_and_waits(self):
        import time as _t
        self._with_feedback(fc.BLOCKED)
        bot = _Bot(state=1)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked, 1)
        self.assertEqual(bot.state, 0)            # nicht ins Leere werfen
        # Timer in der ZUKUNFT -> es wird gewartet, nicht sofort neu gedrueckt.
        self.assertGreater(bot.timer_action, _t.time())

    def test_blocked_during_minigame_is_only_logged(self):
        """Ein laufender Fang darf nie wegen einer Chat-Zeile sterben."""
        self._with_feedback(fc.BLOCKED)
        bot = _Bot(state=3)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked, 1)
        self.assertEqual(bot.state, 3)            # Minispiel laeuft weiter
        self.assertEqual(bot.timer_action, 0.0)   # kein Eingriff

    def test_no_answer_leaves_everything_alone(self):
        self._with_feedback(fc.NONE)
        bot = _Bot(state=1)
        bot._check_bait_feedback(object())
        self.assertEqual((bot._bait_ok, bot._bait_blocked), (0, 0))
        self.assertEqual(bot.state, 1)
        self.assertGreater(bot._bait_pending_since, 0)   # weiter abwarten

    def test_window_expires_so_the_loop_never_hangs(self):
        import time as _t
        self._with_feedback(fc.BLOCKED)
        bot = _Bot(state=1, pending=_t.time() - 99.0)    # laengst abgelaufen
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_pending_since, 0.0)   # aufgegeben
        self.assertEqual(bot._bait_blocked, 0)           # nicht mehr gewertet
        self.assertEqual(bot.state, 1)

    def test_without_pending_press_nothing_happens(self):
        self._with_feedback(fc.BLOCKED)
        bot = _Bot(state=1, pending=0.0)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked, 0)
        self.assertEqual(bot.state, 1)

    def test_streak_resets_after_a_confirmed_bait(self):
        bot = _Bot(state=1)
        self._with_feedback(fc.BLOCKED)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked_streak, 1)
        bot._bait_pending_since = __import__('time').time()
        self._with_feedback(fc.BAITED, sig='zeile-2')
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked_streak, 0)

    def test_same_chat_line_is_only_counted_once(self):
        """Die Chat-Zeile bleibt im Spiel stehen.

        Ohne die Sperre wuerde dieselbe Ablehnung in jedem Frame -- und nach
        dem naechsten Koeder-Versuch gleich wieder -- gewertet: der Bot wartete
        endlos auf eine Antwort, die er laengst gelesen hatte.
        """
        import time as _t
        self._with_feedback(fc.BLOCKED, sig='immer-dieselbe')
        bot = _Bot(state=1)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked, 1)

        bot.state = 1                                   # naechster Versuch
        bot._bait_pending_since = _t.time()
        bot.timer_action = 0.0
        bot._check_bait_feedback(object())
        self.assertEqual(bot._bait_blocked, 1)          # NICHT doppelt gezaehlt
        self.assertEqual(bot.state, 1)                  # kein zweiter Ruecksetzer
        self.assertEqual(bot.timer_action, 0.0)         # keine neue Wartezeit

    def test_reader_error_never_escapes(self):
        class _Boom(object):
            @staticmethod
            def read_action_feedback(_shot):
                raise RuntimeError('kaputt')

        self._bot_mod._fc = _Boom
        bot = _Bot(state=1)
        bot._check_bait_feedback(object())          # darf nicht werfen
        self.assertEqual(bot.state, 1)


class TestAbortCooldown(unittest.TestCase):
    """Der Whitelist-Abbruch darf nicht mehr in derselben Sekunde neu koedern."""

    def test_cooldown_is_positive(self):
        from fishingbot import FishingBot
        self.assertGreater(FishingBot._ABORT_COOLDOWN_S, 0.0)


if __name__ == '__main__':
    unittest.main()
