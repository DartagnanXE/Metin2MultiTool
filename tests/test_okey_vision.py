# -*- coding: utf-8 -*-
"""Okey-Bilderkennung an den echten Bildschirmfotos des Nutzers.

Die Bilder liegen in ``FischOCR/`` und sind bewusst NICHT im Repository
(gitignored, sie zeigen Mitspieler-Namen). Fehlen sie, wird uebersprungen --
nicht gemogelt und nicht abgestuerzt.

DER EIGENTLICHE NACHWEIS steckt in :class:`TestFarbunabhaengigkeit`: die acht
Ziffer-Schablonen stammen aus ZWEI Farben (1/5/6/7 von gelben, 2/3/4/8 von
ROTEN Karten). Wenn damit auch alle BLAUEN Karten richtig gelesen werden, ist
belegt, dass Ziffer und Farbe wirklich getrennt erkannt werden -- und der
Nutzer muss nicht jede Karte in jeder Farbe liefern. Genau das war seine
Bitte.
"""

import os
import unittest

try:
    import cv2 as cv
except Exception:                       # pragma: no cover
    cv = None

BILDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'FischOCR')

#: Was auf den Bildern wirklich zu sehen ist (von Hand abgelesen).
FELDER = {
    20: [(7, 'B'), (5, 'G'), (1, 'G'), (7, 'G'), (6, 'G')],
    21: [(7, 'B'), 'leer', (1, 'G'), 'leer', 'leer'],
    23: [(2, 'R'), (7, 'B'), (5, 'B'), (2, 'G'), (7, 'R')],
    24: [(3, 'R'), (6, 'R'), (1, 'G'), (3, 'G'), (3, 'B')],
    25: [(5, 'G'), (6, 'G'), (7, 'G'), (6, 'B'), (8, 'R')],
    26: [(8, 'G'), (4, 'R'), (4, 'B'), (2, 'B'), (1, 'B')],
    27: [(1, 'R'), (5, 'R'), (8, 'B'), (4, 'G'), 'leer'],
}

#: Rest-Karten und Punkte, wie sie auf dem Bildschirm stehen.
ZAHLEN = {20: (19, 0), 21: (19, 90), 23: (19, 0), 24: (14, 0),
          25: (9, 40), 26: (4, 130), 27: (0, 130)}


def _bild(nummer):
    pfad = os.path.join(BILDER, 'okey_%d.png' % nummer)
    if cv is None or not os.path.exists(pfad):
        return None
    roh = cv.imread(pfad, cv.IMREAD_UNCHANGED)
    if roh is None or roh.shape[0] < 632:
        return None
    return roh[31:632, 1:801][:, :, :3]     # Client-Ausschnitt wie im Bot


def _vorhanden():
    return _bild(20) is not None


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestKartenLesen(unittest.TestCase):
    def test_alle_karten_auf_allen_bildern(self):
        from okey import vision
        falsch = []
        gesamt = 0
        for nummer, soll in sorted(FELDER.items()):
            ist = vision.read_field(_bild(nummer))
            for platz, (a, b) in enumerate(zip(ist, soll), start=1):
                gesamt += 1
                if a != b:
                    falsch.append('Bild %d Platz %d: %r statt %r'
                                  % (nummer, platz, a, b))
        self.assertEqual(falsch, [], '%d von %d Karten falsch'
                         % (len(falsch), gesamt))
        self.assertEqual(gesamt, 35, 'Testumfang veraendert')

    def test_leere_plaetze_werden_nicht_erfunden(self):
        """Gegenprobe: ein freier Platz darf nie eine Karte melden."""
        from okey import vision
        for nummer, soll in sorted(FELDER.items()):
            ist = vision.read_field(_bild(nummer))
            for platz, (a, b) in enumerate(zip(ist, soll), start=1):
                if b == 'leer':
                    self.assertEqual(a, 'leer',
                                     'Bild %d Platz %d erfindet %r'
                                     % (nummer, platz, a))

    def test_kartenrueckseiten_gelten_als_leer(self):
        """Am Rundenende liegen Rueckseiten oben (Bild 22). Sie sind dunkel
        rot -- wuerden sie als rote Karte durchgehen, wuerde der Bot am Ende
        Phantom-Karten spielen."""
        from okey import vision
        img = _bild(22)
        if img is None:
            self.skipTest('Bild 22 fehlt')
        self.assertEqual(vision.read_field(img), ['leer'] * 5)


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestFarbunabhaengigkeit(unittest.TestCase):
    """Der Nachweis, dass Ziffer und Farbe getrennt erkannt werden."""

    #: Aus welcher Farbe die jeweilige Schablone geschnitten wurde.
    HERKUNFT = {1: 'G', 5: 'G', 6: 'G', 7: 'G',
                2: 'R', 3: 'R', 4: 'R', 8: 'R'}

    def test_jede_ziffer_wird_auch_in_fremder_farbe_erkannt(self):
        from okey import vision
        gepruefte = set()
        for nummer, soll in sorted(FELDER.items()):
            ist = vision.read_field(_bild(nummer))
            for a, b in zip(ist, soll):
                if not isinstance(b, tuple):
                    continue
                wert, farbe = b
                if farbe == self.HERKUNFT[wert]:
                    continue            # gleiche Farbe waere kein Nachweis
                self.assertEqual(a, b, 'Ziffer %d in fremder Farbe %s falsch'
                                 % (wert, farbe))
                gepruefte.add((wert, farbe))
        self.assertGreaterEqual(len(gepruefte), 10,
                                'zu wenige fremdfarbige Karten geprueft')

    def test_alle_acht_ziffern_kommen_vor(self):
        werte = {k[0] for soll in FELDER.values() for k in soll
                 if isinstance(k, tuple)}
        self.assertEqual(werte, set(range(1, 9)), 'nicht alle Ziffern im Test')

    def test_alle_drei_farben_kommen_vor(self):
        farben = {k[1] for soll in FELDER.values() for k in soll
                  if isinstance(k, tuple)}
        self.assertEqual(farben, {'R', 'B', 'G'})

    def test_keine_schablone_fehlt(self):
        from okey import vision
        self.assertEqual(vision.fehlende_ziffern(), [])


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestZahlenfelder(unittest.TestCase):
    """Die Zahlen sind GEGENPROBE, nicht Grundlage -- deshalb darf eine Luecke
    hier ``None`` liefern, aber niemals einen falschen Wert."""

    def test_liest_richtig_oder_schweigt(self):
        from okey import vision
        falsch = []
        for nummer, (rest, punkte) in sorted(ZAHLEN.items()):
            img = _bild(nummer)
            gr, gp = vision.read_deck_count(img), vision.read_points(img)
            if gr is not None and gr != rest:
                falsch.append('Bild %d Rest %r statt %d' % (nummer, gr, rest))
            if gp is not None and gp != punkte:
                falsch.append('Bild %d Punkte %r statt %d'
                              % (nummer, gp, punkte))
        self.assertEqual(falsch, [], 'falsch gelesene Zahl (schlimmer als gar '
                                     'keine): %s' % falsch)

    def test_liest_die_meisten_zahlen_wirklich(self):
        """Gegenprobe: eine Erkennung, die IMMER schweigt, wuerde den Test
        darueber ebenfalls bestehen."""
        from okey import vision
        gelesen = sum(1 for n in ZAHLEN
                      if vision.read_deck_count(_bild(n)) is not None)
        gelesen += sum(1 for n in ZAHLEN
                       if vision.read_points(_bild(n)) is not None)
        self.assertGreaterEqual(gelesen, 12, 'kaum eine Zahl gelesen')


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestSicherModusKaestchen(unittest.TestCase):
    def test_gesetzter_haken_ist_messbar_hell(self):
        from okey import vision
        img = _bild(17)
        if img is None:
            self.skipTest('Bild 17 fehlt')
        self.assertGreater(vision.safe_mode_ink(img), 0.05,
                           'der gesetzte Haken ist nicht messbar')

    def test_wirft_nie(self):
        from okey import vision
        self.assertEqual(vision.safe_mode_ink(None), -1.0)


class TestOhneOpenCV(unittest.TestCase):
    """Kopflos ohne OpenCV darf nichts krachen -- die Tests laufen auf Linux."""

    def test_alle_funktionen_bleiben_defensiv(self):
        from okey import vision
        self.assertEqual(vision.read_field(None), ['?'] * 5)
        self.assertIsNone(vision.read_points(None))
        self.assertIsNone(vision.read_deck_count(None))
        self.assertEqual(vision.field_diag(None), [])


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
