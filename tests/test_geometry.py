"""Tests fuer die skalierbare Board-Geometrie (geometry.py).

Kern-Anforderung: bei Referenzgroesse (260x170) MUSS die Geometrie BYTE-IDENTISCH
zu den bisher hartkodierten Werten sein (Default-Pfad in puzzle.py unveraendert).
Zusaetzlich: korrekte lineare Skalierung fuer abweichende Groessen.
"""

import unittest

import geometry as g


class TestReferenceIdentity(unittest.TestCase):
    def test_grid_points_identical_to_hardcoded(self):
        expected = [(15 + 32 * j, 15 + 32 * i)
                    for i in range(4) for j in range(6)]
        self.assertEqual(g.grid_points(g.REF_SIZE), expected)

    def test_cell_point_identity(self):
        for i in range(4):
            for j in range(6):
                self.assertEqual(g.cell_point(i, j, g.REF_SIZE),
                                 (15 + 32 * j, 15 + 32 * i))

    def test_key_points_identity(self):
        self.assertEqual(g.color_sample(g.REF_SIZE), (110, 150))
        self.assertEqual(g.get_piece_point(g.REF_SIZE), (230, 85))
        self.assertEqual(g.confirm_point(g.REF_SIZE), (100, 90))
        self.assertEqual(g.cake_point(g.REF_SIZE), (120, 90))


class TestScaling(unittest.TestCase):
    def test_double_size_doubles_points(self):
        size = (520, 340)  # exakt 2x
        self.assertEqual(g.color_sample(size), (220, 300))
        self.assertEqual(g.get_piece_point(size), (460, 170))
        self.assertEqual(g.confirm_point(size), (200, 180))
        self.assertEqual(g.cell_point(0, 0, size), (30, 30))
        self.assertEqual(g.cell_point(3, 5, size), (350, 222))

    def test_grid_has_24_points(self):
        self.assertEqual(len(g.grid_points((400, 250))), 24)

    def test_points_are_ints(self):
        for (x, y) in g.grid_points((333, 211)):
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)


class TestKeypointOverride(unittest.TestCase):
    """Optionaler ref-Override an den 4 Sonderpunkt-Funktionen.

    ref=None MUSS exakt die Default-Konstante liefern (byte-stabil); ein
    gesetzter Override ersetzt die Konstante und wird mit size skaliert.
    """

    def test_none_override_is_default_identity(self):
        # ref=None == kein Argument == REF_*-Konstante (byte-stabil).
        for fn, expected in (
            (g.color_sample, (110, 150)),
            (g.get_piece_point, (230, 85)),
            (g.confirm_point, (100, 90)),
            (g.cake_point, (120, 90)),
        ):
            self.assertEqual(fn(g.REF_SIZE), expected)
            self.assertEqual(fn(g.REF_SIZE, None), expected)
            self.assertEqual(fn(g.REF_SIZE, ref=None), expected)
            # ref=None auch bei abweichender Groesse == Default-Pfad.
            self.assertEqual(fn((520, 340)), fn((520, 340), None))

    def test_explicit_override_replaces_constant_at_ref_size(self):
        # Bei REF_SIZE ist scale_point die Identitaet -> Override 1:1.
        self.assertEqual(g.color_sample(g.REF_SIZE, (40, 60)), (40, 60))
        self.assertEqual(g.get_piece_point(g.REF_SIZE, ref=(200, 30)), (200, 30))
        self.assertEqual(g.confirm_point(g.REF_SIZE, (90, 100)), (90, 100))
        self.assertEqual(g.cake_point(g.REF_SIZE, (130, 100)), (130, 100))

    def test_explicit_override_is_scaled_by_size(self):
        # Doppelte Groesse -> Override-Referenz verdoppelt (wie scale_point).
        size = (520, 340)  # exakt 2x
        self.assertEqual(g.color_sample(size, (40, 60)), (80, 120))
        self.assertEqual(g.get_piece_point(size, (200, 30)), (400, 60))
        self.assertEqual(g.confirm_point(size, (100, 90)), (200, 180))
        self.assertEqual(g.cake_point(size, (15, 15)), (30, 30))


class TestCropFromGridCorners(unittest.TestCase):
    def test_default_corners_yield_default_crop(self):
        # Default-Markierung: gridTL=Mitte Zelle(0,0), gridBR=Mitte Zelle(3,5)
        # bei Default-Offset(270,227)+Groesse(260,170).
        #   gridTL = (270+15, 227+15)            = (285, 242)
        #   gridBR = (270+15+160, 227+15+96)     = (445, 338)
        # -> scale=1 -> offset(270,227), size(260,170) (byte-stabil).
        result = g.crop_from_grid_corners((285, 242), (445, 338))
        self.assertEqual(result, ((270, 227), (260, 170)))

    def test_double_span_doubles_size(self):
        # Doppelte Spannweite (320x192 statt 160x96) -> scale=2.
        # gridTL=(285,242); gridBR=(285+320, 242+192)=(605,434).
        offset, size = g.crop_from_grid_corners((285, 242), (605, 434))
        self.assertEqual(size, (520, 340))
        # offset = gridTL - 15*scale = (285-30, 242-30) = (255, 212).
        self.assertEqual(offset, (255, 212))

    def test_result_types_are_ints(self):
        offset, size = g.crop_from_grid_corners((100, 100), (300, 250))
        for v in (*offset, *size):
            self.assertIsInstance(v, int)

    def test_null_span_returns_none(self):
        self.assertIsNone(g.crop_from_grid_corners((285, 242), (285, 338)))  # x-Span 0
        self.assertIsNone(g.crop_from_grid_corners((285, 242), (445, 242)))  # y-Span 0
        self.assertIsNone(g.crop_from_grid_corners((285, 242), (285, 242)))  # beide 0
        self.assertIsNone(g.crop_from_grid_corners((285, 242), (200, 300)))  # x negativ


class TestPixelToRef(unittest.TestCase):
    def test_default_keypoint_roundtrips_to_constant(self):
        # Farb-Sample-Pixel am Default-Screen = Offset(270,227)+REF_COLOR_SAMPLE
        # (110,150) = (380,377); bzgl. Default-Griffen -> ref (110,150).
        ref = g.pixel_to_ref((380, 377), (285, 242), (445, 338))
        self.assertAlmostEqual(ref[0], 110.0)
        self.assertAlmostEqual(ref[1], 150.0)

    def test_grid_corners_map_to_grid_origin_and_far_cell(self):
        # gridTL selbst -> Mitte Zelle(0,0) = (15,15).
        tl = g.pixel_to_ref((285, 242), (285, 242), (445, 338))
        self.assertAlmostEqual(tl[0], 15.0)
        self.assertAlmostEqual(tl[1], 15.0)
        # gridBR selbst -> Mitte Zelle(3,5) = (15+160, 15+96) = (175,111).
        br = g.pixel_to_ref((445, 338), (285, 242), (445, 338))
        self.assertAlmostEqual(br[0], 175.0)
        self.assertAlmostEqual(br[1], 111.0)

    def test_roundtrip_under_resize(self):
        # Bei einer 2x-Markierung muss ein Pixel, der per scale_point aus einer
        # bekannten Referenz entstand, wieder auf genau diese Referenz mappen.
        grid_tl, grid_br = (285, 242), (605, 434)  # scale=2
        offset, size = g.crop_from_grid_corners(grid_tl, grid_br)
        # bekannte Referenz -> Screen-Pixel via scale_point + offset ...
        sx, sy = g.scale_point((100, 90), size)
        pixel = (sx + offset[0], sy + offset[1])
        # ... und zurueck -> wieder (100, 90).
        ref = g.pixel_to_ref(pixel, grid_tl, grid_br)
        self.assertAlmostEqual(ref[0], 100.0)
        self.assertAlmostEqual(ref[1], 90.0)

    def test_null_span_returns_none(self):
        self.assertIsNone(g.pixel_to_ref((300, 300), (285, 242), (285, 338)))
        self.assertIsNone(g.pixel_to_ref((300, 300), (285, 242), (445, 242)))


if __name__ == '__main__':
    unittest.main()
