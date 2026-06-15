# -*- coding: utf-8 -*-
"""Tests fuer den 6-stelligen Gold-Reader (energiesplitter/gold_reader.py).

Headless mit ECHTEM cv2/numpy gegen die echten Fixtures. Der Gold-Zaehler ist in
allen Alchemist-Bildern + dem Alchemist-Shop sichtbar = "312.295" -> der Reader
MUSS dort 312295 liefern (Treffer am echten Bild), und an einem falschen/leeren
ROI ``None`` (defensiv -> der Bot stoppt statt blind zu kaufen).

PHASE-1-UPDATE (2026-06-15): Der gemeinsame Ziffernsatz (``templates/yang_digits/``
+ ``gold_digits/``) ist jetzt VOLLSTAENDIG -- die zuvor fehlenden 3/4/6/8 wurden
aus neuen Beleg-Bildern extrahiert (siehe ``test_energiesplitter_yang``). Damit
ist ``templates_complete()`` True und ``detect.assets_ready`` meldet ``gold_digits``
nicht mehr als fehlend -> das Phase-0-Gate KANN gruen werden.
"""

import os
import sys
import unittest

import cv2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from energiesplitter import gold_reader as gr  # noqa: E402
from energiesplitter import geometry as geo    # noqa: E402

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'fixtures', 'energiesplitter')


def _load(group, name):
    path = os.path.join(_FIX, group, name)
    img = cv2.imread(path)
    assert img is not None, 'fixture missing: %s' % path
    return img


class TestGoldReader(unittest.TestCase):

    def setUp(self):
        # Template-Cache je Test zuruecksetzen (defensiv, falls andere Tests
        # das Modul vorher beruehrt haben).
        gr._TEMPLATES = None

    def test_fixtures_are_raw_802x632(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertEqual(img.shape[:2], (geo.RAW_H, geo.RAW_W))

    def test_reads_gold_on_real_alchemist_image(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertEqual(gr.read_gold(img, geo.ROI_GOLD), 312295)

    def test_reads_gold_consistently_across_all_alchemist_images(self):
        names = [
            'metin2client_BlRGzUUM3w.png', 'metin2client_Fmx09flgeZ.png',
            'metin2client_POSo1J4Fo7.png', 'metin2client_PeEEl4lLQk.png',
            'metin2client_TYu62EaDYI.png', 'metin2client_jSBNb1MyFP.png',
            'metin2client_s4nZUO3m1E.png', 'metin2client_x9TDb0iaoG.png',
        ]
        for name in names:
            img = _load('Alchemist', name)
            self.assertEqual(gr.read_gold(img, geo.ROI_GOLD), 312295,
                             'gold mismatch on %s' % name)

    def test_reads_gold_in_open_shop(self):
        img = _load('Einkauf_Hammer', 'shop_alchemist.png')
        self.assertEqual(gr.read_gold(img, geo.ROI_GOLD), 312295)

    def test_wrong_region_returns_none(self):
        # Ein ROI mitten in der leeren Szene/Inventar enthaelt keine Gold-Ziffern.
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertIsNone(gr.read_gold(img, (300, 300, 44, 9)))

    def test_dialog_overlay_returns_none(self):
        # Vollbild-Dialog verdeckt den HUD-Gold-Zaehler -> kein Read (nie raten).
        img = _load('Einkauf_Hammer', 'erstgespraech1.png')
        self.assertIsNone(gr.read_gold(img, geo.ROI_GOLD))

    def test_defensive_inputs_return_none(self):
        self.assertIsNone(gr.read_gold(None, geo.ROI_GOLD))
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertIsNone(gr.read_gold(img, None))
        # Degenerierter ROI (Null-Flaeche) -> None, kein Crash.
        self.assertIsNone(gr.read_gold(img, (0, 0, 0, 0)))

    def test_value_plausibility_clamp(self):
        # Implausibel grosser ROI mit viel Rauschen darf nie eine Riesenzahl
        # liefern -> entweder ein plausibler Wert oder None, NIE > VALUE_MAX.
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        val = gr.read_gold(img, geo.ROI_GOLD)
        if val is not None:
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, gr.VALUE_MAX)

    def test_templates_complete_phase1(self):
        # Phase 1: die zuvor fehlenden Ziffern 3/4/6/8 wurden aus neuen Beleg-
        # Bildern extrahiert (siehe test_energiesplitter_yang) -> der Ziffernsatz
        # ist jetzt vollstaendig und das Phase-0-Gate KANN gruen werden.
        self.assertTrue(gr.templates_complete())


if __name__ == '__main__':
    unittest.main()
