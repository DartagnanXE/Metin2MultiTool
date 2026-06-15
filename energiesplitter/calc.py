# -*- coding: utf-8 -*-
"""Reine Rechen-Logik des Energiesplitter-Moduls (kein IO, keine Vision).

Zwei Funktionen, beide rein und wurffest (Contract §6):

- ``plan_hammer_yang(hammer_count, price_per_item)`` -- Yang-Aufschluesselung
  fuer den Live-Rechner der UI (Hammer + Dolche 1:1 + Summe).
- ``plan_stack_purchase(target_count, free_slots, stack_sizes)`` -- greedy
  Stack-Auswahl fuer den Hammerkauf (groesste Stacks zuerst; kleinere nur, um
  die Zielzahl exakt zu treffen oder in den freien Platz zu passen).

Die UI ruft ausschliesslich diese Funktionen -- KEINE Rechen-Logik in der View.
"""


def _clamp_nonneg_int(value):
  """Wandelt ``value`` in ein int >= 0 (nicht-Zahl/negativ/0 -> 0). Wirft nie."""
  try:
    n = int(value)
  except (TypeError, ValueError):
    return 0
  return n if n > 0 else 0


def plan_hammer_yang(hammer_count, price_per_item):
  """Yang-Aufschluesselung fuer den Live-Rechner (Addendum A3).

  Eingabe = ANZAHL Hammer. Pro Hammer wird 1 Dolch zum gleichen Preis gekauft
  (1:1-Verarbeitung), daher ``dagger_yang == hammer_yang`` und
  ``total_yang == hammer_count * 2 * price_per_item``.

  Negative/0/nicht-Zahl-Eingaben werden auf 0 geklemmt; die Funktion wirft nie
  und liefert immer das vollstaendige Dict mit int-Werten.
  """
  n = _clamp_nonneg_int(hammer_count)
  price = _clamp_nonneg_int(price_per_item)
  per_kind = n * price
  return {
    'hammer_count': n,
    'price_per_item': price,
    'hammer_yang': per_kind,
    'dagger_yang': per_kind,
    'total_yang': n * 2 * price,
  }


def plan_stack_purchase(target_count, free_slots, stack_sizes=(200, 50, 1)):
  """Greedy Stack-Auswahl fuer den Hammerkauf.

  Liefert die Liste der zu kaufenden Stack-Groessen (groesste zuerst), so dass:

  - die Summe der gewaehlten Stacks <= ``target_count`` (nie ueber Bedarf), und
  - die Anzahl gewaehlter Stacks <= ``free_slots`` (jeder Stack kann einen neuen
    Inventarplatz belegen -- konservativ: jeder zaehlt gegen den freien Platz).

  Kleinere Stacks werden nur genutzt, um den verbleibenden Rest exakt
  aufzufuellen / in den Platz zu passen. ``target_count <= 0`` oder
  ``free_slots <= 0`` -> ``[]``. Wirft nie.

  WICHTIG: Der Caller uebergibt die zur LAUFZEIT GELESENEN Stack-Groessen
  (``read_shop_stack``), NICHT die Annahme. Der Default ``(200, 50, 1)``
  spiegelt die echten Hammer-Shop-Stacks (Addendum A1: 1/50/200) und ist ein
  Fallback, falls keine Groessen gelesen wurden.
  """
  target = _clamp_nonneg_int(target_count)
  slots = _clamp_nonneg_int(free_slots)
  if target <= 0 or slots <= 0:
    return []

  # Eingabe-Groessen saeubern: positive ints, absteigend, dedupliziert.
  sizes = []
  seen = set()
  for raw in stack_sizes or ():
    size = _clamp_nonneg_int(raw)
    if size > 0 and size not in seen:
      seen.add(size)
      sizes.append(size)
  if not sizes:
    return []
  sizes.sort(reverse=True)

  chosen = []
  remaining = target
  for size in sizes:
    while size <= remaining and len(chosen) < slots:
      chosen.append(size)
      remaining -= size
    if remaining <= 0 or len(chosen) >= slots:
      break
  return chosen
