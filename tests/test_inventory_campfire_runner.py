# -*- coding: utf-8 -*-
"""Tests for the LIVE Lagerfeuer-Braten wrapper (inventory_campfire_runner).

All headless: the module's soft-imported live deps (``pydirectinput``,
``WindowCapture``) and ``inventory.grid.auto_align`` / ``scan_inventory`` are
MONKEYPATCHED, no game / win32 needed. These pin the THREE live-wiring fixes:

  * LOCK-ONCE -- ``run_campfire_grill`` runs ``auto_align`` exactly ONCE on a
    captured frame and threads the LOCKED lattice into ``run_campfire`` so the
    drag SOURCE + tool double-click hit the grid recognition uses (the user's
    bag sits ~1 slot above DEFAULT_CALIBRATION).
  * PARK -- the managed-scan tab switch parks the cursor OFF the tab/grid after
    the click (MOVE-only, restores PAUSE), exactly like
    ``inventory_runner._Runner.switch_page`` -- so the cursor never occludes the
    slot below the tab.
  * DEFENSIVE -- a failing auto-align lock degrades to ``None`` (run_campfire
    falls back to the calibration lattice); headless park / lock never raise.
"""

import types
import unittest

import interface.inventory_campfire_runner as cr
import inventory_campfire as campfire
from inventory.constants import DEFAULT_CALIBRATION
from inventory.grid import GridLattice
from inventory import hover

try:
    import numpy as np
except Exception:                       # pragma: no cover
    np = None


def _slot(name, row, col, state='item'):
    return types.SimpleNamespace(state=state, name=name, row=row, col=col)


def _scan_sequence(*invs):
    """``scan_inventory``-Fake, das die Inventare der Reihe nach liefert.

    Der Grill scannt seit dem Mehrfeuer-Umbau nach JEDEM Feuer nach; ein Fake,
    der immer dasselbe liefert, waere ein echter Stillstand. Das letzte
    Inventar bleibt stehen.
    """
    state = {'i': 0}

    def _scan(**_kw):
        got = invs[min(state['i'], len(invs) - 1)]
        state['i'] += 1
        return got

    return _scan


def _inv(pages):
    return types.SimpleNamespace(pages=pages)


class _PDI:
    """Records pydirectinput calls; ``PAUSE`` round-trips. No real input."""

    def __init__(self):
        self.PAUSE = 0.0
        self.ev = []

    def keyDown(self, k):
        self.ev.append(('kd', k))

    def keyUp(self, k):
        self.ev.append(('ku', k))

    def click(self, x=None, y=None, **_):
        self.ev.append(('click', int(x), int(y)))

    def doubleClick(self, x=None, y=None, **_):
        self.ev.append(('dc', int(x), int(y)))

    def moveTo(self, x, y):
        self.ev.append(('mv', int(x), int(y)))

    def mouseDown(self, button=None, **_):
        # Bird's-eye right-drag recorded apart from the left fish-drag so the
        # first 'down' stays the fish drag (the assertions key off that).
        self.ev.append(('rdown',) if button == 'right' else ('down',))

    def mouseUp(self, button=None, **_):
        self.ev.append(('rup',) if button == 'right' else ('up',))


class _WinCap:
    offset_x = 1000
    offset_y = 500

    def __init__(self, _name):
        pass

    def get_screenshot(self):
        if np is None:                  # pragma: no cover
            return object()
        # The toggle-safe open guard (inventory.open_probe) probes this frame
        # BEFORE any click; stamp the real tab templates so it reads OPEN and
        # the wrapper proceeds (exercising the probe on the real wiring path).
        try:
            from tests._inv_synth import stamp_open_tabs
        except Exception:               # pragma: no cover - direct invocation
            from _inv_synth import stamp_open_tabs
        return stamp_open_tabs(np.zeros((632, 802, 3), dtype=np.uint8))


class _CampfireRunnerBase(unittest.TestCase):
    def setUp(self):
        self._orig = {}
        for name in ('pydirectinput', 'WindowCapture'):
            self._orig[name] = getattr(cr, name)
        self._orig['grid_auto_align'] = cr.grid_mod.auto_align
        # Plausibilitaets-Pruefung des Locks: auf dem SYNTHETISCHEN Frame findet
        # sie naturgemaess kein Item und wuerde jeden gemockten Lock verwerfen.
        # Hier neutral halten -- ihr eigenes Verhalten prueft
        # TestLockPlausibility.
        self._orig['aligned_match_count'] = cr.grid_mod.aligned_match_count
        cr.grid_mod.aligned_match_count = lambda *a, **k: 42
        self._orig['find_label'] = campfire.find_label
        self._orig['sleep'] = cr.time.sleep
        # Import-inside-function seam: scan_fn does `from inventory.scanner import
        # scan_inventory`, so patch it on the module.
        import inventory.scanner as sc
        self._sc = sc
        self._orig['scan_inventory'] = sc.scan_inventory
        cr.time.sleep = lambda *a, **k: None

    def tearDown(self):
        cr.pydirectinput = self._orig['pydirectinput']
        cr.WindowCapture = self._orig['WindowCapture']
        cr.grid_mod.auto_align = self._orig['grid_auto_align']
        cr.grid_mod.aligned_match_count = self._orig['aligned_match_count']
        campfire.find_label = self._orig['find_label']
        cr.time.sleep = self._orig['sleep']
        self._sc.scan_inventory = self._orig['scan_inventory']


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestLockOnceAndThread(_CampfireRunnerBase):
    def test_locks_grid_once_and_drag_uses_locked_grid(self):
        pdi = _PDI()
        cr.pydirectinput = pdi
        cr.WindowCapture = _WinCap

        locked = GridLattice(origin=(632, 245), pitch=(32, 32))
        align_calls = [0]

        def fake_align(frame, db, calib):
            align_calls[0] += 1
            return locked

        cr.grid_mod.auto_align = fake_align
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))

        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)]})
        # scan_fn calls switch_page_fn per page then returns the map. Der
        # Nachscan nach dem Feuer muss den gegrillten Fisch WEG zeigen -- sonst
        # meldet der Mehrfeuer-Grill zu Recht Stillstand.
        self._sc.scan_inventory = _scan_sequence(
            inv, _inv({'I': [_slot('Lagerfeuer', 0, 0)]}))

        # Nur Seite I freigegeben -- der Fake-Scan liefert auch nur sie. Mit
        # allen vier Seiten waere "complete" unbelegt (scan_incomplete).
        res = cr.run_campfire_grill({'inventory': {'hotkey': 'i',
                                                   'pages': [1]}},
                                    {'Carp': 2}, db=object())

        self.assertEqual(res.status, 'complete')
        # The grid was locked EXACTLY once (one fixed window -> one lock).
        self.assertEqual(align_calls[0], 1)
        # The Carp drag SOURCE uses the LOCKED grid: slot (1,2) on (632,245) +
        # offset (1000,500) = (1712, 793).
        ev = pdi.ev
        down_idx = next(i for i, e in enumerate(ev) if e[0] == 'down')
        self.assertEqual(ev[down_idx - 1], ('mv', 1712, 793))

    def test_failing_lock_degrades_to_calibration_fallback(self):
        # auto_align raising -> _lock_lattice returns None -> run_campfire uses the
        # calibration lattice (slot grabbed at the raw calib, the old behaviour),
        # and the grill still completes without raising.
        pdi = _PDI()
        cr.pydirectinput = pdi
        cr.WindowCapture = _WinCap

        def boom_align(frame, db, calib):
            raise RuntimeError('align down')

        cr.grid_mod.auto_align = boom_align
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))
        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)]})
        self._sc.scan_inventory = _scan_sequence(
            inv, _inv({'I': [_slot('Lagerfeuer', 0, 0)]}))

        res = cr.run_campfire_grill({'inventory': {'hotkey': 'i',
                                                   'pages': [1]}},
                                    {'Carp': 2}, db=object())
        self.assertEqual(res.status, 'complete')
        # Drag SOURCE = calibration-lattice slot (1,2) + offset (NOT the 245 lock).
        from inventory.grid import lattice_from_calibration
        cl = lattice_from_calibration(DEFAULT_CALIBRATION)
        ox, oy = cl.origin
        px, py = cl.pitch
        exp = (1000 + ox + 2 * px + px // 2, 500 + oy + 1 * py + py // 2)
        ev = pdi.ev
        down_idx = next(i for i, e in enumerate(ev) if e[0] == 'down')
        self.assertEqual(ev[down_idx - 1], ('mv',) + exp)


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestManagedScanParksCursor(_CampfireRunnerBase):
    def test_tab_switch_parks_off_grid(self):
        # The scan_fn._switch must park the cursor at hover.tab_park_point AFTER
        # each tab click (MOVE-only) so it never occludes the slot below the tab.
        pdi = _PDI()
        cr.pydirectinput = pdi
        cr.WindowCapture = _WinCap
        cr.grid_mod.auto_align = lambda f, d, c: GridLattice(origin=(632, 245),
                                                             pitch=(32, 32))
        campfire.find_label = lambda *a, **k: (True, 0.99, (300, 400))

        inv = _inv({'I': [_slot('Lagerfeuer', 0, 0), _slot('Carp', 1, 2)]})
        abfolgen = []

        # A scan_inventory that DRIVES switch_page_fn for every page, so _switch
        # (and its park) actually runs -- then returns the map. ``**_kw`` nimmt
        # hover_fn / early_stop_fn / verify_page_fn an: ohne ihn warf der Fake
        # einen TypeError, scan_fn schluckte ihn, und _switch lief NIE -- der
        # Test war gruen, ohne etwas zu pruefen (Review 2026-10-30, G10).
        def fake_scan(switch_page_fn=None, pages=(), **_kw):
            for p in pages:
                start = len(pdi.ev)
                switch_page_fn(p)
                abfolgen.append((p, pdi.ev[start:]))
            return inv

        self._sc.scan_inventory = fake_scan

        cr.run_campfire_grill({'inventory': {'hotkey': 'i'}},
                              {'Carp': 2}, db=object())

        park = hover.to_screen(
            [hover.tab_park_point(DEFAULT_CALIBRATION)],
            (1000, 500))[0]
        # Der Fake lief wirklich -- fuer alle vier Seiten.
        self.assertEqual([p for p, _ev in abfolgen][:4],
                         ['I', 'II', 'III', 'IV'])
        # Jeder Reiter-Klick wird SOFORT weggeparkt, noch vor der Aufnahme --
        # die Reiter-Pruefung liest das Bild direkt danach.
        for seite, ev in abfolgen:
            tx, ty = DEFAULT_CALIBRATION['tabs'][seite]
            self.assertEqual(ev[:2], [('click', 1000 + tx, 500 + ty),
                                      ('mv',) + tuple(park)], seite)
        # PAUSE was restored to its original value after each parked move.
        self.assertEqual(pdi.PAUSE, 0.0)
        # The park x sits LEFT of the grid's left edge (clear of every slot).
        grid_left = int(DEFAULT_CALIBRATION['grid']['tl'][0]) + 1000
        self.assertLess(park[0], grid_left)


def _frame_mit_offener_seite(seite):
    """Synthetischer Frame (Inventar offen), auf dem ``seite`` der hellste
    Reiter ist -- genau das, was ``grid.active_page`` als offen liest."""
    frame = _WinCap('METIN2').get_screenshot()
    cx, cy = DEFAULT_CALIBRATION['tabs'][seite]
    dx, dy = DEFAULT_CALIBRATION['tab_active']['offset']
    frame[cy + dy - 2:cy + dy + 3, cx + dx - 2:cx + dx + 3] = 255
    return frame


class _GrillStartBase(_CampfireRunnerBase):
    """Startet ``run_campfire_grill`` gegen ein Fake-``run_campfire`` und
    liefert dessen Keyword-Argumente (``scan_fn``, ``verify_page_fn`` ...)."""

    def _starte(self, cfg, wincap_cls=_WinCap):
        cr.pydirectinput = self.pdi = _PDI()
        cr.WindowCapture = wincap_cls
        cr.grid_mod.auto_align = lambda f, d, c: GridLattice(
            origin=(632, 245), pitch=(32, 32))
        got = {}
        orig_run = campfire.run_campfire

        def fake_run(states, **kw):
            got.update(kw)
            return campfire.CampfireResult('complete')

        campfire.run_campfire = fake_run
        try:
            cr.run_campfire_grill(cfg, {'Carp': 2}, db=object())
        finally:
            campfire.run_campfire = orig_run
        return got


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestReiterPruefungVerdrahtet(_GrillStartBase):
    """Grill-Scan und Grill-Zug belegen jeden Reiter-Wechsel.

    Nutzer-Meldung 2026-10-30: "Seite I klappt fast immer, II-IV fast nie".
    Der Haupt-Scan prueft den offenen Reiter seit jeher nach, das Grillen tat
    es nicht -- ein verschluckter Klick liess die alte Seite offen.
    """

    def test_grill_scan_prueft_den_offenen_reiter(self):
        got = self._starte({'inventory': {'hotkey': 'i', 'pages': [1, 3]}})
        mitschnitt = {}

        def fake_scan(**kw):
            mitschnitt.update(kw)
            return _inv({'I': [], 'III': []})

        self._sc.scan_inventory = fake_scan
        got['scan_fn']()
        self.assertEqual(tuple(mitschnitt['pages']), ('I', 'III'))
        verify = mitschnitt['verify_page_fn']
        self.assertEqual(verify(_frame_mit_offener_seite('III')), 'III')
        self.assertEqual(verify(_frame_mit_offener_seite('I')), 'I')

    def test_grill_zug_bekommt_pruefung_und_freigegebene_seiten(self):
        got = self._starte({'inventory': {'hotkey': 'i', 'pages': [2, 4]}})
        self.assertEqual(tuple(got['expected_pages']), ('II', 'IV'))
        self.assertTrue(callable(got['verify_page_fn']))

    def test_nachsehen_parkt_den_zeiger_vorher_und_liest_den_reiter(self):
        class _WinCapSeiteII(_WinCap):
            def get_screenshot(self):
                return _frame_mit_offener_seite('II')

        got = self._starte({'inventory': {'hotkey': 'i'}}, _WinCapSeiteII)
        self.pdi.ev[:] = []
        self.assertEqual(got['verify_page_fn'](), 'II')
        park = hover.to_screen(
            [hover.tab_park_point(DEFAULT_CALIBRATION)], (1000, 500))[0]
        # Erst weg vom Reiter (ein Reiter unter dem Zeiger kann heller wirken
        # als der offene), dann nachsehen.
        self.assertEqual(self.pdi.ev, [('mv',) + park])

    def test_ohne_bild_gilt_die_seite_als_nicht_belegt(self):
        class _WinCapBlind(_WinCap):
            blind = False

            def get_screenshot(self):
                if _WinCapBlind.blind:
                    return None
                return _WinCap.get_screenshot(self)

        got = self._starte({'inventory': {'hotkey': 'i'}}, _WinCapBlind)
        _WinCapBlind.blind = True
        self.assertIsNone(got['verify_page_fn']())


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestErsterGrillScanHovert(_GrillStartBase):
    """Frisch gefangene Fische leuchten, bis ein Zeiger sie ueberfaehrt -- und
    leuchtende Fische erkennt die Erkennung nicht. Auf II-IV landen genau die
    (Nutzer-Meldung 2026-10-30). Der ERSTE Scan jedes Grill-Laufs faehrt
    deshalb immer einmal ueber alle Slots, auch ohne die Option."""

    def _scans(self, cfg, anzahl=2):
        got = self._starte(cfg)
        aufrufe = []

        def fake_scan(**kw):
            aufrufe.append(kw)
            return _inv({'I': []})

        self._sc.scan_inventory = fake_scan
        for _ in range(anzahl):
            got['scan_fn']()
        return aufrufe

    def test_erster_scan_hovert_auch_ohne_option(self):
        aufrufe = self._scans({'inventory': {'hotkey': 'i', 'pages': [1]}})
        self.assertTrue(callable(aufrufe[0]['hover_fn']))
        # Ueberfahren loescht den Rahmen dauerhaft -- die Nachscans zwischen
        # den Feuern bleiben ohne Option so schnell wie bisher.
        self.assertIsNone(aufrufe[1]['hover_fn'])

    def test_mit_option_hovert_jeder_scan(self):
        aufrufe = self._scans({'inventory': {'hotkey': 'i', 'pages': [1],
                                             'hover_clear': True}})
        self.assertTrue(callable(aufrufe[0]['hover_fn']))
        self.assertTrue(callable(aufrufe[1]['hover_fn']))

    def test_sweep_folgt_dem_raster_des_scanners(self):
        """Der Scanner reicht jeder Seite ihr eigenes eingerastetes Raster in
        ``hover_fn(page, lattice)`` -- genau das faehrt der Sweep ab. Ein
        Rueckfall-Raster greift auf diesem Weg nie (Pre-Release-Review
        2026-10-30: der vorige Test pruefte nur diesen toten Rueckfall)."""
        aufrufe = self._scans({'inventory': {'hotkey': 'i', 'pages': [1]}},
                              anzahl=1)
        seite = GridLattice(origin=(640, 250), pitch=(32, 32))
        self.pdi.ev[:] = []
        aufrufe[0]['hover_fn']('II', seite)
        erster = hover.to_screen(hover.slot_centres(seite), (1000, 500))[0]
        moves = [e for e in self.pdi.ev if e[0] == 'mv']
        self.assertEqual(moves[0], ('mv',) + tuple(erster))


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestSeitenStehenInDerConsole(_GrillStartBase):
    """Die Seitenwahl gilt fuer Angeln UND Grillen. Wer nur mit Seite I angelt
    und den Timer-Cleanup grillen laesst, bekam still nur Seite I gegrillt --
    jetzt nennt der Start, welche Seiten dran sind."""

    def _zeilen(self, cfg):
        zeilen = []
        orig = cr._emit
        cr._emit = lambda _state, key, **fmt: zeilen.append((key, fmt))
        try:
            self._starte(cfg)
        finally:
            cr._emit = orig
        return zeilen

    def test_eingeschraenkte_seiten_werden_genannt(self):
        zeilen = self._zeilen({'inventory': {'hotkey': 'i', 'pages': [1]}})
        self.assertIn(('campfire.pages_limited',
                       {'pages': 'I', 'missing': 'II, III, IV'}), zeilen)

    def test_alle_seiten(self):
        zeilen = self._zeilen({'inventory': {'hotkey': 'i'}})
        self.assertIn(('campfire.pages_all', {'pages': 'I, II, III, IV'}),
                      zeilen)


class TestParkAndLockHelpersDefensive(unittest.TestCase):
    def test_park_headless_is_noop(self):
        orig = cr.pydirectinput
        cr.pydirectinput = None
        try:
            cr._park_cursor((0, 0), DEFAULT_CALIBRATION)   # must not raise
        finally:
            cr.pydirectinput = orig

    def test_park_restores_pause_and_moves_once(self):
        orig = cr.pydirectinput
        pdi = _PDI()
        pdi.PAUSE = 0.123
        cr.pydirectinput = pdi
        try:
            cr._park_cursor((1000, 500), DEFAULT_CALIBRATION)
        finally:
            cr.pydirectinput = orig
        moves = [e for e in pdi.ev if e[0] == 'mv']
        self.assertEqual(len(moves), 1)            # MOVE-only, exactly one
        self.assertEqual(pdi.PAUSE, 0.123)         # restored in finally

    def test_lock_returns_none_without_window_or_db(self):
        self.assertIsNone(cr._lock_lattice(None, object(), DEFAULT_CALIBRATION))

        class _WC:
            def get_screenshot(self):
                return None
        self.assertIsNone(cr._lock_lattice(_WC(), object(), DEFAULT_CALIBRATION))

    def test_lock_returns_none_on_align_error(self):
        orig = cr.grid_mod.auto_align

        class _WC:
            def get_screenshot(self):
                return 'frame'

        def boom(*a, **k):
            raise RuntimeError('down')

        cr.grid_mod.auto_align = boom
        try:
            self.assertIsNone(
                cr._lock_lattice(_WC(), object(), DEFAULT_CALIBRATION))
        finally:
            cr.grid_mod.auto_align = orig


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestLockPlausibility(_CampfireRunnerBase):
    """Ein Lock, der KEIN Item trifft, ist geraten -- und wird verworfen.

    Gemessen an der leeren Seite IV des Testers (2026-08-11): die
    count-maximierende Suche vergibt dort einen beliebigen Ursprung (623, 234)
    statt (632, 243) -- 9 px daneben, und genau dieser Lock steuert danach JEDEN
    Zug. Auf einer Seite ohne Items gibt es kein Signal, also darf das Ergebnis
    nicht wie ein Messwert behandelt werden.
    """

    def test_lock_without_any_match_falls_back_to_calibration(self):
        cr.pydirectinput = _PDI()
        cr.WindowCapture = _WinCap
        verschoben = GridLattice(origin=(623, 234), pitch=(32, 32))
        cr.grid_mod.auto_align = lambda *a, **k: verschoben
        cr.grid_mod.aligned_match_count = lambda *a, **k: 0     # leere Seite

        self.assertIsNone(cr._lock_lattice(_WinCap('METIN2'), object(), None))

    def test_lock_with_matches_is_kept(self):
        cr.pydirectinput = _PDI()
        cr.WindowCapture = _WinCap
        gut = GridLattice(origin=(632, 243), pitch=(32, 32))
        cr.grid_mod.auto_align = lambda *a, **k: gut
        cr.grid_mod.aligned_match_count = lambda *a, **k: 45

        self.assertIs(cr._lock_lattice(_WinCap('METIN2'), object(), None), gut)

    def test_a_broken_plausibility_check_never_kills_the_lock(self):
        """Defensiv: faellt die Pruefung aus, gilt der Lock wie bisher."""
        cr.pydirectinput = _PDI()
        cr.WindowCapture = _WinCap
        gut = GridLattice(origin=(632, 243), pitch=(32, 32))
        cr.grid_mod.auto_align = lambda *a, **k: gut

        def kaputt(*_a, **_k):
            raise RuntimeError('scorer down')

        cr.grid_mod.aligned_match_count = kaputt
        self.assertIs(cr._lock_lattice(_WinCap('METIN2'), object(), None), gut)
