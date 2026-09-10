# -*- coding: utf-8 -*-
"""Der Okey-Ablauf erkennt jeden Bildschirm eindeutig -- und klickt sonst nie.

Die Schwelle 0,80 ist an den zwoelf Bildern des Nutzers gemessen. Diese Tests
halten die Messung fest: sie pruefen nicht nur, dass ein vorhandenes Element
gefunden wird, sondern auch, dass ein NICHT vorhandenes deutlich darunter
bleibt. Ohne die zweite Haelfte waere eine Schablone, die ueberall 1,0 liefert,
gruen -- und im Spiel katastrophal.
"""

import os
import unittest

try:
    import cv2 as cv
except Exception:                       # pragma: no cover
    cv = None

BILDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'FischOCR')

#: Auf welchen Bildern das Element WIRKLICH zu sehen ist.
#: 16 = Eventuebersicht, 17 = Okey-Vorfenster, 18 = Startdialog,
#: 19..27 = laufendes Brett (22 mit Beenden-Dialog darueber).
ERWARTET = {
    'flow_event_title': {16},
    'flow_okey_label': {16},
    'flow_okey_title': set(range(17, 28)),
    'flow_start_btn': {17, 18},         # der Dialog liegt UEBER dem Startfenster
    'flow_ja_btn': {18, 22},
    'flow_hinweis': set(range(19, 28)),
    'flow_beenden': set(range(19, 28)),
}
ALLE = list(range(16, 28))


def _bild(nummer):
    pfad = os.path.join(BILDER, 'okey_%d.png' % nummer)
    if cv is None or not os.path.exists(pfad):
        return None
    roh = cv.imread(pfad, cv.IMREAD_UNCHANGED)
    if roh is None or roh.shape[0] < 632:
        return None
    return roh[31:632, 1:801][:, :, :3]


def _vorhanden():
    return _bild(16) is not None


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestSchablonenTrennen(unittest.TestCase):
    def test_jedes_element_wird_gefunden_wo_es_ist(self):
        from okey import flow
        fehlend = []
        for name, soll in sorted(ERWARTET.items()):
            for nummer in sorted(soll):
                ok, _pos, guete = flow.find(_bild(nummer), name)
                if not ok:
                    fehlend.append('%s auf Bild %d nur %.3f'
                                   % (name, nummer, guete))
        self.assertEqual(fehlend, [], 'nicht gefunden: %s' % fehlend)

    def test_kein_element_wird_gefunden_wo_es_nicht_ist(self):
        from okey import flow
        falsch = []
        for name, soll in sorted(ERWARTET.items()):
            for nummer in ALLE:
                if nummer in soll:
                    continue
                ok, _pos, guete = flow.find(_bild(nummer), name)
                if ok:
                    falsch.append('%s auf Bild %d faelschlich %.3f'
                                  % (name, nummer, guete))
        self.assertEqual(falsch, [], 'Fehltreffer: %s' % falsch)

    def test_die_luecke_ist_gross_genug(self):
        """Der eigentliche Beleg fuer die Schwelle: der schwaechste ECHTE
        Treffer muss deutlich ueber dem staerksten FALSCHEN liegen."""
        from okey import flow
        schwaechster_echter, staerkster_falscher = 1.0, 0.0
        for name, soll in sorted(ERWARTET.items()):
            for nummer in ALLE:
                guete = flow.find(_bild(nummer), name, thresh=2.0)[2]
                if nummer in soll:
                    schwaechster_echter = min(schwaechster_echter, guete)
                else:
                    staerkster_falscher = max(staerkster_falscher, guete)
        self.assertGreater(schwaechster_echter, staerkster_falscher + 0.20,
                           'echt %.3f vs falsch %.3f -- zu eng'
                           % (schwaechster_echter, staerkster_falscher))
        self.assertLess(staerkster_falscher, flow.FLOW_NCC_MIN)
        self.assertGreater(schwaechster_echter, flow.FLOW_NCC_MIN)


@unittest.skipUnless(_vorhanden(), 'FischOCR/okey_*.png nicht vorhanden')
class TestEventzeile(unittest.TestCase):
    def test_findet_die_okey_zeile(self):
        from okey import flow
        ok, punkt, dbg = flow.find_okey_row(_bild(16))
        self.assertTrue(ok, dbg)
        # Zeile 2 der Uebersicht, Namensfeld -- NICHT der Ansehen-Knopf.
        self.assertEqual(punkt[0], 477)
        self.assertEqual(punkt[1], 193)

    def test_klickt_nicht_ohne_offene_uebersicht(self):
        """Der wichtige Riegel: auf dem Spielbrett erreicht der Schriftzug
        immerhin 0,64. Ohne die zweite Bedingung koennte daraus irgendwann ein
        Klick in die offene Spielwelt werden."""
        from okey import flow
        ok, punkt, dbg = flow.find_okey_row(_bild(20))
        self.assertFalse(ok)
        self.assertEqual(punkt, (0, 0))
        self.assertEqual(dbg.get('grund'), 'uebersicht-nicht-offen')

    def test_brett_erkennung(self):
        from okey import flow
        self.assertFalse(flow.brett_laeuft(_bild(16)), 'Uebersicht = kein Brett')
        self.assertFalse(flow.brett_laeuft(_bild(17)), 'Vorfenster = kein Brett')
        for nummer in range(19, 28):
            self.assertTrue(flow.brett_laeuft(_bild(nummer)),
                            'Bild %d sollte ein Brett sein' % nummer)


class TestDefensiv(unittest.TestCase):
    """Ohne Bild, ohne OpenCV, mit Muell -- nie ein Absturz, nie ein Klick."""

    def test_kein_bild(self):
        from okey import flow
        self.assertEqual(flow.find(None, 'flow_ja_btn'), (False, (0, 0), 0.0))
        self.assertFalse(flow.sichtbar(None, 'flow_ja_btn'))
        self.assertFalse(flow.brett_laeuft(None))
        self.assertFalse(flow.find_okey_row(None)[0])

    def test_unbekannte_schablone(self):
        from okey import flow
        self.assertFalse(flow.find(None, 'gibt_es_nicht')[0])

    def test_diagnose_nennt_alle_schablonen(self):
        from okey import flow
        d = flow.diagnose(None)
        for name in flow.ALL_TEMPLATES:
            self.assertIn(name, d)
        self.assertIn('_schwelle', d)


class TestSchablonenDateienSindDabei(unittest.TestCase):
    """Die Schablonen liegen IM Repository (anders als die Referenzbilder) --
    sonst faende der gebaute Bot im Spiel nichts."""

    def test_alle_dateien_existieren(self):
        from okey import flow
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in flow.ALL_TEMPLATES:
            pfad = os.path.join(wurzel, 'okey_templates', name + '.png')
            self.assertTrue(os.path.exists(pfad), 'fehlt: %s' % pfad)

    def test_ziffern_und_zaehler(self):
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for wert in range(1, 9):
            pfad = os.path.join(wurzel, 'okey_templates',
                                'ziffer_%d.png' % wert)
            self.assertTrue(os.path.exists(pfad), 'fehlt: %s' % pfad)


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
