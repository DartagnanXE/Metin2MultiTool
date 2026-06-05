# -*- coding: utf-8 -*-
"""Tests for the Wegwerfen / fallen lassen (inventory_discard).

Two layers, all headless (no game, no live deps -- everything injected):

  * PURE SELECTION + GEOMETRY: only REMOVE-marked items are dropped, with baits /
    koeder / the campfire tool / puzzle boxes EXCLUDED even when (wrongly) marked;
    the slot list follows the documented page-then-row-major order; the world
    drop point is origin-relative ``(origin_x - 32, origin_y + 16)`` and the
    centred-dialog "Ja" button is the hard-measured ~(352, 316) on an 800x600
    client.
  * ORCHESTRATION with the live deps INJECTED (a recorder input api + synthetic
    capture/scan): one drag per removed item INTO the world followed by a confirm
    "Ja" click all fire in the right sequence; and every failure mode short-
    circuits to a clear status without raising (incl. a drag that blows up mid-
    move still releasing the mouse button).
"""

import types
import unittest

import inventory_discard as discard
from inventory.grid import GridLattice
from inventory.constants import DEFAULT_CALIBRATION, SLOT_PX


def _slot(name, row, col, state='item'):
    return types.SimpleNamespace(state=state, name=name, row=row, col=col)


def _inv(pages):
    return types.SimpleNamespace(pages=pages)


def _noop_sleep(*_a, **_k):
    return None


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

    def keyDown(self, key):
        self.events.append(('keydown', key))

    def keyUp(self, key):
        self.events.append(('keyup', key))


# ---------------------------------------------------------------------------
# Pure selection: which items to discard (bait / tool / box exclusion)
# ---------------------------------------------------------------------------

class TestDiscardItemNames(unittest.TestCase):
    def test_only_remove_state_selected(self):
        # KEEP=0, REMOVE=1, CAMPFIRE=2 -> only the REMOVE items.
        states = {'Carp': 1, 'Eel': 0, 'Zander': 2, 'Gold_Ring': 1}
        self.assertEqual(discard.discard_item_names(states),
                         ['Carp', 'Gold_Ring'])

    def test_baits_tools_boxes_excluded_even_if_marked(self):
        # Worm / Lagerfeuer / koeder / puzzle boxes can NEVER be dropped.
        states = {
            'Worm': 1, 'Lagerfeuer': 1, 'Koeder': 1, 'Bait': 1,
            'Fischpuzzlebox': 1, 'Fischpuzzlebox_Deluxe': 1,
            'Carp': 1,
        }
        self.assertEqual(discard.discard_item_names(states), ['Carp'])

    def test_koeder_umlaut_excluded(self):
        self.assertEqual(discard.discard_item_names({'Köder': 1, 'Eel': 1}),
                         ['Eel'])

    def test_empty_and_junk_states(self):
        self.assertEqual(discard.discard_item_names({}), [])
        self.assertEqual(discard.discard_item_names(None), [])

    def test_denylist_contains_tools_and_boxes(self):
        for n in ('Worm', 'Lagerfeuer', 'Fischpuzzlebox',
                  'Fischpuzzlebox_Deluxe', 'Köder'):
            self.assertIn(n, discard.NON_DISCARDABLE_NAMES)


class TestItemSlotsToDiscard(unittest.TestCase):
    def test_page_order_preserves_scanner_slot_order(self):
        # PAGE order (I before II) and, within a page, the scanner's slot order.
        # Page II is listed first in the dict but must still come AFTER page I.
        inv = _inv({
            'II': [_slot('Zander', 1, 1)],
            'I': [_slot('Carp', 0, 0), _slot('Gold_Ring', 2, 3)],
        })
        self.assertEqual(
            discard.item_slots_to_discard(inv, ['Carp', 'Zander', 'Gold_Ring']),
            [('I', 0, 0, 'Carp'), ('I', 2, 3, 'Gold_Ring'),
             ('II', 1, 1, 'Zander')])

    def test_excludes_baits_from_targets(self):
        inv = _inv({'I': [_slot('Worm', 0, 0), _slot('Carp', 0, 1)]})
        # Even if Worm sneaks into names, it is dropped here.
        self.assertEqual(
            discard.item_slots_to_discard(inv, ['Worm', 'Carp']),
            [('I', 0, 1, 'Carp')])

    def test_empty_when_no_names(self):
        inv = _inv({'I': [_slot('Carp', 0, 0)]})
        self.assertEqual(discard.item_slots_to_discard(inv, []), [])

    def test_ignores_non_item_slots(self):
        inv = _inv({'I': [_slot('Carp', 0, 0, state='empty'),
                          _slot('Carp', 0, 1, state='item')]})
        self.assertEqual(discard.item_slots_to_discard(inv, ['Carp']),
                         [('I', 0, 1, 'Carp')])


# ---------------------------------------------------------------------------
# World / dialog geometry (pure)
# ---------------------------------------------------------------------------

class TestDropPoint(unittest.TestCase):
    def test_origin_relative_left_of_panel(self):
        lat = GridLattice(origin=(632, 245), pitch=(32, 32))
        # World drop point = (origin_x - 32, origin_y + SLOT_PX//2), no offset.
        self.assertEqual(discard.drop_point(lat),
                         (632 - 32, 245 + SLOT_PX // 2))

    def test_offset_added(self):
        lat = GridLattice(origin=(600, 240), pitch=(32, 32))
        self.assertEqual(discard.drop_point(lat, offset=(10, 20)),
                         (10 + 600 - 32, 20 + 240 + SLOT_PX // 2))

    def test_none_lattice_returns_none(self):
        self.assertIsNone(discard.drop_point(None))

    def test_drop_offset_constant(self):
        self.assertEqual(discard.DROP_OFFSET_FROM_ORIGIN, (-32, SLOT_PX // 2))


class TestConfirmYesPoint(unittest.TestCase):
    def test_measured_800x600(self):
        # The centred dialog's "Ja" on the 800x600 client = (352, 316).
        self.assertEqual(discard.confirm_yes_point(800, 600), (352, 316))

    def test_offset_added(self):
        self.assertEqual(discard.confirm_yes_point(800, 600, offset=(5, 7)),
                         (352 + 5, 316 + 7))

    def test_calibration_client_size_consistent(self):
        # Sanity: the bundled calibration client (~799x602) lands near (352,316).
        cw, ch = DEFAULT_CALIBRATION['client']
        x, y = discard.confirm_yes_point(cw, ch)
        self.assertEqual(x, cw // 2 - 48)
        self.assertEqual(y, ch // 2 + 16)

    def test_bad_size_does_not_raise(self):
        # A junk client size degrades to the centre maths (0,0 -> offset only).
        self.assertEqual(discard.confirm_yes_point(None, None, offset=(3, 4)),
                         (3 - 48, 4 + 16))


# ---------------------------------------------------------------------------
# _slot_screen: prefers the LOCKED lattice over raw calibration
# ---------------------------------------------------------------------------

class TestSlotScreen(unittest.TestCase):
    def test_uses_injected_locked_lattice(self):
        lat = GridLattice(origin=(632, 245), pitch=(32, 32))
        # Slot (0,0) centre = origin + pitch//2 (+ offset).
        self.assertEqual(
            discard._slot_screen(0, 0, DEFAULT_CALIBRATION, 0, 0, lattice=lat),
            (632 + 16, 245 + 16))

    def test_falls_back_to_calibration_when_no_lattice(self):
        # Without a locked lattice it derives from DEFAULT_CALIBRATION (origin
        # 633,244 -- the live client grid corner). This is the un-aligned path.
        self.assertEqual(
            discard._slot_screen(0, 0, DEFAULT_CALIBRATION, 0, 0),
            (633 + 16, 244 + 16))

    def test_offset_added(self):
        lat = GridLattice(origin=(600, 240), pitch=(32, 32))
        self.assertEqual(
            discard._slot_screen(1, 2, DEFAULT_CALIBRATION, 10, 20, lattice=lat),
            (10 + 600 + 2 * 32 + 16, 20 + 240 + 1 * 32 + 16))


# ---------------------------------------------------------------------------
# run_discard orchestration (deps injected)
# ---------------------------------------------------------------------------

class TestRunDiscardOrchestration(unittest.TestCase):
    def _lat(self):
        return GridLattice(origin=(600, 240), pitch=(32, 32))

    def test_full_happy_path_drags_and_confirms(self):
        rec = _Recorder()
        inv = _inv({
            'I': [_slot('Carp', 1, 2), _slot('Worm', 0, 0)],   # Worm excluded
            'II': [_slot('Gold_Ring', 0, 0)],
        })
        res = discard.run_discard(
            {'Carp': 1, 'Gold_Ring': 1, 'Worm': 1},
            inp=rec,
            capture_fn=lambda: 'frame',
            scan_fn=lambda: inv,
            client_size=(800, 600),
            offset=(10, 20),
            lattice=self._lat(),
            sleep=_noop_sleep)

        self.assertEqual(res.status, 'done')
        # Two items dropped (Carp + Gold_Ring), Worm excluded.
        self.assertEqual(len(res.dropped), 2)
        names = sorted(d[3] for d in res.dropped)
        self.assertEqual(names, ['Carp', 'Gold_Ring'])
        # Drop point = world left of panel + offset.
        self.assertEqual(res.drop_point, (10 + 600 - 32, 20 + 240 + 16))

        ev = rec.events
        # Exactly two drags (one down/up pair per item).
        self.assertEqual([e[0] for e in ev].count('down'), 2)
        self.assertEqual([e[0] for e in ev].count('up'), 2)
        # Every drag ENDS on the world drop point (last move before each up).
        world = (10 + 600 - 32, 20 + 240 + 16)
        ups = [i for i, e in enumerate(ev) if e[0] == 'up']
        for up_i in ups:
            last_move = max(i for i, e in enumerate(ev)
                            if e[0] == 'move' and i < up_i)
            self.assertEqual(ev[last_move][1:], world)
        # The confirm "Ja" is clicked AFTER each drag's release, at (352,316)+off.
        yes = (10 + 352, 20 + 316)
        yes_clicks = [i for i, e in enumerate(ev)
                      if e[0] == 'click' and e[1:] == yes]
        self.assertEqual(len(yes_clicks), 2)
        # Ordering: 1st up < 1st yes-click < 2nd up (drag, confirm, drag, ...).
        self.assertLess(ups[0], yes_clicks[0])
        self.assertLess(yes_clicks[0], ups[1])

    def test_no_items_marked_short_circuits_without_window_work(self):
        rec = _Recorder()
        called = {'scan': False}

        def scan():
            called['scan'] = True
            return _inv({})

        res = discard.run_discard(
            {'Carp': 0, 'Worm': 1},   # nothing in REMOVE except excluded Worm
            inp=rec, capture_fn=lambda: 'f', scan_fn=scan,
            client_size=(800, 600), sleep=_noop_sleep)
        self.assertEqual(res.status, 'no_items')
        self.assertFalse(called['scan'])         # bailed before scanning
        self.assertEqual(rec.events, [])         # no input at all

    def test_no_matching_slots_returns_no_items(self):
        rec = _Recorder()
        inv = _inv({'I': [_slot('Eel', 0, 0)]})   # marked Carp not present
        res = discard.run_discard(
            {'Carp': 1}, inp=rec, capture_fn=lambda: 'f',
            scan_fn=lambda: inv, client_size=(800, 600), sleep=_noop_sleep)
        self.assertEqual(res.status, 'no_items')
        # Never dragged / confirmed.
        self.assertNotIn('down', [e[0] for e in rec.events])
        self.assertNotIn('click', [e[0] for e in rec.events])

    def test_scan_failure_returns_error(self):
        rec = _Recorder()
        res = discard.run_discard(
            {'Carp': 1}, inp=rec, capture_fn=lambda: 'f',
            scan_fn=lambda: None, client_size=(800, 600), sleep=_noop_sleep)
        self.assertEqual(res.status, 'error')
        self.assertEqual(rec.events, [])         # nothing dragged

    def test_drag_failure_releases_button_and_does_not_crash(self):
        # An input api whose moveTo blows up mid-drag must still release + the
        # run must finish defensively (no exception escapes).
        class _Boom(_Recorder):
            def moveTo(self, x, y):
                super().moveTo(x, y)
                if [e[0] for e in self.events].count('move') > 3:
                    raise RuntimeError('boom')
        rec = _Boom()
        inv = _inv({'I': [_slot('Carp', 1, 1)]})
        res = discard.run_discard(
            {'Carp': 1}, inp=rec, capture_fn=lambda: 'f',
            scan_fn=lambda: inv, client_size=(800, 600),
            lattice=self._lat(), sleep=_noop_sleep)
        # Even with a drag error, the button is released in drag()'s finally.
        self.assertIn(('up',), rec.events)
        self.assertIn(res.status, ('done', 'error'))

    def test_falls_back_to_calibration_lattice_when_none(self):
        # With NO injected lattice the drag source derives from DEFAULT_CALIBRATION
        # (origin 633,244) -- the run still completes + confirms.
        rec = _Recorder()
        inv = _inv({'I': [_slot('Carp', 0, 0)]})
        res = discard.run_discard(
            {'Carp': 1}, inp=rec, capture_fn=lambda: 'f',
            scan_fn=lambda: inv, client_size=(800, 600), offset=(0, 0),
            sleep=_noop_sleep)
        self.assertEqual(res.status, 'done')
        # Drop point uses the calibration origin (633) when no lattice is locked.
        self.assertEqual(res.drop_point, (633 - 32, 244 + 16))

    def test_capture_fn_may_be_none(self):
        # The pure flow does not need capture_fn; None must not break it.
        rec = _Recorder()
        inv = _inv({'I': [_slot('Carp', 0, 0)]})
        res = discard.run_discard(
            {'Carp': 1}, inp=rec, capture_fn=None,
            scan_fn=lambda: inv, client_size=(800, 600),
            lattice=self._lat(), sleep=_noop_sleep)
        self.assertEqual(res.status, 'done')


# ---------------------------------------------------------------------------
# drag primitive (mirrors campfire.drag contract)
# ---------------------------------------------------------------------------

class TestDrag(unittest.TestCase):
    def test_press_hold_move_release(self):
        rec = _Recorder()
        discard.drag(rec, 10, 20, 110, 70, steps=5, sleep=_noop_sleep)
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
            discard.drag(rec, 0, 0, 50, 50, steps=4, sleep=_noop_sleep)
        except RuntimeError:
            pass
        self.assertIn(('up',), rec.events)


if __name__ == '__main__':
    unittest.main()
