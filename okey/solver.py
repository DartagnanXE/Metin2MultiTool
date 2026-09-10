# -*- coding: utf-8 -*-
"""Schneller hellsichtiger Optimierer (Bitmasken) + die Strategien.

Zwei Dinge stecken hier drin:

1. :func:`clairvoyant` -- der maximal moegliche Score bei BEKANNTER
   Deck-Reihenfolge, exakt per Dynamischer Programmierung. Wer die
   Reihenfolge kennt, kann nie schlechter spielen als jemand, der sie nicht
   kennt: der Mittelwert dieser Zahl ist damit eine **harte obere Schranke
   fuer jede Strategie**. So laesst sich "wie weit ist das noch vom Optimum
   entfernt" messen, ohne das echte (viel zu grosse) MDP zu loesen.

2. Die spielbaren Strategien -- von "immer die beste Kombination nehmen" bis
   zur Stichproben-Suche :func:`pimc_action`, die den bekannten Deck-Rest
   mehrfach durchmischt und jede Variante hellsichtig durchrechnet.

Warum das MDP nicht exakt loesbar ist: der Zustand ist (Feld, Rest-Deck).
Schon die Zahl der Paare liegt bei C(24,5) * 2^19 ~ 2*10^10 -- selbst mit der
Farb-Symmetrie (Faktor 6) bleibt es unerreichbar. Deshalb obere Schranke +
starke Strategie, und die Luecke dazwischen wird gemessen statt behauptet.
"""

import random

from .combos import COMBOS_BY_CARD, best_points, playable, popcount

FIELD_SIZE = 5


# ---------------------------------------------------------------------------
# 1) Hellsichtiges Optimum (obere Schranke)
# ---------------------------------------------------------------------------

def clairvoyant(order, memo=None):
    """Maximaler Score fuer die feste Deck-Reihenfolge ``order`` (24 Ids).

    ACHTUNG ``memo``: Der Schluessel ist ``(position, feld)`` und enthaelt die
    Reihenfolge NICHT. Ein Speicher darf deshalb nur innerhalb EINER
    Reihenfolge wiederverwendet werden -- sonst liefert er Werte aus einem
    fremden Deck (von Codex 2026-09-08 an einem Gegenbeispiel gezeigt).
    Uebergibt man einen Speicher, wird die Reihenfolge darin vermerkt und bei
    Missbrauch ein Fehler ausgeloest, statt still falsch zu rechnen.
    """
    if memo is None:
        memo = {}
    order = tuple(order)
    gebunden = memo.setdefault('__order__', order)
    if gebunden != order:
        raise ValueError('Speicher gehoert zu einer anderen Deck-Reihenfolge')
    field = 0
    for cid in order[:FIELD_SIZE]:
        field |= 1 << cid
    return _cv(order, field, FIELD_SIZE, memo)


def _refill(order, field, pos):
    """Feld auf 5 auffuellen -> ``(feld, position)``."""
    n = FIELD_SIZE - popcount(field)
    while n > 0 and pos < len(order):
        field |= 1 << order[pos]
        pos += 1
        n -= 1
    return field, pos


def _cv(order, field, pos, memo):
    key = (pos, field)
    hit = memo.get(key)
    if hit is not None:
        return hit

    best = 0
    for cmask, punkte, _ids in playable(field):
        nf, np_ = _refill(order, field & ~cmask, pos)
        wert = punkte + _cv(order, nf, np_, memo)
        if wert > best:
            best = wert

    # Wegwerfen lohnt nur, solange nachgezogen werden kann: ohne Ersatz kann es
    # den Score nie erhoehen. Beweisbar verlustfreie Beschneidung -- und sie
    # garantiert die Terminierung (jede Aktion verbraucht eine Deck-Karte oder
    # verkleinert das Feld).
    if pos < len(order):
        rest = field
        while rest:
            bit = rest & -rest
            rest ^= bit
            nf, np_ = _refill(order, field & ~bit, pos)
            wert = _cv(order, nf, np_, memo)
            if wert > best:
                best = wert

    memo[key] = best
    return best


def clairvoyant_best_action(order, field, pos, memo=None):
    """Beste Aktion im Zustand -> ``('play'|'discard', maske, restwert)``."""
    if memo is None:
        memo = {}
    order = tuple(order)
    best = (None, 0, -1)
    for cmask, punkte, _ids in playable(field):
        nf, np_ = _refill(order, field & ~cmask, pos)
        wert = punkte + _cv(order, nf, np_, memo)
        if wert > best[2]:
            best = ('play', cmask, wert)
    if pos < len(order):
        rest = field
        while rest:
            bit = rest & -rest
            rest ^= bit
            nf, np_ = _refill(order, field & ~bit, pos)
            wert = _cv(order, nf, np_, memo)
            if wert > best[2]:
                best = ('discard', bit, wert)
    return best


# ---------------------------------------------------------------------------
# 2) Spielbare Strategien (kennen nur Feld + Rest-MENGE, nicht die Reihenfolge)
# ---------------------------------------------------------------------------

def legal_actions(field, deck_left):
    """Alle erlaubten Aktionen -> ``[('play', maske, punkte), ('discard', bit, 0)]``."""
    acts = [('play', m, p) for m, p, _i in playable(field)]
    if deck_left > 0:
        rest = field
        while rest:
            bit = rest & -rest
            rest ^= bit
            acts.append(('discard', bit, 0))
    return acts


def greedy_action(field, deck_mask, deck_left):
    """Immer die punktbeste Kombination; sonst die schwaechste Karte weg.

    Die Referenz-Strategie ("so spielt man intuitiv"). Der Wegwerf-Teil nutzt
    :func:`card_potential` -- ohne den waere der Vergleich unfair, weil eine
    zufaellige Wegwerf-Wahl fuer sich schon viel Score kostet.
    """
    p = playable(field)
    if p:
        return ('play', p[0][0], p[0][1])
    return ('discard', _worst_card_bit(field, deck_mask), 0)


def card_potential(cid, field, deck_mask):
    """Wie viel ist die Karte ``cid`` noch wert?

    Bewertet wird die beste Kombination, die mit ihr UEBERHAUPT noch zustande
    kommen kann (die beiden Partner duerfen im Feld oder im Rest-Deck liegen),
    abgezuegt eine kleine Strafe fuer jeden Partner, der erst noch gezogen
    werden muss. So schlaegt eine fast fertige 80-Punkte-Reihe eine
    theoretische 100er, fuer die noch zwei Karten fehlen.
    """
    bit = 1 << cid
    verfuegbar = field | deck_mask | bit
    best = 0.0
    # COMBOS_BY_CARD statt playable(): dieselbe Menge (alle Kombinationen mit
    # dieser Karte), aber VORBERECHNET -- rund 25 statt 170 Kandidaten, und vor
    # allem ohne den Zwischenspeicher zu beruehren.
    #
    # WARUM DAS WICHTIG IST (2026-09-08, am Absturz gemessen): Diese Funktion
    # fragte ``playable(feld | restdeck)`` ab, also mit GROSSEN Masken. Davon
    # gibt es Millionen verschiedene, sie wiederholen sich praktisch nie, und
    # jede legte bis zu 170 Kombinationen im Cache ab. Der wuchs dadurch
    # ungebremst: nach 300 Partien 1,4 Mio. Eintraege und 514 MB, danach stuerzte
    # der Interpreter ab. Der Cache soll nur FELD-Masken sehen (hoechstens 5
    # Karten, also 55.455 moegliche) -- die wiederholen sich staendig.
    for cmask, punkte, _ids in COMBOS_BY_CARD[cid]:
        if cmask & verfuegbar != cmask:
            continue                            # Partner fehlt endgueltig
        fehlend = popcount(cmask & ~field)      # Partner, die nicht im Feld sind
        wert = punkte - 12.0 * (fehlend - 1)    # -1: die Karte selbst
        if wert > best:
            best = wert
    return best


def _worst_card_bit(field, deck_mask):
    """Bit der Karte mit dem geringsten Restwert."""
    schlechteste, wert = None, None
    rest = field
    while rest:
        bit = rest & -rest
        rest ^= bit
        cid = bit.bit_length() - 1
        w = card_potential(cid, field & ~bit, deck_mask)
        if wert is None or w < wert:
            schlechteste, wert = bit, w
    return schlechteste


def threshold_action(field, deck_mask, deck_left, budget, schwelle):
    """Wie ``greedy``, aber eine schwache Kombination wird ausgelassen.

    ``budget`` = wie viele Kombinationen zeitlich ueberhaupt noch passen
    (``(deck_left + |feld|) // 3``). Ist das Budget knapp, wird JEDE
    Kombination genommen -- am Ende zaehlt jeder Zug. Ist noch Luft, wird eine
    Kombination unter ``schwelle`` uebersprungen und stattdessen die
    schwaechste Karte entsorgt.
    """
    p = playable(field)
    if not p:
        return ('discard', _worst_card_bit(field, deck_mask), 0)
    beste = p[0]
    if deck_left == 0 or budget <= 1 or beste[1] >= schwelle:
        return ('play', beste[0], beste[1])
    return ('discard', _worst_card_bit(field, deck_mask), 0)


def pimc_action(field, deck_mask, samples=24, rng=None, top_k=None):
    """Stichproben-Suche: den bekannten Deck-Rest mehrfach mischen.

    Fuer jede gemischte Reihenfolge wird jede Kandidaten-Aktion hellsichtig
    zu Ende gerechnet; gewaehlt wird die Aktion mit dem besten MITTELWERT.
    Das ist die staerkste hier praktikable Strategie: die Karten-MENGE ist dem
    Spieler ohnehin bekannt (Kartenzaehlen), unbekannt ist nur die Reihenfolge
    -- und genau ueber die wird hier gemittelt.

    ``top_k`` beschraenkt die Kandidaten auf die k aussichtsreichsten Aktionen
    (spart Rechenzeit, ohne die Auswahl praktisch zu aendern).
    """
    if rng is None:
        rng = random
    deck = [i for i in range(24) if deck_mask & (1 << i)]
    kandidaten = legal_actions(field, len(deck))
    if len(kandidaten) == 1:
        return kandidaten[0]
    if top_k and len(kandidaten) > top_k:
        kandidaten = _shortlist(kandidaten, field, deck_mask, top_k)

    summe = [0] * len(kandidaten)
    for _ in range(samples):
        order = list(deck)
        rng.shuffle(order)
        # Reihenfolge kuenstlich vorne um das Feld ergaenzen: die DP zieht ab
        # ``pos``; das Feld ist bereits gesetzt, also beginnt das Deck bei 0.
        memo = {}
        seq = tuple(order)
        for i, (art, maske, punkte) in enumerate(kandidaten):
            nf, np_ = _refill(seq, field & ~maske, 0)
            summe[i] += punkte + _cv(seq, nf, np_, memo)
    beste = max(range(len(kandidaten)), key=lambda i: summe[i])
    return kandidaten[beste]


def _shortlist(kandidaten, field, deck_mask, k):
    """Die k aussichtsreichsten Aktionen (Punkte bzw. Restwert als Rangmass)."""
    def rang(a):
        art, maske, punkte = a
        if art == 'play':
            return (1, punkte)
        cid = maske.bit_length() - 1
        return (0, -card_potential(cid, field & ~maske, deck_mask))
    return sorted(kandidaten, key=rang, reverse=True)[:k]


# ---------------------------------------------------------------------------
# 3) Rollout-Strategie -- die praktikable Naeherung ans Optimum
# ---------------------------------------------------------------------------

def rollout_action(field, deck_mask, base_policy, rollouts=16, rng=None,
                   top_k=8):
    """Jede Kandidaten-Aktion mehrfach zu Ende SPIELEN und mitteln.

    Unterschied zu :func:`pimc_action`: dort wird jede Stichprobe hellsichtig
    OPTIMAL zu Ende gerechnet (teuer, ~100 ms), hier wird sie mit einer
    schnellen Grundstrategie zu Ende GESPIELT (~0,15 ms) -- billig genug, um
    auf genug Deals gemessen zu werden.

    ZUR GARANTIE, ehrlich: Der klassische Satz "Rollout ist mindestens so gut
    wie die Grundstrategie" gilt fuer EXAKTE Erwartungswerte. Hier werden
    endliche Stichproben maximiert; ein Stichprobenfehler kann eine schlechtere
    Aktion nach vorne bringen, und ``top_k`` kann die Basis-Aktion sogar ganz
    ausschliessen. Es ist also eine Heuristik ohne Garantie -- gemessen wirkt
    sie (281,7 -> 304,0 bei 24 Stichproben), bewiesen ist sie nicht.
    (Von Codex 2026-09-08 zu Recht angemahnt.)

    Der Zufall steckt nur in der REIHENFOLGE des Rest-Decks; seine
    Zusammensetzung ist bekannt (Kartenzaehlen) und wird exakt benutzt.
    """
    if rng is None:
        rng = random
    deck = [i for i in range(24) if deck_mask & (1 << i)]
    kandidaten = legal_actions(field, len(deck))
    if len(kandidaten) == 1:
        return kandidaten[0]
    if top_k and len(kandidaten) > top_k:
        kandidaten = _shortlist(kandidaten, field, deck_mask, top_k)

    summe = [0] * len(kandidaten)
    for _ in range(rollouts):
        order = list(deck)
        rng.shuffle(order)
        for i, (art, maske, punkte) in enumerate(kandidaten):
            summe[i] += punkte + _rollout(field & ~maske, order, base_policy)
    beste = max(range(len(kandidaten)), key=lambda i: summe[i])
    return kandidaten[beste]


def _rollout(field, order, base_policy):
    """Ab ``field`` mit ``order`` als Rest-Deck zu Ende spielen -> Punkte."""
    pos = 0
    n = FIELD_SIZE - popcount(field)
    while n > 0 and pos < len(order):
        field |= 1 << order[pos]
        pos += 1
        n -= 1
    score = 0
    while True:
        deck_left = len(order) - pos
        if deck_left == 0 and not playable(field):
            return score
        deck_mask = 0
        for cid in order[pos:]:
            deck_mask |= 1 << cid
        art, maske, punkte = base_policy(field, deck_mask, deck_left)
        field &= ~maske
        if art == 'play':
            score += punkte
        n = FIELD_SIZE - popcount(field)
        while n > 0 and pos < len(order):
            field |= 1 << order[pos]
            pos += 1
            n -= 1


def base_greedy(field, deck_mask, deck_left):
    """Grundstrategie fuer die Rollouts: schnell, ohne eigene Stichproben."""
    return greedy_action(field, deck_mask, deck_left)


def make_base_threshold(schwelle):
    """Grundstrategie mit fester Mindestpunktzahl."""
    def base(field, deck_mask, deck_left):
        budget = (deck_left + popcount(field)) // 3
        return threshold_action(field, deck_mask, deck_left, budget, schwelle)
    return base


# ---------------------------------------------------------------------------
# 4) Netto-Regel -- die beste Strategie OHNE Simulation
# ---------------------------------------------------------------------------

def smart_action(field, deck_mask, deck_left, alpha=0.35, endspiel=3):
    """Kombination nur nehmen, wenn sie mehr bringt als die Karten noch wert sind.

    Der Kern des Spiels in einer Zeile: eine Kombination kostet DREI Karten.
    Eine gemischte 6-7-8 bringt 60 Punkte und verbrennt dabei genau die drei
    Karten, aus denen eine farbreine 6-7-8 mit 100 Punkten haette werden
    koennen. Deshalb wird von den Punkten der Restwert der verbrauchten Karten
    abgezogen (``card_potential``, gewichtet mit ``alpha``) und mit der
    Alternative "schwaechste Karte wegwerfen" verglichen.

    ``alpha`` = wie stark der Restwert zaehlt; 0,35 ist der auf 300 Deals
    gemessene Bestwert (281,7 Punkte gegen 265,7 der gierigen Strategie).
    Sobald das Deck fast leer ist (``deck_left <= endspiel``), wird jede
    Kombination genommen -- dann gibt es keine Zukunft mehr zu schonen.
    """
    p = playable(field)
    if not p:
        return ('discard', _worst_card_bit(field, deck_mask), 0)
    if deck_left <= endspiel:
        return ('play', p[0][0], p[0][1])

    bester, bestwert = None, None
    for cmask, punkte, _ids in p:
        kosten = 0.0
        rest = cmask
        while rest:
            bit = rest & -rest
            rest ^= bit
            cid = bit.bit_length() - 1
            kosten += card_potential(cid, field & ~bit, deck_mask)
        netto = punkte - alpha * kosten
        if bestwert is None or netto > bestwert:
            bester, bestwert = (cmask, punkte), netto

    wbit = _worst_card_bit(field, deck_mask)
    wcid = wbit.bit_length() - 1
    wegwerf_netto = -alpha * card_potential(wcid, field & ~wbit, deck_mask)
    if bestwert >= wegwerf_netto:
        return ('play', bester[0], bester[1])
    return ('discard', wbit, 0)


def make_base_smart(alpha=0.35):
    """Die Netto-Regel als Grundstrategie fuer Rollouts."""
    def base(field, deck_mask, deck_left):
        return smart_action(field, deck_mask, deck_left, alpha=alpha)
    return base
