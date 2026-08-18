# -*- coding: utf-8 -*-
"""Das Koeder-Nachlegen blaettert nur so weit, bis der Koeder gefunden ist.

User-Report 2026-08-18: "wenn der Bot den Fischkoeder (Wurm) nachlegen moechte,
geht er einmal durch alle Seiten, brauch er aber gar nicht, die liegen immer auf
Seite 1 -- zieht etwas Zeit".

Gesucht wird das ERSTE Vorkommen: ``find_first`` laeuft die Seiten in fester
Reihenfolge ab und nimmt den ersten Treffer. Steht der auf Seite I, aendert keine
weitere Seite das Ergebnis -- sie kostet nur einen Tab-Klick, eine Settle-Pause
und 45 Slot-Klassifikationen. Der Frueh-Ausstieg
(``scan_inventory(early_stop_fn=...)``) ueberspringt genau diese Arbeit.

Die Gleichwertigkeit haengt daran, dass Ausstiegs-Test und Auswahl DIESELBE
Regel benutzen (``slot_is_usable``). Waere der Ausstieg laxer, wuerde der Scan an
einer Seite halten, an der ``find_first`` dann doch vorbeilaeuft -- Ergebnis:
faelschlich "kein Koeder mehr" und ein gestoppter Bot. Genau das pinnt
``TestAusstiegUndAuswahlEntscheidenGleich``.
"""

import types
import unittest

from interface import refill
from inventory import scanner


def _slot(name, row=0, col=0, state='item', distance=0.0):
    return types.SimpleNamespace(state=state, name=name, row=row, col=col,
                                 distance=distance)


class _Wincap:
    offset_x = 0
    offset_y = 0

    def get_screenshot(self):
        return None


class _Recorder:
    """Nimmt Tab-Klicks + Drag-Schritte auf (wie die uebrigen refill-Tests)."""

    def __init__(self):
        self.events = []

    def click(self, x=None, y=None, button=None):
        self.events.append(('click', x, y))

    def moveTo(self, x, y):
        self.events.append(('move', x, y))

    def mouseDown(self):
        self.events.append(('down',))

    def mouseUp(self):
        self.events.append(('up',))


class TestAusstiegUndAuswahlEntscheidenGleich(unittest.TestCase):
    """``page_holds`` darf NIE grosszuegiger sein als ``find_first``."""

    def test_treffer_auf_der_seite(self):
        self.assertTrue(refill.page_holds([_slot('Worm')], ('Worm',)))

    def test_leere_und_fremde_slots_halten_nicht(self):
        self.assertFalse(refill.page_holds(
            [_slot(None, state='empty'), _slot('Fischpuzzlebox')], ('Worm',)))

    def test_zu_unsicherer_treffer_haelt_den_scan_nicht_an(self):
        """Ein Kandidat jenseits der Match-Grenze wird von ``find_first``
        verworfen -- der Frueh-Ausstieg muss ihn genauso verwerfen, sonst endet
        der Scan auf einer Seite ohne brauchbaren Koeder."""
        zu_weit = _slot('Worm', distance=refill.REFILL_MAX_DISTANCE + 5.0)
        self.assertFalse(refill.page_holds([zu_weit], ('Worm',)))
        inv = types.SimpleNamespace(pages={'I': [zu_weit]})
        self.assertIsNone(refill.find_first(inv, ('Worm',)))

    def test_grenzfall_genau_auf_der_schwelle_zaehlt_fuer_beide(self):
        genau = _slot('Worm', distance=refill.REFILL_MAX_DISTANCE)
        self.assertTrue(refill.page_holds([genau], ('Worm',)))
        inv = types.SimpleNamespace(pages={'I': [genau]})
        self.assertEqual(refill.find_first(inv, ('Worm',)), ('I', 0, 0))

    def test_ohne_distanz_angabe_zaehlt_fuer_beide(self):
        ohne = types.SimpleNamespace(state='item', name='Worm', row=1, col=2)
        self.assertTrue(refill.page_holds([ohne], ('Worm',)))
        inv = types.SimpleNamespace(pages={'I': [ohne]})
        self.assertEqual(refill.find_first(inv, ('Worm',)), ('I', 1, 2))

    def test_wirft_nie(self):
        self.assertFalse(refill.page_holds(None, ('Worm',)))
        self.assertFalse(refill.page_holds([object()], ('Worm',)))


class TestScannerBrichtAb(unittest.TestCase):
    """``scan_inventory`` fragt nach jeder Seite nach -- und hoert dann auf."""

    def _lauf(self, treffer_seite, early=True):
        besucht = []

        def switch_page_fn(page):
            besucht.append(page)

        def fake_page(page, *_a, **_k):
            return [_slot('Worm')] if page == treffer_seite else [
                _slot(None, state='empty')]

        stop = (lambda page, slots: refill.page_holds(slots, ('Worm',))) \
            if early else None
        orig = scanner._scan_one_page
        scanner._scan_one_page = lambda page, *a, **k: fake_page(page)
        try:
            inv = scanner.scan_inventory(
                capture_fn=lambda: None, switch_page_fn=switch_page_fn,
                db=object(), early_stop_fn=stop)
        finally:
            scanner._scan_one_page = orig
        return besucht, inv

    def test_stoppt_nach_seite_eins(self):
        besucht, inv = self._lauf('I')
        self.assertEqual(besucht, [])   # switch macht der echte Scanner intern
        self.assertEqual(list(inv.pages), ['I'])

    def test_laeuft_bis_zur_seite_mit_dem_treffer(self):
        _besucht, inv = self._lauf('III')
        self.assertEqual(list(inv.pages), ['I', 'II', 'III'])

    def test_ohne_treffer_werden_alle_seiten_gescannt(self):
        _besucht, inv = self._lauf('gibtsnicht')
        self.assertEqual(list(inv.pages), ['I', 'II', 'III', 'IV'])

    def test_ohne_rueckfrage_unveraendert_alle_seiten(self):
        _besucht, inv = self._lauf('I', early=False)
        self.assertEqual(list(inv.pages), ['I', 'II', 'III', 'IV'])

    def test_werfende_rueckfrage_kippt_den_scan_nicht(self):
        def kaputt(_page, _slots):
            raise RuntimeError('boom')

        orig = scanner._scan_one_page
        scanner._scan_one_page = lambda page, *a, **k: [_slot('Worm')]
        try:
            inv = scanner.scan_inventory(
                capture_fn=lambda: None, switch_page_fn=lambda _p: None,
                db=object(), early_stop_fn=kaputt)
        finally:
            scanner._scan_one_page = orig
        # Im Zweifel weiterscannen -> bisheriges Verhalten, kein Absturz.
        self.assertEqual(list(inv.pages), ['I', 'II', 'III', 'IV'])


class TestNachlegenBlaettertNichtWeiter(unittest.TestCase):
    """Der echte ``refill_from_inventory``-Pfad, mit einem Scanner-Double, das
    die Seiten-Schleife des Originals nachbildet (Wechsel -> Seite -> Rueckfrage).
    """

    def _lauf(self, layout):
        from inventory import scanner as scanner_mod
        gewechselt = []

        def fake_scan(*, capture_fn, switch_page_fn, db, calib, pages=None,
                      early_stop_fn=None):
            seiten = {}
            for page in (pages or refill.PAGE_ORDER):
                switch_page_fn(page)
                gewechselt.append(page)
                seiten[page] = layout.get(page, [])
                if early_stop_fn is not None and early_stop_fn(page, seiten[page]):
                    break
            return types.SimpleNamespace(pages=seiten)

        orig = scanner_mod.scan_inventory
        scanner_mod.scan_inventory = fake_scan
        try:
            rec = _Recorder()
            result = refill.refill_from_inventory(
                ('Worm',), (200, 200), inp=rec, wincap=_Wincap(),
                db=object(), sleep=lambda *_: None)
        finally:
            scanner_mod.scan_inventory = orig
        return result, gewechselt, rec

    def test_koeder_auf_seite_eins_kostet_eine_seite(self):
        result, gewechselt, rec = self._lauf({'I': [_slot('Worm')]})
        self.assertEqual(result, 'dragged')
        self.assertEqual(gewechselt, ['I'],
                         'es wurden Seiten durchgeblaettert, die niemand braucht')
        self.assertIn(('down',), rec.events)

    def test_koeder_auf_seite_drei_blaettert_bis_dorthin(self):
        result, gewechselt, _rec = self._lauf({'III': [_slot('Worm')]})
        self.assertEqual(result, 'dragged')
        self.assertEqual(gewechselt, ['I', 'II', 'III'])

    def test_kein_koeder_scannt_weiter_alle_seiten(self):
        """Erst wenn WIRKLICH nichts da ist, darf 'empty' gemeldet werden --
        sonst stoppte der Bot mit vollem Beutel."""
        result, gewechselt, _rec = self._lauf({})
        self.assertEqual(result, 'empty')
        self.assertEqual(gewechselt, ['I', 'II', 'III', 'IV'])

    def test_ergebnis_gleich_wie_beim_vollscan(self):
        """Gleichwertigkeits-Nachweis: derselbe Slot wird gezogen wie ohne
        Frueh-Ausstieg -- Seite II traegt hier ebenfalls einen Wurm."""
        layout = {'I': [_slot('Worm', row=2, col=3)],
                  'II': [_slot('Worm', row=0, col=0)]}
        voll = refill.find_first(types.SimpleNamespace(pages=layout), ('Worm',))
        self.assertEqual(voll, ('I', 2, 3))
        result, gewechselt, _rec = self._lauf(layout)
        self.assertEqual(result, 'dragged')
        self.assertEqual(gewechselt, ['I'])


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
