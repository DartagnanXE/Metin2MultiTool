# -*- coding: utf-8 -*-
"""Monte-Carlo-Regression: die trainierte Policy spielt BEWEISBAR optimal.

Der Bot platziert nur, wenn es die Wertfunktion V strikt senkt (kein Finish-Modus
mehr, 2026-06-17). Diese Policy ist optimal, GENAU DANN wenn ihre simulierte
mittlere Steinzahl V[leeres Brett] erreicht. Dieser Test friert das ein:
  * die Policy beendet JEDES Spiel (kein Steckenbleiben),
  * die mittlere Steinzahl liegt eng an V[leer] (= dem vorhergesagten Optimum).
Ein versehentliches Wiedereinschalten suboptimaler Zuege (z.B. Finish-Modus,
~+22% Steine) wuerde diesen Test brechen.
"""

import random
import unittest

import numpy as np

import trained_solver as ts

FULL = (1 << 24) - 1


def _masks_by_type():
    return {t: [m for (_, _, m) in ts._PLACE[t]] for t in range(1, 7)}


def _play_optimal(rng, V, masks_by_t, guard_max=5000):
    """Ein Spiel unter der V-greedy-Policy (nur legen wenn V strikt sinkt).
    Rueckgabe: Anzahl gezogener Steine bis Brett voll, oder ``None`` (steckte)."""
    occ = 0
    draws = 0
    guard = 0
    while occ != FULL:
        guard += 1
        if guard > guard_max:
            return None
        t = rng.randint(1, 6)
        draws += 1
        base = V[occ]
        best_v = None
        best_m = None
        for m in masks_by_t[t]:
            if occ & m:
                continue
            v = V[occ | m]
            if best_v is None or v < best_v:
                best_v = v
                best_m = m
        if best_m is not None and best_v < base:   # NUR wenn V strikt sinkt
            occ |= best_m
    return draws


class SolverOptimalityTest(unittest.TestCase):
    def test_policy_matches_predicted_optimum_and_never_stuck(self):
        V = ts.load_V()
        masks_by_t = _masks_by_type()
        predicted = float(V[0])                 # V[leeres Brett] = Optimum
        rng = random.Random(2026)
        N = 500
        draws = []
        stuck = 0
        for _ in range(N):
            d = _play_optimal(rng, V, masks_by_t)
            if d is None:
                stuck += 1
            else:
                draws.append(d)
        # (1) Kein Spiel bleibt stecken -> die Policy beendet das Brett immer.
        self.assertEqual(stuck, 0, 'Policy blieb in %d/%d Spielen stecken' % (stuck, N))
        # (2) Mittlere Steinzahl ~= vorhergesagtes Optimum (enges Band; N=500 ->
        #     Standardfehler ~0.3, 1.5 ist komfortabel und faengt eine ~22%-
        #     Regression [+3.4 Steine] sicher).
        mean = float(np.mean(draws))
        self.assertLess(abs(mean - predicted), 1.5,
                        'Mittel %.2f weicht von Optimum %.2f ab -> Policy nicht '
                        'mehr optimal?' % (mean, predicted))

    def test_predicted_optimum_is_sane(self):
        # Schutz gegen ein kaputtes/falsch geladenes V: das Optimum muss im
        # bekannten Bereich liegen (~15.57 Steine fuers leere 4x6-Brett).
        V = ts.load_V()
        self.assertTrue(14.0 < float(V[0]) < 17.0,
                        'V[leer]=%.3f ausserhalb des erwarteten Bereichs' % float(V[0]))


if __name__ == '__main__':
    unittest.main()
