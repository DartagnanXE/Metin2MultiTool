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
    # Die selbstkalibrierende Abbruch-Wartezeit haengt an derselben Rueckmeldung,
    # also gehoert sie in diesen Nachbau (sonst testet man an ihr vorbei).
    _tighten_abort_cooldown = _FB._tighten_abort_cooldown
    _relax_abort_cooldown = _FB._relax_abort_cooldown
    _ABORT_COOLDOWN_START_S = _FB._ABORT_COOLDOWN_START_S
    _ABORT_COOLDOWN_MIN_S = _FB._ABORT_COOLDOWN_MIN_S
    _ABORT_COOLDOWN_MAX_S = _FB._ABORT_COOLDOWN_MAX_S
    _ABORT_COOLDOWN_UP_S = _FB._ABORT_COOLDOWN_UP_S
    _ABORT_COOLDOWN_DOWN_S = _FB._ABORT_COOLDOWN_DOWN_S
    _ABORT_COOLDOWN_CLEAN_CASTS = _FB._ABORT_COOLDOWN_CLEAN_CASTS

    def __init__(self, state=1, pending=None):
        import time as _t
        self.state = state
        self._bait_pending_since = _t.time() if pending is None else pending
        self._bait_ok = 0
        self._bait_blocked = 0
        self._bait_blocked_streak = 0
        self._bait_last_feedback_sig = None
        self.timer_action = 0.0
        self._abort_cooldown = self._ABORT_COOLDOWN_START_S
        self._clean_casts_since_block = 0


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

    def test_a_rejection_lengthens_the_abort_wait(self):
        """Verdrahtung: die Client-Antwort speist wirklich den Regler."""
        bot = _Bot(state=1)
        before = bot._abort_cooldown
        self._with_feedback(fc.BLOCKED)
        bot._check_bait_feedback(object())
        self.assertGreater(bot._abort_cooldown, before)

    def test_a_confirmation_counts_towards_shortening(self):
        bot = _Bot(state=1)
        self._with_feedback(fc.BAITED)
        bot._check_bait_feedback(object())
        self.assertEqual(bot._clean_casts_since_block, 1)

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
    """Der Whitelist-Abbruch darf nicht in derselben Sekunde neu koedern --
    und die Wartezeit regelt sich seit v1.6.8 selbst ein."""

    def setUp(self):
        from fishingbot import FishingBot
        self.FB = FishingBot

    def test_start_value_is_in_the_requested_range(self):
        # Live-Wunsch 2026-08-09: "von 1 s auf etwa 0,5 bis 0,7 s".
        self.assertGreaterEqual(self.FB._ABORT_COOLDOWN_START_S, 0.5)
        self.assertLessEqual(self.FB._ABORT_COOLDOWN_START_S, 0.7)

    def test_bounds_are_sane(self):
        self.assertGreater(self.FB._ABORT_COOLDOWN_MIN_S, 0.0)
        self.assertLess(self.FB._ABORT_COOLDOWN_MIN_S,
                        self.FB._ABORT_COOLDOWN_START_S)
        self.assertGreater(self.FB._ABORT_COOLDOWN_MAX_S,
                           self.FB._ABORT_COOLDOWN_START_S)

    def test_reacts_faster_upwards_than_downwards(self):
        """Ein verlorener Wurf wiegt schwerer als eine Zehntelsekunde."""
        self.assertGreater(self.FB._ABORT_COOLDOWN_UP_S,
                           self.FB._ABORT_COOLDOWN_DOWN_S)


class _CooldownBot(object):
    """Nur der Zustand, den die beiden Regler anfassen."""

    from fishingbot import FishingBot as _FB
    _tighten_abort_cooldown = _FB._tighten_abort_cooldown
    _relax_abort_cooldown = _FB._relax_abort_cooldown
    for _n in ('_ABORT_COOLDOWN_START_S', '_ABORT_COOLDOWN_MIN_S',
               '_ABORT_COOLDOWN_MAX_S', '_ABORT_COOLDOWN_UP_S',
               '_ABORT_COOLDOWN_DOWN_S', '_ABORT_COOLDOWN_CLEAN_CASTS'):
        locals()[_n] = getattr(_FB, _n)
    del _n

    def __init__(self):
        self.state = 0
        self._abort_cooldown = self._ABORT_COOLDOWN_START_S
        self._clean_casts_since_block = 0


class TestCooldownSelfCalibration(unittest.TestCase):
    """Der Regelkreis: nach einer Ablehnung laenger, nach sauberen Wuerfen kuerzer."""

    def test_rejection_lengthens_the_wait(self):
        bot = _CooldownBot()
        bot._tighten_abort_cooldown()
        self.assertAlmostEqual(
            bot._abort_cooldown,
            bot._ABORT_COOLDOWN_START_S + bot._ABORT_COOLDOWN_UP_S, places=6)

    def test_lengthening_is_capped(self):
        bot = _CooldownBot()
        for _ in range(50):
            bot._tighten_abort_cooldown()
        self.assertAlmostEqual(bot._abort_cooldown,
                               bot._ABORT_COOLDOWN_MAX_S, places=6)

    def test_clean_casts_below_the_threshold_change_nothing(self):
        bot = _CooldownBot()
        for _ in range(bot._ABORT_COOLDOWN_CLEAN_CASTS - 1):
            bot._relax_abort_cooldown()
        self.assertAlmostEqual(bot._abort_cooldown,
                               bot._ABORT_COOLDOWN_START_S, places=6)

    def test_enough_clean_casts_shorten_the_wait(self):
        bot = _CooldownBot()
        for _ in range(bot._ABORT_COOLDOWN_CLEAN_CASTS):
            bot._relax_abort_cooldown()
        self.assertAlmostEqual(
            bot._abort_cooldown,
            bot._ABORT_COOLDOWN_START_S - bot._ABORT_COOLDOWN_DOWN_S, places=6)

    def test_shortening_is_floored(self):
        bot = _CooldownBot()
        for _ in range(bot._ABORT_COOLDOWN_CLEAN_CASTS * 60):
            bot._relax_abort_cooldown()
        self.assertAlmostEqual(bot._abort_cooldown,
                               bot._ABORT_COOLDOWN_MIN_S, places=6)

    def test_rejection_resets_the_clean_streak(self):
        """Sonst koennte kurz nach einer Ablehnung sofort wieder gesenkt werden."""
        bot = _CooldownBot()
        for _ in range(bot._ABORT_COOLDOWN_CLEAN_CASTS - 1):
            bot._relax_abort_cooldown()
        bot._tighten_abort_cooldown()
        self.assertEqual(bot._clean_casts_since_block, 0)
        after = bot._abort_cooldown
        bot._relax_abort_cooldown()          # ein einzelner sauberer Wurf
        self.assertAlmostEqual(bot._abort_cooldown, after, places=6)

    def test_a_rejection_is_undone_by_many_clean_casts(self):
        """Regelkreis schliesst sich: hoch nach Fehler, langsam wieder runter."""
        bot = _CooldownBot()
        bot._tighten_abort_cooldown()
        raised = bot._abort_cooldown
        rounds = int(round(bot._ABORT_COOLDOWN_UP_S / bot._ABORT_COOLDOWN_DOWN_S))
        for _ in range(bot._ABORT_COOLDOWN_CLEAN_CASTS * rounds):
            bot._relax_abort_cooldown()
        self.assertLess(bot._abort_cooldown, raised)
        self.assertAlmostEqual(bot._abort_cooldown,
                               bot._ABORT_COOLDOWN_START_S, places=6)

    def test_regulators_never_raise(self):
        class _Broken(_CooldownBot):
            def __init__(self):
                _CooldownBot.__init__(self)
                self._abort_cooldown = 'kaputt'   # erzwingt einen TypeError

        _Broken()._tighten_abort_cooldown()
        _Broken()._relax_abort_cooldown()


class TestTooltipObstruction(unittest.TestCase):
    """Ein Item-Tooltip darf nie als Chat-Nachricht durchgehen.

    Live-Report 2026-08-09: Nach dem Nachlegen blieb der Zeiger auf dem Koeder-
    Quickslot stehen. Der Client blendet dort seinen Item-Tooltip ein -- und der
    klappt NACH OBEN auf, quer ueber die Chat-Zeile. Am Bild gemessen:
    Tooltip-Rahmen y[514,592] gegen die Lesezone y[579,596], also 14 von 18
    Zeilen verdeckt (inkl. der ganzen Textzeile y[582,589]). Der Bot las ab da
    den Tooltip -- auf einem LEEREN Chat fand die Segmentierung 5 "Woerter".
    Folge: keine Fischnamen mehr, Whitelist wirkungslos.
    """

    def test_threshold_sits_in_the_measured_gap(self):
        # 66 px = breitestes echtes Wort ueber alle gelabelten Zeilen,
        # 100 px = der Tooltip-Block. Die Schwelle muss dazwischen liegen.
        self.assertGreater(fc.MAX_WORD_WIDTH, 66)
        self.assertLess(fc.MAX_WORD_WIDTH, 100)

    def test_empty_word_list_is_never_obstructed(self):
        self.assertFalse(fc.zone_obstructed([]))
        self.assertFalse(fc.zone_obstructed(None))

    def test_broken_input_is_treated_as_clear(self):
        # Defensiv: unbrauchbare Eingabe darf nicht faelschlich blockieren.
        self.assertFalse(fc.zone_obstructed(['kaputt']))

    def test_wide_block_is_obstructed(self):
        self.assertTrue(fc.zone_obstructed([(0, 10), (14, 14 + 100)]))

    @unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
    def test_tooltip_frame_is_rejected(self):
        """Das echte Tooltip-Bild: verdeckt erkannt, beide Leser liefern NONE."""
        path = os.path.join(_FISCH_DIR, 'tooltip_verdeckt_chatzeile.png')
        if not os.path.exists(path):
            self.skipTest('Referenzbild fehlt')
        bgr = np.array(Image.open(path).convert('RGB'))[:, :, ::-1]
        self.assertTrue(fc.chat_zone_obstructed(bgr))
        self.assertEqual(fc.read_hook(bgr).kind, fc.NONE)
        self.assertEqual(fc.read_action_feedback(bgr)[0], fc.NONE)
        # Kein Fingerabdruck -> ein spaeterer FREIER Frame darf dieselbe Zeile
        # normal auswerten (sonst waere sie dauerhaft verbrannt).
        self.assertIsNone(fc.read_action_feedback(bgr)[1])

    @unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
    def test_real_chat_lines_are_never_called_obstructed(self):
        """Die teure Fehlrichtung: echter Text darf NIE als verdeckt gelten."""
        import glob
        checked = 0
        for path in sorted(glob.glob(os.path.join(_FISCH_DIR, '*.png'))):
            if os.path.basename(path) == 'tooltip_verdeckt_chatzeile.png':
                continue
            bgr = np.array(Image.open(path).convert('RGB'))[:, :, ::-1]
            self.assertFalse(fc.chat_zone_obstructed(bgr),
                             '%s faelschlich als verdeckt' % os.path.basename(path))
            checked += 1
        if checked == 0:
            self.skipTest('keine Referenzbilder vorhanden')


class TestObstructionDiagnostic(unittest.TestCase):
    """``_obstructed_diag`` -- meldet die Verdeckung, ohne den Loop zu belasten.

    Der Zeitstempel wird VOR der Pruefung gesetzt: sonst drosselt nur der
    Treffer-Fall, und im Normalfall (Zone frei) liefe die zweite Binarisierung
    in JEDEM Minispiel-Frame mit.
    """

    def setUp(self):
        import fishingbot
        self.mod = fishingbot
        self._orig_fc = fishingbot._fc

    def tearDown(self):
        self.mod._fc = self._orig_fc

    def _bot(self):
        from fishingbot import FishingBot

        class _B(object):
            _obstructed_diag = FishingBot._obstructed_diag
            _BAIT_DIAG_INTERVAL = FishingBot._BAIT_DIAG_INTERVAL

            def __init__(self):
                self.state = 3
                self._last_obstructed_log = 0.0

        return _B()

    def _spy(self, verdict):
        calls = []

        class _Fc(object):
            @staticmethod
            def chat_zone_obstructed(_shot):
                calls.append(1)
                return verdict

        self.mod._fc = _Fc
        return calls

    def test_clear_zone_is_probed_only_once_per_interval(self):
        calls = self._spy(False)
        bot = self._bot()
        for _ in range(25):
            bot._obstructed_diag(object())
        self.assertEqual(len(calls), 1)      # nicht 25 Binarisierungen

    def test_obstruction_is_probed_only_once_per_interval(self):
        calls = self._spy(True)
        bot = self._bot()
        for _ in range(25):
            bot._obstructed_diag(object())
        self.assertEqual(len(calls), 1)      # eine Meldung, kein Log-Spam

    def test_probe_error_never_escapes(self):
        class _Boom(object):
            @staticmethod
            def chat_zone_obstructed(_shot):
                raise RuntimeError('kaputt')

        self.mod._fc = _Boom
        self._bot()._obstructed_diag(object())   # darf nicht werfen


class TestCursorPark(unittest.TestCase):
    """Der Zeiger muss nach dem Nachlegen vom Quickslot WEG -- ohne Klick."""

    def setUp(self):
        from interface import refill
        self.refill = refill

    def test_park_point_clear_of_chat_zone(self):
        """Auf BEIDEN Frame-Hoehen ausserhalb der Lesezone (Live 601, Ref 632)."""
        px, py = self.refill.CURSOR_PARK_XY
        for height in (601, 632):
            x0, y0, x1, y1 = fc.chat_region_for_frame(height)
            inside = (x0 <= px < x1) and (y0 <= py < y1)
            self.assertFalse(inside,
                             'Park-Punkt %r liegt in der Chat-Zone bei H=%d'
                             % ((px, py), height))

    def test_park_point_clear_of_every_quickslot(self):
        """Nicht auf einem Slot -> der Client zeigt dort keinen Tooltip."""
        px, py = self.refill.CURSOR_PARK_XY
        r = self.refill.QUICKSLOT_PROBE_RADIUS
        for slot, (sx, sy) in self.refill.QUICKSLOT_XY.items():
            self.assertFalse(abs(px - sx) <= r and abs(py - sy) <= r,
                             'Park-Punkt sitzt auf Quickslot %d' % slot)

    def test_park_moves_with_the_window_offset_and_never_clicks(self):
        class _Api(object):
            def __init__(self):
                self.moves = []
                self.clicks = 0

            def moveTo(self, x, y):
                self.moves.append((x, y))

            def mouseDown(self, *_a, **_k):
                self.clicks += 1

            def mouseUp(self, *_a, **_k):
                self.clicks += 1

            def click(self, *_a, **_k):
                self.clicks += 1

        api = _Api()
        self.refill.park_cursor(api, 100, 50, sleep=lambda *_a: None)
        px, py = self.refill.CURSOR_PARK_XY
        self.assertEqual(api.moves, [(100 + px, 50 + py)])
        # Ein Klick in die Welt wuerde die Figur loslaufen lassen.
        self.assertEqual(api.clicks, 0)

    def test_park_failure_is_swallowed(self):
        class _Broken(object):
            @staticmethod
            def moveTo(_x, _y):
                raise RuntimeError('kein Fenster')

        self.refill.park_cursor(_Broken(), 0, 0, sleep=lambda *_a: None)


if __name__ == '__main__':
    unittest.main()
