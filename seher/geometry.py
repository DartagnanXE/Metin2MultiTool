"""Geometrie des Seherwettstreit-Fensters (800x600-Client, Fenster wandert).

ALLE Koordinaten sind RELATIV zum Anker = Top-Left des Treffers des
Titel-Templates (seher/templates/title.png, der Schriftzug "Seherwettstreit"
in der Fenster-Titelleiste). Kalibriert aus zwei realen Screenshots mit
verschobenem Fenster (tools_seher/calibrate.py): Anker-NCC war auf beiden
exakt 1.0000, die Fenster-Verschiebung (+55,+78) wurde fehlerfrei getrackt.

Slots sind (x, y) der Top-Left-Ecke einer Kartenzelle (40x50), Pitch 42 px.
"""

# Karten-Zellen
CARD_W = 40
CARD_H = 50
PITCH = 42

# Anker-Qualitaet: 1.0 auf beiden Fixtures; <0.8 = Fenster nicht da/verdeckt.
ANCHOR_NCC_MIN = 0.80

# Gegner-Rueckseiten (oben): 5 schwarze, darunter 4 weisse.
OPP_BLACK_SLOTS = tuple((-117 + PITCH * k, 32) for k in range(5))
OPP_WHITE_SLOTS = tuple((-96 + PITCH * k, 87) for k in range(4))

# Eigene Karten (unten): weisse Reihe 1,3,5,7 ueber schwarzer Reihe 0,2,4,6,8.
MY_WHITE_SLOTS = tuple((-96 + PITCH * k, 204) for k in range(4))
MY_BLACK_SLOTS = tuple((-117 + PITCH * k, 258) for k in range(5))

# Score-Anzeigen im rechten Panel (Ziffer hell auf fast-schwarzer Box).
# Box liegt rel x ~121..214 -- ROI bewusst schmaler (140..210), damit sie
# sicher IM Fenster bleibt (eine breitere ROI ragte in den Welthintergrund
# und erzeugte False-Positives im Diff -- Benchmark-Befund).
SCORE_OPP_ROI = (140, 52, 70, 26)    # x, y, w, h relativ zum Anker
SCORE_ME_ROI = (140, 196, 70, 26)

# Nachrichtenband (schwarzer Streifen zwischen Gegner- und Spieler-Reihen);
# nur Debug-Signal (Text "Deine Zahl ist ..." erscheint bei der Auswertung).
MESSAGE_ROI = (-110, 147, 200, 44)

# Rotes Kreuz: kalibrierte Kreuze hatten 246-287 rote Pixel im Slot;
# leere Slots ~0. Schwelle mit grossem Sicherheitsabstand beidseitig.
CROSS_RED_MIN = 80


def slot_of_value(value):
    """Top-Left-Slot (relativ zum Anker) der eigenen Karte `value` (0-8)."""
    if value % 2 == 1:
        return MY_WHITE_SLOTS[(value - 1) // 2]
    return MY_BLACK_SLOTS[value // 2]


def click_center_of_value(value):
    """Klick-Zentrum (relativ zum Anker) der eigenen Karte `value`."""
    x, y = slot_of_value(value)
    return (x + CARD_W // 2, y + CARD_H // 2)
