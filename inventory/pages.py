# -*- coding: utf-8 -*-
"""Welche Inventar-Seiten (I-IV) darf der Bot ueberhaupt anfassen?

EINE Quelle fuer alle Bot-Teile: Der Nutzer markiert in den Einstellungen die
Seiten, die benutzt werden duerfen; unmarkierte bleiben komplett unberuehrt --
kein Reiter-Klick, kein Screenshot, keine Erkennung, kein Drag. Das spart pro
uebersprungener Seite einen Reiter-Klick samt Settle, einen Screenshot und 45
Slot-Vergleiche; beim Lagerfeuer zaehlt das mehrfach, weil dort nach JEDEM Feuer
neu gescannt wird.

Reine Logik: kein win32, kein Toolkit, keine Bildverarbeitung -> headless
testbar. Das echte Reiter-Umschalten bleibt in den Runnern.

Die Zaehlweise ist bewusst doppelt bedienbar, weil beide Schreibweisen im
Bestand vorkommen: der Energiesplitter rechnet mit ``1..4``, die Inventar-Engine
(``inventory.constants.PAGES``) mit roemischen Labels ``'I'..'IV'``.
:func:`normalize_pages` nimmt beides an, :func:`roman_pages` liefert genau das
Tupel, das die Scanner-API erwartet.

FAIL-SAFE: Eine leere oder unbrauchbare Auswahl ergibt IMMER alle vier Seiten.
Lieber einmal zu viel scannen als einen Bot, der nirgends nachschaut und
scheinbar grundlos nichts findet.
"""

#: Die vier Inventar-Seiten als 1..4 <-> roemische Reiter-Labels.
PAGE_TO_ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}
ROMAN_TO_PAGE = {r: p for p, r in PAGE_TO_ROMAN.items()}
ALL_PAGES = (1, 2, 3, 4)


def normalize_pages(value):
    """Beliebige Eingabe -> sortiertes Tupel eindeutiger Seiten aus ``1..4``.

    Akzeptiert Listen/Tupel/Sets aus ints (oder int-artigen Strings) sowie
    roemische Labels (``'I'..'IV'``). Leeres/ungueltiges Ergebnis ->
    :data:`ALL_PAGES` (fail-safe, siehe Modul-Doku). Wirft nie.
    """
    if value is None:
        return ALL_PAGES
    out = set()
    try:
        items = value if isinstance(value, (list, tuple, set)) else [value]
        for item in items:
            if item in ROMAN_TO_PAGE:            # 'I'..'IV'
                out.add(ROMAN_TO_PAGE[item])
                continue
            try:
                n = int(item)
            except (TypeError, ValueError):
                continue
            if n in PAGE_TO_ROMAN:
                out.add(n)
    except TypeError:
        return ALL_PAGES
    return tuple(sorted(out)) if out else ALL_PAGES


def roman_pages(value):
    """Freigegebene Seiten als roemisches Tupel -- das Format der Scanner-API.

    ``[1, 3]`` -> ``('I', 'III')``. Immer in Reiter-Reihenfolge (I vor II vor
    ...), unabhaengig davon, wie der Nutzer die Haken gesetzt hat: der Scan
    klickt die Reiter der Reihe nach durch, alles andere waere unnoetiges
    Hin-und-Her. Wirft nie.
    """
    return tuple(PAGE_TO_ROMAN[p] for p in normalize_pages(value))


def is_allowed(page_or_roman, enabled):
    """``True``, wenn die Seite (``1..4`` ODER ``'I'..'IV'``) freigegeben ist."""
    pages = set(normalize_pages(enabled))
    if page_or_roman in ROMAN_TO_PAGE:
        return ROMAN_TO_PAGE[page_or_roman] in pages
    try:
        return int(page_or_roman) in pages
    except (TypeError, ValueError):
        return False


def pages_from_config(cfg):
    """Freigegebene Seiten aus einem Config-Dict lesen (``inventory.pages``).

    Bequemlichkeit fuer die Runner, damit sie den Schluesselpfad nicht jeweils
    selbst kennen muessen. Fehlt der Eintrag oder ist die Config unbrauchbar,
    greift derselbe Fail-safe wie ueberall: alle vier Seiten. Wirft nie.
    """
    try:
        return normalize_pages((cfg or {}).get('inventory', {}).get('pages'))
    except Exception:
        return ALL_PAGES


__all__ = ['PAGE_TO_ROMAN', 'ROMAN_TO_PAGE', 'ALL_PAGES', 'normalize_pages',
           'roman_pages', 'is_allowed', 'pages_from_config']
