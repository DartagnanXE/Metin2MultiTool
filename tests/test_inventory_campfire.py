# -*- coding: utf-8 -*-
"""Tests for the Lagerfeuer-Braten (inventory_campfire).

Three layers, all headless:

  * LABEL RECOGNITION against the six real marked campfire shots
    (``FischOCR/Lagerfeuer markeirung/Feuer1-6.png``): the "Lagerfeuer" label is
    found at high confidence and pixel-exact, while a non-campfire fishing frame
    is correctly rejected (no false fire). Skipped cleanly if cv2/numpy/PIL or the
    images are unavailable.
  * PURE SELECTION: only CAMPFIRE-marked fish are grilled, with baits / koeder /
    the campfire tool / puzzle boxes EXCLUDED even when (wrongly) marked; the
    slot list follows the documented page-then-row-major order; the fire offset
    is the hard-calibrated (20, 21).
  * ORCHESTRATION with the live deps INJECTED (a recorder input api + synthetic
    capture/scan): the place double-click, the bird's-eye hold, the rotate-on-miss
    retry, and one drag per fish onto the fire all fire in the right sequence; and
    every failure mode short-circuits to a clear status without raising.
"""

import os
import types
import unittest

import inventory_campfire as campfire
from inventory.grid import GridLattice, lattice_from_calibration
from inventory.constants import DEFAULT_CALIBRATION

try:
    import numpy as np
except Exception:                       # pragma: no cover
    np = None

try:
    import cv2  # noqa: F401
    _HAS_CV = True
except Exception:                       # pragma: no cover
    _HAS_CV = False

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:                       # pragma: no cover
    _HAS_PIL = False


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CAMPFIRE_DIR = os.path.join(_ROOT, 'FischOCR', 'Lagerfeuer markeirung')
_FISH_DIR = os.path.join(_ROOT, 'FischOCR')

# Hand-verified label top-left per reference (the glyph box) -- the truth the
# matcher must land on (within a pixel or two).
_LABEL_TL = {
    'Feuer1': (394, 410), 'Feuer2': (352, 401), 'Feuer3': (405, 400),
    'Feuer4': (405, 400), 'Feuer5': (362, 412), 'Feuer6': (347, 411),
}


def _load_rgb(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8)


def _slot(name, row, col, state='item'):
    return types.SimpleNamespace(state=state, name=name, row=row, col=col)


def _inv(pages):
    return types.SimpleNamespace(pages=pages)


# -- recorder input api (records every action in order) ---------------------

class _Recorder:
    """Stand-in for pydirectinput; records the action stream for assertions."""

    def __init__(self):
        self.events = []

    def moveTo(self, x, y):
        self.events.append(('move', int(x), int(y)))

    def mouseDown(self):
        self.events.append(('down',))

    def mouseUp(self):
        self.events.append(('up',))

    def click(self, x=None, y=None, **_):
        self.events.append(('click', int(x), int(y)))

    def doubleClick(self, x=None, y=None, **_):
        self.events.append(('dclick', int(x), int(y)))

    def keyDown(self, key):
        self.events.append(('keydown', key))

    def keyUp(self, key):
        self.events.append(('keyup', key))


def _noop_sleep(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# Label recognition against the real reference shots
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_CV and _HAS_PIL and np is not None,
                     'cv2 / PIL / numpy required for label recognition')
class TestLabelRecognitionReal(unittest.TestCase):
    def setUp(self):
        self.tmpl = campfire.load_label_template()
        if self.tmpl is None:
            self.skipTest('bundled campfire template not loadable')

    def test_template_shape_and_ink(self):
        # The hard-calibrated 47x11 glyph with ~112 ink pixels.
        self.assertEqual(self.tmpl.shape, (11, 47))
        self.assertEqual(int(self.tmpl.sum()), 112)

    def test_found_on_every_reference_pixel_exact(self):
        for name, truth in _LABEL_TL.items():
            path = os.path.join(_CAMPFIRE_DIR, name + '.png')
            if not os.path.exists(path):
                self.skipTest('reference %s missing' % name)
            rgb = _load_rgb(path)
            found, score, tl = campfire.find_label(rgb, template=self.tmpl)
            self.assertTrue(found, '%s: not found (score %.3f)' % (name, score))
            self.assertGreaterEqual(score, 0.95, name)
            # Localisation within a couple of pixels of the hand-verified box.
            self.assertLessEqual(abs(tl[0] - truth[0]), 2, '%s x' % name)
            self.assertLessEqual(abs(tl[1] - truth[1]), 2, '%s y' % name)

    def test_fire_point_is_offset_below_label(self):
        path = os.path.join(_CAMPFIRE_DIR, 'Feuer3.png')
        if not os.path.exists(path):
            self.skipTest('Feuer3 missing')
        _found, _score, tl = campfire.find_label(_load_rgb(path),
                                                 template=self.tmpl)
        fire = campfire.fire_point_from_label(tl)
        # The red placement circle sits at (+20, +21) from the label top-left.
        self.assertEqual(fire, (tl[0] + 20, tl[1] + 21))

    def test_no_false_positive_on_plain_fishing_frame(self):
        # A normal catch screenshot has NO campfire label -> must stay well under
        # threshold (measured <= ~0.53 on these; threshold is 0.80).
        for fname in ('Lachs.png', 'Zander.png', 'thunfisch.png'):
            path = os.path.join(_FISH_DIR, fname)
            if not os.path.exists(path):
                continue
            found, score, _tl = campfire.find_label(_load_rgb(path),
                                                    template=self.tmpl)
            self.assertFalse(found, '%s falsely matched (%.3f)' % (fname, score))
            self.assertLess(score, campfire.LABEL_MATCH_THRESHOLD, fname)


# ---------------------------------------------------------------------------
# Label matcher: defensive degradation
# ---------------------------------------------------------------------------

class TestFindLabelDefensive(unittest.TestCase):
    def test_none_frame_returns_not_found(self):
        found, score, tl = campfire.find_label(None, template=None)
        self.assertFalse(found)
        self.assertEqual(score, 0.0)
        self.assertIsNone(tl)

    def test_no_green_frame_returns_not_found(self):
        if np is None:
            self.skipTest('numpy required')
        # An all-blue frame has zero green text pixels.
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        frame[:, :, 2] = 200
        tmpl = np.ones((11, 47), dtype=np.uint8)
        found, score, _tl = campfire.find_label(frame, template=tmpl)
        self.assertFalse(found)
        self.assertEqual(score, 0.0)

    def test_frame_smaller_than_template(self):
        if np is None:
            self.skipTest('numpy required')
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        tmpl = np.ones((11, 47), dtype=np.uint8)
        found, _score, _tl = campfire.find_label(frame, template=tmpl)
        self.assertFalse(found)

    def test_fire_point_none_for_none_label(self):
        self.assertIsNone(campfire.fire_point_from_label(None))


# ---------------------------------------------------------------------------
# Green prefilter
# ---------------------------------------------------------------------------

class TestGreenTextMask(unittest.TestCase):
    @unittest.skipUnless(np is not None, 'numpy required')
    def test_picks_green_drops_blue_and_white(self):
        frame = np.zeros((3, 3, 3), dtype=np.uint8)
        frame[0, 0] = (60, 180, 60)     # label green -> kept
        frame[1, 1] = (20, 20, 220)     # blue -> dropped
        frame[2, 2] = (230, 230, 230)   # white -> dropped (g-b too small)
        m = campfire.green_text_mask(frame)
        self.assertEqual(int(m[0, 0]), 1)
        self.assertEqual(int(m[1, 1]), 0)
        self.assertEqual(int(m[2, 2]), 0)

    def test_none_input(self):
        self.assertIsNone(campfire.green_text_mask(None))


# ---------------------------------------------------------------------------
# Pure selection: which fish to grill (bait / tool exclusion)
# ---------------------------------------------------------------------------

class TestCampfireFishNames(unittest.TestCase):
    def test_only_campfire_state_selected(self):
        states = {'Carp': 2, 'Eel': 0, 'Zander': 1, 'Salmon': 2}
        self.assertEqual(campfire.campfire_fish_names(states),
                         ['Carp', 'Salmon'])

    def test_baits_and_tools_excluded_even_if_marked(self):
        # Worm / Lagerfeuer / koeder / puzzle boxes can NEVER be grilled.
        states = {
            'Worm': 2, 'Lagerfeuer': 2, 'Koeder': 2, 'Bait': 2,
            'Fischpuzzlebox': 2, 'Fischpuzzlebox_Deluxe': 2,
            'Carp': 2,
        }
        self.assertEqual(campfire.campfire_fish_names(states), ['Carp'])

    def test_empty_and_junk_states(self):
        self.assertEqual(campfire.campfire_fish_names({}), [])
        self.assertEqual(campfire.campfire_fish_names(None), [])

    def test_worm_is_in_non_burnable(self):
        self.assertIn('Worm', campfire.NON_BURNABLE_NAMES)
        self.assertIn('Lagerfeuer', campfire.NON_BURNABLE_NAMES)


class TestFishSlotsToGrill(unittest.TestCase):
    def test_page_order_preserves_scanner_slot_order(self):
        # The function enforces PAGE order (I before II) and, within a page, keeps
        # the scanner's slot order (the real scanner emits slots row-major). Here
        # page II is listed first in the dict but must still come AFTER page I.
        inv = _inv({
            'II': [_slot('Zander', 1, 1)],
            'I': [_slot('Carp', 0, 0), _slot('Carp', 2, 3)],
        })
        self.assertEqual(
            campfire.fish_slots_to_grill(inv, ['Carp', 'Zander']),
            [('I', 0, 0, 'Carp'), ('I', 2, 3, 'Carp'), ('II', 1, 1, 'Zander')])

    def test_excludes_baits_from_targets(self):
        inv = _inv({'I': [_slot('Worm', 0, 0), _slot('Carp', 0, 1)]})
        # Even if Worm sneaks into names, it is dropped here.
        self.assertEqual(
            campfire.fish_slots_to_grill(inv, ['Worm', 'Carp']),
            [('I', 0, 1, 'Carp')])

    def test_empty_when_no_names(self):
        inv = _inv({'I': [_slot('Carp', 0, 0)]})
        self.assertEqual(campfire.fish_slots_to_grill(inv, []), [])


# ---------------------------------------------------------------------------
# locate_fire: rotate-until-found
# ---------------------------------------------------------------------------

class TestLocateFire(unittest.TestCase):
    def test_found_on_first_look_no_rotation(self):
        # find_label is patched to "find" immediately.
        calls = {'rot': 0}

        def cap():
            return 'frame'

        def rot():
            calls['rot'] += 1

        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (100, 200))
        try:
            fire, score, rotations = campfire.locate_fire(
                cap, rotate_fn=rot, sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertEqual(fire, (100 + 20, 200 + 21))
        self.assertEqual(rotations, 0)
        self.assertEqual(calls['rot'], 0)
        self.assertAlmostEqual(score, 0.99)

    def test_rotates_until_found(self):
        # Miss twice, then hit on the 3rd frame -> 2 rotations.
        seq = [(False, 0.2, None), (False, 0.3, None), (True, 0.95, (50, 60))]
        state = {'i': 0}
        calls = {'rot': 0}

        def fake_find(*_a, **_k):
            r = seq[min(state['i'], len(seq) - 1)]
            state['i'] += 1
            return r

        orig = campfire.find_label
        campfire.find_label = fake_find
        try:
            fire, _score, rotations = campfire.locate_fire(
                lambda: 'f', rotate_fn=lambda: calls.__setitem__(
                    'rot', calls['rot'] + 1),
                max_attempts=5, sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertEqual(fire, (50 + 20, 60 + 21))
        self.assertEqual(rotations, 2)
        self.assertEqual(calls['rot'], 2)

    def test_gives_up_after_max_attempts(self):
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (False, 0.1, None)
        try:
            fire, score, rotations = campfire.locate_fire(
                lambda: 'f', rotate_fn=lambda: None,
                max_attempts=3, sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertIsNone(fire)
        self.assertEqual(rotations, 2)        # 1 initial look + 2 rotations
        self.assertAlmostEqual(score, 0.1)

    def test_capture_failure_is_swallowed(self):
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (False, 0.0, None)

        def boom():
            raise RuntimeError('capture down')
        try:
            fire, _score, _rot = campfire.locate_fire(
                boom, rotate_fn=lambda: None, max_attempts=2,
                sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertIsNone(fire)


# ---------------------------------------------------------------------------
# run_campfire orchestration (deps injected)
# ---------------------------------------------------------------------------

class TestRunCampfireOrchestration(unittest.TestCase):
    def _scan_returning(self, inv):
        return lambda: inv

    def test_full_happy_path_places_and_grills(self):
        rec = _Recorder()
        inv = _inv({
            'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)],
            'II': [_slot('Zander', 0, 0)],
        })
        # Patch label-finding so the fire is "found" immediately.
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))
        try:
            res = campfire.run_campfire(
                {'Carp': 2, 'Zander': 2, 'Worm': 2},   # Worm excluded
                inp=rec,
                capture_rgb_fn=lambda: 'frame',
                scan_fn=self._scan_returning(inv),
                offset=(10, 20),
                sleep=_noop_sleep)
        finally:
            campfire.find_label = orig

        self.assertEqual(res.status, 'done')
        # Two fish grilled (Carp + Zander), Worm excluded.
        self.assertEqual(len(res.grilled), 2)
        names = sorted(g[3] for g in res.grilled)
        self.assertEqual(names, ['Carp', 'Zander'])
        self.assertEqual(res.fire_point, (300 + 20, 400 + 21))

        ev = rec.events
        # The campfire tool was placed via a DOUBLE-CLICK before any drag.
        self.assertIn('dclick', [e[0] for e in ev])
        first_dclick = next(i for i, e in enumerate(ev) if e[0] == 'dclick')
        first_down = next(i for i, e in enumerate(ev) if e[0] == 'down')
        self.assertLess(first_dclick, first_down)
        # Bird's-eye key held (keydown 'g' ... keyup 'g').
        self.assertIn(('keydown', 'g'), ev)
        self.assertIn(('keyup', 'g'), ev)
        # Exactly two drags (one down/up pair per fish).
        self.assertEqual([e[0] for e in ev].count('down'), 2)
        self.assertEqual([e[0] for e in ev].count('up'), 2)
        # Every drag ends on the fire SCREEN point (world + offset).
        fire_screen = (300 + 20 + 10, 400 + 21 + 20)
        moves = [e for e in ev if e[0] == 'move']
        ups = [i for i, e in enumerate(ev) if e[0] == 'up']
        for up_i in ups:
            last_move = max(i for i, e in enumerate(ev)
                            if e[0] == 'move' and i < up_i)
            self.assertEqual(ev[last_move][1:], fire_screen)

    def test_stops_grilling_when_fire_expired(self):
        # Feuer-Lebensdauer ~35s: ist die Frist abgelaufen, wird NICHT mehr
        # gegrillt (Fisch-Drag ins Leere vermieden). Sauberer Abschluss 'done'.
        from unittest import mock
        rec = _Recorder()
        inv = _inv({
            'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)],
            'II': [_slot('Zander', 0, 0)],
        })
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))
        try:
            # monotonic: Platzieren bei 0 (Frist=35), erste Loop-Pruefung bei 100
            # (>35) -> sofort Schluss, KEIN Fisch gegrillt.
            with mock.patch.object(campfire.time, 'monotonic',
                                   side_effect=[0.0] + [100.0] * 10):
                res = campfire.run_campfire(
                    {'Carp': 2, 'Zander': 2},
                    inp=rec,
                    capture_rgb_fn=lambda: 'frame',
                    scan_fn=self._scan_returning(inv),
                    offset=(10, 20),
                    sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertEqual(res.status, 'done')
        self.assertEqual(len(res.grilled), 0)        # Frist abgelaufen vor Fisch 1
        # KEIN Fisch-Drag passiert (kein down/up).
        self.assertEqual([e[0] for e in rec.events].count('down'), 0)

    def test_no_fish_marked_short_circuits_without_window_work(self):
        rec = _Recorder()
        called = {'scan': False}

        def scan():
            called['scan'] = True
            return _inv({})

        res = campfire.run_campfire(
            {'Carp': 0, 'Worm': 2},   # nothing in CAMPFIRE except excluded Worm
            inp=rec, capture_rgb_fn=lambda: 'f', scan_fn=scan,
            sleep=_noop_sleep)
        self.assertEqual(res.status, 'no_fish')
        self.assertFalse(called['scan'])         # bailed before scanning
        self.assertEqual(rec.events, [])         # no input at all

    def test_no_campfire_item_in_inventory(self):
        rec = _Recorder()
        inv = _inv({'I': [_slot('Carp', 0, 0)]})   # no Lagerfeuer tool
        res = campfire.run_campfire(
            {'Carp': 2}, inp=rec, capture_rgb_fn=lambda: 'f',
            scan_fn=lambda: inv, sleep=_noop_sleep)
        self.assertEqual(res.status, 'no_campfire_item')
        # Never placed / dragged.
        self.assertNotIn('dclick', [e[0] for e in rec.events])
        self.assertNotIn('down', [e[0] for e in rec.events])

    def test_label_not_found_places_but_does_not_grill(self):
        rec = _Recorder()
        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 1)]})
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (False, 0.2, None)
        try:
            res = campfire.run_campfire(
                {'Carp': 2}, inp=rec, capture_rgb_fn=lambda: 'f',
                scan_fn=lambda: inv, sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        self.assertEqual(res.status, 'label_not_found')
        # The tool WAS placed (double-clicked) ...
        self.assertIn('dclick', [e[0] for e in rec.events])
        # ... but no fish was dragged (no mouse-down for a drag).
        self.assertEqual([e[0] for e in rec.events].count('down'), 0)

    def test_scan_failure_returns_error(self):
        rec = _Recorder()
        res = campfire.run_campfire(
            {'Carp': 2}, inp=rec, capture_rgb_fn=lambda: 'f',
            scan_fn=lambda: None, sleep=_noop_sleep)
        self.assertEqual(res.status, 'error')

    def test_drag_failure_does_not_crash(self):
        # An input api whose moveTo blows up mid-drag must still release + the
        # run must finish defensively (no exception escapes).
        class _Boom(_Recorder):
            def moveTo(self, x, y):
                super().moveTo(x, y)
                if [e[0] for e in self.events].count('move') > 3:
                    raise RuntimeError('boom')
        rec = _Boom()
        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 1)]})
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (100, 100))
        try:
            res = campfire.run_campfire(
                {'Carp': 2}, inp=rec, capture_rgb_fn=lambda: 'f',
                scan_fn=lambda: inv, sleep=_noop_sleep)
        finally:
            campfire.find_label = orig
        # Even with a drag error, the button is released in drag()'s finally.
        self.assertIn(('up',), rec.events)
        self.assertIn(res.status, ('done', 'error'))


# ---------------------------------------------------------------------------
# _slot_screen / drag honour the LOCKED lattice (FIX 1+2)
# ---------------------------------------------------------------------------

class TestSlotScreenLattice(unittest.TestCase):
    """The drag SOURCE + tool double-click must hit the LOCKED grid, not the raw
    (un-aligned) DEFAULT_CALIBRATION that grabs ~1 slot too low."""

    def test_lattice_none_matches_calibration_lattice(self):
        # With lattice=None the historical calibration-lattice maths is kept
        # byte-identical (the headless-test fallback).
        lat = lattice_from_calibration(DEFAULT_CALIBRATION)
        ox, oy = lat.origin
        px, py = lat.pitch
        for (row, col) in ((0, 0), (1, 2), (8, 4)):
            exp = (100 + ox + col * px + px // 2, 200 + oy + row * py + py // 2)
            self.assertEqual(
                campfire._slot_screen(row, col, DEFAULT_CALIBRATION, 100, 200),
                exp)

    def test_locked_lattice_origin_pitch_used(self):
        # A locked lattice (e.g. from auto_align) -> its origin/pitch drive the
        # slot centre, NOT the calibration grid. The user's bag sits ~30px (≈1
        # slot) higher than DEFAULT_CALIBRATION; this is exactly that correction.
        locked = GridLattice(origin=(632, 245), pitch=(32, 32))
        # slot (1,2): x = 632 + 2*32 + 16 = 712 ; y = 245 + 1*32 + 16 = 293
        self.assertEqual(
            campfire._slot_screen(1, 2, DEFAULT_CALIBRATION, 1000, 500,
                                  lattice=locked),
            (1000 + 712, 500 + 293))
        # And it differs from the raw-calibration result (proves the fix bites).
        raw = campfire._slot_screen(1, 2, DEFAULT_CALIBRATION, 1000, 500)
        self.assertNotEqual(raw,
                            campfire._slot_screen(1, 2, DEFAULT_CALIBRATION,
                                                  1000, 500, lattice=locked))

    def test_find_item_slot_threads_lattice(self):
        locked = GridLattice(origin=(632, 245), pitch=(32, 32))
        inv = _inv({'I': [_slot('Lagerfeuer', 1, 2)]})
        page, xy = campfire._find_item_slot(inv, 'Lagerfeuer',
                                            DEFAULT_CALIBRATION, 1000, 500,
                                            lattice=locked)
        self.assertEqual(page, 'I')
        self.assertEqual(xy, (1000 + 712, 500 + 293))

    def test_run_campfire_drags_from_locked_grid(self):
        # End-to-end: a locked lattice passed to run_campfire must place the
        # drag SOURCE (and the tool double-click) on the LOCKED grid.
        rec = _Recorder()
        locked = GridLattice(origin=(632, 245), pitch=(32, 32))
        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)]})
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))
        try:
            res = campfire.run_campfire(
                {'Carp': 2}, inp=rec, capture_rgb_fn=lambda: 'frame',
                scan_fn=lambda: inv, offset=(1000, 500),
                sleep=_noop_sleep, lattice=locked)
        finally:
            campfire.find_label = orig
        self.assertEqual(res.status, 'done')
        ev = rec.events
        # The Carp drag SOURCE = locked slot (1,2) + offset = (1712, 793).
        down_idx = next(i for i, e in enumerate(ev) if e[0] == 'down')
        self.assertEqual(ev[down_idx - 1], ('move', 1712, 793))
        # The tool was double-clicked at the locked slot (0,0) = (648, 761).
        # x = 632 + 16 = 648 ; y = 245 + 16 = 261 ; + offset (1000,500).
        self.assertIn(('dclick', 1000 + 648, 500 + 261), ev)


# ---------------------------------------------------------------------------
# drag primitive (mirrors refill.drag contract)
# ---------------------------------------------------------------------------

class TestDrag(unittest.TestCase):
    def test_press_hold_move_release(self):
        rec = _Recorder()
        campfire.drag(rec, 10, 20, 110, 70, steps=5, sleep=_noop_sleep)
        ev = rec.events
        self.assertEqual(ev[0], ('move', 10, 20))
        self.assertEqual(ev[1], ('down',))
        self.assertEqual(ev[-1], ('up',))
        moves = [e for e in ev if e[0] == 'move']
        self.assertEqual(moves[-1], ('move', 110, 70))

    def test_releases_even_if_move_raises(self):
        class _Boom(_Recorder):
            def moveTo(self, x, y):
                if len(self.events) > 2:
                    raise RuntimeError('boom')
                super().moveTo(x, y)
        rec = _Boom()
        try:
            campfire.drag(rec, 0, 0, 50, 50, steps=4, sleep=_noop_sleep)
        except RuntimeError:
            pass
        self.assertIn(('up',), rec.events)


if __name__ == '__main__':
    unittest.main()
