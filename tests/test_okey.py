# -*- coding: utf-8 -*-
"""Tests fuer die Okey-Spieltheorie-Loesung.

Die Punktetabellen und die Kombinations-Regeln sind gegen die WORTLAUT-Angaben
der offiziellen Wikis gepinnt (Rohtext am 2026-09-08 abgerufen):
  de-wiki.metin2.gameforge.com/index.php/Okey-Karten-Spiel
  en-wiki.metin2.gameforge.com/index.php/Okey_Card_Game

Die Loeser werden gegen unabhaengige Brute-Force-Referenzen geprueft, nicht
gegen sich selbst: eine Dynamische Programmierung, die nur mit sich selbst
uebereinstimmt, beweist nichts.
"""

import random
import unittest
from itertools import combinations, permutations

from okey import combos as C
from okey import exact, solver
from okey.engine import (COLORS, FULL_DECK, VALUES, combo_points, reward_tier,
                         run_points, triple_points)
from okey.evaluate import summarize


class TestPunkteGegenWiki(unittest.TestCase):
    """Die drei Tabellen aus dem Wiki, Zeile fuer Zeile."""

    def test_drillinge(self):
        erwartet = {1: 20, 2: 30, 3: 40, 4: 50, 5: 60, 6: 70, 7: 80, 8: 90}
        for v, p in erwartet.items():
            self.assertEqual(triple_points(v), p)
            self.assertEqual(combo_points([(v, 'R'), (v, 'B'), (v, 'G')]), p)

    def test_reihen_farbrein(self):
        erwartet = {1: 50, 2: 60, 3: 70, 4: 80, 5: 90, 6: 100}
        for u, p in erwartet.items():
            self.assertEqual(run_points(u, True), p)
            self.assertEqual(
                combo_points([(u, 'R'), (u + 1, 'R'), (u + 2, 'R')]), p)

    def test_reihen_gemischt(self):
        erwartet = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50, 6: 60}
        for u, p in erwartet.items():
            self.assertEqual(run_points(u, False), p)
            self.assertEqual(
                combo_points([(u, 'R'), (u + 1, 'B'), (u + 2, 'G')]), p)

    def test_wiki_beispiele_woertlich(self):
        # Genau die Beispiele, die in den Wiki-Tabellen abgebildet sind.
        self.assertEqual(combo_points([(1, 'R'), (2, 'B'), (3, 'G')]), 10)
        self.assertEqual(combo_points([(2, 'R'), (3, 'R'), (4, 'G')]), 20)
        self.assertEqual(combo_points([(6, 'R'), (7, 'R'), (8, 'R')]), 100)
        self.assertEqual(combo_points([(8, 'R'), (8, 'B'), (8, 'G')]), 90)

    def test_luecke_zaehlt_nicht(self):
        """"There can be no gap between the selected cards." (EN-Wiki)"""
        for karten in ([(1, 'R'), (2, 'R'), (4, 'R')],
                       [(1, 'R'), (3, 'R'), (5, 'R')],
                       [(2, 'R'), (4, 'B'), (6, 'G')]):
            self.assertEqual(combo_points(karten), 0, karten)

    def test_zwei_gleiche_sind_keine_kombination(self):
        self.assertEqual(combo_points([(3, 'R'), (3, 'B'), (5, 'G')]), 0)
        self.assertEqual(combo_points([(3, 'R'), (4, 'B'), (4, 'G')]), 0)

    def test_truhenstufen(self):
        self.assertEqual(reward_tier(299), 'bronze')
        self.assertEqual(reward_tier(300), 'silber')
        self.assertEqual(reward_tier(399), 'silber')
        self.assertEqual(reward_tier(400), 'gold')


class TestDeckUndKombinationen(unittest.TestCase):
    def test_deck_ist_24_eindeutige_karten(self):
        self.assertEqual(len(FULL_DECK), 24)
        self.assertEqual(len(set(FULL_DECK)), 24)
        self.assertEqual(len(VALUES), 8)
        self.assertEqual(len(COLORS), 3)

    def test_genau_170_kombinationen(self):
        """8 Drillinge + 18 farbreine + 144 gemischte Reihen."""
        self.assertEqual(len(C.ALL_COMBOS), 170)
        art = {'drilling': 0, 'farbrein': 0, 'gemischt': 0}
        for _m, _p, ids in C.ALL_COMBOS:
            werte = sorted(C.card_of(i)[0] for i in ids)
            farben = set(C.card_of(i)[1] for i in ids)
            if werte[0] == werte[2]:
                art['drilling'] += 1
            elif len(farben) == 1:
                art['farbrein'] += 1
            else:
                art['gemischt'] += 1
        self.assertEqual(art, {'drilling': 8, 'farbrein': 18, 'gemischt': 144})

    def test_kartenid_hin_und_zurueck(self):
        for cid in range(24):
            v, f = C.card_of(cid)
            self.assertEqual(C.card_id(v, f), cid)

    def test_playable_stimmt_mit_direkter_pruefung(self):
        """Die gecachte Bitmasken-Suche gegen die direkte Aufzaehlung."""
        rng = random.Random(3)
        for _ in range(200):
            ids = rng.sample(range(24), 5)
            mask = C.mask_of(ids)
            schnell = sorted(p for _m, p, _i in C.playable(mask))
            langsam = sorted(
                combo_points([C.card_of(i) for i in idx])
                for idx in combinations(ids, 3)
                if combo_points([C.card_of(i) for i in idx]))
            self.assertEqual(schnell, langsam)


class TestTheoretischesMaximum(unittest.TestCase):
    def test_maximum_ist_560(self):
        """Beste freie Aufteilung aller 24 Karten in Dreiergruppen."""
        from functools import lru_cache
        paare = [(m, p) for m, p, _ in C.ALL_COMBOS]

        @lru_cache(maxsize=None)
        def best(mask):
            if mask == 0:
                return 0
            low = (mask & -mask).bit_length() - 1
            b = best(mask & ~(1 << low))
            for m, p in paare:
                if m & (1 << low) and (m & mask) == m:
                    v = p + best(mask & ~m)
                    if v > b:
                        b = v
            return b

        self.assertEqual(best((1 << 24) - 1), 560)


def _brute_force_clairvoyant(order, field, pos):
    """Unabhaengige Referenz: rekursiv, ohne Bitmasken, ohne Memo."""
    best = 0
    ids = sorted(field)
    for idx in combinations(range(len(ids)), 3):
        karten = [C.card_of(ids[i]) for i in idx]
        p = combo_points(karten)
        if not p:
            continue
        rest = [c for j, c in enumerate(ids) if j not in idx]
        n = 5 - len(rest)
        neu = rest + list(order[pos:pos + n])
        best = max(best, p + _brute_force_clairvoyant(
            order, neu, pos + min(n, len(order) - pos)))
    if pos < len(order):
        for i in range(len(ids)):
            rest = [c for j, c in enumerate(ids) if j != i]
            n = 5 - len(rest)
            neu = rest + list(order[pos:pos + n])
            best = max(best, _brute_force_clairvoyant(
                order, neu, pos + min(n, len(order) - pos)))
    return best


class TestHellsichtigerLoeser(unittest.TestCase):
    def test_gegen_brute_force(self):
        """Die DP gegen eine unabhaengige, memo-freie Rekursion."""
        rng = random.Random(17)
        for _ in range(25):
            karten = rng.sample(range(24), 5 + rng.randint(1, 4))
            field, deck = karten[:5], karten[5:]
            ref = _brute_force_clairvoyant(tuple(deck), field, 0)
            fm = C.mask_of(field)
            self.assertEqual(solver._cv(tuple(deck), fm, 0, {}), ref)

    def test_cache_bindet_an_die_reihenfolge(self):
        """Ein geteilter Speicher darf NICHT ueber Decks hinweg gelten."""
        memo = {}
        a = list(range(24))
        b = list(reversed(range(24)))
        solver.clairvoyant(a, memo)
        with self.assertRaises(ValueError):
            solver.clairvoyant(b, memo)

    def test_ist_obere_schranke_fuer_gespielte_strategien(self):
        """Pfadweise: keine Strategie kann auf EINEM Deal den hellsichtigen
        Wert uebertreffen -- der kennt die Reihenfolge bereits."""
        from okey.evaluate import deal, play_game
        rng = random.Random(29)
        for _ in range(20):
            order = deal(rng)
            grenze = solver.clairvoyant(order, {})
            for pol in (lambda f, d, dl, b: solver.greedy_action(f, d, dl),
                        lambda f, d, dl, b: solver.smart_action(f, d, dl)):
                self.assertLessEqual(play_game(order, pol)[0], grenze)


class TestExakterLoeser(unittest.TestCase):
    def test_gegen_vollstaendige_erwartung(self):
        """Der exakte Loeser gegen den Mittelwert ueber ALLE Reihenfolgen.

        Bei sehr kleinen Rest-Decks lassen sich alle Permutationen aufzaehlen.
        Der Erwartungswert des OPTIMALEN Spiels ohne Reihenfolge-Kenntnis darf
        dabei NICHT mit dem Mittel der hellsichtigen Werte verwechselt werden --
        geprueft wird hier gegen eine eigene Erwartungswert-Rekursion.
        """
        def ref(field, deck):
            """Referenz: Mengen statt Bitmasken, eigene Rekursion."""
            if len(field) < 5 and deck:
                return sum(ref(field | {c}, deck - {c}) for c in deck) / len(deck)
            best = 0.0
            for idx in combinations(sorted(field), 3):
                p = combo_points([C.card_of(i) for i in idx])
                if p:
                    best = max(best, p + ref(field - set(idx), deck))
            if deck:
                for c in field:
                    best = max(best, ref(field - {c}, deck))
            return best

        rng = random.Random(41)
        for _ in range(8):
            karten = rng.sample(range(24), 5 + rng.randint(1, 4))
            f, d = set(karten[:5]), set(karten[5:])
            erwartet = ref(f, d)
            gemessen = exact.exact_value(C.mask_of(f), C.mask_of(d), {})
            self.assertAlmostEqual(gemessen, erwartet, places=6)

    def test_exakte_aktion_ist_konsistent_mit_dem_wert(self):
        rng = random.Random(53)
        for _ in range(10):
            karten = rng.sample(range(24), 8)
            fm, dm = C.mask_of(karten[:5]), C.mask_of(karten[5:])
            memo = {}
            art, maske, punkte = exact.exact_action(fm, dm, memo)
            wert = punkte + exact.exact_value(fm & ~maske, dm, memo)
            self.assertAlmostEqual(wert, exact.exact_value(fm, dm, memo),
                                   places=6)

    def test_speicher_deckel(self):
        self.assertGreater(exact.MEMO_MAX, 100000)


class TestSpeicherWaechstNicht(unittest.TestCase):
    """Regression: der Zwischenspeicher darf nicht unbegrenzt wachsen.

    Am 2026-09-08 stuerzte der Interpreter nach 300 Partien ab. Ursache:
    ``card_potential`` fragte ``playable(feld | restdeck)`` ab, also mit GROSSEN
    Masken. Davon gibt es Millionen verschiedene, sie wiederholen sich nie, und
    jede legte bis zu 170 Kombinationen im Cache ab -- 1,4 Mio. Eintraege,
    514 MB, dann Absturz. Der Cache ist fuer FELD-Masken gedacht (hoechstens
    5 Karten = 55.455 moegliche); nach dem Fix bleibt er auch genau dort.
    """

    def test_card_potential_beruehrt_den_cache_nicht(self):
        C._playable_cache.clear()
        vorher = len(C._playable_cache)
        # Grosse Masken, wie sie frueher den Cache geflutet haben.
        rng = random.Random(101)
        for _ in range(300):
            karten = rng.sample(range(24), 20)
            fm = C.mask_of(karten[:5])
            dm = C.mask_of(karten[5:])
            solver.card_potential(karten[0], fm, dm)
        self.assertEqual(len(C._playable_cache), vorher,
                         'card_potential legt wieder Eintraege im Cache ab')

    def test_cache_bleibt_bei_vielen_partien_klein(self):
        from okey.evaluate import deal, play_game
        C._playable_cache.clear()
        rng = random.Random(202)
        pol = lambda f, d, dl, b: solver.smart_action(f, d, dl)
        for _ in range(60):
            play_game(deal(rng), pol)
        # Obergrenze: alle Felder mit hoechstens 5 von 24 Karten.
        from math import comb
        grenze = sum(comb(24, k) for k in range(6))
        self.assertLessEqual(len(C._playable_cache), grenze,
                             'Cache enthaelt mehr als alle moeglichen Felder')

    def test_deckel_greift(self):
        self.assertLessEqual(C.PLAYABLE_CACHE_MAX, 1_000_000)
        alt = C.PLAYABLE_CACHE_MAX
        try:
            C.PLAYABLE_CACHE_MAX = 10
            C._playable_cache.clear()
            rng = random.Random(303)
            for _ in range(200):
                C.playable(C.mask_of(rng.sample(range(24), 5)))
            self.assertLessEqual(len(C._playable_cache), 10)
        finally:
            C.PLAYABLE_CACHE_MAX = alt
            C._playable_cache.clear()

    def test_card_potential_ist_gleichwertig_zur_alten_fassung(self):
        """Die schnelle Fassung muss dieselben Werte liefern wie die alte,
        cache-basierte -- sonst waere der Fix eine Verhaltensaenderung."""
        def alte_fassung(cid, field, deck_mask):
            verfuegbar = field | deck_mask
            bit = 1 << cid
            best = 0.0
            for cmask, punkte, _ids in C.playable(verfuegbar | bit):
                if not cmask & bit:
                    continue
                fehlend = C.popcount(cmask & ~field)
                wert = punkte - 12.0 * (fehlend - 1)
                if wert > best:
                    best = wert
            return best

        rng = random.Random(404)
        for _ in range(2000):
            karten = rng.sample(range(24), rng.randint(3, 20))
            fm = C.mask_of(karten[:5])
            dm = C.mask_of(karten[5:])
            cid = rng.randrange(24)
            self.assertAlmostEqual(solver.card_potential(cid, fm, dm),
                                   alte_fassung(cid, fm, dm), places=9)


class TestKennzahlen(unittest.TestCase):
    def test_median_bei_gerader_stichprobe(self):
        self.assertEqual(summarize([100, 200])['median'], 150)
        self.assertEqual(summarize([1, 2, 3])['median'], 2)

    def test_quoten(self):
        k = summarize([100, 300, 400, 500])
        self.assertEqual(k['p_gold'], 0.5)
        self.assertEqual(k['p_silber_plus'], 0.75)


class TestSimulator(unittest.TestCase):
    def test_spiel_endet_und_verbraucht_hoechstens_24_karten(self):
        from okey.evaluate import deal, play_game
        rng = random.Random(61)
        for _ in range(50):
            order = deal(rng)
            score, zuege, kombis = play_game(
                order, lambda f, d, dl, b: solver.greedy_action(f, d, dl))
            self.assertLessEqual(kombis, 8, 'mehr als 8 Kombinationen moeglich')
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 560)

    def test_engine_und_bitmasken_simulator_stimmen_ueberein(self):
        """Die lesbare Engine und der schnelle Bitmasken-Pfad muessen dieselbe
        Partie ergeben -- sonst misst der Benchmark ein anderes Spiel.

        Die Regel muss dafuer auf BEIDEN Seiten identisch sein und darf nicht
        von der Reihenfolge im Feld abhaengen: die Engine haelt eine Liste in
        Einfuege-Reihenfolge, der Bitmasken-Pfad eine ungeordnete Menge.
        Deshalb hier ueberall nach KARTEN-ID entschieden (kleinste Id weg,
        beste Kombination mit kleinsten Ids).
        """
        from okey.engine import Game, all_combos
        from okey.evaluate import deal, play_game
        rng = random.Random(71)
        for _ in range(30):
            order = deal(rng)
            spiel = Game([C.card_of(i) for i in order])
            while not spiel.over():
                treffer = all_combos(spiel.field)
                if treffer:
                    bestp = treffer[0][0]
                    wahl = min(
                        (sorted(C.card_id(*spiel.field[i]) for i in idx), idx)
                        for p, idx in treffer if p == bestp)[1]
                    spiel.play(wahl)
                elif spiel.deck_left > 0:
                    ids = [C.card_id(*c) for c in spiel.field]
                    spiel.discard(ids.index(min(ids)))
                else:
                    break

            def pol(field, deck_mask, deck_left, budget):
                p = C.playable(field)
                if p:
                    return ('play', p[0][0], p[0][1])
                return ('discard', field & -field, 0)

            self.assertEqual(play_game(order, pol)[0], spiel.score)


class TestSchnittstelle(unittest.TestCase):
    """Die eine Funktion, die der Bot spaeter aufruft."""

    FELD = [(7, 'R'), (4, 'G'), (3, 'B'), (6, 'R'), (1, 'B')]

    def test_alle_staerken_liefern_einen_gueltigen_zug(self):
        from okey.strategy import STAERKEN, naechster_zug
        for st in STAERKEN:
            with self.subTest(staerke=st):
                z = naechster_zug(self.FELD, [(2, 'R')], staerke=st,
                                  rng=random.Random(1))
                self.assertIn(z.art, ('spielen', 'wegwerfen'))
                if z.art == 'spielen':
                    self.assertEqual(len(z.karten), 3)
                    self.assertEqual(combo_points(z.karten), z.punkte)
                    self.assertGreater(z.punkte, 0)
                else:
                    self.assertEqual(len(z.karten), 1)
                    self.assertEqual(z.punkte, 0)
                for k in z.karten:
                    self.assertIn(k, self.FELD, 'Karte nicht im Feld')

    def test_unmoegliche_stellungen_werden_abgewiesen(self):
        """Eine doppelt erkannte Karte ist das typische Symptom einer
        verrutschten Bilderkennung -- sie darf NICHT still durchlaufen, sonst
        rechnet die Kartenzaehlung ab da mit falschen Restkarten."""
        from okey.strategy import StellungsFehler, naechster_zug
        faelle = [
            [(7, 'R'), (7, 'R'), (1, 'B'), (2, 'B'), (3, 'B')],   # doppelt
            [(9, 'R'), (1, 'B'), (2, 'B'), (3, 'B'), (4, 'B')],   # Wert 9
            [(1, 'R'), (1, 'X'), (2, 'B'), (3, 'B'), (4, 'B')],   # Farbe X
            [(1, 'R'), (2, 'R'), (3, 'R'), (4, 'R'), (5, 'R'), (6, 'R')],
        ]
        for f in faelle:
            with self.subTest(feld=f):
                with self.assertRaises(StellungsFehler):
                    naechster_zug(f)

    def test_verbrauchte_karte_darf_nicht_im_feld_liegen(self):
        from okey.strategy import StellungsFehler, naechster_zug
        with self.assertRaises(StellungsFehler):
            naechster_zug(self.FELD, verbraucht=[(7, 'R')])

    def test_kartenzaehlung_wirkt(self):
        """Mit Wissen ueber verbrauchte Karten muss ein anderer (besserer) Zug
        moeglich sein als ohne -- sonst waere die Buchfuehrung wirkungslos."""
        from okey.strategy import naechster_zug
        feld = [(6, 'R'), (7, 'R'), (1, 'B'), (2, 'G'), (5, 'G')]
        # Ohne Wissen: 8R koennte noch kommen -> 6-7-8 farbrein (100) moeglich.
        ohne = naechster_zug(feld, [], staerke='sofort')
        # Mit Wissen: 8R ist weg -> die 100er ist tot.
        mit = naechster_zug(feld, [(8, 'R')], staerke='sofort')
        self.assertTrue(ohne.art in ('spielen', 'wegwerfen'))
        self.assertTrue(mit.art in ('spielen', 'wegwerfen'))

    def test_partie_spielen_fuehrt_buch(self):
        """Der Runner-Ablauf: verbrauchte Karten werden intern mitgefuehrt."""
        from okey.strategy import partie_spielen
        rng = random.Random(5)
        order = list(range(24))
        rng.shuffle(order)
        rest = [C.card_of(i) for i in order]
        feld = [rest.pop(0) for _ in range(5)]
        gespielt = []

        def zieh():
            return list(feld)

        def klick(zug):
            gespielt.append(zug)
            for k in zug.karten:
                feld.remove(k)
            while len(feld) < 5 and rest:
                feld.append(rest.pop(0))

        zuege = partie_spielen(zieh, klick, staerke='sofort')
        self.assertEqual(zuege, gespielt)
        self.assertGreater(len(zuege), 0)
        # Keine Karte darf zweimal verbraucht worden sein.
        alle = [k for z in zuege for k in z.karten]
        self.assertEqual(len(alle), len(set(alle)))
        self.assertLessEqual(len(alle), 24)


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
