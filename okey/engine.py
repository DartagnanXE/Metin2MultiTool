# -*- coding: utf-8 -*-
"""Exakte Regel-Engine des Metin2 Okey-Karten-Spiels.

QUELLEN (2026-09-08 abgerufen, Rohtext der Wiki-Seiten):
  * de-wiki.metin2.gameforge.com/index.php/Okey-Karten-Spiel
  * en-wiki.metin2.gameforge.com/index.php/Okey_Card_Game

REGELN, wie sie dort stehen:
  * Ein Okey-Kartenset entsteht aus 24 Sammelkarten. Das Spiel hat die Werte
    1..8 in den Farben Rot/Blau/Gelb -> 8*3 = 24 Karten, JEDE GENAU EINMAL.
    Das Deck ist also vollstaendig bekannt; unbekannt ist nur die Reihenfolge.
  * Start kostet 30.000 Yang + 1 Kartenset.
  * Auf dem Feld liegen 5 Karten. Drei davon werden zu einer Kombination
    gewaehlt:
      - drei gleiche Zahlen (dann zwingend drei verschiedene Farben),
      - drei aufsteigende Zahlen OHNE LUECKE ("There can be no gap"),
        Farben egal -- alle gleich gibt mehr Punkte.
  * Passt nichts, wirft man per Rechtsklick EINE Karte weg.
  * Punkte (exakt aus den Wiki-Tabellen, hier als Formel nachgerechnet):
      Drilling Wert v      -> 10*v + 10   (v=1..8  ->  20..90)
      Reihe gleiche Farbe  -> 10*u + 40   (u=1..6  ->  50..100, u = kleinste)
      Reihe gemischt       -> 10*u        (u=1..6  ->  10..60)
  * Belohnung: <300 Bronze, 300-399 Silber, ab 400 Gold.

MODELLIERTE ANNAHMEN (im Spiel zu pruefen, siehe README):
  A1 Nach jeder entfernten Karte wird aus dem Rest des Sets nachgezogen, bis
     das Deck leer ist. Das Feld bleibt also bei 5 Karten, solange es geht.
  A2 Wegwerfen ist immer erlaubt, nicht nur wenn keine Kombination da ist.
  A3 Es gibt kein Zug-/Zeitlimit ausser dem Deck selbst.
  Alle drei sind fuer die Strategie folgenreich -- A1 macht das Deck zu einer
  harten Obergrenze von 8 Kombinationen (24/3), A2 erlaubt das bewusste
  Wegwerfen einer spielbaren, aber schwachen Kombination.

Reines Python (stdlib), keine Abhaengigkeit, headless testbar.
"""

from itertools import combinations

VALUES = tuple(range(1, 9))          # 1..8
COLORS = ('R', 'B', 'G')             # Rot, Blau, Gelb
FIELD_SIZE = 5
COMBO_SIZE = 3

#: Das vollstaendige Deck: jede (Wert, Farbe)-Kombination genau einmal.
FULL_DECK = tuple((v, c) for v in VALUES for c in COLORS)
DECK_SIZE = len(FULL_DECK)           # 24


def triple_points(value):
    """Punkte fuer einen Drilling des Wertes ``value`` (20..90)."""
    return 10 * value + 10


def run_points(low, same_color):
    """Punkte fuer eine Reihe ``low, low+1, low+2`` (gleiche Farbe: +40)."""
    return 10 * low + (40 if same_color else 0)


def combo_points(cards):
    """Punkte der 3er-Auswahl ``cards`` -- 0, wenn es keine gueltige ist.

    ``cards`` ist eine Folge von ``(wert, farbe)``. Wirft nie.
    """
    if len(cards) != COMBO_SIZE:
        return 0
    werte = sorted(c[0] for c in cards)
    farben = [c[1] for c in cards]
    if werte[0] == werte[1] == werte[2]:
        # Drilling: im 24er-Set gibt es jeden Wert nur dreimal, je Farbe einmal
        # -- drei gleiche Werte sind also automatisch dreifarbig. Der Test
        # bleibt trotzdem stehen, damit die Funktion auch fuer fremde Decks
        # (Doppelkarten) korrekt bleibt.
        return triple_points(werte[0]) if len(set(farben)) == COMBO_SIZE else 0
    if werte[1] == werte[0] + 1 and werte[2] == werte[1] + 1:
        return run_points(werte[0], len(set(farben)) == 1)
    return 0


def all_combos(field):
    """Alle gueltigen 3er-Auswahlen aus ``field`` -> ``[(punkte, indizes), ...]``.

    Absteigend nach Punkten sortiert; bei Gleichstand stabil nach Indizes.
    """
    treffer = []
    for idx in combinations(range(len(field)), COMBO_SIZE):
        p = combo_points([field[i] for i in idx])
        if p:
            treffer.append((p, idx))
    treffer.sort(key=lambda t: (-t[0], t[1]))
    return treffer


def best_combo_points(field):
    """Punkte der besten Kombination im Feld (0, wenn keine existiert)."""
    treffer = all_combos(field)
    return treffer[0][0] if treffer else 0


def reward_tier(score):
    """Truhe zur Punktzahl: ``'bronze' | 'silber' | 'gold'``."""
    if score >= 400:
        return 'gold'
    if score >= 300:
        return 'silber'
    return 'bronze'


class Game:
    """Ein Durchgang mit fester (verdeckter) Deck-Reihenfolge.

    ``deck`` ist die gemischte Liste aller 24 Karten; gezogen wird von vorne.
    Der Spieler sieht ``field``; welche Karten noch im Deck liegen, ergibt
    sich aus ``FULL_DECK`` minus Feld minus Verbrauchtem -- diese Menge ist
    dem Spieler bekannt (Kartenzaehlen), die REIHENFOLGE nicht.
    """

    __slots__ = ('deck', 'pos', 'field', 'score', 'log')

    def __init__(self, deck):
        self.deck = list(deck)
        self.pos = 0
        self.field = []
        self.score = 0
        self.log = []
        self._refill()

    # -- Zustand ---------------------------------------------------------
    def _refill(self):
        while len(self.field) < FIELD_SIZE and self.pos < len(self.deck):
            self.field.append(self.deck[self.pos])
            self.pos += 1

    @property
    def deck_left(self):
        return len(self.deck) - self.pos

    def remaining_unknown(self):
        """Die Karten, die noch im Deck liegen -- als Menge (Reihenfolge unbekannt).

        Genau das, was ein Kartenzaehler weiss: alles minus Feld minus schon
        Verbrauchtes.
        """
        return set(self.deck[self.pos:])

    def over(self):
        """Das Spiel ist vorbei, wenn nichts mehr geht: kein Nachziehen mehr
        moeglich UND keine Kombination mehr im Feld."""
        if self.deck_left > 0:
            return False
        return best_combo_points(self.field) == 0

    # -- Zuege -----------------------------------------------------------
    def play(self, idx):
        """Kombination ``idx`` (3 Feld-Indizes) spielen -> Punkte."""
        cards = [self.field[i] for i in idx]
        p = combo_points(cards)
        if p == 0:
            raise ValueError('ungueltige Kombination: %r' % (cards,))
        for i in sorted(idx, reverse=True):
            del self.field[i]
        self.score += p
        self.log.append(('play', tuple(cards), p))
        self._refill()
        return p

    def discard(self, i):
        """Karte ``i`` wegwerfen (und, wenn moeglich, nachziehen)."""
        card = self.field.pop(i)
        self.log.append(('discard', card, 0))
        self._refill()
        return card
