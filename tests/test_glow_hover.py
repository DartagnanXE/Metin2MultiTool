# -*- coding: utf-8 -*-
"""Maus-Hover vor dem Scan: Leuchtrahmen loeschen (User-Wunsch 2026-09-10).

WARUM ES DAS BRAUCHT. Ein frisch erhaltenes Item traegt einen LEUCHT-RAHMEN,
bis der Zeiger einmal darueber gefahren ist. Am echten Client gemessen
(2026-08-11): derselbe Yabbie hat im dunklen Slot die Match-Distanz **0,1**, im
leuchtenden **26,45** -- gegen die Schwelle 22. Er gilt damit als "unbekannt"
und wandert nie aufs Lagerfeuer. Genau das wurde als Fehler gemeldet.

Die Schwelle anzuheben scheidet aus: bei Distanz 29,5 liegt ein dokumentierter
Fehltreffer (bronzenes Abzeichen als 'Worm', 2026-08-05). Zwischen 26,45 und
29,5 passt keine Schwelle.

ZWEI HARTE ZUSAGEN, die diese Tests festhalten:
  1. Der Sweep KLICKT NIE -- ein Klick wuerde ein Item aufnehmen.
  2. Er ist standardmaessig AUS; ohne Schalter aendert sich am Verhalten nichts.
"""

import unittest

from inventory import glow
from inventory.constants import COLS, DEFAULT_CALIBRATION, ROWS
from inventory.grid import lattice_from_calibration


class _Recorder:
    """Eingabe-Attrappe: zeichnet Bewegungen auf, KLICKS waeren ein Fehler."""

    PAUSE = 0.05

    def __init__(self):
        self.moves = []
        self.clicks = []
        self.pause_verlauf = []

    def moveTo(self, x, y):
        self.pause_verlauf.append(self.PAUSE)
        self.moves.append((x, y))

    def click(self, *a, **k):           # pragma: no cover - darf nie passieren
        self.clicks.append((a, k))

    def mouseDown(self, *a, **k):       # pragma: no cover
        self.clicks.append(('down', a, k))


def _lattice():
    return lattice_from_calibration(DEFAULT_CALIBRATION)


class TestSweep(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self.lat = _lattice()

    def _sweep(self, **kw):
        kw.setdefault('sleep', lambda s: None)
        return glow.sweep(self.rec, self.lat, **kw)

    def test_faehrt_jeden_slot_genau_einmal_an(self):
        n = self._sweep()
        self.assertEqual(n, ROWS * COLS)
        self.assertEqual(n, 45)
        # 45 Slots + 1 Parkposition
        self.assertEqual(len(self.rec.moves), 46)
        self.assertEqual(len(set(self.rec.moves[:45])), 45, 'Slot doppelt')

    def test_klickt_niemals(self):
        """DIE wichtigste Zusage: ein Klick wuerde das Item aufnehmen."""
        self._sweep()
        self.assertEqual(self.rec.clicks, [], 'der Sweep hat GEKLICKT')

    def test_parkt_den_zeiger_unter_dem_raster(self):
        """Sonst steht der Hardware-Zeiger auf der folgenden Aufnahme mit im
        Bild und degradiert genau diesen Slot zu 'unbekannt'."""
        self._sweep()
        park = self.rec.moves[-1]
        unterste = max(y for _x, y in self.rec.moves[:45])
        self.assertGreater(park[1], unterste, 'Park liegt nicht unter dem Raster')

    def test_laeuft_mit_voller_geschwindigkeit(self):
        """Waehrend des Sweeps muss PAUSE 0 sein -- sonst warte die
        Eingabe-Schicht nach JEDER der 45 Bewegungen ihre 0,05 s ab (2,3 s)."""
        self._sweep()
        self.assertTrue(all(p == 0 for p in self.rec.pause_verlauf),
                        'PAUSE war waehrend des Sweeps nicht 0')

    def test_stellt_pause_wieder_her(self):
        self._sweep()
        self.assertEqual(self.rec.PAUSE, 0.05)

    def test_stellt_pause_auch_nach_fehler_wieder_her(self):
        class Kaputt(_Recorder):
            def moveTo(self, x, y):
                raise RuntimeError('boom')
        k = Kaputt()
        glow.sweep(k, self.lat, sleep=lambda s: None)
        self.assertEqual(k.PAUSE, 0.05, 'PAUSE blieb auf 0 stehen')

    def test_schlangenlinie(self):
        """Boustrophedon: 44 kurze Spruenge statt 44 kurze + 8 lange."""
        self._sweep()
        xs = [x for x, _y in self.rec.moves[:45]]
        zeile0, zeile1 = xs[:COLS], xs[COLS:2 * COLS]
        self.assertEqual(zeile0, sorted(zeile0))
        self.assertEqual(zeile1, sorted(zeile1, reverse=True))

    def test_offset_wird_addiert(self):
        ohne = glow.sweep(_Recorder(), self.lat, sleep=lambda s: None)
        r2 = _Recorder()
        glow.sweep(r2, self.lat, offset=(100, 200), sleep=lambda s: None)
        r3 = _Recorder()
        glow.sweep(r3, self.lat, offset=(0, 0), sleep=lambda s: None)
        self.assertEqual(ohne, 45)
        dx = r2.moves[0][0] - r3.moves[0][0]
        dy = r2.moves[0][1] - r3.moves[0][1]
        self.assertEqual((dx, dy), (100, 200))

    def test_tempo_wird_gedeckelt(self):
        geschlafen = []
        glow.sweep(self.rec, self.lat, speed_ms=9999,
                   sleep=lambda s: geschlafen.append(s))
        self.assertLessEqual(max(geschlafen), glow.MAX_SPEED_MS / 1000.0)

    def test_tempo_null_schlaeft_nicht_je_slot(self):
        geschlafen = []
        glow.sweep(self.rec, self.lat, speed_ms=0,
                   sleep=lambda s: geschlafen.append(s))
        # nur die eine Settle-Pause am Ende, keine 45 Einzelpausen
        self.assertEqual(len(geschlafen), 1)

    def test_defensiv(self):
        self.assertEqual(glow.sweep(None, self.lat), 0)
        self.assertEqual(glow.sweep(self.rec, None), 0)
        self.assertEqual(self.rec.moves, [])


class TestHoverFn(unittest.TestCase):
    """Die Form, die die Scanner erwarten: ``hover_fn(page)``."""

    def test_ruft_den_sweep_je_seite(self):
        rec = _Recorder()
        fn = glow.make_hover_fn(rec, lambda _p: _lattice(),
                                sleep=lambda s: None)
        fn('I')
        fn('II')
        self.assertEqual(len(rec.moves), 2 * 46)
        self.assertEqual(rec.clicks, [])

    def test_ohne_raster_wird_uebersprungen(self):
        rec = _Recorder()
        fn = glow.make_hover_fn(rec, lambda _p: None, sleep=lambda s: None)
        fn('I')
        self.assertEqual(rec.moves, [])

    def test_werfende_raster_funktion_kippt_nicht(self):
        rec = _Recorder()

        def kaputt(_p):
            raise RuntimeError('boom')
        fn = glow.make_hover_fn(rec, kaputt, sleep=lambda s: None)
        fn('I')          # darf nicht werfen
        self.assertEqual(rec.moves, [])


class TestScannerVerdrahtung(unittest.TestCase):
    """``capture_pages`` muss VOR der Aufnahme hovern -- danach waere zu spaet."""

    def _lauf(self, hover_fn):
        from inventory import scanner
        reihenfolge = []

        def switch(page):
            reihenfolge.append(('switch', page))

        def capture():
            reihenfolge.append(('capture', None))
            return object()

        def hf(page):
            reihenfolge.append(('hover', page))
            if hover_fn:
                hover_fn(page)

        scanner.capture_pages(capture, switch, pages=('I', 'II'),
                              hover_fn=hf if hover_fn is not None else None)
        return reihenfolge

    def test_hover_liegt_zwischen_wechsel_und_aufnahme(self):
        r = self._lauf(lambda p: None)
        # Erste Seite: switch -> hover -> capture
        self.assertEqual(r[0], ('switch', 'I'))
        self.assertEqual(r[1], ('hover', 'I'))
        self.assertEqual(r[2], ('capture', None))

    def test_ohne_hover_fn_unveraendertes_verhalten(self):
        r = self._lauf(None)
        self.assertNotIn('hover', [a for a, _b in r])
        self.assertEqual(r[0], ('switch', 'I'))
        self.assertEqual(r[1], ('capture', None))

    def test_werfendes_hover_kippt_den_scan_nicht(self):
        from inventory import scanner

        def kaputt(_p):
            raise RuntimeError('boom')
        # capture_pages faengt Fehler je Seite ab -> Ergebnis ist leer, aber
        # es fliegt nichts nach oben.
        out = scanner.capture_pages(lambda: object(), lambda p: None,
                                    pages=('I',), hover_fn=kaputt)
        self.assertIsInstance(out, dict)


class TestVoreinstellung(unittest.TestCase):
    """Default AUS -- ohne Schalter aendert sich nichts am Verhalten."""

    def test_default_ist_aus(self):
        from interface.config.defaults import DEFAULTS
        self.assertFalse(DEFAULTS['inventory']['hover_clear'])
        self.assertEqual(DEFAULTS['inventory']['hover_speed_ms'], 0)

    def test_validierung_faengt_muell(self):
        from interface.config.validate import validate
        for roh, erwartet_ms in ((-5, 0), (9999, 50), ('schnell', 0),
                                 (None, 0), (7, 7)):
            with self.subTest(roh=roh):
                c = validate({'inventory': {'hover_speed_ms': roh}})
                self.assertEqual(c['inventory']['hover_speed_ms'], erwartet_ms)

    def test_validierung_haelt_den_schalter(self):
        from interface.config.validate import validate
        self.assertTrue(
            validate({'inventory': {'hover_clear': True}})['inventory']['hover_clear'])
        self.assertFalse(
            validate({'inventory': {'hover_clear': False}})['inventory']['hover_clear'])


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
