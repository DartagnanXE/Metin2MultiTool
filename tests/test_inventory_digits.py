# -*- coding: utf-8 -*-
"""Headless tests for the stack-number reader (:mod:`inventory.digits`).

The end-to-end real-font accuracy (1..20 in the game's small AND large stack
fonts) is validated manually against the calibration screenshots and frozen as
bundled templates; here we lock the DECODE PIPELINE (band white-masking,
fixed-width try-all-n segmentation, NCC matching, multi-digit assembly, the
no-number = single-item case, and graceful degradation) on synthetic slots so it
runs anywhere without shipping a screenshot.
"""

import os
import unittest

try:
    import numpy as np
except Exception:
    np = None

try:
    from PIL import Image, ImageFont, ImageDraw
except Exception:
    Image = None

from inventory import digits
from inventory.constants import SLOT_PX

_CONSOLA = r'C:\Windows\Fonts\consola.ttf'


def _have_deps():
    return np is not None and Image is not None and bool(digits._load_templates())


def _slot_with_number(num, size=14, font_path=_CONSOLA):
    """A dark SLOT_PX slot with ``num`` drawn white, bottom-right (game style)."""
    img = Image.new('RGB', (SLOT_PX, SLOT_PX), (18, 16, 14))
    font = ImageFont.truetype(font_path, size)
    draw = ImageDraw.Draw(img)
    s = str(num)
    box = draw.textbbox((0, 0), s, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text((SLOT_PX - 1 - w - box[0], SLOT_PX - 1 - h - box[1]), s,
              fill=(255, 255, 255), font=font)
    return np.asarray(img, dtype=np.float32)


@unittest.skipUnless(_have_deps() and os.path.exists(_CONSOLA),
                     'numpy/PIL/templates/consola required')
class TestReadCountRendered(unittest.TestCase):
    def test_single_digits_0_to_9(self):
        # Render with a digit BAR so a lone digit still has a band; 1..9 + 0.
        for d in list(range(1, 10)) + [0]:
            cr = digits.read_count(_slot_with_number(d))
            self.assertEqual(cr.value, d, 'misread single digit %d -> %s'
                             % (d, cr.value))

    def test_multi_digit_numbers(self):
        for n in (10, 16, 20, 25, 42, 99, 138, 200, 999, 1234):
            cr = digits.read_count(_slot_with_number(n))
            self.assertEqual(cr.value, n, 'misread %d -> %s' % (n, cr.value))
            self.assertEqual(cr.n_digits, len(str(n)))

    def test_a_confident_read_is_flagged_confident(self):
        cr = digits.read_count(_slot_with_number(200))
        self.assertTrue(cr.confident)
        self.assertGreaterEqual(cr.confidence, digits.CONF_MIN)


@unittest.skipUnless(np is not None, 'numpy required')
class TestReadCountEdgeCases(unittest.TestCase):
    def test_empty_band_is_single_item(self):
        # A dark slot with no white digit ink -> a single, unstacked item.
        slot = np.full((SLOT_PX, SLOT_PX, 3), 16.0, dtype=np.float32)
        cr = digits.read_count(slot)
        self.assertEqual(cr.value, 1)
        self.assertEqual(cr.n_digits, 0)
        self.assertTrue(cr.confident)

    def test_none_and_bad_shapes_never_raise(self):
        for bad in (None, np.zeros((4, 4), dtype=np.float32),
                    np.zeros((SLOT_PX, SLOT_PX, 1), dtype=np.float32)):
            cr = digits.read_count(bad)
            self.assertIsNone(cr.value)
            self.assertFalse(cr.confident)

    def test_degrades_without_numpy(self):
        saved = digits.np
        try:
            digits.np = None
            cr = digits.read_count(np.zeros((SLOT_PX, SLOT_PX, 3)))
            self.assertIsNone(cr.value)
        finally:
            digits.np = saved


class TestTemplatesAndHelpers(unittest.TestCase):
    @unittest.skipUnless(_have_deps(), 'numpy/PIL/templates required')
    def test_templates_cover_all_ten_digits(self):
        tmpl = digits._load_templates()
        self.assertEqual(set(tmpl.keys()), set(range(10)))
        for d in range(10):
            self.assertGreater(len(tmpl[d]), 0)

    @unittest.skipUnless(np is not None, 'numpy required')
    def test_white_mask_and_ink_bbox(self):
        band = np.zeros((10, 32, 3), dtype=np.float32)
        band[3:7, 5:9, :] = 255.0
        mask = digits._white_mask(band)
        self.assertGreater(mask.max(), 0.9)
        bb = digits._ink_bbox(mask)
        self.assertIsNotNone(bb)
        x0, x1, y0, y1 = bb
        self.assertTrue(x0 <= 5 and x1 >= 9 and y0 <= 3 and y1 >= 7)
        self.assertIsNone(digits._ink_bbox(np.zeros((10, 32), dtype=np.float32)))


if __name__ == '__main__':
    unittest.main()
