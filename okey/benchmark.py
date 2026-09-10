# -*- coding: utf-8 -*-
"""Alle Strategien auf denselben Deals messen (gemeinsame Zufallszahlen).

Aufruf:  python3 -m okey.benchmark [anzahl_deals]

Ausgabe: Tabelle mit Mittelwert, Median, Streuung und -- der eigentlich
interessanten Zahl -- dem Anteil der Spiele, die Gold (>=400) bzw. mindestens
Silber (>=300) erreichen. Dazu das hellsichtige Optimum als obere Schranke.
"""

import random
import sys
import time

from .evaluate import (deal, format_table, make_pimc, make_threshold,
                       play_game, policy_greedy, summarize)
from .solver import (base_greedy, clairvoyant, legal_actions,
                     make_base_threshold, rollout_action)


def make_rollout(rollouts, base=None, seed=0, top_k=8):
    rng = random.Random(seed)
    base = base or base_greedy

    def policy(field, deck_mask, deck_left, budget):
        return rollout_action(field, deck_mask, base, rollouts=rollouts,
                              rng=rng, top_k=top_k)
    policy.__name__ = 'rollout_%d' % rollouts
    return policy


def make_random(seed=0):
    rng = random.Random(seed)

    def policy(field, deck_mask, deck_left, budget):
        return rng.choice(legal_actions(field, deck_left))
    return policy


def main(n_games=200, pimc_games=40, seed=1):
    rng = random.Random(seed)
    deals = [deal(rng) for _ in range(n_games)]

    tests = [
        ('zufaellig (Boden)', make_random(2), n_games),
        ('gierig (best. Kombi)', policy_greedy, n_games),
        ('Schwelle 50', make_threshold(50), n_games),
        ('Schwelle 60', make_threshold(60), n_games),
        ('Schwelle 70', make_threshold(70), n_games),
        ('Rollout 8 (Basis gierig)', make_rollout(8, seed=5), n_games),
        ('Rollout 24 (Basis gierig)', make_rollout(24, seed=6), n_games),
        ('Rollout 24 (Basis S60)',
         make_rollout(24, base=make_base_threshold(60), seed=7), n_games),
        ('PIMC 16 (hellsichtige Stichp.)', make_pimc(16, seed=8), pimc_games),
    ]

    ergebnis = {}
    for name, policy, n in tests:
        t0 = time.perf_counter()
        scores = [play_game(o, policy)[0] for o in deals[:n]]
        dt = time.perf_counter() - t0
        ergebnis[name] = summarize(scores)
        ergebnis[name]['sek_pro_spiel'] = dt / n
        print('  %-32s fertig (%d Deals, %.3f s/Spiel)' % (name, n, dt / n),
              flush=True)

    t0 = time.perf_counter()
    cv = [clairvoyant(o) for o in deals]
    ergebnis['OPTIMUM (hellsichtig)'] = summarize(cv)
    ergebnis['OPTIMUM (hellsichtig)']['sek_pro_spiel'] = \
        (time.perf_counter() - t0) / n_games
    print('  %-32s fertig' % 'OPTIMUM (hellsichtig)', flush=True)

    print()
    print(format_table(ergebnis))
    print()
    print('Hinweis: PIMC laeuft auf weniger Deals (Rechenzeit) -- sein '
          'Mittelwert ist\ndeshalb ungenauer; der Standardfehler steht unten.')
    print()
    for name, k in sorted(ergebnis.items(), key=lambda t: -t[1]['mittel']):
        print('%-32s Mittel %6.1f +- %4.1f (n=%d, %.4f s/Spiel)'
              % (name, k['mittel'], k['stdfehler'], k['n'],
                 k.get('sek_pro_spiel', 0)))
    return ergebnis


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    main(n_games=n)
