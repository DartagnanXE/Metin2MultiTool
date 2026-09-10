# -*- coding: utf-8 -*-
"""Strategien auf denselben Deals gegeneinander messen.

Alle Strategien laufen ueber die IDENTISCHEN gemischten Decks (gemeinsame
Zufallszahlen). Das entfernt den groessten Teil der Streuung aus dem Vergleich:
Unterschiede stammen dann aus der Strategie, nicht aus dem Kartenglueck. Auf
denselben Deals laeuft auch das hellsichtige Optimum -- daraus wird die Luecke
"Strategie gegen bestmoeglich" direkt ablesbar.
"""

import random

from .combos import popcount
from .solver import (FIELD_SIZE, clairvoyant, greedy_action, pimc_action,
                     playable, threshold_action)

FULL_MASK = (1 << 24) - 1


def deal(rng):
    """Eine gemischte Deck-Reihenfolge (24 Karten-Ids)."""
    order = list(range(24))
    rng.shuffle(order)
    return order


def play_game(order, policy):
    """Ein Durchgang mit ``policy`` -> ``(score, zuege, kombinationen)``.

    ``policy(field, deck_mask, deck_left, budget)`` liefert
    ``(art, maske, punkte)``. ``deck_mask`` ist die Menge der noch im Deck
    liegenden Karten -- genau das, was ein Kartenzaehler weiss.
    """
    field = 0
    pos = 0
    for cid in order[:FIELD_SIZE]:
        field |= 1 << cid
    pos = FIELD_SIZE

    score, zuege, kombis = 0, 0, 0
    while True:
        deck_left = len(order) - pos
        if deck_left == 0 and not playable(field):
            break
        deck_mask = 0
        for cid in order[pos:]:
            deck_mask |= 1 << cid
        budget = (deck_left + popcount(field)) // 3
        art, maske, punkte = policy(field, deck_mask, deck_left, budget)
        field &= ~maske
        if art == 'play':
            score += punkte
            kombis += 1
        zuege += 1
        # nachziehen
        n = FIELD_SIZE - popcount(field)
        while n > 0 and pos < len(order):
            field |= 1 << order[pos]
            pos += 1
            n -= 1
        if zuege > 200:                     # Reissleine, darf nie greifen
            raise RuntimeError('Endlosschleife in play_game')
    return score, zuege, kombis


# -- Strategien als Policy-Funktionen ---------------------------------------

def policy_greedy(field, deck_mask, deck_left, budget):
    return greedy_action(field, deck_mask, deck_left)


def make_threshold(schwelle):
    def policy(field, deck_mask, deck_left, budget):
        return threshold_action(field, deck_mask, deck_left, budget, schwelle)
    policy.__name__ = 'schwelle_%d' % schwelle
    return policy


def make_pimc(samples, seed=0, top_k=6):
    rng = random.Random(seed)

    def policy(field, deck_mask, deck_left, budget):
        return pimc_action(field, deck_mask, samples=samples, rng=rng,
                           top_k=top_k)
    policy.__name__ = 'pimc_%d' % samples
    return policy


def policy_random(field, deck_mask, deck_left, budget, rng=random):
    from .solver import legal_actions
    return rng.choice(legal_actions(field, deck_left))


# -- Auswertung -------------------------------------------------------------

def summarize(scores):
    """Kennzahlen einer Score-Liste."""
    n = len(scores)
    s = sorted(scores)
    mittel = sum(scores) / n
    # Median bei GERADEM n als Mittel der beiden mittleren Werte -- die
    # Kurzform s[n//2] liefert dort den oberen Wert (Codex-Pruefung 2026-09-08:
    # summarize([100, 200]) gab 200 statt 150).
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {
        'n': n,
        'mittel': mittel,
        'median': median,
        'min': s[0],
        'max': s[-1],
        'p_gold': sum(1 for x in scores if x >= 400) / n,
        'p_silber_plus': sum(1 for x in scores if x >= 300) / n,
        'stdfehler': (sum((x - mittel) ** 2 for x in scores) / (n - 1) / n) ** 0.5
        if n > 1 else 0.0,
    }


def run(policies, n_games=200, seed=1, with_upper_bound=True):
    """Alle Strategien auf denselben ``n_games`` Deals laufen lassen.

    :return: ``{name: kennzahlen}`` -- inklusive ``'OPTIMUM (hellsichtig)'``,
        wenn ``with_upper_bound``.
    """
    rng = random.Random(seed)
    deals = [deal(rng) for _ in range(n_games)]
    ergebnis = {}
    for name, policy in policies:
        scores = [play_game(order, policy)[0] for order in deals]
        ergebnis[name] = summarize(scores)
    if with_upper_bound:
        ergebnis['OPTIMUM (hellsichtig)'] = summarize(
            [clairvoyant(order) for order in deals])
    return ergebnis


def format_table(ergebnis):
    """Ergebnis als Textblock."""
    kopf = ('%-26s %7s %7s %6s %6s %8s %8s' %
            ('Strategie', 'Mittel', 'Median', 'Min', 'Max',
             'P(Gold)', 'P(>=300)'))
    zeilen = [kopf, '-' * len(kopf)]
    for name, k in sorted(ergebnis.items(), key=lambda t: -t[1]['mittel']):
        zeilen.append('%-26s %7.1f %7.0f %6.0f %6.0f %7.1f%% %7.1f%%' % (
            name, k['mittel'], k['median'], k['min'], k['max'],
            100 * k['p_gold'], 100 * k['p_silber_plus']))
    return '\n'.join(zeilen)
