"""Tests fuer die umschaltbare Farb-Klassifikation des Puzzle-Bots.

Hintergrund: ``PuzzleBot._classify_piece`` (puzzle.py) ist nicht direkt
importierbar, weil puzzle.py numpy/cv2/win32/pydirectinput voraussetzt (unter
WSL/Linux nicht installierbar). Diese Tests sichern daher den ALGORITHMISCHEN
Vertrag der beiden Klassifikationspfade als stdlib-only Referenz ab:

  * 'single' (Default): die sechs engen BGR-Fenster muessen bit-identisch zum
    bisherigen, funktionierenden get_new_piece_color klassifizieren (keine
    Regression -- altes Verhalten garantiert erhalten).
  * 'multi' : naechste Referenzfarbe (kleinste quadratische Distanz zu den 6
    PIECE_REF_BGR-Zentroiden). Jeder Zentroid und sein Nahbereich muessen auf
    den richtigen Steintyp fallen.

Die hier hinterlegte Referenz-Tabelle/Logik MUSS mit puzzle.py uebereinstimmen;
weichen sie ab, schlagen diese Tests fehl (Drift-Schutz).

stdlib-only (unittest). Lauf: python3 -m unittest tests.test_color_sampling -v
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# -- Referenz-Implementierungen, identisch zu puzzle.PuzzleBot --------------

# Muss PuzzleBot.PIECE_REF_BGR exakt spiegeln.
PIECE_REF_BGR = {
    4: (37, 65, 250),
    1: (25, 160, 250),
    5: (42, 250, 42),
    3: (250, 250, 25),
    2: (250, 107, 0),
    6: (55, 245, 255),
}


def classify_single(bgr):
    """Spiegelt den 'single'-Zweig von _classify_piece (die sechs engen
    BGR-Fenster). BEWUSSTE ABWEICHUNG vom Ur-Original (2026-06-10): das
    BLAU-Fenster (Typ 2) wurde von g 100..115 auf g 60..130 verbreitert --
    live gemessen las der blaue Stein (255, 74, 0) und fiel durch. Sonst
    bit-identisch zum urspruenglichen get_new_piece_color."""
    b, g, r = bgr
    if b > 35 and b < 40 and g > 60 and g < 70 and r > 240 and r < 260:
        return 4
    elif b > 20 and b < 30 and g > 150 and g < 170 and r > 240 and r < 260:
        return 1
    elif b > 35 and b < 50 and g > 240 and g < 260 and r > 35 and r < 50:
        return 5
    elif b > 240 and b < 260 and g > 240 and g < 260 and r > 20 and r < 30:
        return 3
    elif b > 240 and b < 260 and g > 60 and g < 130 and r > -10 and r < 10:
        return 2
    elif b > 50 and b < 60 and g > 235 and g < 255 and r > 250 and r < 260:
        return 6
    return None


def classify_multi(bgr):
    """Spiegelt den 'multi'-Zweig: naechste Referenzfarbe (quadr. Distanz)."""
    b, g, r = bgr
    best_type = None
    best_dist = None
    for piece_type, ref in PIECE_REF_BGR.items():
        db = b - ref[0]
        dg = g - ref[1]
        dr = r - ref[2]
        dist = db * db + dg * dg + dr * dr
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_type = piece_type
    return best_type


# -- ORIGINAL-Referenz (vor dem Redesign) fuer den Byte-Stabilitaets-Check --

def original_get_new_piece_color(b, g, r):
    """Wortgetreue Kopie der urspruenglichen Verzweigung aus
    get_new_piece_color (vor Einfuehrung des Color-Toggles)."""
    piece_type = None
    if b > 35 and b < 40 and g > 60 and g < 70 and r > 240 and r < 260:
        piece_type = 4
    elif b > 20 and b < 30 and g > 150 and g < 170 and r > 240 and r < 260:
        piece_type = 1
    elif b > 35 and b < 50 and g > 240 and g < 260 and r > 35 and r < 50:
        piece_type = 5
    elif b > 240 and b < 260 and g > 240 and g < 260 and r > 20 and r < 30:
        piece_type = 3
    elif b > 240 and b < 260 and g > 100 and g < 115 and r > -10 and r < 10:
        piece_type = 2
    elif b > 50 and b < 60 and g > 235 and g < 255 and r > 250 and r < 260:
        piece_type = 6
    return piece_type


class TestSingleModeByteStable(unittest.TestCase):
    """'single' bleibt bit-identisch zum Original -- AUSSER der bewussten
    Blau-Fenster-Verbreiterung (g 100..115 -> 60..130, 2026-06-10)."""

    def test_full_bgr_sweep_identical_outside_blue_widening(self):
        # Grobe, aber vollstaendige Abdeckung des BGR-Wuerfels (Schrittweite 5).
        # Einzige erlaubte Abweichung: das verbreiterte BLAU-Fenster (Typ 2);
        # dort muss classify_single 2 liefern, wo das Original None lieferte.
        for b in range(0, 256, 5):
            for g in range(0, 256, 5):
                for r in range(0, 256, 5):
                    got = classify_single((b, g, r))
                    orig = original_get_new_piece_color(b, g, r)
                    if got == orig:
                        continue
                    in_widened_blue = (240 < b < 260 and 60 < g < 130
                                       and -10 < r < 10)
                    if not (in_widened_blue and got == 2 and orig is None):
                        self.fail('single-Klassifikation weicht unerlaubt ab '
                                  'bei BGR=({}, {}, {}): {} vs {}'
                                  .format(b, g, r, got, orig))

    def test_live_measured_blue_classifies(self):
        # Der live gemessene blaue Stein (2026-06-10), der mit dem alten
        # Fenster durchfiel und sofort verworfen wurde.
        self.assertEqual(classify_single((255, 74, 0)), 2)

    def test_each_reference_centroid_hits_its_type_in_single(self):
        # Die Zentroide liegen bewusst in den engen Fenstern -> 'single' muss
        # sie ebenfalls korrekt treffen (gemeinsame Herkunft der Tabelle).
        for ptype, ref in PIECE_REF_BGR.items():
            with self.subTest(ptype=ptype):
                self.assertEqual(classify_single(ref), ptype)

    def test_black_is_unclassified_in_single(self):
        # Schwarz/Garbage (alle Kanaele 0) trifft keines der sechs Fenster.
        self.assertIsNone(classify_single((0, 0, 0)))


class TestTolerantCentroidsDisjoint(unittest.TestCase):
    """Invariante des Toleranz-Fallbacks (_classify_piece_tolerant, tol=40):
    KEINE BGR-Farbe kann zwei Zentroiden gleichzeitig treffen, und dunkle
    Hintergrund-/Garbage-Pixel treffen keines. Bricht dieser Test, wurde ein
    Zentroid verschoben/ergaenzt und die Toleranz ist nicht mehr beweisbar
    verwechslungsfrei -> tol senken oder Zentroide pruefen."""

    TOL = 40

    # HISTORIE: tol=45 fiel hier durch -- Orange(1)/Gelb(6) haben nur 85
    # Kanal-Luecke (85 < 2*45). 40 ist der groesste sichere Wert in 5er-Schritten.

    def test_no_colour_hits_two_centroids(self):
        # Paarweise: zwei Wuerfel [ref +- tol]^3 schneiden sich nur, wenn ALLE
        # drei Kanal-Abstaende <= 2*tol sind. Direkt ueber die Paare bewiesen
        # (aequivalent zum vollen BGR-Sweep, aber exakt statt Schrittweite).
        refs = list(PIECE_REF_BGR.items())
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                (t1, r1), (t2, r2) = refs[i], refs[j]
                max_gap = max(abs(r1[k] - r2[k]) for k in range(3))
                self.assertGreater(
                    max_gap, 2 * self.TOL,
                    'Zentroide {} und {} ueberlappen bei tol={}'.format(
                        t1, t2, self.TOL))

    def test_dark_pixels_hit_no_centroid(self):
        # Jedes Zentroid hat einen Kanal >= 160 -> alle Kanaele <= 110 koennen
        # nie innerhalb tol=40 liegen (160 - 110 = 50 > 40).
        for ref in PIECE_REF_BGR.values():
            self.assertGreaterEqual(max(ref), 160)


class TestMultiModeNearestColor(unittest.TestCase):
    """'multi' ordnet jede Farbe der naechsten Referenz zu."""

    def test_centroids_classify_exactly(self):
        for ptype, ref in PIECE_REF_BGR.items():
            with self.subTest(ptype=ptype):
                self.assertEqual(classify_multi(ref), ptype)

    def test_small_noise_keeps_classification(self):
        # +-8 pro Kanal darf die Zuordnung nicht kippen (Robustheitsgewinn ggue.
        # den engen Fenstern ist der Zweck des 'multi'-Modus).
        deltas = (-8, -4, 0, 4, 8)
        for ptype, ref in PIECE_REF_BGR.items():
            for db in deltas:
                for dg in deltas:
                    for dr in deltas:
                        noisy = (
                            min(255, max(0, ref[0] + db)),
                            min(255, max(0, ref[1] + dg)),
                            min(255, max(0, ref[2] + dr)),
                        )
                        with self.subTest(ptype=ptype, noisy=noisy):
                            self.assertEqual(classify_multi(noisy), ptype)

    def test_multi_never_returns_none(self):
        # 'multi' liefert immer einen Typ (das Schwarz-Sonderfall-Handling
        # passiert im Aufrufer get_new_piece_color, nicht im Klassifikator).
        for bgr in [(0, 0, 0), (128, 128, 128), (255, 255, 255), (10, 200, 5)]:
            with self.subTest(bgr=bgr):
                self.assertIn(classify_multi(bgr), (1, 2, 3, 4, 5, 6))


if __name__ == '__main__':  # pragma: no cover
    unittest.main(verbosity=2)
