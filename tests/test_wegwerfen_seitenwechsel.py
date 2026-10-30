# -*- coding: utf-8 -*-
"""Wegwerfen ueber mehrere Inventar-Seiten: jeder Reiter-Wechsel wird belegt.

Derselbe Mechanismus wie beim Grillen (Nutzer-Meldung 2026-10-30, Review G12),
nur mit schlimmerer Folge: Bleibt ein Reiter-Klick aus, steht noch die alte
Seite offen, der Zug greift dort an derselben Stelle zu -- und das blinde "Ja"
laesst ein Item fallen, das nie markiert war.

Die Tests fahren den echten Ablauf (:func:`inventory_discard.run_discard`)
gegen ein kleines Spielmodell. Gemessen wird am MODELL, was wirklich auf dem
Boden liegt; die Erfolgsmeldung des Bots allein beweist nichts.
"""

import types
import unittest

import inventory_discard as discard
from interface import inventory_manage as im
from inventory.constants import DEFAULT_CALIBRATION
from inventory.grid import GridLattice

try:
    import numpy as np
except Exception:                       # pragma: no cover
    np = None

OFFSET = (10, 20)
LAT = GridLattice(origin=(600, 240), pitch=(32, 32))
CLIENT = (800, 600)
JA = discard.confirm_yes_point(CLIENT[0], CLIENT[1], offset=OFFSET)
SEITEN = ('I', 'II', 'III', 'IV')
MARKIERT = {'Old_Boot': im.REMOVE}


def _slot_unter(x, y):
    ox, oy = LAT.origin
    px, py = LAT.pitch
    col = (x - OFFSET[0] - ox) // px
    row = (y - OFFSET[1] - oy) // py
    if 0 <= col < 5 and 0 <= row < 9:
        return (row, col)
    return None


def _reiter_unter(x, y):
    for seite, (tx, ty) in DEFAULT_CALIBRATION['tabs'].items():
        if abs(x - OFFSET[0] - tx) <= 17 and abs(y - OFFSET[1] - ty) <= 7:
            return seite
    return None


class _Spiel(object):
    """Spielmodell mit der Eingabe-API von pydirectinput (Wegwerfen).

    Ein Zug aus dem Raster in die Welt oeffnet den Dialog "Moechtest du X
    fallen lassen?", ein Klick auf "Ja" laesst genau dieses Item fallen.

    :param verschluckt_nach_ja: ein Reiter-Klick DIREKT nach dem "Ja" schaltet
        nicht um; der Klick danach wirkt wieder.
    :param tote_reiter: Reiter, die nie umschalten.
    """

    def __init__(self, seiten, verschluckt_nach_ja=False, tote_reiter=()):
        self.seiten = {p: dict(seiten.get(p, {})) for p in SEITEN}
        self.sichtbar = 'I'
        self.maus = (0, 0)
        self.gehalten = None
        self.dialog = None
        self.zuletzt_ja = False
        self.verschluckt_nach_ja = verschluckt_nach_ja
        self.tote_reiter = set(tote_reiter)
        self.am_boden = []
        self.reiter_klicks = []
        self.PAUSE = 0.05

    # -- Eingabe ----------------------------------------------------------
    def moveTo(self, x, y):
        self.maus = (int(x), int(y))

    def click(self, x=None, y=None, **_):
        self.moveTo(x, y)
        if (self.dialog is not None and abs(x - JA[0]) <= 3
                and abs(y - JA[1]) <= 3):
            seite, rc, item = self.dialog
            self.dialog = None
            del self.seiten[seite][rc]
            self.am_boden.append((seite, rc[0], rc[1], item))
            self.zuletzt_ja = True
            return
        seite = _reiter_unter(x, y)
        verschluckt = self.zuletzt_ja and self.verschluckt_nach_ja
        self.zuletzt_ja = False
        if seite is None:
            return
        self.reiter_klicks.append(seite)
        if verschluckt or seite in self.tote_reiter:
            return
        self.sichtbar = seite

    def mouseDown(self, *_a, **_k):
        rc = _slot_unter(*self.maus)
        item = self.seiten[self.sichtbar].get(rc) if rc else None
        self.gehalten = (self.sichtbar, rc, item) if item else None

    def mouseUp(self, *_a, **_k):
        gehalten, self.gehalten = self.gehalten, None
        if gehalten is not None and _slot_unter(*self.maus) is None:
            self.dialog = gehalten

    # -- Sicht des Bots ----------------------------------------------------
    def sichtbare_seite(self):
        return self.sichtbar

    def scan(self):
        """Perfekter Scan aller Seiten -- isoliert den Wegwerf-Zug."""
        return types.SimpleNamespace(pages={
            p: [types.SimpleNamespace(state='item', name=n, row=r, col=c)
                for (r, c), n in sorted(self.seiten[p].items())]
            for p in SEITEN})

    def rest(self, name='Old_Boot'):
        return {p: sorted(rc for rc, n in s.items() if n == name)
                for p, s in self.seiten.items()}


def _beutel():
    """Seite I traegt Wertvolles GENAU dort, wo auf II und III der Muell liegt
    -- dort greift ein Zug, der auf der falschen Seite landet."""
    return {
        'I': {(0, 0): 'Fischpuzzlebox_Deluxe', (0, 1): 'Gold_Ring',
              (1, 0): 'Worm'},
        'II': {(0, 0): 'Old_Boot', (0, 1): 'Old_Boot'},
        'III': {(0, 0): 'Old_Boot', (1, 0): 'Carp'},
    }


def _wirf(spiel, pruefen=True, expected_pages=SEITEN, verify=None,
          abort_fn=None):
    return discard.run_discard(
        MARKIERT, inp=spiel, capture_fn=lambda: 'frame', scan_fn=spiel.scan,
        client_size=CLIENT, offset=OFFSET, lattice=LAT,
        sleep=lambda *_a, **_k: None, abort_fn=abort_fn,
        verify_page_fn=(verify or spiel.sichtbare_seite) if pruefen else None,
        expected_pages=expected_pages if pruefen else None)


class _LogMitschnitt(object):
    """Faengt Schluessel und Werte von ``discard._flog`` mit."""

    def __enter__(self):
        self.keys = []
        self.eintraege = []
        self._orig = discard._flog

        def _mit(_state, key, **fmt):
            self.keys.append(key)
            self.eintraege.append((key, dict(fmt)))

        discard._flog = _mit
        return self

    def __exit__(self, *_exc):
        discard._flog = self._orig
        return False


def _ohne_seite(spiel, seite):
    """Scan, dem ``seite`` fehlt (Reiter liess sich beim Scan nicht oeffnen)."""
    voll = spiel.scan

    def _scan():
        inv = voll()
        del inv.pages[seite]
        return inv

    spiel.scan = _scan
    return spiel


class TestVerschluckterReiterKlick(unittest.TestCase):

    @staticmethod
    def _spiel():
        spiel = _Spiel(_beutel(), verschluckt_nach_ja=True)
        spiel.zuletzt_ja = True     # der naechste Reiter-Klick geht verloren
        return spiel

    def test_ohne_pruefung_faellt_ein_nie_markiertes_item(self):
        """Gegenprobe: Das Modell loest den Fehler wirklich aus. Ohne Pruefung
        klickt der Ablauf blind wie bis v1.6.15 -- und laesst die Deluxe-Box
        von Seite I fallen."""
        spiel = self._spiel()
        _wirf(spiel, pruefen=False)
        am_boden = {item for (_p, _r, _c, item) in spiel.am_boden}
        self.assertIn('Fischpuzzlebox_Deluxe', am_boden)

    def test_mit_pruefung_nur_markierte_items_von_der_richtigen_seite(self):
        spiel = self._spiel()
        res = _wirf(spiel)
        self.assertEqual(res.status, 'done')
        self.assertEqual({item for (_p, _r, _c, item) in spiel.am_boden},
                         {'Old_Boot'})
        self.assertEqual(spiel.rest(), {p: [] for p in SEITEN})
        self.assertEqual(spiel.seiten['I'], _beutel()['I'])
        # Was der Bot meldet, ist genau das, was im Spiel fiel.
        self.assertEqual(sorted(res.dropped), sorted(spiel.am_boden))


class TestReiterDerNieAufgeht(unittest.TestCase):

    def test_seite_bleibt_unberuehrt_und_der_lauf_ist_unvollstaendig(self):
        spiel = _Spiel(_beutel(), tote_reiter={'III'})
        with _LogMitschnitt() as log:
            res = _wirf(spiel)
        self.assertEqual(res.status, 'incomplete')
        self.assertEqual(spiel.rest()['II'], [])
        self.assertEqual(spiel.rest()['III'], [(0, 0)])
        self.assertEqual({item for (_p, _r, _c, item) in spiel.am_boden},
                         {'Old_Boot'})
        fehl = [fmt for key, fmt in log.eintraege
                if key == 'discard.page_switch_failed']
        self.assertEqual(fehl, [{'page': 'III', 'got': 'II'}])
        self.assertIn('discard.incomplete', log.keys)

    def test_not_aus_waehrend_des_nachsehens(self):
        spiel = _Spiel(_beutel())
        stopp = {'an': False}

        def _blick():
            stopp['an'] = True          # F6 genau waehrend des Nachsehens
            return spiel.sichtbar

        res = _wirf(spiel, verify=_blick, abort_fn=lambda: stopp['an'])
        self.assertEqual(res.status, 'aborted')
        self.assertEqual(spiel.am_boden, [])


class TestOhnePruefungWieBisher(unittest.TestCase):

    def test_ein_reiterklick_je_item(self):
        """Ohne ``verify_page_fn`` bleibt der Klickstrom exakt der alte."""
        spiel = _Spiel(_beutel())
        res = _wirf(spiel, pruefen=False)
        self.assertEqual(res.status, 'done')
        self.assertEqual(spiel.reiter_klicks, ['II', 'II', 'III'])


class TestEhrlichesEnde(unittest.TestCase):

    def test_fehlt_eine_seite_im_scan_ist_es_unvollstaendig(self):
        spiel = _ohne_seite(_Spiel(_beutel()), 'III')
        with _LogMitschnitt() as log:
            res = _wirf(spiel)
        self.assertEqual(res.status, 'incomplete')
        self.assertEqual(spiel.rest()['II'], [])        # lesbare Seiten laufen
        self.assertEqual(spiel.rest()['III'], [(0, 0)])  # III bleibt liegen
        self.assertIn(('discard.scan_incomplete', {'pages': 'III'}),
                      log.eintraege)

    def test_ohne_ziel_aber_mit_fehlender_seite_ist_nicht_nichts_zu_tun(self):
        spiel = _ohne_seite(_Spiel({'III': {(0, 0): 'Old_Boot'}}), 'III')
        self.assertEqual(_wirf(spiel).status, 'incomplete')

    def test_ohne_erwartete_seiten_zaehlt_der_scan_wie_bisher(self):
        spiel = _ohne_seite(_Spiel(_beutel()), 'III')
        self.assertEqual(_wirf(spiel, expected_pages=None).status, 'done')


@unittest.skipUnless(np is not None, 'numpy required for the captured frame')
class TestVerdrahtung(unittest.TestCase):
    """Der Wegwerf-Runner gibt Scan und Zug die Reiter-Pruefung mit."""

    def setUp(self):
        from interface import inventory_discard_runner as dr
        import inventory.scanner as sc
        try:
            from tests.test_inventory_campfire_runner import (
                _PDI, _WinCap, _frame_mit_offener_seite)
        except Exception:               # pragma: no cover - direct invocation
            from test_inventory_campfire_runner import (
                _PDI, _WinCap, _frame_mit_offener_seite)
        self.dr, self.sc = dr, sc
        self._PDI, self._WinCap = _PDI, _WinCap
        self._frame = _frame_mit_offener_seite
        self._orig = (dr.pydirectinput, dr.WindowCapture, dr.time.sleep,
                      discard.run_discard, sc.scan_inventory)
        dr.time.sleep = lambda *_a, **_k: None

    def tearDown(self):
        (self.dr.pydirectinput, self.dr.WindowCapture, self.dr.time.sleep,
         discard.run_discard, self.sc.scan_inventory) = self._orig

    def _starte(self, cfg, wincap_cls=None):
        self.dr.pydirectinput = self.pdi = self._PDI()
        self.dr.WindowCapture = wincap_cls or self._WinCap
        got = {}

        def fake_run(states, **kw):
            got.update(kw)
            return discard.DiscardResult('done')

        discard.run_discard = fake_run
        self.dr.run_discard_items(cfg, MARKIERT, db=object())
        return got

    def test_zug_bekommt_pruefung_und_freigegebene_seiten(self):
        got = self._starte({'inventory': {'hotkey': 'i', 'pages': [2, 4]}})
        self.assertEqual(tuple(got['expected_pages']), ('II', 'IV'))
        self.assertTrue(callable(got['verify_page_fn']))

    def test_scan_prueft_den_offenen_reiter(self):
        got = self._starte({'inventory': {'hotkey': 'i', 'pages': [1, 3]}})
        mitschnitt = {}

        def fake_scan(**kw):
            mitschnitt.update(kw)
            return types.SimpleNamespace(pages={})

        self.sc.scan_inventory = fake_scan
        got['scan_fn']()
        self.assertEqual(tuple(mitschnitt['pages']), ('I', 'III'))
        verify = mitschnitt['verify_page_fn']
        self.assertEqual(verify(self._frame('III')), 'III')

    def test_nachsehen_parkt_den_zeiger_vorher_und_liest_den_reiter(self):
        frame = self._frame

        class _WinCapSeiteIV(self._WinCap):
            def get_screenshot(self):
                return frame('IV')

        got = self._starte({'inventory': {'hotkey': 'i'}}, _WinCapSeiteIV)
        self.pdi.ev[:] = []
        self.assertEqual(got['verify_page_fn'](), 'IV')
        from inventory import hover
        park = hover.to_screen(
            [hover.tab_park_point(DEFAULT_CALIBRATION)], (1000, 500))[0]
        self.assertEqual(self.pdi.ev, [('mv',) + tuple(park)])


if __name__ == '__main__':
    unittest.main()
