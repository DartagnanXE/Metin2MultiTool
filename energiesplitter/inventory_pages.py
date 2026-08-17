# -*- coding: utf-8 -*-
"""Reine Logik fuer die freigegebenen Inventar-Seiten des Energie-Bots (Item 3).

Der Nutzer markiert in den Einstellungen, welche der vier Inventar-Seiten (I-IV)
der Bot nutzen darf. Der Bot fasst NUR markierte Seiten an (Frei-Slot-Suche /
Dolch-Verarbeitung); unmarkierte bleiben unberuehrt -- er "schaut dort nicht
nach". Diese Schicht ist toolkit-/win32-frei und headless-testbar; das echte
Reiter-Umschalten lebt im Bot (``detect.active_page`` + ``INV_TAB_CENTERS``).
"""

#: Die vier Inventar-Seiten als 1..4 <-> roemische Reiter-Labels (wie
#: ``energiesplitter.detect.active_page`` / ``calibration.INV_TAB_CENTERS``).
#:
#: EINE Quelle fuer den ganzen Bot: die Seiten-Logik liegt seit der
#: Inventar-Seitenauswahl (2026-08-11) in :mod:`inventory.pages` und wird hier
#: nur RE-EXPORTIERT -- der Fisch-Teil (Scan/Lagerfeuer/Wegwerfen/Koeder) und
#: der Energiesplitter sollen sich nicht unterschiedlich verhalten, wenn jemand
#: die Normalisierung anfasst. Verhalten unveraendert (identische Semantik,
#: identischer Fail-safe auf alle vier Seiten).
from inventory.pages import (          # noqa: F401  (bewusster Re-Export)
    PAGE_TO_ROMAN, ROMAN_TO_PAGE, ALL_PAGES, normalize_pages, is_allowed,
)


def working_page(enabled):
    """Die Arbeits-Seite = NIEDRIGSTE freigegebene Seite (Default 1).

    Auf ihr fuehrt der Bot seine Frei-Slot-/Lande-Logik aus (frueher fix Seite 1).
    Leeres ``enabled`` -> 1 (fail-safe)."""
    pages = normalize_pages(enabled)
    return pages[0] if pages else 1


def target_tab(active_roman, enabled):
    """Welchen Reiter ('I'..'IV') muss der Bot klicken, um auf eine ERLAUBTE
    Seite zu kommen -- oder ``None``, wenn die offene Seite schon erlaubt ist.

    * offene Seite (``active_roman``) bereits freigegeben -> ``None`` (kein Klick).
    * offene Seite gesperrt ODER unbekannt (``None``) -> Reiter der Arbeits-Seite
      (niedrigste freigegebene). Reiner Entscheid (kein I/O), damit der Bot-Guard
      headless testbar bleibt."""
    if active_roman is not None and is_allowed(active_roman, enabled):
        return None
    return PAGE_TO_ROMAN[working_page(enabled)]


# ``is_allowed`` kommt aus :mod:`inventory.pages` (Re-Export oben) -- hier
# bewusst KEINE zweite Definition, sonst driften die beiden Bot-Teile
# auseinander, sobald jemand nur eine der Kopien anfasst.
