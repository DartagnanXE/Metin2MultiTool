# -*- coding: utf-8 -*-
"""Der Not-Aus (F6) greift beim Inventar-Managen ueberall sofort.

User-Report 2026-09-10: "Während Inventar managen wird nicht direkt beendet,
wenn man F6 drückt -- der Notaus scheint nicht überall sofort zu greifen."

BEFUND (am simulierten Lauf gemessen). Die Abbruch-Flagge wurde nur an ZWEI
Stellen geprueft: vor jedem Fisch und zwischen zwei Feuern. Alles dazwischen
lief ungebremst weiter:

    F6 waehrend ...                    Verzoegerung
    Inventar-Scan                      1,60 s
    Feuer legen / Vogelperspektive     0,80 s
    Fisch aufs Feuer ziehen            0,20 s

Der Scan ist die groesste Luecke -- und er laeuft nach JEDEM Feuer erneut.

DIE VIER GESCHLOSSENEN LUECKEN:
  1. Wartezeiten schlafen jetzt in 0,05-s-Scheiben und pruefen jede davon
     (:func:`inventory_campfire.abbrechbar_schlafen`).
  2. Die Feuersuche prueft vor jedem der bis zu acht Drehversuche.
  3. Der Nachscan bricht nach der laufenden Seite ab statt nach allen vieren.
  4. Das Wegwerfen startet nach einem F6 waehrend des Grillens gar nicht erst.
"""

import unittest

import inventory_campfire as cf


class _Uhr:
    """Virtuelle Uhr: zaehlt Schlafzeit und misst, was NACH dem Not-Aus vergeht."""

    def __init__(self, ab=None):
        self.t = 0.0
        self.ab = ab
        self.nach = 0.0

    def sleep(self, s):
        d = float(s or 0)
        self.t += d
        if self.ab is not None and self.t >= self.ab:
            self.nach += d

    def abort(self):
        return self.ab is not None and self.t >= self.ab


class TestAbbrechbarSchlafen(unittest.TestCase):
    """Der Baustein: eine lange Pause in pruefbare Scheiben zerlegen."""

    def test_schlaeft_voll_aus_wenn_nichts_abbricht(self):
        u = _Uhr()
        weiter = cf.abbrechbar_schlafen(u.sleep, 0.8, None)
        self.assertTrue(weiter)
        self.assertAlmostEqual(u.t, 0.8, places=6)

    def test_bricht_bei_not_aus_sofort_ab(self):
        u = _Uhr(ab=0.2)
        weiter = cf.abbrechbar_schlafen(u.sleep, 0.8, u.abort)
        self.assertFalse(weiter, 'meldet kein Abbruch')
        # Nach dem Not-Aus darf hoechstens EINE Scheibe vergehen.
        self.assertLessEqual(u.nach, 0.05 + 1e-9,
                             'zu lange nach dem Not-Aus geschlafen')

    def test_gesamtzeit_bleibt_gleich_ohne_not_aus(self):
        """Die Zerlegung darf nichts verlangsamen."""
        for dauer in (0.05, 0.4, 0.8, 1.0):
            with self.subTest(dauer=dauer):
                u = _Uhr()
                cf.abbrechbar_schlafen(u.sleep, dauer, lambda: False)
                self.assertAlmostEqual(u.t, dauer, places=6)

    def test_wirft_nie(self):
        def kaputt():
            raise RuntimeError('boom')
        u = _Uhr()
        cf.abbrechbar_schlafen(u.sleep, 0.1, kaputt)       # darf nicht werfen

        def kaputter_schlaf(_s):
            raise RuntimeError('boom')
        cf.abbrechbar_schlafen(kaputter_schlaf, 0.1, None)

    def test_null_und_muell(self):
        u = _Uhr()
        self.assertTrue(cf.abbrechbar_schlafen(u.sleep, 0, None))
        self.assertTrue(cf.abbrechbar_schlafen(u.sleep, None, None))
        self.assertEqual(u.t, 0.0)


class TestFeuersuche(unittest.TestCase):
    """Die Suche dreht bis zu acht Mal -- der Not-Aus muss dazwischen greifen."""

    def test_bricht_vor_dem_naechsten_drehversuch_ab(self):
        drehungen = []
        u = _Uhr(ab=0.0)        # sofort abgebrochen
        fire, score, versuche = cf.locate_fire(
            lambda: 'frame', template=object(),
            rotate_fn=lambda: drehungen.append(1),
            sleep=u.sleep, abort_fn=u.abort)
        self.assertIsNone(fire)
        self.assertEqual(drehungen, [], 'trotz Not-Aus gedreht')

    def test_ohne_not_aus_wird_weiter_gesucht(self):
        """Gegenprobe: ohne Abbruch laeuft die Suche wie bisher."""
        drehungen = []
        orig = cf.find_label
        cf.find_label = lambda *a, **k: (False, 0.1, None)
        try:
            u = _Uhr()
            fire, score, versuche = cf.locate_fire(
                lambda: 'frame', template=object(),
                rotate_fn=lambda: drehungen.append(1), sleep=u.sleep,
                abort_fn=lambda: False)
        finally:
            cf.find_label = orig
        self.assertIsNone(fire)
        self.assertGreater(len(drehungen), 1, 'gar nicht gedreht')


def _lauf(ab, scan_scheibe=0.4):
    """Einen kompletten Grill-Lauf simulieren -> ``(uhr, ergebnis)``.

    ``scan_scheibe`` bildet den Nachscan ab: er kostet 1,6 s (vier Seiten a
    ~0,35 s Erkennung plus Reiter-Klicks) und kann seit dem Fix nach JEDER
    Seite abbrechen.
    """
    from tests.test_inventory_campfire import _Recorder, _inv, _slot
    u = _Uhr(ab=ab)
    inv = _inv({'I': [_slot('Lagerfeuer', 0, 0)]
                + [_slot('Carp', 1, i) for i in range(5)],
                'II': [_slot('Zander', 0, i) for i in range(5)]})
    leer = _inv({'I': [_slot('Lagerfeuer', 0, 0)], 'II': []})
    folge = [inv, inv, leer, leer, leer, leer]

    def scan_fn():
        rest = 1.6
        while rest > 0:
            if u.abort():
                break
            d = scan_scheibe if rest > scan_scheibe else rest
            u.sleep(d)
            rest -= d
        return folge.pop(0) if folge else leer

    orig = cf.find_label
    cf.find_label = lambda *a, **k: (True, 0.99, (300, 400))
    try:
        res = cf.run_campfire({'Carp': 2, 'Zander': 2}, inp=_Recorder(),
                              capture_rgb_fn=lambda: 'frame', scan_fn=scan_fn,
                              offset=(10, 20), sleep=u.sleep,
                              abort_fn=u.abort)
    finally:
        cf.find_label = orig
    return u, res


class TestGrillenBrichtUeberallAb(unittest.TestCase):
    """Der ganze Ablauf, an jeder Phase angehalten."""

    #: Obergrenze der Verzoegerung. Eine Seite des Nachscans (~0,4 s) ist die
    #: laengste nicht weiter teilbare Einheit -- sie ist EINE numpy-Operation.
    GRENZE = 0.45

    def test_reagiert_in_jeder_phase_schnell(self):
        for ab in (0.01, 0.5, 1.0, 1.7, 2.5, 3.5, 5.0):
            with self.subTest(f6_bei=ab):
                u, res = _lauf(ab)
                self.assertEqual(res.status, 'aborted',
                                 'Lauf endete nicht als abgebrochen')
                self.assertLessEqual(
                    u.nach, self.GRENZE,
                    'nach F6 vergingen noch %.2f s' % u.nach)

    def test_scan_phase_war_die_groesste_luecke(self):
        """Regression: frueher lief hier der GANZE Scan (1,6 s) durch."""
        u, res = _lauf(0.5)
        self.assertLess(u.nach, 1.6,
                        'der Scan laeuft wieder komplett durch')
        self.assertEqual(res.status, 'aborted')

    def test_ohne_not_aus_laeuft_alles_durch(self):
        """Gegenprobe: der Fix darf einen normalen Lauf nicht abwuergen."""
        u, res = _lauf(None)
        self.assertNotEqual(res.status, 'aborted')
        self.assertGreater(len(res.grilled), 0, 'nichts gegrillt')

    def test_abgebrochener_lauf_meldet_was_schon_gegrillt_wurde(self):
        """Ehrlichkeit: der Abbruch darf die bisherige Arbeit nicht verschweigen."""
        u, res = _lauf(3.5)
        self.assertEqual(res.status, 'aborted')
        self.assertGreater(len(res.grilled), 0)


class TestWegwerfenStartetNichtNachF6(unittest.TestCase):
    """Nach F6 waehrend des Grillens darf das Wegwerfen gar nicht anlaufen."""

    def test_sofortiger_ausstieg_ohne_fenster_oder_scan(self):
        from interface import inventory_discard_runner as dr
        from interface import inventory_manage as im
        beruehrt = []

        # Wuerde etwas angefasst, landete es hier -- der Ausstieg muss VOR
        # jedem Fenster-, Probe- oder Scan-Schritt passieren.
        orig_win = dr.WindowCapture
        dr.WindowCapture = lambda *a, **k: beruehrt.append('fenster')
        try:
            res = dr.run_discard_items(
                {}, {'Carp': im.REMOVE}, abort_fn=lambda: True)
        finally:
            dr.WindowCapture = orig_win
        self.assertEqual(getattr(res, 'status', None), 'aborted')
        self.assertEqual(beruehrt, [], 'trotz Not-Aus etwas angefasst')

    def test_ohne_not_aus_laeuft_es_normal_an(self):
        """Gegenprobe: ohne F6 darf der Sofort-Ausstieg nicht greifen."""
        from interface import inventory_discard_runner as dr
        res = dr.run_discard_items({}, {}, abort_fn=lambda: False)
        # Ohne markierte Items ist 'no_items' das richtige Ergebnis --
        # entscheidend ist nur, dass es NICHT 'aborted' ist.
        self.assertNotEqual(getattr(res, 'status', None), 'aborted')


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
