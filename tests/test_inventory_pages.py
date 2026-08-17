# -*- coding: utf-8 -*-
"""Freigegebene Inventar-Seiten (I-IV) -- eine Quelle fuer den ganzen Bot.

Der Nutzer markiert, welche Seiten benutzt werden duerfen; abgewaehlte bleiben
KOMPLETT unberuehrt: kein Reiter-Klick, kein Screenshot, keine Erkennung. Zwei
Ebenen werden hier gesichert:

  * die reine Logik (:mod:`inventory.pages`) inklusive Fail-safe,
  * die Verdrahtung -- dass der Scanner wirklich nur die freigegebenen Reiter
    anfaesst (der eigentliche Zweck; eine korrekte Liste nuetzt nichts, wenn sie
    unterwegs verlorengeht).
"""

import types
import unittest

from inventory import pages as inv_pages


class TestNormalize(unittest.TestCase):
    def test_plain_selection(self):
        self.assertEqual(inv_pages.normalize_pages([1, 3]), (1, 3))

    def test_sorted_and_deduped(self):
        self.assertEqual(inv_pages.normalize_pages([4, 1, 4, 1]), (1, 4))

    def test_roman_labels_are_accepted(self):
        self.assertEqual(inv_pages.normalize_pages(['I', 'IV']), (1, 4))

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(inv_pages.normalize_pages(['2', 3]), (2, 3))

    def test_empty_falls_back_to_all(self):
        """FAIL-SAFE: lieber einmal zu viel scannen als nirgends nachschauen."""
        for leer in ([], (), set(), None):
            self.assertEqual(inv_pages.normalize_pages(leer),
                             inv_pages.ALL_PAGES)

    def test_garbage_falls_back_to_all(self):
        for muell in ('kaputt', [0, 9, -1], [None], object()):
            self.assertEqual(inv_pages.normalize_pages(muell),
                             inv_pages.ALL_PAGES)

    def test_partial_garbage_keeps_the_valid_rest(self):
        self.assertEqual(inv_pages.normalize_pages([1, 'quatsch', 'IV']), (1, 4))


class TestRomanPages(unittest.TestCase):
    def test_maps_to_the_scanner_format(self):
        self.assertEqual(inv_pages.roman_pages([1, 3]), ('I', 'III'))

    def test_always_in_tab_order(self):
        """Reiter werden der Reihe nach durchgeklickt -- nie in Klick-Reihenfolge
        des Nutzers, das waere unnoetiges Hin-und-Her."""
        self.assertEqual(inv_pages.roman_pages([4, 2]), ('II', 'IV'))

    def test_empty_gives_all_four(self):
        self.assertEqual(inv_pages.roman_pages([]), ('I', 'II', 'III', 'IV'))


class TestIsAllowed(unittest.TestCase):
    def test_both_notations(self):
        self.assertTrue(inv_pages.is_allowed(1, [1, 2]))
        self.assertTrue(inv_pages.is_allowed('II', [1, 2]))
        self.assertFalse(inv_pages.is_allowed(3, [1, 2]))
        self.assertFalse(inv_pages.is_allowed('IV', [1, 2]))

    def test_garbage_is_not_allowed(self):
        self.assertFalse(inv_pages.is_allowed(None, [1, 2]))
        self.assertFalse(inv_pages.is_allowed('quatsch', [1, 2]))


class TestPagesFromConfig(unittest.TestCase):
    def test_reads_the_key(self):
        self.assertEqual(
            inv_pages.pages_from_config({'inventory': {'pages': [2]}}), (2,))

    def test_missing_key_gives_all(self):
        for cfg in ({}, {'inventory': {}}, None):
            self.assertEqual(inv_pages.pages_from_config(cfg),
                             inv_pages.ALL_PAGES)


class TestEnergiesplitterSharesTheSameSource(unittest.TestCase):
    """Beide Bot-Teile MUESSEN dieselbe Normalisierung benutzen.

    Sonst verhaelt sich dieselbe Einstellung im Angel- und im Energie-Teil
    unterschiedlich, sobald jemand nur eine der Kopien anfasst.
    """

    def test_functions_are_identical_objects(self):
        from energiesplitter import inventory_pages as es_pages
        self.assertIs(es_pages.normalize_pages, inv_pages.normalize_pages)
        self.assertIs(es_pages.is_allowed, inv_pages.is_allowed)
        self.assertIs(es_pages.ALL_PAGES, inv_pages.ALL_PAGES)


class TestScannerOnlyTouchesAllowedTabs(unittest.TestCase):
    """DER eigentliche Zweck: abgewaehlte Reiter werden nicht angefasst."""

    def test_scan_inventory_switches_only_to_allowed_pages(self):
        from inventory.scanner import scan_inventory
        geklickt = []

        def capture_fn():
            return None            # Erkennung faellt aus -> Seite bleibt leer

        def switch_page_fn(page):
            geklickt.append(page)

        scan_inventory(capture_fn=capture_fn, switch_page_fn=switch_page_fn,
                       db=None, pages=inv_pages.roman_pages([1, 3]))
        self.assertEqual(geklickt, ['I', 'III'])

    def test_capture_pages_buffers_only_allowed_pages(self):
        from inventory.scanner import capture_pages
        geklickt = []
        captured = capture_pages(
            capture_fn=lambda: types.SimpleNamespace(shape=(601, 800, 3)),
            switch_page_fn=geklickt.append,
            pages=inv_pages.roman_pages([2, 4]))
        # Erfasst werden GENAU die freigegebenen Seiten ...
        self.assertEqual(sorted(dict(captured or {}).keys()), ['II', 'IV'])
        # ... und kein gesperrter Reiter wird angefasst. Der letzte Klick ist der
        # dokumentierte Ruecksprung auf die ERSTE erfasste Seite -- hier richtig
        # 'II' statt blind 'I', das waere eine gesperrte Seite gewesen.
        self.assertEqual(geklickt[:2], ['II', 'IV'])
        self.assertNotIn('I', geklickt)
        self.assertNotIn('III', geklickt)
        self.assertEqual(geklickt[-1], 'II')


class TestConfigValidation(unittest.TestCase):
    """Die Auswahl muss die Config-Validierung unbeschadet ueberstehen."""

    def _validated(self, cfg):
        from interface.config.validate import validate
        return validate(dict(cfg))['inventory']['pages']

    def test_default_is_all_four(self):
        self.assertEqual(self._validated({}), [1, 2, 3, 4])

    def test_selection_survives(self):
        self.assertEqual(self._validated({'inventory': {'pages': [1, 3]}}),
                         [1, 3])

    def test_empty_selection_is_repaired(self):
        self.assertEqual(self._validated({'inventory': {'pages': []}}),
                         [1, 2, 3, 4])

    def test_garbage_is_repaired(self):
        self.assertEqual(self._validated({'inventory': {'pages': 'kaputt'}}),
                         [1, 2, 3, 4])


class TestCampfireRescanAcceptsASubset(unittest.TestCase):
    """Abgewaehlte Seiten duerfen den Lagerfeuer-Nachscan nicht als
    'unvollstaendig' erscheinen lassen.

    Der Grill sagt seit v1.6.9 nur dann "fertig", wenn ein VOLLSTAENDIGER
    Nachscan keinen markierten Fisch mehr findet -- gemessen an den Seiten, die
    der ERSTE Scan des Laufs geliefert hat. Genau deshalb funktioniert die
    Seitenauswahl hier ohne Sonderfall: scannt der Lauf durchgehend nur die
    freigegebenen Seiten, ist das die vollstaendige Sicht, und der Status muss
    'complete' sein -- nicht 'scan_incomplete'.
    """

    def test_subset_scan_still_reports_complete(self):
        import inventory_campfire as campfire

        def _slot(name, row, col):
            return types.SimpleNamespace(state='item', name=name,
                                         row=row, col=col)

        # Nur Seite I und III -- so wie der Scanner bei Auswahl [1, 3] liefert.
        voll = types.SimpleNamespace(pages={
            'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)],
            'III': [],
        })
        leer = types.SimpleNamespace(pages={
            'I': [_slot('Lagerfeuer', 0, 0)],
            'III': [],
        })
        state = {'n': 0}

        def _scan():
            got = voll if state['n'] == 0 else leer
            state['n'] += 1
            return got

        class _Rec(object):
            def __getattr__(self, _n):
                return lambda *a, **k: None

        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))
        try:
            res = campfire.run_campfire(
                {'Carp': 2}, inp=_Rec(), capture_rgb_fn=lambda: 'frame',
                scan_fn=_scan, offset=(0, 0), sleep=lambda *_a, **_k: None)
        finally:
            campfire.find_label = orig

        self.assertEqual(res.status, 'complete')
        self.assertEqual(res.remaining, 0)


if __name__ == '__main__':
    unittest.main()
