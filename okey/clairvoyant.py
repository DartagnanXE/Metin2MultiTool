# -*- coding: utf-8 -*-
"""Hellsichtige Optimalloesung: der beste Score bei BEKANNTER Deck-Reihenfolge.

Wozu das gut ist: Der echte Spieler kennt die Reihenfolge nicht. Wer sie kennt,
kann nie schlechter spielen -- der hellsichtige Wert ist also eine **obere
Schranke fuer jede denkbare Strategie**. Der Abstand zwischen ihm und einer
Strategie ist damit ein ehrliches Mass fuer "wie viel fehlt noch zum Optimum",
ohne dass man das (viel zu grosse) echte MDP loesen muesste.

Verfahren: exakte Dynamische Programmierung ueber ``(deck_position, feld)``.
Das Feld ist eine Teilmenge der bereits aufgedeckten Karten; die Deck-Position
bestimmt, was als naechstes kommt. Beides zusammen ist der komplette Zustand,
weil Punkte additiv sind. Memoisiert -> jeder Zustand wird einmal geloest.

Wegwerfen bei LEEREM Deck ist ausgeschlossen: es entfernt eine Karte ohne
Ersatz und kann den Score nie erhoehen. Das ist eine beweisbar verlustfreie
Beschneidung und garantiert zugleich die Terminierung (jede Aktion verbraucht
entweder eine Deck-Karte oder verkleinert das Feld).
"""

from .engine import FIELD_SIZE, all_combos


def solve(deck, field=None, pos=None, memo=None):
    """Maximal erreichbare Punktzahl ab dem gegebenen Zustand.

    :param deck: die vollstaendige Deck-Reihenfolge (Liste von Karten).
    :param field: aktuelles Feld; ``None`` -> frischer Start (5 Karten geben).
    :param pos: Anzahl bereits gezogener Deck-Karten.
    :param memo: optionaler geteilter Memo-Dict (ueber mehrere Aufrufe hinweg
        wiederverwendbar, solange ``deck`` dasselbe ist).
    :return: die maximale Restpunktzahl (int).
    """
    if field is None:
        field, pos = list(deck[:FIELD_SIZE]), FIELD_SIZE
    if memo is None:
        memo = {}
    return _solve(tuple(deck), tuple(sorted(field)), pos, memo)


def _refill(deck, field, pos):
    """Feld auf 5 auffuellen -> ``(feld_tupel, neue_position)``."""
    need = FIELD_SIZE - len(field)
    if need <= 0 or pos >= len(deck):
        return field, pos
    take = min(need, len(deck) - pos)
    return tuple(sorted(field + tuple(deck[pos:pos + take]))), pos + take


def _solve(deck, field, pos, memo):
    key = (pos, field)
    hit = memo.get(key)
    if hit is not None:
        return hit

    best = 0
    combos = all_combos(field)

    # (1) Eine Kombination spielen.
    for punkte, idx in combos:
        rest = tuple(c for i, c in enumerate(field) if i not in idx)
        nf, np_ = _refill(deck, rest, pos)
        wert = punkte + _solve(deck, nf, np_, memo)
        if wert > best:
            best = wert

    # (2) Eine Karte wegwerfen -- nur solange nachgezogen werden kann.
    if pos < len(deck):
        gesehen = set()
        for i, card in enumerate(field):
            if card in gesehen:
                continue
            gesehen.add(card)
            rest = tuple(c for j, c in enumerate(field) if j != i)
            nf, np_ = _refill(deck, rest, pos)
            wert = _solve(deck, nf, np_, memo)
            if wert > best:
                best = wert

    memo[key] = best
    return best
