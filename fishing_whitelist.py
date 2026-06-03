# -*- coding: utf-8 -*-
"""Reine Entscheidungs-Logik der Angel-Whitelist: "Soll dieser Biss behalten
oder das Minispiel abgebrochen werden?"

Zwei Eingaben -> EINE Entscheidung:

  * ein :class:`fishing_chat.HookResult` (WAS haengt am Haken -- Fisch/Item/Niete/
    nichts, Name, ``confident``), und
  * eine ``states``-Abbildung ``{name: zustand}`` mit den Inventar-3-Zustaenden
    (:data:`KEEP` / :data:`REMOVE` / :data:`CAMPFIRE`) -- dieselben drei Zustaende
    wie in :mod:`interface.inventory_manage`. Der Schluessel ist der offizielle
    DE-Anzeigename (das, was :func:`fishing_chat.read_hook` als ``name`` liefert).

Regel (Spec):

  * aktiv  (KEEP)     -> angeln  (behalten),
  * Feuer  (CAMPFIRE) -> angeln  (man WILL den Fisch, nur grillt man ihn danach),
  * grau   (REMOVE)   -> ABBRECHEN  (unerwuenscht),
  * NIETE             -> ABBRECHEN  (nichts Verwertbares),
  * nichts/unsicher (kind=NONE oder ``confident=False`` oder Name unbekannt)
    -> WEITERANGELN. Lieber einen unerwuenschten Fisch mitnehmen als versehentlich
    einen gewollten abbrechen.

Die Whitelist ist nur aktiv, wenn der Aufrufer ``enabled=True`` setzt. Ist sie
aus (Default), wird IMMER weitergeangelt -> byte-stabil zum bisherigen Verhalten.

Wie der restliche Bestandscode wirft hier NICHTS: jede Stufe faellt defensiv auf
:data:`KEEP_FISHING` (weiterangeln) zurueck.
"""

# Inventar-Zustaende -- 1:1 zu interface.inventory_manage (hier lokal gespiegelt,
# damit dieses Modul toolkit-/Tk-frei und ueberall importierbar bleibt; bei
# Abweichung wuerde der Import unten den Wert ohnehin angleichen).
KEEP, REMOVE, CAMPFIRE = 0, 1, 2

# Entscheidungs-Ergebnisse (reine Sentinels).
KEEP_FISHING = 'keep_fishing'   # normal weiterfischen / Minispiel zuende spielen
ABORT = 'abort'                 # Minispiel abbrechen + neu auswerfen


# Lazy import der WAHREN Konstanten/Typen aus dem Bestandscode -- defensiv, damit
# headless / ohne das interface-Paket nichts bricht (dann gelten die lokalen
# Spiegel-Werte oben).
try:                                    # pragma: no cover - reiner Import-Guard
    from interface.inventory_manage import (
        KEEP as _IM_KEEP, REMOVE as _IM_REMOVE, CAMPFIRE as _IM_CAMPFIRE)
    KEEP, REMOVE, CAMPFIRE = _IM_KEEP, _IM_REMOVE, _IM_CAMPFIRE
except Exception:                       # pragma: no cover
    pass

try:
    import fishing_chat as _fc
    _FISH, _ITEM, _NIETE, _NONE, _UNKNOWN = (
        _fc.FISH, _fc.ITEM, _fc.NIETE, _fc.NONE, _fc.UNKNOWN)
except Exception:                       # pragma: no cover - standalone
    _FISH, _ITEM, _NIETE, _NONE, _UNKNOWN = (
        'fish', 'item', 'niete', 'none', 'UNKNOWN')


def decide(result, states=None, enabled=False):
    """Whitelist-Entscheidung fuer einen Biss. Wirft NIE.

    Parameter:
      * ``result``  -- ein :class:`fishing_chat.HookResult` (oder ein beliebiges
        Objekt mit ``kind`` / ``name`` / ``confident``).
      * ``states``  -- ``{DE-Name: KEEP|REMOVE|CAMPFIRE}`` (z.B. aus der Inventar-
        Verwaltung). Fehlt ein Name, gilt er als KEEP (behalten).
      * ``enabled`` -- nur ``True`` schaltet die Whitelist scharf; sonst IMMER
        :data:`KEEP_FISHING` (byte-stabil).

    Rueckgabe: :data:`ABORT` (Minispiel abbrechen) oder :data:`KEEP_FISHING`
    (weiterfischen). Im Zweifel IMMER :data:`KEEP_FISHING`.
    """
    try:
        if not enabled or result is None:
            return KEEP_FISHING

        kind = getattr(result, 'kind', _NONE)

        # NIETE -> es gibt nichts -> abbrechen + neu auswerfen.
        if kind == _NIETE:
            return ABORT

        # Nur ein ECHTER Biss (Fisch/Item) wird gegen die Whitelist geprueft.
        if kind not in (_FISH, _ITEM):
            return KEEP_FISHING

        # Unsicherer Biss (Name nicht sicher erkannt) -> NIE abbrechen.
        name = getattr(result, 'name', None)
        confident = bool(getattr(result, 'confident', False))
        if not confident or not name or name == _UNKNOWN:
            return KEEP_FISHING

        # Sicherer Name -> Inventar-Zustand nachschlagen (fehlt = KEEP).
        state = _lookup_state(states, name)
        if state == REMOVE:
            return ABORT
        # KEEP oder CAMPFIRE (beide = gewollt) -> behalten.
        return KEEP_FISHING
    except Exception:
        # Defensiv: ein Fehler darf NIE einen gewollten Fang abbrechen.
        return KEEP_FISHING


def _lookup_state(states, name):
    """Zustand fuer ``name`` aus ``states`` (Default KEEP). Wirft nie."""
    if not states:
        return KEEP
    try:
        return states.get(name, KEEP)
    except Exception:
        return KEEP


def should_abort(result, states=None, enabled=False):
    """Bequemer bool-Shim: ``True`` gdw. :func:`decide` == :data:`ABORT`."""
    return decide(result, states=states, enabled=enabled) == ABORT


__all__ = [
    'KEEP', 'REMOVE', 'CAMPFIRE',
    'KEEP_FISHING', 'ABORT',
    'decide', 'should_abort',
]
