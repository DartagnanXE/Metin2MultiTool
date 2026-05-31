"""Tests fuer die Puzzle-Board-Erkennung (detection.py).

Spec REDESIGN_SPEC.md Sec.9: Pflichttest 'Auto-Detection (Mock-Screenshot)' +
Mark-Offset. cv2 ist in der Testumgebung meist nicht da; der auto-Pfad wird
zusaetzlich deterministisch via Monkeypatch (detection.cv = None) auf den
Headless-Fallback gezwungen.
"""

import unittest

import detection


class TestBasics(unittest.TestCase):
    def test_default_mode(self):
        self.assertEqual(detection.resolve_offset('default'), (270, 227))

    def test_unknown_mode_falls_back(self):
        self.assertEqual(detection.resolve_offset('bogus'), (270, 227))

    def test_none_mode_falls_back(self):
        self.assertEqual(detection.resolve_offset(None), (270, 227))

    def test_custom_default_offset(self):
        self.assertEqual(
            detection.resolve_offset('default', default_offset=(11, 22)),
            (11, 22))

    def test_always_int_pair_never_none(self):
        for mode in ('default', 'auto', 'mark', 'XXX', None):
            off = detection.resolve_offset(mode)
            self.assertIsInstance(off, tuple)
            self.assertEqual(len(off), 2)
            self.assertTrue(all(isinstance(v, int) for v in off))


class TestMark(unittest.TestCase):
    def test_valid_in_bounds_kept(self):
        self.assertEqual(
            detection.resolve_offset('mark', saved_offset=(100, 90)),
            (100, 90))

    def test_none_falls_back(self):
        self.assertEqual(
            detection.resolve_offset('mark', saved_offset=None), (270, 227))

    def test_out_of_bounds_falls_back_to_default(self):
        # M1-Fix: ausserhalb -> Default statt stilles Klemmen.
        self.assertEqual(
            detection.resolve_offset('mark', saved_offset=(9999, 9999)),
            (270, 227))

    def test_unreadable_falls_back(self):
        self.assertEqual(
            detection.resolve_offset('mark', saved_offset='garbage'),
            (270, 227))


class TestAutoHeadless(unittest.TestCase):
    def setUp(self):
        self._cv = detection.cv

    def tearDown(self):
        detection.cv = self._cv

    def test_auto_without_cv2_falls_back_to_default(self):
        detection.cv = None
        self.assertEqual(detection.resolve_offset('auto'), (270, 227))

    def test_auto_with_mock_screenshot_returns_valid_offset(self):
        detection.cv = None
        shot = [[(0, 0, 0)] * 300 for _ in range(200)]
        off = detection.resolve_offset('auto', screenshot=shot)
        mx, my = detection._bounds(shot)
        self.assertTrue(0 <= off[0] <= mx and 0 <= off[1] <= my)


class TestClampBounds(unittest.TestCase):
    def test_default_offset_clamped(self):
        off = detection.resolve_offset('default', default_offset=(99999, 99999))
        self.assertEqual(off, detection._bounds(None))

    def test_bounds_from_screenshot_shape(self):
        shot = [[(0, 0, 0)] * 300 for _ in range(200)]
        self.assertEqual(detection._bounds(shot), (40, 30))


if __name__ == '__main__':
    unittest.main()
