# -*- coding: utf-8 -*-
"""Aus dem Verhalten der starken Strategie einfache Regeln ableiten.

Zweck: Die Rollout-/PIMC-Strategie ist stark, aber als Handlungsanweisung fuer
einen Menschen unbrauchbar ("simuliere 24 Partien pro Klick"). Hier wird
protokolliert, WAS die starke Strategie in welcher Lage tut -- und daraus
werden die Faustregeln abgelesen, die ein Mensch am Bildschirm anwenden kann.

Aufruf:  python3 -m okey.derive_rules [anzahl_deals]
"""

import random
import sys
from collections import Counter, defaultdict

from .combos import card_of, playable, popcount
from .evaluate import deal
from .solver import (FIELD_SIZE, base_greedy, card_potential, rollout_action)


def combo_type(mask):
    """``'drilling' | 'farbrein' | 'gemischt'`` einer Kombinations-Maske."""
    ids = [i for i in range(24) if mask & (1 << i)]
    werte = sorted(card_of(i)[0] for i in ids)
    farben = set(card_of(i)[1] for i in ids)
    if werte[0] == werte[2]:
        return 'drilling'
    return 'farbrein' if len(farben) == 1 else 'gemischt'


def trace(order, policy_action):
    """Ein Spiel protokollieren -> Liste von Entscheidungs-Datensaetzen."""
    field = 0
    for cid in order[:FIELD_SIZE]:
        field |= 1 << cid
    pos = FIELD_SIZE
    sätze = []
    while True:
        deck_left = len(order) - pos
        if deck_left == 0 and not playable(field):
            break
        deck_mask = 0
        for cid in order[pos:]:
            deck_mask |= 1 << cid
        moeglich = playable(field)
        beste = moeglich[0][1] if moeglich else 0
        art, maske, punkte = policy_action(field, deck_mask, deck_left)
        sätze.append({
            'deck_left': deck_left,
            'beste_moeglich': beste,
            'beste_typ': combo_type(moeglich[0][0]) if moeglich else None,
            'art': art,
            'punkte': punkte,
            'typ': combo_type(maske) if art == 'play' else None,
            'weggeworfen': (card_of(maske.bit_length() - 1)
                            if art == 'discard' else None),
            'feld': [card_of(i) for i in range(24) if field & (1 << i)],
            'deck_mask': deck_mask,
            'field_mask': field,
        })
        field &= ~maske
        n = FIELD_SIZE - popcount(field)
        while n > 0 and pos < len(order):
            field |= 1 << order[pos]
            pos += 1
            n -= 1
    return sätze


def main(n_deals=120, rollouts=24, seed=42):
    rng = random.Random(seed)
    prng = random.Random(seed + 1)

    def policy(field, deck_mask, deck_left):
        return rollout_action(field, deck_mask, base_greedy,
                              rollouts=rollouts, rng=prng, top_k=8)

    alle = []
    for i in range(n_deals):
        alle.extend(trace(deal(rng), policy))
        if (i + 1) % 20 == 0:
            print('  %d/%d Deals' % (i + 1, n_deals), flush=True)

    print('\n=== 1. Wann wird eine spielbare Kombination GENOMMEN? ===')
    print('%-8s %-10s %-10s %-10s' % ('Wert', 'genommen', 'ausgelassen', 'Quote'))
    nach_wert = defaultdict(lambda: [0, 0])
    for s in alle:
        if s['beste_moeglich'] == 0:
            continue
        nach_wert[s['beste_moeglich']][0 if s['art'] == 'play' else 1] += 1
    for wert in sorted(nach_wert):
        g, a = nach_wert[wert]
        print('%-8d %-10d %-10d %5.1f%%' % (wert, g, a, 100 * g / max(1, g + a)))

    print('\n=== 2. Dasselbe, aufgeteilt nach Rest-Deck ===')
    print('%-8s %-14s %-14s %-14s' % ('Wert', 'Deck>=12', 'Deck 6-11', 'Deck<=5'))
    buckets = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for s in alle:
        if s['beste_moeglich'] == 0:
            continue
        b = 'hoch' if s['deck_left'] >= 12 else (
            'mittel' if s['deck_left'] >= 6 else 'niedrig')
        buckets[s['beste_moeglich']][b][0 if s['art'] == 'play' else 1] += 1
    for wert in sorted(buckets):
        z = []
        for b in ('hoch', 'mittel', 'niedrig'):
            g, a = buckets[wert][b]
            z.append('%5.1f%% (%d)' % (100 * g / max(1, g + a), g + a))
        print('%-8d %-14s %-14s %-14s' % (wert, z[0], z[1], z[2]))

    print('\n=== 3. Welche Kombinations-TYPEN werden gespielt? ===')
    typen = Counter(s['typ'] for s in alle if s['art'] == 'play')
    gesamt = sum(typen.values())
    for t, n in typen.most_common():
        print('  %-10s %5d  (%4.1f%%)' % (t, n, 100 * n / gesamt))

    print('\n=== 4. Welche Karten werden weggeworfen? ===')
    weg = Counter(s['weggeworfen'][0] for s in alle if s['art'] == 'discard')
    ges = sum(weg.values())
    print('  nach Kartenwert:')
    for v in range(1, 9):
        print('    Wert %d: %4d  (%4.1f%%)' % (v, weg[v], 100 * weg[v] / max(1, ges)))

    print('\n=== 5. Wegwurf: hatte die Karte noch Partner? ===')
    mit, ohne = 0, 0
    for s in alle:
        if s['art'] != 'discard':
            continue
        cid = None
        for i in range(24):
            if s['field_mask'] & (1 << i) and card_of(i) == s['weggeworfen']:
                cid = i
                break
        if cid is None:
            continue
        pot = card_potential(cid, s['field_mask'] & ~(1 << cid), s['deck_mask'])
        if pot >= 70:
            mit += 1
        else:
            ohne += 1
    print('  weggeworfen mit Restwert >=70: %d (%.1f%%)'
          % (mit, 100 * mit / max(1, mit + ohne)))
    print('  weggeworfen mit Restwert  <70: %d (%.1f%%)'
          % (ohne, 100 * ohne / max(1, mit + ohne)))

    print('\n=== 6. Zuege pro Spiel ===')
    plays = sum(1 for s in alle if s['art'] == 'play')
    discs = sum(1 for s in alle if s['art'] == 'discard')
    print('  Kombinationen: %.2f/Spiel   Wegwuerfe: %.2f/Spiel'
          % (plays / n_deals, discs / n_deals))


if __name__ == '__main__':
    main(n_deals=int(sys.argv[1]) if len(sys.argv) > 1 else 120)
