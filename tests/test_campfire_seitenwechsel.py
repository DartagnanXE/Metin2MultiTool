# -*- coding: utf-8 -*-
"""Grillen ueber mehrere Inventar-Seiten: jeder Reiter-Wechsel wird belegt.

Nutzer-Meldung 2026-10-30: "Seite I klappt fast immer, II-IV fast nie" -- er
angelt mit nur Seite I freigegeben und hakt zum Grillen alle vier an.

Das Spiel kann Reiter-Klicks verschlucken (belegt seit v1.1.2: "Scan blieb auf
Seite I"). Der Haupt-Scan prueft deshalb jeden Wechsel nach; das Grillen tat
das nicht. Blieb ein Klick aus, stand die alte Seite noch offen, und der Zug
griff dort an derselben Stelle zu. Seite I merkt davon nichts, weil sie beim
Angeln ohnehin offen ist.

Die Tests fahren den echten Ablauf (:func:`inventory_campfire.run_campfire`)
gegen ein kleines Spielmodell: vier Seiten, eine sichtbare Seite, ein Feuer.
Das Modell kann einen Reiter-Klick verschlucken oder einen Reiter ganz tot
stellen. Gemessen wird am MODELL, was wirklich passiert ist: welche Fische
weg sind und ob etwas von der falschen Seite im Feuer landete. Die
Erfolgsmeldung des Bots allein beweist nichts.
"""

import types
import unittest

import inventory_campfire as campfire
from inventory.constants import DEFAULT_CALIBRATION
from inventory.grid import lattice_from_calibration

OFFSET = (10, 20)
LAT = lattice_from_calibration(DEFAULT_CALIBRATION)
LABEL_TL = (300, 400)
FEUER = (OFFSET[0] + LABEL_TL[0] + 20, OFFSET[1] + LABEL_TL[1] + 21)
FISCHE = frozenset({'Carp', 'Zander', 'Salmon'})
SEITEN = ('I', 'II', 'III', 'IV')


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
    """Spielmodell mit der Eingabe-API von pydirectinput.

    :param verschluckt_nach_ablegen: ein Reiter-Klick DIREKT nach dem Ablegen
        eines Items im Feuer schaltet nicht um; der Klick danach wirkt wieder.
    :param tote_reiter: Reiter, die nie umschalten.
    :param schluck_fn: optional ``(seite) -> bool``; ``True`` verschluckt
        genau diesen Reiter-Klick (fuer gezielte Einzelfaelle).
    :param uhr: optional ``() -> Sekunden``. Dann brennt das Feuer nur
        ``FIRE_LIFETIME_S`` lang; ein spaeter losgelassener Fisch faellt ins
        Leere (``ins_leere``) statt aufs Feuer.
    """

    def __init__(self, seiten, verschluckt_nach_ablegen=False,
                 tote_reiter=(), schluck_fn=None, uhr=None):
        self.seiten = {p: dict(seiten.get(p, {})) for p in SEITEN}
        self.sichtbar = 'I'
        self.maus = (0, 0)
        self.gehalten = None
        self.zuletzt_abgelegt = False
        self.verschluckt_nach_ablegen = verschluckt_nach_ablegen
        self.tote_reiter = set(tote_reiter)
        self.schluck_fn = schluck_fn
        self.uhr = uhr
        self.feuer_ab = None
        self.gegrillt = []
        self.falsch_ins_feuer = []
        self.ins_leere = []
        self.doppelklicks = []
        self.PAUSE = 0.05

    # -- Eingabe ----------------------------------------------------------
    def moveTo(self, x, y):
        self.maus = (int(x), int(y))

    def click(self, x=None, y=None, **_):
        self.moveTo(x, y)
        seite = _reiter_unter(x, y)
        verschluckt = self.zuletzt_abgelegt and self.verschluckt_nach_ablegen
        self.zuletzt_abgelegt = False
        if seite is None or verschluckt or seite in self.tote_reiter:
            return
        if self.schluck_fn is not None and self.schluck_fn(seite):
            return
        self.sichtbar = seite

    def doubleClick(self, x=None, y=None, **_):
        self.moveTo(x, y)
        rc = _slot_unter(x, y)
        item = self.seiten[self.sichtbar].get(rc) if rc else None
        self.doppelklicks.append((self.sichtbar, rc, item))
        self.zuletzt_abgelegt = False
        if self.uhr is not None:
            self.feuer_ab = self.uhr()

    def mouseDown(self, button=None, **_):
        if button == 'right':
            return
        rc = _slot_unter(*self.maus)
        if rc is not None:
            self.gehalten = (self.sichtbar, rc,
                             self.seiten[self.sichtbar].get(rc))

    def mouseUp(self, button=None, **_):
        if button == 'right' or self.gehalten is None:
            return
        seite, rc, item = self.gehalten
        self.gehalten = None
        if (abs(self.maus[0] - FEUER[0]) > 3
                or abs(self.maus[1] - FEUER[1]) > 3):
            return
        if (self.uhr is not None and self.feuer_ab is not None
                and self.uhr() - self.feuer_ab > campfire.FIRE_LIFETIME_S):
            self.ins_leere.append((seite, rc[0], rc[1], item))
            return
        self.zuletzt_abgelegt = True
        if item in FISCHE:
            del self.seiten[seite][rc]
            self.gegrillt.append((seite, rc[0], rc[1], item))
        elif item is not None:
            self.falsch_ins_feuer.append((seite, rc[0], rc[1], item))

    def keyDown(self, _key):
        pass

    def keyUp(self, _key):
        pass

    # -- Sicht des Bots ----------------------------------------------------
    def sichtbare_seite(self):
        return self.sichtbar

    def scan(self):
        """Perfekter Scan aller Seiten -- isoliert den Grill-Zug."""
        return types.SimpleNamespace(pages={
            p: [types.SimpleNamespace(state='item', name=n, row=r, col=c)
                for (r, c), n in sorted(self.seiten[p].items())]
            for p in SEITEN})

    def rest(self):
        return {p: sorted(n for n in s.values() if n in FISCHE)
                for p, s in self.seiten.items()}


def _beutel(werkzeug_seite='I'):
    """Seite I mit Werkzeug, Koeder und Box AN DENSELBEN STELLEN, an denen auf
    den anderen Seiten Fische liegen -- genau dort greift ein Zug, der auf der
    falschen Seite landet."""
    beutel = {
        'I': {(0, 1): 'Worm', (0, 2): 'Carp', (1, 0): 'Fischpuzzlebox',
              (1, 1): 'Zander'},
        'II': {(0, 0): 'Carp', (0, 1): 'Salmon', (0, 2): 'Zander',
               (1, 0): 'Carp', (1, 1): 'Salmon'},
        'III': {(0, 0): 'Zander', (0, 1): 'Carp', (2, 2): 'Salmon'},
        'IV': {(0, 0): 'Salmon'},
    }
    beutel[werkzeug_seite][(0, 0)] = 'Lagerfeuer'
    return beutel


def _grille(spiel, pruefen=True, expected_pages=SEITEN, verify=None,
            abort_fn=None):
    orig = campfire.find_label
    campfire.find_label = lambda *a, **k: (True, 0.99, LABEL_TL)
    try:
        return campfire.run_campfire(
            {'Carp': 2, 'Zander': 2, 'Salmon': 2},
            inp=spiel, capture_rgb_fn=lambda: 'frame', scan_fn=spiel.scan,
            offset=OFFSET, sleep=lambda *_a, **_k: None,
            verify_page_fn=(verify or spiel.sichtbare_seite) if pruefen
            else None,
            expected_pages=expected_pages if pruefen else None,
            abort_fn=abort_fn)
    finally:
        campfire.find_label = orig


class _LogMitschnitt(object):
    """Faengt Schluessel (``keys``) und Werte (``eintraege``) von
    ``campfire._flog`` mit."""

    def __enter__(self):
        self.keys = []
        self.eintraege = []
        self._orig = campfire._flog

        def _mit(_state, key, **fmt):
            self.keys.append(key)
            self.eintraege.append((key, dict(fmt)))

        campfire._flog = _mit
        return self

    def __exit__(self, *_exc):
        campfire._flog = self._orig
        return False


class TestVerschluckterReiterKlick(unittest.TestCase):

    def test_ohne_pruefung_landen_items_der_falschen_seite_im_feuer(self):
        """Gegenprobe: Das Modell loest den gemeldeten Fehler wirklich aus.

        Ohne Pruefung klickt der Grill blind wie bis v1.6.15. Dann zieht er fuer
        Seite II von Seite I -- Lagerfeuer, Wurm und Puzzlebox landen im Feuer.
        Ohne diesen Test koennte der naechste gruen sein, weil das Modell gar
        nichts verschluckt.
        """
        spiel = _Spiel(_beutel(), verschluckt_nach_ablegen=True)
        _grille(spiel, pruefen=False)
        falsch = {item for (_p, _r, _c, item) in spiel.falsch_ins_feuer}
        self.assertTrue({'Lagerfeuer', 'Worm', 'Fischpuzzlebox'} <= falsch)

    def test_alle_seiten_werden_gegrillt_und_nichts_falsches(self):
        spiel = _Spiel(_beutel(), verschluckt_nach_ablegen=True)
        res = _grille(spiel)

        self.assertEqual(spiel.falsch_ins_feuer, [])
        self.assertEqual(spiel.rest(), {p: [] for p in SEITEN})
        self.assertEqual(res.status, 'complete')
        self.assertEqual(res.cycles, 1)            # ein Feuer reicht
        # Was der Bot meldet, ist genau das, was im Spiel verschwand.
        self.assertEqual(sorted(res.grilled), sorted(spiel.gegrillt))

    def test_das_feuer_wird_nur_auf_der_werkzeugseite_gelegt(self):
        # Werkzeug auf Seite II, Start auf Seite IV: der erste Klick wird
        # verschluckt -- ein blinder Doppelklick traefe Seite IV.
        spiel = _Spiel(_beutel(werkzeug_seite='II'),
                       verschluckt_nach_ablegen=True)
        spiel.sichtbar = 'IV'
        spiel.zuletzt_abgelegt = True
        _grille(spiel)
        self.assertTrue(spiel.doppelklicks)
        for seite, _rc, item in spiel.doppelklicks:
            self.assertEqual((seite, item), ('II', 'Lagerfeuer'))


class TestReiterDerNieAufgeht(unittest.TestCase):

    def test_seite_wird_uebersprungen_und_ehrlich_gemeldet(self):
        spiel = _Spiel(_beutel(), tote_reiter={'III'})
        with _LogMitschnitt() as log:
            res = _grille(spiel)

        # Seite III bleibt unberuehrt, alles andere ist gegrillt.
        self.assertEqual(spiel.rest()['III'], ['Carp', 'Salmon', 'Zander'])
        for seite in ('I', 'II', 'IV'):
            self.assertEqual(spiel.rest()[seite], [], seite)
        self.assertEqual(spiel.falsch_ins_feuer, [])
        self.assertNotIn('III', {g[0] for g in res.grilled})
        # Kein "fertig": das zweite Feuer aenderte nichts -> Stillstand.
        self.assertEqual(res.status, 'stalled')
        self.assertEqual(res.remaining, 3)
        self.assertIn('campfire.page_switch_failed', log.keys)

    def test_werkzeugseite_tot_heisst_kein_feuer_und_kein_doppelklick(self):
        spiel = _Spiel(_beutel(werkzeug_seite='II'), tote_reiter={'II'})
        with _LogMitschnitt() as log:
            res = _grille(spiel)
        self.assertEqual(res.status, 'page_switch_failed')
        self.assertEqual(spiel.doppelklicks, [])
        self.assertEqual(spiel.gegrillt, [])
        self.assertIn('campfire.tool_page_failed', log.keys)

    def test_not_aus_im_zweiten_versuch_ist_abbruch_kein_seitenfehler(self):
        spiel = _Spiel(_beutel(werkzeug_seite='II'), tote_reiter={'II'})
        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, LABEL_TL)
        stopp = {'an': False}

        def _sichtbar():
            stopp['an'] = True          # F6 genau waehrend des Nachsehens
            return spiel.sichtbar

        try:
            res = campfire.run_campfire(
                {'Carp': 2}, inp=spiel, capture_rgb_fn=lambda: 'frame',
                scan_fn=spiel.scan, offset=OFFSET,
                sleep=lambda *_a, **_k: None, verify_page_fn=_sichtbar,
                abort_fn=lambda: stopp['an'])
        finally:
            campfire.find_label = orig
        self.assertEqual(res.status, 'aborted')
        self.assertEqual(spiel.doppelklicks, [])

    def test_logzeile_nennt_die_seite_die_stattdessen_offen_war(self):
        """Die Console muss zeigen, WAS statt der gewuenschten Seite offen war
        -- nur so laesst sich ein verschluckter Klick von einem fehlenden Bild
        unterscheiden (Review 2026-10-30, G28)."""
        spiel = _Spiel(_beutel(), tote_reiter={'III'})
        with _LogMitschnitt() as log:
            _grille(spiel)
        fehl = [fmt for key, fmt in log.eintraege
                if key == 'campfire.page_switch_failed']
        self.assertTrue(fehl)
        self.assertEqual(fehl[0], {'page': 'III', 'got': 'II'})

    def test_logzeile_der_werkzeugseite_nennt_die_offene_seite(self):
        spiel = _Spiel(_beutel(werkzeug_seite='II'), tote_reiter={'II'})
        with _LogMitschnitt() as log:
            _grille(spiel)
        fehl = [fmt for key, fmt in log.eintraege
                if key == 'campfire.tool_page_failed']
        self.assertEqual(fehl, [{'page': 'II', 'got': 'I'}])


class TestOhnePruefungWieBisher(unittest.TestCase):

    def test_ein_reiterklick_je_fisch_plus_werkzeug(self):
        """Ohne ``verify_page_fn`` bleibt der Klickstrom exakt der alte."""
        spiel = _Spiel(_beutel())
        klicks = []
        orig_click = spiel.click

        def _click(x=None, y=None, **kw):
            klicks.append(_reiter_unter(x, y))
            orig_click(x=x, y=y, **kw)

        spiel.click = _click
        res = _grille(spiel, pruefen=False)
        fische = len(res.grilled)
        self.assertEqual(fische, 11)
        # 1 Werkzeug-Reiter + 1 Reiter je Fisch, sonst nichts.
        self.assertEqual(len(klicks), fische + 1)
        self.assertEqual(klicks[0], 'I')


class TestEhrlichesEnde(unittest.TestCase):

    @staticmethod
    def _inv(pages):
        return types.SimpleNamespace(pages={
            p: [types.SimpleNamespace(state='item', name=n, row=r, col=c)
                for (n, r, c) in slots]
            for p, slots in pages.items()})

    def _run(self, *scans, expected=None):
        folge = list(scans)
        zaehler = {'i': 0}

        def _scan():
            got = folge[min(zaehler['i'], len(folge) - 1)]
            zaehler['i'] += 1
            return got

        orig = campfire.find_label
        campfire.find_label = lambda *a, **k: (True, 0.99, LABEL_TL)
        try:
            return campfire.run_campfire(
                {'Carp': 2}, inp=_Spiel({}), capture_rgb_fn=lambda: 'frame',
                scan_fn=_scan, offset=OFFSET, sleep=lambda *_a, **_k: None,
                expected_pages=expected)
        finally:
            campfire.find_label = orig

    def test_seite_fehlt_schon_im_ersten_scan_ist_nicht_fertig(self):
        voll = self._inv({'I': [('Lagerfeuer', 0, 0), ('Carp', 1, 0)]})
        leer = self._inv({'I': [('Lagerfeuer', 0, 0)]})
        res = self._run(voll, leer, expected=('I', 'II'))
        self.assertEqual(res.status, 'scan_incomplete')
        self.assertEqual(len(res.grilled), 1)

    def test_ohne_fisch_aber_mit_fehlender_seite_ist_nicht_no_fish(self):
        nur_werkzeug = self._inv({'I': [('Lagerfeuer', 0, 0)]})
        res = self._run(nur_werkzeug, expected=('I', 'II'))
        self.assertEqual(res.status, 'scan_incomplete')
        self.assertEqual(res.cycles, 0)

    def test_ohne_erwartete_seiten_zaehlt_der_erste_scan_wie_bisher(self):
        voll = self._inv({'I': [('Lagerfeuer', 0, 0), ('Carp', 1, 0)]})
        leer = self._inv({'I': [('Lagerfeuer', 0, 0)]})
        self.assertEqual(self._run(voll, leer).status, 'complete')
        nur_werkzeug = self._inv({'I': [('Lagerfeuer', 0, 0)]})
        self.assertEqual(self._run(nur_werkzeug).status, 'no_fish')

    def test_wieder_aufgetauchte_seite_ist_kein_stillstand(self):
        """Fehlt Seite II in EINEM Nachscan, darf ihr Wiederauftauchen keinen
        Stillstand vortaeuschen. Der alte Summenvergleich haette hier nach
        zwei Feuern gestoppt (1 Fisch >= 1 Fisch), obwohl jedes Feuer wirkte.
        """
        s1 = self._inv({'I': [('Lagerfeuer', 0, 0), ('Carp', 1, 0),
                              ('Carp', 1, 1)],
                        'II': [('Carp', 0, 0)]})
        s2 = self._inv({'I': [('Lagerfeuer', 0, 0), ('Carp', 1, 1)]})
        s3 = self._inv({'I': [('Lagerfeuer', 0, 0)], 'II': [('Carp', 0, 0)]})
        s4 = self._inv({'I': [('Lagerfeuer', 0, 0)], 'II': []})
        res = self._run(s1, s2, s3, s4)
        self.assertEqual(res.status, 'complete')
        self.assertEqual(res.cycles, 3)

    def test_fehlt_die_lagerfeuer_seite_ist_es_unvollstaendig(self):
        """Kann das Lagerfeuer auf der ungelesenen Seite liegen, ist "kein
        Lagerfeuer im Inventar" unbelegt -- und hiesse fuer den Nutzer:
        nachkaufen (Review 2026-10-30, G2)."""
        nur_fisch = self._inv({'I': [('Carp', 1, 0)]})
        res = self._run(nur_fisch, expected=('I', 'II'))
        self.assertEqual(res.status, 'scan_incomplete')

    def test_vollstaendiger_scan_ohne_lagerfeuer_bleibt_kein_lagerfeuer(self):
        nur_fisch = self._inv({'I': [('Carp', 1, 0)], 'II': []})
        res = self._run(nur_fisch, expected=('I', 'II'))
        self.assertEqual(res.status, 'no_campfire_item')


class TestKeinFortschritt(unittest.TestCase):
    T1 = ('I', 0, 0, 'Carp')
    T2 = ('II', 0, 0, 'Carp')

    def test_gleiche_seiten_wie_der_alte_summenvergleich(self):
        beide = {'I', 'II'}
        self.assertTrue(campfire._kein_fortschritt(
            [self.T1, self.T2], beide, [self.T1, self.T2], beide))
        self.assertFalse(campfire._kein_fortschritt(
            [self.T1], beide, [self.T1, self.T2], beide))

    def test_nur_gemeinsame_seiten_zaehlen(self):
        # Vorher fehlte II; jetzt ist I leer und II zurueck -> Fortschritt.
        self.assertFalse(campfire._kein_fortschritt(
            [self.T2], {'I', 'II'}, [self.T1], {'I'}))

    def test_ohne_gemeinsame_seite_kein_urteil(self):
        self.assertFalse(campfire._kein_fortschritt(
            [self.T2], {'II'}, [self.T1], {'I'}))


class TestNachFehlschlagGiltKeineSeiteAlsOffen(unittest.TestCase):
    """Scheitert ein belegter Wechsel, wurde trotzdem zweimal ein Reiter
    geklickt. Danach darf KEINE Seite mehr als belegt offen gelten -- auch die
    alte nicht (Review 2026-10-30, G1)."""

    def test_alte_seite_wird_nach_fehlschlag_neu_belegt(self):
        # Werkzeug auf III, Fische auf I und III. Der Wechsel nach I KLAPPT,
        # aber beide Blicke liefern kein Bild -> Seite I gilt als gescheitert.
        # Danach verschluckt das Spiel den ersten Klick auf III. Stuende
        # "offen" noch auf III, kaeme dafuer nur der alte Blindklick -- und der
        # Zug griffe auf Seite I in den Wurm.
        beutel = {
            'I': {(0, 1): 'Worm', (0, 2): 'Carp', (2, 2): 'Fischpuzzlebox'},
            'III': {(0, 0): 'Lagerfeuer', (0, 1): 'Carp', (2, 2): 'Salmon'},
        }
        geschluckt = {'n': 0}

        def _schluck(seite):
            if seite == 'III' and spiel.sichtbar == 'I' and not geschluckt['n']:
                geschluckt['n'] += 1
                return True
            return False

        spiel = _Spiel(beutel, schluck_fn=_schluck)
        spiel.sichtbar = 'III'
        blicke = {'n': 0}

        def _blick():
            blicke['n'] += 1
            if spiel.sichtbar == 'I' and blicke['n'] <= 3:
                return None             # kein Bild, genau beim Wechsel nach I
            return spiel.sichtbar

        with _LogMitschnitt() as log:
            res = _grille(spiel, verify=_blick)

        self.assertEqual(spiel.falsch_ins_feuer, [])
        self.assertEqual(spiel.rest(), {p: [] for p in SEITEN})
        self.assertEqual(res.status, 'complete')
        fehl = [fmt for key, fmt in log.eintraege
                if key == 'campfire.page_switch_failed']
        self.assertEqual(fehl, [{'page': 'I', 'got':
                                 campfire._t('inventory.page_no_frame')}])


class TestNotAusNachDemNachsehen(unittest.TestCase):

    def test_f6_waehrend_erfolgreicher_pruefung_legt_kein_feuer(self):
        """Das Nachsehen dauert (Zeiger parken, Bild holen). Kommt F6 genau
        dann, darf trotz richtiger Seite kein Feuer mehr gelegt werden
        (Review 2026-10-30, G7)."""
        spiel = _Spiel(_beutel())
        stopp = {'an': False}

        def _blick():
            stopp['an'] = True          # F6 waehrend des Nachsehens ...
            return spiel.sichtbar       # ... und die Seite stimmt

        res = _grille(spiel, verify=_blick, abort_fn=lambda: stopp['an'])
        self.assertEqual(res.status, 'aborted')
        self.assertEqual(spiel.doppelklicks, [])
        self.assertEqual(spiel.gegrillt, [])


class TestFristGiltBeimLoslassen(unittest.TestCase):

    def test_kein_fisch_landet_nach_ablauf_des_feuers(self):
        """Der belegte Wechsel nach Seite II dauert hier so lange, dass das
        Feuer waehrenddessen ausgeht. Danach darf kein Fisch mehr losgelassen
        werden -- er fiele ins Leere (Review 2026-10-30, G8)."""
        uhr = {'t': 1000.0}
        spiel = _Spiel(_beutel(), uhr=lambda: uhr['t'])
        gesprungen = {'ja': False}

        def _blick():
            if spiel.sichtbar == 'II' and not gesprungen['ja']:
                gesprungen['ja'] = True
                uhr['t'] += campfire.FIRE_LIFETIME_S + 1.0
            return spiel.sichtbar

        orig_time = campfire.time
        campfire.time = types.SimpleNamespace(monotonic=lambda: uhr['t'],
                                              sleep=lambda *_a: None)
        try:
            with _LogMitschnitt() as log:
                res = _grille(spiel, verify=_blick)
        finally:
            campfire.time = orig_time

        self.assertEqual(spiel.ins_leere, [])
        self.assertIn('campfire.fire_expired', log.keys)
        self.assertEqual(spiel.falsch_ins_feuer, [])
        # Das naechste Feuer holt die Fische von Seite II nach.
        self.assertEqual(res.status, 'complete')
        self.assertEqual(spiel.rest(), {p: [] for p in SEITEN})


if __name__ == '__main__':
    unittest.main()
