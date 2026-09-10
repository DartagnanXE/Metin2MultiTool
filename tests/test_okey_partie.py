# -*- coding: utf-8 -*-
"""Der Okey-Partie-Ablauf gegen einen ECHTEN Spielsimulator.

Kein Papp-Brett mit vorgegebenen Antworten: der Simulator hier setzt die
Spielregeln um, die der Nutzer beschrieben hat (2026-09-10) --

    "eine Karte mit Linksklick wird von den 5 ausgewählt, mit Rechtsklick wird
     eine Karte entfernt; ausgewählte Karten erscheinen unten in der Dreier
     Reihe und bei 3 wird sofort abgerechnet; wenn man falsche 3er wählt,
     kommen die wieder nach oben; mit dem Stapel zieht man die leeren Karten
     oben nach."

-- und laesst den Ablauf dagegen laufen. Damit pruefen die Tests nicht, ob der
Code das tut, was der Code tut, sondern ob am Ende eine plausible Partie
herauskommt: alle 24 Karten verbraucht, nur gueltige Kombinationen gelegt,
die Punkte stimmen mit der Regel ueberein.
"""

import random
import unittest
from unittest import mock

from okey import partie
from okey.engine import COLORS, VALUES, combo_points


class Simulator(partie.Brett):
    """Ein spielbares Okey -- so genau, wie es die Beschreibung hergibt."""

    def __init__(self, mischung=None, abbruch_nach=None, brett=True):
        alle = [(v, c) for v in VALUES for c in COLORS]
        if mischung is None:
            random.Random(7).shuffle(alle)
            mischung = alle
        self.stapel = list(mischung)
        self.feld = ['leer'] * 5
        self.auswahl = []
        self.punkte = 0
        self.verbraucht = []
        self.brett_da = brett
        self.klicks = 0
        self.abbruch_nach = abbruch_nach
        self.spur = []
        self._nachziehen()

    # -- Spielmechanik ----------------------------------------------------
    def _nachziehen(self):
        for i in range(5):
            if self.feld[i] == 'leer' and self.stapel:
                self.feld[i] = self.stapel.pop(0)

    def _abrechnen(self):
        karten = list(self.auswahl)
        self.auswahl = []
        punkte = combo_points(karten)
        if punkte > 0:
            self.punkte += punkte
            self.verbraucht.extend(karten)
            self.spur.append(('kombi', punkte))
        else:
            # Ungueltig -> die drei wandern zurueck auf freie Plaetze.
            for karte in karten:
                for i in range(5):
                    if self.feld[i] == 'leer':
                        self.feld[i] = karte
                        break
            self.spur.append(('abgelehnt', 0))

    # -- Schnittstelle zum Ablauf -----------------------------------------
    def bild(self):
        return self          # der Ablauf reicht das Bild nur weiter

    def klick_karte(self, index, rechts=False):
        self.klicks += 1
        karte = self.feld[index]
        if karte == 'leer':
            return
        self.feld[index] = 'leer'
        if rechts:
            self.verbraucht.append(karte)
            self.spur.append(('weg', karte))
            self._nachziehen()
            return
        self.auswahl.append(karte)
        if len(self.auswahl) == 3:
            self._abrechnen()

    def klick_stapel(self):
        self.klicks += 1
        self._nachziehen()

    def schlafen(self, sekunden):
        pass

    def abbruch(self):
        return (self.abbruch_nach is not None
                and self.klicks >= self.abbruch_nach)

    def melde(self, was, **werte):
        pass


def _spielen(sim, staerke='sofort'):
    """Den Ablauf gegen den Simulator laufen lassen."""
    with mock.patch.object(partie.flow, 'brett_laeuft',
                           side_effect=lambda i: i.brett_da), \
         mock.patch.object(partie.vision, 'read_field',
                           side_effect=lambda i: list(i.feld)), \
         mock.patch.object(partie.vision, 'read_points',
                           side_effect=lambda i: i.punkte):
        return partie.spielen(sim, staerke=staerke)


class TestVollePartie(unittest.TestCase):
    def test_spielt_bis_nichts_mehr_geht(self):
        sim = Simulator()
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'fertig')
        self.assertGreater(bericht.punkte, 0, 'keine einzige Kombination')
        self.assertEqual(bericht.punkte, sim.punkte,
                         'Buchfuehrung weicht vom Spiel ab')

    def test_keine_karte_geht_verloren_oder_doppelt(self):
        """Die Identitaet, auf der die Kartenzaehlung ruht: jede der 24 Karten
        ist genau einmal irgendwo."""
        sim = Simulator()
        _spielen(sim)
        alle = list(sim.verbraucht) + [k for k in sim.feld if k != 'leer'] \
            + list(sim.stapel) + list(sim.auswahl)
        self.assertEqual(len(alle), 24, 'Karten verschwunden oder verdoppelt')
        self.assertEqual(len(set(alle)), 24, 'eine Karte doppelt')

    def test_nur_gueltige_kombinationen(self):
        """Gegenprobe zur Nutzer-Beschreibung: eine falsche Dreiergruppe
        wandert zurueck nach oben. Das darf nie passieren."""
        for seed in range(6):
            alle = [(v, c) for v in VALUES for c in COLORS]
            random.Random(seed).shuffle(alle)
            sim = Simulator(mischung=alle)
            _spielen(sim)
            abgelehnt = [e for e in sim.spur if e[0] == 'abgelehnt']
            self.assertEqual(abgelehnt, [],
                             'Seed %d: ungueltige Dreiergruppe gelegt' % seed)

    def test_punkte_entsprechen_der_regel(self):
        sim = Simulator()
        bericht = _spielen(sim)
        soll = sum(p for art, p in sim.spur if art == 'kombi')
        self.assertEqual(bericht.punkte, soll)
        self.assertEqual(bericht.kombis,
                         len([e for e in sim.spur if e[0] == 'kombi']))

    def test_staerkere_stufe_spielt_nicht_schlechter(self):
        """Kein Feinvergleich (dafuer braeuchte es hunderte Partien), sondern
        eine Plausibilitaetsschranke: die beste Stufe darf nicht auffaellig
        unter der Faustregel landen."""
        alle = [(v, c) for v in VALUES for c in COLORS]
        random.Random(3).shuffle(alle)
        schnell = _spielen(Simulator(mischung=list(alle)), 'sofort').punkte
        stark = _spielen(Simulator(mischung=list(alle)), 'schnell').punkte
        self.assertGreaterEqual(stark, schnell - 60)


class TestNachziehen(unittest.TestCase):
    def test_fuellt_leere_plaetze_auf(self):
        sim = Simulator()
        sim.feld[0] = sim.feld[3] = 'leer'
        with mock.patch.object(partie.vision, 'read_field',
                               side_effect=lambda i: list(i.feld)):
            feld = partie._nachziehen(sim, [])
        self.assertNotIn('leer', feld, 'Plaetze blieben leer')

    def test_zieht_nicht_wenn_der_stapel_leer_ist(self):
        """Die Grenze kommt aus der eigenen Buchfuehrung, nicht vom Bildschirm:
        24 minus verbraucht minus offen. Sind 20 Karten verbraucht und liegen
        4 offen, ist der Stapel rechnerisch leer -- dann darf kein Klick mehr
        auf den Stapel gehen, egal wie das Feld aussieht."""
        sim = Simulator()
        sim.stapel = []
        sim.feld[0] = 'leer'                       # 4 offene Karten
        offen = [k for k in sim.feld if k != 'leer']
        alle = [(v, c) for v in VALUES for c in COLORS]
        verbraucht = [k for k in alle if k not in offen]     # genau 20
        self.assertEqual(len(verbraucht), 20)
        vorher = sim.klicks
        with mock.patch.object(partie.vision, 'read_field',
                               side_effect=lambda i: list(i.feld)):
            partie._nachziehen(sim, verbraucht)
        self.assertEqual(sim.klicks, vorher,
                         'trotz leerem Stapel auf den Stapel geklickt')

    def test_deckt_ein_komplett_verdecktes_brett_auf(self):
        """Der Partie-ANFANG: alle fuenf Plaetze verdeckt, 24 Karten im Stapel
        (Bild 19 des Nutzers). Deckt der Stapel je Klick nur EINE Karte auf,
        muss das Nachziehen trotzdem auf fuenf kommen."""
        sim = Simulator()
        sim.stapel = [k for k in sim.feld if k != 'leer'] + sim.stapel
        sim.feld = ['leer'] * 5

        def einzeln():                 # ein Klick = EINE Karte
            sim.klicks += 1
            for i in range(5):
                if sim.feld[i] == 'leer' and sim.stapel:
                    sim.feld[i] = sim.stapel.pop(0)
                    return
        sim.klick_stapel = einzeln
        with mock.patch.object(partie.vision, 'read_field',
                               side_effect=lambda i: list(i.feld)):
            feld = partie._nachziehen(sim, [])
        self.assertNotIn('leer', feld, 'Brett blieb halb verdeckt')

    def test_zieht_sehr_wohl_wenn_noch_karten_da_sind(self):
        """Gegenprobe zum Test darueber -- sonst wuerde ein Ablauf, der NIE
        nachzieht, ihn ebenfalls bestehen."""
        sim = Simulator()
        sim.feld[0] = 'leer'
        vorher = sim.klicks
        with mock.patch.object(partie.vision, 'read_field',
                               side_effect=lambda i: list(i.feld)):
            partie._nachziehen(sim, [])
        self.assertGreater(sim.klicks, vorher, 'gar nicht nachgezogen')


class TestRundenende(unittest.TestCase):
    """Ist der Stapel leer und nichts mehr legbar, wird aufgehoert -- nicht
    noch sinnlos weggeworfen.

    Geprueft wird die Regel direkt UND ihre Wirkung in einer vollen Partie.
    Ein erster Anlauf setzte eine Endstellung von Hand zusammen und schlug fehl
    -- ``spielen()`` fuehrt seine EIGENE Buchfuehrung, die immer bei null
    beginnt; eine von aussen gesetzte Restliste sieht sie gar nicht.
    """

    def test_regel_greift_nur_bei_leerem_stapel(self):
        alle = [(v, c) for v in VALUES for c in COLORS]
        rest = [(1, 'R'), (4, 'B'), (7, 'G'), (2, 'R')]     # keine Kombination
        verbraucht = [k for k in alle if k not in rest]
        self.assertTrue(partie._nichts_mehr_zu_holen(rest, verbraucht))
        # Liegt noch eine Karte im Stapel, gilt die Regel NICHT -- es kann ja
        # noch etwas Passendes kommen.
        self.assertFalse(partie._nichts_mehr_zu_holen(rest, verbraucht[:-1]))

    def test_regel_greift_nicht_bei_spielbarer_hand(self):
        alle = [(v, c) for v in VALUES for c in COLORS]
        rest = [(3, 'R'), (3, 'B'), (3, 'G'), (8, 'R')]     # Drilling moeglich
        verbraucht = [k for k in alle if k not in rest]
        self.assertFalse(partie._nichts_mehr_zu_holen(rest, verbraucht))

    def test_volle_partie_endet_ohne_sinnlose_klicks(self):
        """Am Ende einer echten Partie darf nicht mehr geklickt werden, sobald
        nichts mehr legbar ist."""
        from okey.combos import card_id, mask_of, playable
        sim = Simulator()
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'fertig')
        offen = [k for k in sim.feld if k != 'leer']
        if sim.stapel:
            self.skipTest('diese Mischung endete nicht mit leerem Stapel')
        # Es blieb nichts Spielbares liegen -- sonst haette der Ablauf zu
        # frueh aufgehoert.
        self.assertFalse(playable(mask_of(card_id(*k) for k in offen)),
                         'eine legbare Kombination blieb liegen: %s' % offen)


class TestNotAusUndFehler(unittest.TestCase):
    def test_not_aus_beendet_die_partie(self):
        sim = Simulator(abbruch_nach=2)
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'abbruch')

    def test_verschwundenes_brett_meldet_sich(self):
        sim = Simulator(brett=False)
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'brett-weg')

    def test_unlesbares_feld_stoppt_statt_zu_raten(self):
        sim = Simulator()
        with mock.patch.object(partie.flow, 'brett_laeuft', return_value=True), \
             mock.patch.object(partie.vision, 'read_field',
                               return_value=['?'] * 5), \
             mock.patch.object(partie.vision, 'field_diag', return_value=[]), \
             mock.patch.object(partie.vision, 'read_points', return_value=0):
            bericht = partie.spielen(sim, staerke='sofort')
        self.assertEqual(bericht.status, 'unlesbar')
        self.assertEqual(sim.klicks, 0, 'trotz unlesbarem Feld geklickt')

    def test_unlesbares_feld_beim_klicken_gilt_nicht_als_erledigt(self):
        """Der teure Fall: eine ausgefallene Aufnahme liefert fuenfmal '?'.
        Die Karte gilt dann NICHT als weg -- sonst buchte der Ablauf sie als
        verbraucht, obwohl sie noch oben liegt, und die Identitaet
        "Stapel = 24 - verbraucht - offen" waere gebrochen."""
        sim = Simulator()
        karte = [k for k in sim.feld if k != 'leer'][0]
        with mock.patch.object(partie.vision, 'read_field',
                               return_value=['?'] * 5), \
             mock.patch.object(partie.vision, 'field_diag', return_value=[]):
            erledigt = partie._karte_klicken(sim, karte)
        self.assertEqual(erledigt, 'unlesbar',
                         'unlesbares Feld als Erfolg gewertet')
        self.assertEqual(sim.klicks, 0, 'ins Unklare geklickt')

    def test_unlesbar_ERST_NACH_dem_klick_gilt_auch_nicht_als_erledigt(self):
        """Die zweite Haelfte derselben Regel -- und die war ungeprueft: das
        Feld ist VOR dem Klick lesbar, danach faellt die Aufnahme aus. Ohne die
        Pruefung waere ein leeres ``'?'``-Feld der "Beweis", dass die Karte weg
        ist -- der Ablauf buchte sie als verbraucht, ohne es zu wissen."""
        sim = Simulator()
        karte = [k for k in sim.feld if k != 'leer'][0]
        gelesen = [0]

        def wechselhaft(_bild):
            gelesen[0] += 1
            # Die ersten Lesungen (vor dem Klick) sind sauber, danach nicht.
            return list(sim.feld) if gelesen[0] <= 1 else ['?'] * 5

        with mock.patch.object(partie.vision, 'read_field',
                               side_effect=wechselhaft), \
             mock.patch.object(partie.vision, 'field_diag', return_value=[]):
            erledigt = partie._karte_klicken(sim, karte)
        self.assertEqual(erledigt, 'unlesbar',
                         'unlesbare Quittung als Erfolg gewertet')

    def test_verdecktes_fenster_meldet_unlesbar_nicht_abgelehnt(self):
        """Der Reiter soll die richtige Ursache zeigen: ein verdecktes Fenster
        ist kein vom Spiel abgelehnter Zug."""
        sim = Simulator()
        with mock.patch.object(partie.flow, 'brett_laeuft', return_value=True), \
             mock.patch.object(partie.vision, 'field_diag', return_value=[]), \
             mock.patch.object(partie.vision, 'read_points', return_value=0):
            gelesen = [0]

            def erst_gut_dann_blind(_bild):
                gelesen[0] += 1
                return list(sim.feld) if gelesen[0] <= 2 else ['?'] * 5
            with mock.patch.object(partie.vision, 'read_field',
                                   side_effect=erst_gut_dann_blind):
                bericht = partie.spielen(sim, staerke='sofort')
        self.assertEqual(bericht.status, 'unlesbar')

    def test_not_aus_im_zug_meldet_abbruch_nicht_fehler(self):
        """Der Stop-Knopf waehrend der drei Klicks einer Kombination ist kein
        abgelehnter Zug -- der Reiter zeigte sonst eine Fehlermeldung."""
        sim = Simulator(abbruch_nach=1)
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'abbruch',
                         'Not-Aus als Fehler ausgewiesen')

    def test_doppelt_gelesene_karte_stoppt(self):
        """Das typische Symptom einer verrutschten Erkennung -- es darf NICHT
        zu einem Klick fuehren, weil es die Kartenzaehlung dauerhaft
        verfaelschen wuerde."""
        sim = Simulator()
        doppelt = [(7, 'R'), (7, 'R'), (2, 'B'), (3, 'G'), (4, 'R')]
        with mock.patch.object(partie.flow, 'brett_laeuft', return_value=True), \
             mock.patch.object(partie.vision, 'read_field',
                               return_value=doppelt), \
             mock.patch.object(partie.vision, 'read_points', return_value=0):
            bericht = partie.spielen(sim, staerke='sofort')
        self.assertEqual(bericht.status, 'stellungsfehler')
        self.assertEqual(sim.klicks, 0)

    def test_zurueckgewiesene_kombination_stoppt(self):
        """Wenn die drei Karten wieder oben liegen, stimmt etwas
        Grundsaetzliches nicht -- dann wird nicht weitergeklickt."""
        sim = Simulator()

        def klick_ohne_wirkung(index, rechts=False):
            sim.klicks += 1        # der Klick kommt nie an

        sim.klick_karte = klick_ohne_wirkung
        bericht = _spielen(sim)
        self.assertEqual(bericht.status, 'zug-abgelehnt')


class TestTruhen(unittest.TestCase):
    def test_grenzen_wie_im_wiki(self):
        self.assertEqual(partie.truhe_von(299), 'bronze')
        self.assertEqual(partie.truhe_von(300), 'silber')
        self.assertEqual(partie.truhe_von(399), 'silber')
        self.assertEqual(partie.truhe_von(400), 'gold')
        self.assertEqual(partie.truhe_von(560), 'gold')


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
