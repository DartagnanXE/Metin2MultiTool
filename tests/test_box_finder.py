# -*- coding: utf-8 -*-
"""Tests fuer den dedizierten Puzzle-Box-Finder (interface.refill.find_box_slot).

Kalibriert/validiert am echten Client-Screenshot (2026-06-17): am FESTEN
Kalibrier-Grid abtasten (kein Auto-Align -- der lockt ~10px daneben) + nur die
OBERE Icon-Haelfte matchen (untere traegt die grosse Stueckzahl). Diese Tests
bauen synthetische Frames mit dem echten Box-Template am bekannten Slot.
"""

import os
import unittest

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from interface import refill
from inventory.constants import DEFAULT_CALIBRATION
from inventory.grid import lattice_from_calibration
from respath import resource_path


def _slot_center(row, col):
    lat = lattice_from_calibration(DEFAULT_CALIBRATION)
    ox, oy = lat.origin
    px, py = lat.pitch
    return int(ox + col * px + px // 2), int(oy + row * py + py // 2)


def _frame_with_box(row, col, name='Fischpuzzlebox', stack_noise=False):
    """600x800 BGR-Frame, dunkler Hintergrund, echtes Box-Icon am Slot (row,col).
    ``stack_noise`` malt helle Pixel in die UNTERE Icon-Haelfte (simuliert die
    grosse Stueckzahl) -> der Finder muss trotzdem matchen (obere Haelfte)."""
    frame = np.full((600, 800, 3), 12, np.uint8)
    tpl = cv2.imread(resource_path(os.path.join('inventory_icons', name + '.png')),
                     cv2.IMREAD_UNCHANGED)
    bgr = tpl[:, :, :3]
    alpha = tpl[:, :, 3]
    th, tw = bgr.shape[:2]
    cx, cy = _slot_center(row, col)
    y0, x0 = cy - th // 2, cx - tw // 2
    region = frame[y0:y0 + th, x0:x0 + tw]
    m = alpha > 32
    region[m] = bgr[m]
    if stack_noise:
        region[th // 2:, :] = 240   # untere Haelfte hell ueberschreiben
    return frame


@unittest.skipIf(cv2 is None, 'cv2 nicht verfuegbar')
class BoxFinderTest(unittest.TestCase):
    def test_finds_standard_box_at_exact_slot(self):
        frame = _frame_with_box(4, 2, 'Fischpuzzlebox')
        loc = refill.find_box_slot(lambda: frame, lambda p: None, ('Fischpuzzlebox',))
        self.assertIsNotNone(loc)
        _page, row, col, name = loc
        self.assertEqual((row, col, name), (4, 2, 'Fischpuzzlebox'))

    def test_matches_despite_stack_number_in_lower_half(self):
        # Genau der Client-Fall: grosse Stueckzahl in der unteren Haelfte.
        frame = _frame_with_box(4, 2, 'Fischpuzzlebox', stack_noise=True)
        loc = refill.find_box_slot(lambda: frame, lambda p: None, ('Fischpuzzlebox',))
        self.assertIsNotNone(loc, 'Box muss trotz Stueckzahl erkannt werden')
        self.assertEqual(loc[1:], (4, 2, 'Fischpuzzlebox'))

    def test_empty_inventory_returns_none(self):
        frame = np.full((600, 800, 3), 12, np.uint8)
        self.assertIsNone(
            refill.find_box_slot(lambda: frame, lambda p: None, ('Fischpuzzlebox',)))

    def test_returns_first_in_row_major_order(self):
        # Zwei Boxen: (4,2) und (1,0) -> der frueheste (row-major) gewinnt.
        frame = _frame_with_box(4, 2, 'Fischpuzzlebox')
        # zweite Box an (1,0) einbauen
        tpl = cv2.imread(resource_path(os.path.join('inventory_icons',
                         'Fischpuzzlebox.png')), cv2.IMREAD_UNCHANGED)
        bgr, alpha = tpl[:, :, :3], tpl[:, :, 3]
        cx, cy = _slot_center(1, 0)
        reg = frame[cy - 16:cy + 16, cx - 16:cx + 16]
        reg[alpha > 32] = bgr[alpha > 32]
        loc = refill.find_box_slot(lambda: frame, lambda p: None, ('Fischpuzzlebox',))
        self.assertEqual(loc[1:], (1, 0, 'Fischpuzzlebox'))


def _open_grid_frame():
    """Frame mit periodischer Slot-Struktur: helle Slot-Innenflaechen, dunkle
    Raender -> ``inventory_looks_open`` muss True liefern."""
    frame = np.zeros((600, 800, 3), np.uint8)
    lat = lattice_from_calibration(DEFAULT_CALIBRATION)
    ox, oy = lat.origin
    px, py = lat.pitch
    for row in range(9):
        for col in range(5):
            y = int(oy + row * py)
            x = int(ox + col * px)
            frame[y + 2:y + px - 2, x + 2:x + px - 2] = 110   # helle Slot-Innenflaeche
    return frame


@unittest.skipIf(cv2 is None, 'cv2 nicht verfuegbar')
class InventoryOpenCheckTest(unittest.TestCase):
    def test_detects_open_grid(self):
        is_open, diff = refill.inventory_looks_open(_open_grid_frame())
        self.assertTrue(is_open)
        self.assertGreater(diff, refill.INVENTORY_OPEN_MIN_DIFF)

    def test_uniform_frame_not_open(self):
        frame = np.full((600, 800, 3), 90, np.uint8)   # gleichmaessig (Spielwelt-aehnlich)
        is_open, _diff = refill.inventory_looks_open(frame)
        self.assertFalse(is_open)


@unittest.skipIf(cv2 is None, 'cv2 nicht verfuegbar')
class BoxRefillToggleTest(unittest.TestCase):
    class _Inp:
        PAUSE = 0

        def __init__(self):
            self.events = []

        def moveTo(self, x, y):
            self.events.append(('move', x, y))

        def mouseDown(self, **k):
            self.events.append(('down',))

        def mouseUp(self, **k):
            self.events.append(('up',))

        def click(self, **k):
            self.events.append(('click',))

    def test_opens_when_closed_then_places(self):
        # Erst geschlossen (gleichmaessig), nach open_toggle_fn offen (Grid+Box).
        closed = np.full((600, 800, 3), 90, np.uint8)
        open_box = _open_grid_frame()
        # echte Box ins offene Frame an Slot (4,2) setzen
        tpl = cv2.imread(resource_path(os.path.join('inventory_icons',
                         'Fischpuzzlebox.png')), cv2.IMREAD_UNCHANGED)
        bgr, alpha = tpl[:, :, :3], tpl[:, :, 3]
        cx, cy = _slot_center(4, 2)
        reg = open_box[cy - 16:cy + 16, cx - 16:cx + 16]
        reg[alpha > 32] = bgr[alpha > 32]
        state = {'open': False}

        def capture():
            return open_box if state['open'] else closed

        toggles = {'n': 0}

        def toggle():
            toggles['n'] += 1
            state['open'] = True   # Hotkey oeffnet die (geschlossene) Tasche

        wc = type('W', (), {'offset_x': 0, 'offset_y': 0,
                            'get_screenshot': staticmethod(capture)})()
        inp = self._Inp()
        res = refill.box_refill_from_inventory(
            ('Fischpuzzlebox',), (503, 328), inp=inp, wincap=wc,
            open_toggle_fn=toggle, sleep=lambda s: None)
        self.assertEqual(res, 'dragged')
        self.assertGreaterEqual(toggles['n'], 1)   # Tasche wurde geoeffnet
        self.assertIn(('click',), inp.events)       # Zwei-Klick-Move (aufnehmen+setzen)
        self.assertNotIn(('down',), inp.events)     # KEIN Drag mehr (Box->Box-Slot ist UI)
        self.assertNotIn(('up',), inp.events)

    def test_never_opens_returns_empty_without_blind_clicks(self):
        closed = np.full((600, 800, 3), 90, np.uint8)
        wc = type('W', (), {'offset_x': 0, 'offset_y': 0,
                            'get_screenshot': staticmethod(lambda: closed)})()
        inp = self._Inp()
        res = refill.box_refill_from_inventory(
            ('Fischpuzzlebox',), (503, 328), inp=inp, wincap=wc,
            open_toggle_fn=lambda: None, sleep=lambda s: None)
        self.assertEqual(res, 'empty')
        # Bleibt das Inventar zu, wird NICHT blind in die Tabs/Welt geklickt.
        self.assertNotIn(('click',), inp.events)


if __name__ == '__main__':
    unittest.main()
