# -*- coding: utf-8 -*-
"""EXAKTE Loesung -- soweit sie rechenbar ist.

Der Denkfehler, den dieses Modul korrigiert: Das Okey-Spiel sieht aus wie ein
Kartenspiel mit verdeckten Karten, ist aber keines. Das Deck besteht aus genau
24 bekannten Karten; was noch drin liegt, ergibt sich jederzeit aus
"alles minus Feld minus verbraucht". **Verborgene Information gibt es nicht**,
nur Zufall beim Ziehen. Damit ist der Zustand ``(feld, rest_menge)`` vollstaendig
beobachtbar und markowsch -- ein gewoehnliches Markow-Entscheidungsproblem.

Folge fuer die Verfahrenswahl:

* Die Stichproben-Suche ``pimc_action`` (Deck mischen, jede Variante hellsichtig
  loesen) ist hier das FALSCHE Werkzeug. Sie unterstellt in jeder Stichprobe,
  der Spieler kenne die Reihenfolge -- der bekannte Fehler "strategy fusion".
  Sie waehlt dadurch Zuege, die nur mit Blick in die Zukunft gut sind.
* Richtig ist Erwartungswert-Suche ueber den echten Zustand: an jedem
  Zufallsknoten wird ueber ALLE gleich wahrscheinlichen Karten gemittelt, statt
  eine Reihenfolge zu raten. Das konvergiert gegen das echte Optimum.

Das Ziehen von drei Karten wird bewusst als drei EINZELNE Zuege modelliert.
Das Ergebnis ist identisch (die Reihenfolge innerhalb eines Nachziehens ist
fuer den Wert egal), aber der Verzweigungsgrad sinkt von C(k,3) auf k -- und
die Zwischenzustaende sind selbst wieder memoisierbar. Ohne diesen Kniff waere
schon ein Endspiel mit 9 Restkarten unbezahlbar.

Der Memo-Schluessel ``(feld, rest_menge)`` ist NICHT spielabhaengig: derselbe
Zustand kann in ganz verschiedenen Partien auftreten. Der Speicher wird deshalb
ueber Spiele hinweg wiederverwendet -- der Hauptgrund, warum das exakte
Endspiel praktisch bezahlbar ist.
"""

from .combos import playable, popcount

FIELD_SIZE = 5

#: Gemeinsamer Speicher ueber alle Aufrufe. Schluessel ``(feld, rest_menge)``.
#: Der Schluessel ist NICHT spielabhaengig -- derselbe Zustand kann in ganz
#: verschiedenen Partien auftreten, deshalb ist die Wiederverwendung hier
#: (anders als beim hellsichtigen Cache) korrekt.
MEMO = {}

#: Obergrenze, damit der Speicher nicht den Arbeitsspeicher sprengt. Ein Lauf
#: ueber 300 Deals kam ungebremst auf 19 Mio. Eintraege.
MEMO_MAX = 4_000_000


def _maybe_trim(memo):
    if memo is MEMO and len(memo) > MEMO_MAX:
        memo.clear()


def exact_value(field, deck_mask, memo=None):
    """Exakter Erwartungswert der Restpunkte bei optimalem Weiterspielen.

    ``deck_mask`` ist die MENGE der noch im Deck liegenden Karten; ihre
    Reihenfolge ist gleichverteilt zufaellig. Rueckgabe ist ein float (ein
    Erwartungswert, keine erreichbare Punktzahl).
    """
    if memo is None:
        memo = MEMO
    _maybe_trim(memo)
    return _v(field, deck_mask, memo)


def _v(field, deck_mask, memo):
    key = (field, deck_mask)
    hit = memo.get(key)
    if hit is not None:
        return hit

    # -- Zufallsknoten: Feld ist nicht voll und es liegt noch etwas im Deck ---
    if popcount(field) < FIELD_SIZE and deck_mask:
        summe = 0.0
        n = 0
        rest = deck_mask
        while rest:
            bit = rest & -rest
            rest ^= bit
            summe += _v(field | bit, deck_mask & ~bit, memo)
            n += 1
        wert = summe / n
        memo[key] = wert
        return wert

    # -- Entscheidungsknoten -------------------------------------------------
    best = 0.0
    for cmask, punkte, _ids in playable(field):
        wert = punkte + _v(field & ~cmask, deck_mask, memo)
        if wert > best:
            best = wert

    # Wegwerfen lohnt nur, solange nachgezogen werden kann.
    if deck_mask:
        rest = field
        while rest:
            bit = rest & -rest
            rest ^= bit
            wert = _v(field & ~bit, deck_mask, memo)
            if wert > best:
                best = wert

    memo[key] = best
    return best


def exact_action(field, deck_mask, memo=None):
    """Die EXAKT optimale Aktion -> ``('play'|'discard', maske, punkte)``.

    Nur aufrufen, wenn ``popcount(deck_mask)`` klein genug ist (siehe
    :func:`affordable`); sonst laeuft die Rechnung aus dem Ruder.
    """
    if memo is None:
        memo = MEMO
    _maybe_trim(memo)
    beste, bestwert = None, None
    for cmask, punkte, _ids in playable(field):
        wert = punkte + _v(field & ~cmask, deck_mask, memo)
        if bestwert is None or wert > bestwert:
            beste, bestwert = ('play', cmask, punkte), wert
    if deck_mask:
        rest = field
        while rest:
            bit = rest & -rest
            rest ^= bit
            wert = _v(field & ~bit, deck_mask, memo)
            if bestwert is None or wert > bestwert:
                beste, bestwert = ('discard', bit, 0), wert
    return beste


def affordable(deck_mask, grenze=10):
    """``True``, wenn das exakte Verfahren hier noch bezahlbar ist."""
    return popcount(deck_mask) <= grenze
