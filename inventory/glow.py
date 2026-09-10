# -*- coding: utf-8 -*-
"""Leuchtrahmen loeschen: der Zeiger-Sweep ueber alle Inventar-Slots.

WOZU. Ein frisch gefangenes oder frisch erhaltenes Item traegt einen
LEUCHT-RAHMEN, bis der Zeiger einmal darueber gefahren ist. Der faelscht die
Erkennung massiv. Gemessen am echten Client (2026-08-11): derselbe Yabbie hat
im dunklen Slot die Match-Distanz **0,1**, im leuchtenden **26,45** -- gegen die
Schwelle 22. Er faellt damit aus der Erkennung, gilt als "unbekannt" und wird
z.B. nie gegrillt. Genau dieser Fall wurde als Fehler gemeldet.

Die Schwelle einfach anzuheben ist KEINE Loesung: bei Distanz 29,5 liegt ein
dokumentierter Fehltreffer (ein bronzenes Abzeichen als 'Worm' erkannt,
2026-08-05). Zwischen 26,45 und 29,5 ist kein Platz fuer eine Schwelle. Das
Leuchten muss also weg, statt toleriert zu werden.

WIE. Einmal mit der Maus ueber jede Slot-Mitte fahren -- ausschliesslich
``moveTo``, **nie ein Klick**: ein Klick wuerde das Item aufnehmen. Danach wird
der Zeiger unter das Raster geparkt, damit er auf der folgenden Aufnahme keinen
Slot verdeckt (der Hardware-Zeiger landet je nach Betriebssystem mit im Bild und
kann einen Slot zu "unbekannt" degradieren).

Die Reihenfolge ist BOUSTROPHEDON (Schlangenlinie, siehe :mod:`inventory.hover`):
Zeile 0 links->rechts, Zeile 1 rechts->links usw. Das sind 44 kurze Spruenge
statt 44 kurzer plus 8 langer Ruecksprunge -- messbar schneller und ruhiger.

Dieses Modul haelt den LIVE-Teil (Maus bewegen) an EINER Stelle, damit ihn alle
Scan-Pfade teilen: der Inventar-Scan, das Lagerfeuer-Grillen und das Wegwerfen.
Vorher lag er nur im Inventar-Runner und wurde von den anderen beiden nicht
benutzt -- deshalb blieben dort leuchtende Items unerkannt.
"""

import time

from . import hover
from .constants import HOVER_SETTLE_S

#: Obergrenze der Zusatzpause je Slot (ms). Bei 50 ms dauert ein Sweep ueber
#: 45 Slots schon 2,3 s -- darueber waere er unbrauchbar.
MAX_SPEED_MS = 50


def sweep(inp, lattice, offset=(0, 0), speed_ms=0, sleep=None,
          settle=HOVER_SETTLE_S):
    """Einmal ueber alle Slots fahren und den Zeiger danach wegparken.

    :param inp: Eingabe-Schicht mit ``moveTo(x, y)`` (pydirectinput live, ein
        Rekorder im Test). ``None`` -> no-op.
    :param lattice: das eingerastete Raster (``slot_box(row, col)``).
    :param offset: Fenster-Offset, wie bei jedem anderen Klick im Bot.
    :param speed_ms: zusaetzliche Pause je Slot in Millisekunden. 0 = volle
        Geschwindigkeit (dann wird auch ``PAUSE`` der Eingabe-Schicht auf 0
        gesetzt und danach zurueckgestellt).
    :param sleep: Schlaf-Funktion (Tests reichen eine Attrappe herein).
    :return: die Anzahl tatsaechlich angefahrener Punkte (0 = nichts getan).

    Wirft NIE: ein Fehler beim Bewegen darf weder den Scan noch den Angel-Loop
    kippen -- im schlimmsten Fall bleibt das Leuchten stehen und einzelne Slots
    werden schlechter erkannt, was ohne diesen Sweep ohnehin der Zustand waere.
    """
    if inp is None or lattice is None:
        return 0
    if sleep is None:
        sleep = time.sleep
    try:
        punkte = hover.to_screen(hover.slot_centres(lattice), offset)
        park = hover.to_screen([hover.park_point(lattice)], offset)[0]
    except Exception:
        return 0

    ms = max(0, min(MAX_SPEED_MS, int(speed_ms or 0)))
    alt_pause = getattr(inp, 'PAUSE', None)
    getan = 0
    try:
        # Volle Geschwindigkeit: die Eingabe-Schicht wartet sonst nach JEDER
        # Bewegung ihre eigene PAUSE ab (0,05 s -> 45 Slots = 2,3 s).
        try:
            inp.PAUSE = 0
        except Exception:
            pass
        for (x, y) in punkte:
            inp.moveTo(int(x), int(y))
            getan += 1
            if ms:
                sleep(ms / 1000.0)
        # Zeiger unter das Raster parken -- NIE ein Klick.
        inp.moveTo(int(park[0]), int(park[1]))
    except Exception:
        pass
    finally:
        if alt_pause is not None:
            try:
                inp.PAUSE = alt_pause
            except Exception:
                pass
    # Dem Client einen Moment geben, das Leuchten wirklich zu loeschen, bevor
    # die naechste Aufnahme entsteht.
    try:
        sleep(settle)
    except Exception:
        pass
    return getan


def make_hover_fn(inp, lattice_fn, offset=(0, 0), speed_ms=0, sleep=None,
                  log_fn=None):
    """Baut das ``hover_fn(page)``, das die Scanner erwarten.

    ``lattice_fn(page)`` liefert das Raster fuer die Seite (meist immer
    dasselbe -- der Beutel ist ein festes Fenster). Liefert es ``None``, wird
    uebersprungen statt geraten.
    """
    def hover_fn(page, lattice=None):
        try:
            lat = lattice if lattice is not None else lattice_fn(page)
            n = sweep(inp, lat, offset=offset, speed_ms=speed_ms, sleep=sleep)
            if log_fn is not None and n:
                log_fn(page, n)
        except Exception:
            pass
    return hover_fn
