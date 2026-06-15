# -*- coding: utf-8 -*-
"""Reine Rechen-Hilfen des Energiesplitter-Moduls (kein IO, keine Vision).

Nach dem Umbau 2026-06-16 ist die Mechanik fix und braucht KEINE Yang-Rechnung
und KEINEN greedy Stack-Plan mehr:

- Aktion 1 kauft IMMER 200er-Stacks, ``stack_count`` (X) mal.
- Aktion 2 verarbeitet Dolche EINZELN NACHEINANDER (1 Hammer + 1 Dolch je Drag).

Es verbleibt nur ein winziger, wurffester Helfer fuer das Clampen von
nicht-negativen ganzen Zahlen (von der View/dem Bot wiederverwendet). Der frueher
hier lebende Yang-Rechner (``plan_hammer_yang``) und der Stack-Greedy
(``plan_stack_purchase``) wurden mit dem Yang-Konzept ersatzlos entfernt.
"""


def clamp_nonneg_int(value):
  """Wandelt ``value`` in ein int >= 0 (nicht-Zahl/negativ/0 -> 0). Wirft nie."""
  try:
    n = int(value)
  except (TypeError, ValueError):
    return 0
  return n if n > 0 else 0
