# -*- coding: utf-8 -*-
"""Der Okey-Ablauf im Spiel: klickt das Richtige -- und im Zweifel gar nichts.

Gegen ein Papp-Spiel, das die Bildschirme des echten Clients nachstellt:
Spielwelt -> Eventuebersicht -> Okey-Vorfenster -> Startdialog -> Brett.

Die wichtigsten Tests sind die NEGATIVEN. Ein Ablauf, der bei jedem Zweifel
trotzdem klickt, wuerde alle Positiv-Tests bestehen und im Spiel Unfug
anrichten -- ein Klick in die offene Welt laeuft irgendwohin.
"""

import os
import tempfile
import unittest
from unittest import mock

from interface import okey_runner as R


class FakeWincap:
    def __init__(self, spiel):
        self.spiel = spiel
        self.offset_x, self.offset_y = 100, 50

    def get_screenshot(self):
        return self.spiel.schirm


class FakeSpiel:
    """Die Bildschirme des Clients als Zustandsautomat."""

    def __init__(self, schirm='welt', haken=True, okey_zeile=True):
        self.schirm = schirm
        self.haken = haken
        self.okey_zeile = okey_zeile
        self.klicks = []           # (x, y) in Bildschirm-Koordinaten
        self.tasten = []
        self.klick_wirkt = True

    # -- was der Runner "sieht" -----------------------------------------
    def sichtbar(self, img, name, thresh=None):
        s = self.schirm
        return {
            'flow_event_title': s == 'uebersicht',
            'flow_okey_label': s == 'uebersicht' and self.okey_zeile,
            'flow_okey_title': s in ('vorfenster', 'startdialog', 'brett',
                                     'enddialog'),
            'flow_start_btn': s in ('vorfenster', 'startdialog'),
            'flow_ja_btn': s in ('startdialog', 'enddialog'),
            'flow_hinweis': s in ('brett', 'enddialog'),
            'flow_beenden': s in ('brett', 'enddialog'),
        }.get(name, False)

    def okey_row(self, img):
        if self.schirm != 'uebersicht':
            return (False, (0, 0), {'grund': 'uebersicht-nicht-offen'})
        if not self.okey_zeile:
            return (False, (0, 0), {'grund': 'okey-zeile-nicht-gefunden'})
        return (True, (477, 193), {'zeile': 1.0})

    def ink(self, img):
        return 0.14 if self.haken else 0.02

    # -- was der Runner "tut" -------------------------------------------
    def klick(self, x, y, **kw):
        self.klicks.append((x, y))
        if not self.klick_wirkt:
            return
        client = (x - 100, y - 50)
        if self.schirm == 'uebersicht' and client == (477, 193):
            self.schirm = 'vorfenster'
        elif self.schirm == 'vorfenster' and client == (526, 461):
            self.haken = not self.haken
        elif self.schirm == 'vorfenster' and client == (306, 460):
            self.schirm = 'startdialog'
        elif self.schirm == 'startdialog' and client == (359, 322):
            self.schirm = 'brett'
        elif self.schirm == 'brett' and client == (400, 465):
            self.schirm = 'enddialog'
        elif self.schirm == 'enddialog' and client == (359, 322):
            self.schirm = 'vorfenster'

    def ctrl_e(self):
        self.tasten.append('ctrl+e')
        self.schirm = 'welt' if self.schirm == 'uebersicht' else 'uebersicht'

    def client_klicks(self):
        return [(x - 100, y - 50) for x, y in self.klicks]


class _Basis(unittest.TestCase):
    def aufsetzen(self, spiel):
        # Das Ergebnis-Protokoll in einen Wegwerf-Ordner umleiten. Ohne das
        # schreibt die Testsuite eine echte okey_results.jsonl in den
        # Projektordner -- beim ersten Lauf genau passiert.
        self.protokoll = os.path.join(tempfile.mkdtemp(), R.RESULTS_FILENAME)
        eingabe = mock.Mock()
        eingabe.PAUSE = 0.1
        eingabe.click.side_effect = spiel.klick
        eingabe.rightClick.side_effect = spiel.klick
        eingabe.moveTo.side_effect = lambda *a, **k: None
        for name in ('keyDown', 'keyUp', 'press'):
            getattr(eingabe, name).side_effect = lambda *a, **k: None

        patches = [
            mock.patch.object(R, '_input', eingabe),
            mock.patch.object(R, '_press_ctrl_e', spiel.ctrl_e),
            mock.patch.object(R.flow, 'sichtbar', spiel.sichtbar),
            mock.patch.object(R.flow, 'find_okey_row', spiel.okey_row),
            mock.patch.object(R.flow, 'brett_laeuft',
                              lambda i: spiel.sichtbar(i, 'flow_hinweis')),
            mock.patch.object(R.flow, 'find_click',
                              lambda i, n, **k: (spiel.sichtbar(i, n),
                                                 (400, 465), 1.0)),
            mock.patch.object(R.vision, 'safe_mode_ink', spiel.ink),
            mock.patch.object(R, '_diagnose', lambda *a, **k: None),
            mock.patch('time.sleep', lambda *_a: None),
            mock.patch.object(R, 'sibling_path', lambda _n: self.protokoll),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return FakeWincap(spiel)


class TestStartAblauf(_Basis):
    def test_kompletter_weg_von_der_welt_bis_zum_brett(self):
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        ok, schritt = R._spiel_starten(cap)
        self.assertTrue(ok, schritt)
        self.assertEqual(spiel.schirm, 'brett')
        self.assertFalse(spiel.haken, 'der Haken blieb gesetzt')
        self.assertEqual(spiel.tasten, ['ctrl+e'])
        # Reihenfolge: Eventzeile, Haken, Start, Ja
        self.assertEqual(spiel.client_klicks(),
                         [(477, 193), (526, 461), (306, 460), (359, 322)])

    def test_offene_uebersicht_wird_nicht_zugeschaltet(self):
        """Strg+E ist ein UMSCHALTER: steht die Uebersicht schon, wuerde ein
        weiterer Druck sie wieder schliessen."""
        spiel = FakeSpiel('uebersicht')
        cap = self.aufsetzen(spiel)
        R._spiel_starten(cap)
        self.assertEqual(spiel.tasten, [], 'Strg+E trotz offener Uebersicht')

    def test_laufendes_brett_wird_uebernommen(self):
        spiel = FakeSpiel('brett')
        cap = self.aufsetzen(spiel)
        ok, _s = R._spiel_starten(cap)
        self.assertTrue(ok)
        self.assertEqual(spiel.klicks, [], 'am laufenden Brett herumgeklickt')

    def test_ohne_okey_zeile_wird_nirgendwo_hingeklickt(self):
        """Der Kern-Negativtest: das Event fehlt in der Liste (es laeuft
        gerade nicht). Dann darf KEIN Klick fallen."""
        spiel = FakeSpiel('welt', okey_zeile=False)
        cap = self.aufsetzen(spiel)
        ok, schritt = R._spiel_starten(cap)
        self.assertFalse(ok)
        self.assertEqual(schritt, 'okeyzeile')
        self.assertEqual(spiel.klicks, [], 'trotz fehlender Zeile geklickt')

    def test_not_aus_greift_im_startablauf(self):
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        ok, _schritt = R._spiel_starten(cap, abort_fn=lambda: True)
        self.assertFalse(ok)
        self.assertEqual(spiel.klicks, [])


class TestSichererModus(_Basis):
    def test_gesetzter_haken_wird_entfernt(self):
        spiel = FakeSpiel('vorfenster', haken=True)
        cap = self.aufsetzen(spiel)
        ok, notiz = R._haken_entfernen(cap)
        self.assertTrue(ok, notiz)
        self.assertFalse(spiel.haken)
        self.assertEqual(len(spiel.klicks), 1)

    def test_bereits_leeres_kaestchen_bleibt_am_ende_leer(self):
        """Ohne Vorher/Nachher-Vergleich wuerde der eine Klick den Haken
        SETZEN -- genau das Gegenteil des Gewollten."""
        spiel = FakeSpiel('vorfenster', haken=False)
        cap = self.aufsetzen(spiel)
        ok, notiz = R._haken_entfernen(cap)
        self.assertTrue(ok, notiz)
        self.assertFalse(spiel.haken, 'der Haken wurde gesetzt statt entfernt')
        self.assertEqual(len(spiel.klicks), 2, 'nicht zurueckgenommen')

    def test_wirkungsloser_klick_faellt_auf(self):
        spiel = FakeSpiel('vorfenster', haken=True)
        spiel.klick_wirkt = False
        cap = self.aufsetzen(spiel)
        ok, notiz = R._haken_entfernen(cap)
        self.assertFalse(ok)
        self.assertEqual(notiz, 'unveraendert')

    def test_ohne_haken_kein_start(self):
        """Lieber gar nicht spielen als mit gesetztem Sicherem Modus."""
        spiel = FakeSpiel('vorfenster', haken=True)
        spiel.klick_wirkt = False
        cap = self.aufsetzen(spiel)
        ok, schritt = R._spiel_starten(cap)
        self.assertFalse(ok)
        self.assertEqual(schritt, 'sicherermodus')
        self.assertNotIn((306, 460), spiel.client_klicks(),
                         'Start trotz gesetztem Haken geklickt')

    def test_nicht_messbar_bricht_ab(self):
        spiel = FakeSpiel('vorfenster')
        cap = self.aufsetzen(spiel)
        with mock.patch.object(R.vision, 'safe_mode_ink', return_value=-1.0):
            ok, notiz = R._haken_entfernen(cap)
        self.assertFalse(ok)
        self.assertEqual(notiz, 'nicht-messbar')
        self.assertEqual(spiel.klicks, [])


class TestBeenden(_Basis):
    def test_beenden_und_ja(self):
        spiel = FakeSpiel('brett')
        cap = self.aufsetzen(spiel)
        self.assertTrue(R._spiel_beenden(cap))
        self.assertEqual(spiel.client_klicks(), [(400, 465), (359, 322)])

    def test_stehender_dialog_wird_nur_bestaetigt(self):
        spiel = FakeSpiel('enddialog')
        cap = self.aufsetzen(spiel)
        self.assertTrue(R._spiel_beenden(cap))
        self.assertEqual(spiel.client_klicks(), [(359, 322)],
                         'gegen das offene Dialogfenster geklickt')

    def test_ohne_beenden_knopf_kein_klick(self):
        spiel = FakeSpiel('vorfenster')
        cap = self.aufsetzen(spiel)
        self.assertFalse(R._spiel_beenden(cap))
        self.assertEqual(spiel.klicks, [])


class TestSession(_Basis):
    def _session(self, spiel, decks=2, bericht_status='fertig', punkte=330,
                 abort_fn=None):
        cap = self.aufsetzen(spiel)
        from okey.partie import Bericht
        bericht = Bericht(status=bericht_status, punkte=punkte, kombis=3,
                          zuege=9, weggeworfen=1, schritt='',
                          bildschirm_punkte=punkte)
        self.fenstername = []

        # STRENGE Nachbildung: genau EIN Argument, so wie der echte
        # WindowCapture(window_name). Eine nachsichtige Attrappe
        # (lambda *a, **k) verdeckte, dass der Runner ohne Argument aufrief --
        # im Spiel waere jede Sitzung sofort mit TypeError gestorben.
        def fenster(name):
            self.fenstername.append(name)
            return cap

        with mock.patch.object(R, 'WindowCapture', fenster), \
             mock.patch.object(R.partie, 'spielen', return_value=bericht):
            return R.run_okey_session(decks=decks, staerke='sofort',
                                      abort_fn=abort_fn)

    def test_uebergibt_den_fensternamen(self):
        import constants
        self._session(FakeSpiel('welt'), decks=1)
        self.assertEqual(self.fenstername, [constants.GAME_NAME])

    def test_spielt_die_gewuenschte_zahl_an_sets(self):
        ses = self._session(FakeSpiel('welt'), decks=3)
        self.assertEqual(ses.gespielt, 3)
        zeilen = open(self.protokoll, encoding='utf-8').read().strip()
        self.assertEqual(len(zeilen.split('\n')), 3,
                         'nicht jedes Set wurde protokolliert')
        self.assertEqual(ses.punkte_gesamt, 990)
        self.assertEqual(ses.truhen['silber'], 3)
        self.assertEqual(ses.grund, 'fertig')

    def test_truhen_werden_nach_punkten_einsortiert(self):
        self.assertEqual(self._session(FakeSpiel('welt'), 1, punkte=420)
                         .truhen['gold'], 1)
        self.assertEqual(self._session(FakeSpiel('welt'), 1, punkte=120)
                         .truhen['bronze'], 1)

    def test_not_aus_beendet_die_sitzung_sofort(self):
        ses = self._session(FakeSpiel('welt'), decks=5,
                            abort_fn=lambda: True)
        self.assertEqual(ses.gespielt, 0)
        self.assertEqual(ses.grund, 'abbruch')

    def test_fehler_in_der_partie_stoppt_die_reihe(self):
        """Nach einem unklaren Bild wird NICHT das naechste Set angefangen --
        sonst wiederholt sich derselbe Fehler stumm."""
        ses = self._session(FakeSpiel('welt'), decks=5,
                            bericht_status='unlesbar')
        self.assertEqual(ses.gespielt, 1)
        self.assertEqual(ses.grund, 'fehler')
        self.assertEqual(ses.fehler_schritt, 'unlesbar')

    def test_gescheitertes_beenden_stoppt_statt_phantom_sets(self):
        """Bleibt die Runde offen, sieht der naechste Durchlauf ein laufendes
        Brett, uebernimmt es mit leerer Buchfuehrung und meldete ein zweites,
        leeres Set. Der Nutzer bekaeme Phantom-Sets statt einer Meldung."""
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        from okey.partie import Bericht
        bericht = Bericht(status='fertig', punkte=330, kombis=3, zuege=9,
                          weggeworfen=1, schritt='', bildschirm_punkte=330)
        with mock.patch.object(R, 'WindowCapture', lambda name: cap), \
             mock.patch.object(R.partie, 'spielen', return_value=bericht), \
             mock.patch.object(R, '_spiel_beenden', return_value=False):
            ses = R.run_okey_session(decks=5, staerke='sofort')
        self.assertEqual(ses.gespielt, 1, 'Phantom-Sets gezaehlt')
        self.assertEqual(ses.grund, 'fehler')
        self.assertEqual(ses.fehler_schritt, 'beenden')

    def test_truhe_zaehlt_genau_dann_wenn_ausgezahlt_wurde(self):
        """Massgeblich ist NICHT, ob die Partie sauber lief, sondern ob
        "Beenden/Ja" durchging -- nur dann gibt es die Truhe. Eine wegen eines
        unklaren Bildes abgebrochene Partie, die sich noch beenden laesst, hat
        ihre Punkte wirklich bekommen; sie zu verschweigen waere falsch.
        """
        ses = self._session(FakeSpiel('welt'), decks=1,
                            bericht_status='unlesbar', punkte=420)
        self.assertEqual(ses.truhen['gold'], 1, 'ausgezahlte Truhe verschwiegen')
        self.assertEqual(ses.spiele[0].truhe, 'gold')

    def test_ohne_beenden_keine_truhe(self):
        """Gegenprobe: geht "Beenden" nicht durch, wurde nichts ausgezahlt --
        dann darf auch nichts in der Statistik stehen."""
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        from okey.partie import Bericht
        bericht = Bericht(status='fertig', punkte=420, kombis=3, zuege=9,
                          weggeworfen=1, schritt='', bildschirm_punkte=420)
        with mock.patch.object(R, 'WindowCapture', lambda name: cap), \
             mock.patch.object(R.partie, 'spielen', return_value=bericht), \
             mock.patch.object(R, '_spiel_beenden', return_value=False):
            ses = R.run_okey_session(decks=1, staerke='sofort')
        self.assertEqual(sum(ses.truhen.values()), 0)
        self.assertEqual(ses.spiele[0].truhe, '')

    def test_not_aus_beendet_die_runde_nicht_mehr(self):
        """Nach einem Stop wird nicht weitergeklickt -- der Nutzer sitzt davor
        und will, dass sofort Ruhe ist."""
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        from okey.partie import Bericht
        bericht = Bericht(status='abbruch', punkte=90, kombis=1, zuege=3,
                          weggeworfen=0, schritt='im-zug', bildschirm_punkte=90)
        gerufen = []
        with mock.patch.object(R, 'WindowCapture', lambda name: cap), \
             mock.patch.object(R.partie, 'spielen', return_value=bericht), \
             mock.patch.object(R, '_spiel_beenden',
                               side_effect=lambda *a, **k: gerufen.append(1)):
            ses = R.run_okey_session(decks=1, staerke='sofort')
        self.assertEqual(gerufen, [], 'nach dem Not-Aus weitergeklickt')
        self.assertEqual(ses.grund, 'abbruch')

    def test_abgeraeumtes_brett_zaehlt_nicht_als_gespieltes_set(self):
        """Ein uebernommenes, leeres Brett liefert null Zuege. Frueher waere
        das als volles Set mit 0 Punkten und Bronze-Truhe in Statistik UND
        Protokoll gewandert -- ein Phantom-Set."""
        spiel = FakeSpiel('welt')
        cap = self.aufsetzen(spiel)
        from okey.partie import Bericht
        leer = Bericht(status='fertig', punkte=0, kombis=0, zuege=0,
                       weggeworfen=0, schritt='', bildschirm_punkte=0)
        with mock.patch.object(R, 'WindowCapture', lambda name: cap), \
             mock.patch.object(R.partie, 'spielen', return_value=leer):
            ses = R.run_okey_session(decks=3, staerke='sofort')
        self.assertEqual(ses.gespielt, 0, 'Phantom-Set gezaehlt')
        self.assertEqual(sum(ses.truhen.values()), 0)
        self.assertEqual(ses.fehler_schritt, 'leeres-brett')
        self.assertFalse(os.path.exists(self.protokoll),
                         'Phantom-Set ins Protokoll geschrieben')

    def test_ohne_live_abhaengigkeiten_kein_absturz(self):
        with mock.patch.object(R, 'WindowCapture', None):
            ses = R.run_okey_session(decks=1)
        self.assertEqual(ses.grund, 'deps')
        self.assertEqual(ses.gespielt, 0)


class TestProtokoll(unittest.TestCase):
    """Die Statistik ueberlebt den Programmneustart -- aber sie darf nie eine
    Partie kippen."""

    def test_schreibt_eine_zeile_je_set(self):
        import json
        import tempfile
        spiel = R.OkeySpiel(punkte=330, kombis=4, zuege=11, weggeworfen=1,
                            truhe='silber', status='fertig', dauer_s=12.5)
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, R.RESULTS_FILENAME)
            with mock.patch.object(R, 'sibling_path', lambda _n: pfad):
                R._protokollieren(spiel, 'beste')
                R._protokollieren(spiel, 'beste')
            zeilen = open(pfad, encoding='utf-8').read().strip().split('\n')
        self.assertEqual(len(zeilen), 2)
        eintrag = json.loads(zeilen[0])
        self.assertEqual(eintrag['punkte'], 330)
        self.assertEqual(eintrag['truhe'], 'silber')
        self.assertEqual(eintrag['stufe'], 'beste')

    def test_ein_schreibfehler_kippt_nichts(self):
        spiel = R.OkeySpiel(punkte=1, truhe='bronze', status='fertig')
        with mock.patch.object(R, 'sibling_path',
                               side_effect=OSError('kein Platz')):
            R._protokollieren(spiel, 'beste')      # darf nicht werfen


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
