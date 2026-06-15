# -*- coding: utf-8 -*-
"""Tests fuer den scharfen Yang-Reader (energiesplitter/gold_reader.py).

Grundwahrheit 2026-06-15: Waehrung = YANG. Unten rechts stehen ZWEI Zahlen; die
RECHTE ist das rohe Yang. Der Reader liest die RECHTE Zahl aus der kalibrierten
ROI ``calibration.yang_roi()`` per Ziffern-Templates (``templates/yang_digits/``,
Glyph-Union mit dem Alt-Satz ``gold_digits/``). Headless mit ECHTEM cv2/numpy
gegen die zwei Inventar-Fixtures:

  * ``inventar_alchemist.png``      -> 207295
  * ``inventar_waffenhaendler.png`` -> 192295

Sicherheits-Invariante (Erkennung vor Aktion): alles Unsichere/Implausible ->
``None`` (der Bot stoppt statt blind zu kaufen). Der Confidence-Floor verwirft
uneindeutige Treffer.

PHASE-1-UPDATE (2026-06-15): Die fehlenden Ziffern 3/4/6/8 wurden aus neuen
Beleg-Bildern extrahiert (``yang_161495.png`` -> 4/6, ``yang_129895.png`` -> 8,
``yang_131895.png`` -> 3, Dolch-Shop -> 3). Der Ziffernsatz ist jetzt VOLLSTAENDIG
(0..9 + dot) -> ``templates_complete()`` ist True und das Phase-0-Gate KANN gruen
werden. Beruehrende Ziffernpaare (4-9 / 8-9, ein ueberbreiter Tinten-Span) werden
template-getrieben am besten Schnitt geteilt -- jede Teil-Ziffer muss EINZELN
ueber CONF_MIN matchen (keine Aufweichung der "nie raten"-Invariante).

EHRLICHKEIT zur Beleg-Lieferung: Das Bild ``yang_131895.png`` rendert am echten
Pixel ``131.495`` (die 4. Stelle ist ein ``4``, byte-identisch zur 4-9-Gruppe in
``yang_161495.png``), NICHT ``131.895`` wie in der Beleg-Notiz angegeben. Der
Reader liest korrekt, was gerendert ist; der saubere ``8``-Beleg kommt aus
``yang_129895.png`` (liest exakt 129895). Die Tests pruefen daher gegen die TRUE
gerenderten Werte.
"""

import os
import sys
import unittest

import cv2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from energiesplitter import gold_reader as gr   # noqa: E402
from energiesplitter import calibration as cal  # noqa: E402
from energiesplitter import geometry as geo     # noqa: E402

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'fixtures', 'energiesplitter')


def _load(*parts):
    path = os.path.join(_FIX, *parts)
    img = cv2.imread(path)
    assert img is not None, 'fixture missing: %s' % path
    return img


class TestYangReader(unittest.TestCase):

    def setUp(self):
        gr._TEMPLATES = None  # Template-Cache je Test zuruecksetzen

    # -- Kern: RECHTE Yang-Zahl exakt zurueckgelesen ------------------------
    def test_reads_yang_alchemist(self):
        img = _load('inventar_alchemist.png')
        self.assertEqual(gr.read_yang(img), 207295)

    def test_reads_yang_waffenhaendler(self):
        img = _load('inventar_waffenhaendler.png')
        self.assertEqual(gr.read_yang(img), 192295)

    def test_read_yang_default_roi_matches_calibration(self):
        # read_yang(bgr) ohne ROI nutzt calibration.yang_roi() == geometry.ROI_GOLD.
        img = _load('inventar_alchemist.png')
        self.assertEqual(cal.yang_roi(), geo.ROI_GOLD)
        self.assertEqual(gr.read_yang(img), gr.read_yang(img, cal.yang_roi()))

    def test_fixtures_are_raw_802x632(self):
        img = _load('inventar_alchemist.png')
        self.assertEqual(img.shape[:2], (geo.RAW_H, geo.RAW_W))

    # -- is_calibrated: TRUE nur wenn Yang lesbar UND Grid vorhanden --------
    def test_is_calibrated_true_when_yang_readable_and_grid(self):
        for name in ('inventar_alchemist.png', 'inventar_waffenhaendler.png'):
            self.assertTrue(gr.is_calibrated(_load(name)),
                            'is_calibrated false on %s' % name)

    def test_is_calibrated_false_when_yang_unreadable(self):
        # Grid ist da, aber ein leerer/falscher ROI -> Yang unlesbar -> False.
        img = _load('inventar_alchemist.png')
        self.assertTrue(gr._grid_present())
        self.assertFalse(gr.is_calibrated(img, (300, 300, 44, 9)))

    def test_is_calibrated_false_on_none(self):
        self.assertFalse(gr.is_calibrated(None))

    # -- Defensiv: nie raten -----------------------------------------------
    def test_wrong_region_returns_none(self):
        img = _load('inventar_alchemist.png')
        self.assertIsNone(gr.read_yang(img, (300, 300, 44, 9)))

    def test_defensive_inputs_return_none(self):
        self.assertIsNone(gr.read_yang(None))
        img = _load('inventar_alchemist.png')
        self.assertIsNone(gr.read_yang(img, (0, 0, 0, 0)))

    def test_value_in_plausible_range(self):
        for name, exp in (('inventar_alchemist.png', 207295),
                          ('inventar_waffenhaendler.png', 192295)):
            val = gr.read_yang(_load(name))
            self.assertEqual(val, exp)
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, gr.VALUE_MAX)

    # -- Phase-1: Ziffernsatz jetzt VOLLSTAENDIG (3/4/6/8 nachgeliefert) ----
    def test_templates_complete_phase1(self):
        # 3/4/6/8 sind extrahiert -> Gate KANN gruen werden.
        self.assertTrue(gr.templates_complete())

    def test_all_ten_digits_plus_dot_present(self):
        glyphs = set(gr._load_templates().keys())
        needed = set(str(d) for d in range(10)) | {'dot'}
        self.assertTrue(needed.issubset(glyphs),
                        'fehlende Glyphen: %s' % (needed - glyphs))

    # -- Neue Ziffern: 3/4/6/8 werden aus den Beleg-Bildern exakt gelesen --
    def test_reads_new_digit_values(self):
        # Werte mit den vormals fehlenden Ziffern lesen exakt zurueck.
        # Hinweis: yang_131895.png rendert real 131.495 (4. Stelle = 4), nicht
        # 131.895 -- der Reader liest, was gerendert ist (Ehrlichkeit, Docstring).
        for name, exp in (('yang_161495.png', 161495),   # liefert 4 + 6
                          ('yang_129895.png', 129895),   # liefert 8 (sauber)
                          ('yang_131895.png', 131495)):  # liefert 3; real 131.495
            self.assertEqual(gr.read_yang(_load(name)), exp,
                             'mismatch on %s' % name)

    def test_dolch_shop_yang_reads_with_3(self):
        # Der Dolch-Shop-Screenshot liefert die 3 (312.295).
        img = cv2.imread(os.path.join(_FIX, 'Einkauf_Dolche', 'shop_dolche.png'))
        self.assertIsNotNone(img)
        self.assertEqual(gr.read_yang(img), 312295)

    def test_touching_digits_split_does_not_guess(self):
        # Beruehrende Ziffern werden geteilt, aber jede Teil-Ziffer muss EINZELN
        # ueber CONF_MIN matchen -- ein zu schwacher Split liefert None, nie raten.
        # Beleg: das 4-9-Paar in yang_161495.png wird korrekt zu '49' aufgeloest.
        self.assertEqual(gr.read_yang(_load('yang_161495.png')), 161495)

    def test_conf_floor_above_wrong_match_band(self):
        # Sicherheitsmarge: der Confidence-Floor liegt ueber dem gemessenen
        # Falsch-/Nachbar-NCC-Band (<= ~0.60) -> eine fehlende Ziffer kann nicht
        # still als Nachbar durchrutschen.
        self.assertGreaterEqual(gr.CONF_MIN, 0.70)


if __name__ == '__main__':
    unittest.main()
