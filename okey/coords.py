# -*- coding: utf-8 -*-
"""Alle Bildschirm-Positionen des Okey-Events -- an EINER Stelle.

Alle Werte sind CLIENT-Pixel im festen 800x600-Fenster (der Bot rechnet den
Fenster-Offset ueberall selbst dazu, genau wie beim Angeln). Gemessen am
2026-09-10 aus sieben Bildschirmfotos des Nutzers; die Messung steht jeweils
als Kommentar dabei, damit spaeter nachvollziehbar ist, woher eine Zahl kommt
und wie man sie nachmisst.

WAS FEST IST UND WAS NICHT (Angabe des Nutzers, an den Bildern bestaetigt):
  * Das Okey-Fenster, der Start-Knopf, der Haken "Sicherer Modus", beide
    Ja/Nein-Dialoge und das ganze Spielfeld liegen IMMER an derselben Stelle.
  * NUR die Zeile des Okey-Events in der Eventuebersicht wandert -- welches
    Event an welcher Stelle steht, wechselt. Deshalb wird dort nach dem TEXT
    gesucht statt eine feste Zeile anzuklicken (siehe vision.find_event_row).
"""

# -- Eventuebersicht (Strg+E) -----------------------------------------------
#
# Die Zeilen liegen untereinander; gemessen an Bild 16:
#   Name-Knopf     x 389..565  (Mitte 477)
#   "Ansehen"      x 575..670  -> NICHT anklicken, das oeffnet nur die Info
#   Zeilen-Mitten  y 146 / 193 / 241 / 288  (Abstand ~47,5)
EVENT_LIST_NAME_X = 477            # Klick-x auf den Namens-Knopf einer Zeile
EVENT_LIST_ROW_Y = (146, 193, 241, 288)
EVENT_LIST_SEARCH_BOX = (380, 120, 580, 320)   # x0, y0, x1, y1 fuer die Textsuche

# -- Okey-Fenster (nach dem Klick auf die Event-Zeile) ----------------------
#
# Gemessen an Bild 17. Beide Elemente liegen fest.
START_BUTTON = (306, 460)          # x 265..348, y 453..468
SAFE_MODE_CHECKBOX = (526, 461)    # x 510..543, y 453..470 -- Haken MUSS raus

# -- Ja/Nein-Dialoge --------------------------------------------------------
#
# Gemessen an Bild 18 (Startgebuehr) UND Bild 22 (Beenden): BEIDE Dialoge
# nutzen exakt dieselben Knopf-Positionen -- ein Glueck fuer die Erkennung.
DIALOG_YES = (359, 322)            # x 330..388, y 314..330
DIALOG_NO = (438, 322)             # x 410..468, y 314..330

# -- Spielfeld --------------------------------------------------------------
#
# Die fuenf offenen Karten. Gemessen an Bild 20: Kartenkoerper x-Anfang
# 263/322/381/440/499, Breite 38, y 168..220 -> Mitten unten.
CARD_SLOT_X = (281, 340, 399, 458, 517)
CARD_SLOT_Y = 194
CARD_HALF_W = 19                   # halbe Kartenbreite  (Koerper 38 px)
CARD_HALF_H = 26                   # halbe Kartenhoehe   (Koerper 52 px)

# Die drei Auswahl-Plaetze darunter (dorthin wandert eine angeklickte Karte).
# Gemessen an Bild 21: Mitten (359, 282), (399, 282), (439, 282).
PICK_SLOT_X = (359, 399, 439)
PICK_SLOT_Y = 282

# Der gruene Nachziehstapel unten links. Gemessen an Bild 19: x 273..305,
# y 346..391 -> Mitte (288, 367).
DECK = (288, 367)

# Zahlenfelder. Gemessen an Bild 21 (Zeile y 383..396):
#   Rest-Karten ("X 19")  x 336..360
#   Punkte     ("90")     x 442..532
DECK_COUNT_BOX = (336, 383, 360, 396)      # x0, y0, x1, y1
POINTS_BOX = (442, 383, 532, 396)

# "Beenden" -- beendet die Runde und zahlt die Truhe aus.
# Gemessen an Bild 21: x 359..441, y 458..473.
END_BUTTON = (400, 465)

# -- Farben der Karten ------------------------------------------------------
#
# Gemessen an Bild 20 (OpenCV-Farbton, 0..179):
#   Blau  H = 102
#   Gelb  H =  25..26
#   Rot   liegt am Farbkreis-Anfang bzw. -Ende (0..10 / 170..179)
#
# Die Bereiche sind bewusst weit: die Karten sind kraeftig gefaerbt (Saettigung
# ueber 200 gemessen), zwischen den drei Farbtoenen liegen riesige Luecken.
COLOR_HUES = {
    'B': (88, 118),      # Blau
    'G': (14, 40),       # Gelb  ("G" wie in engine.COLORS)
    'R': (170, 12),      # Rot -- laeuft ueber den Nullpunkt, siehe vision
}
CARD_MIN_SAT = 110       # gemessen 205..217 -> reichlich Abstand
CARD_MIN_VAL = 110       # gemessen 179..195

#: Anteil kraeftig gefaerbter Pixel, ab dem ein Platz als BELEGT gilt.
#: Gemessen: belegt 0,78..0,87 -- leer exakt 0,00. Die Schwelle sitzt in der
#: Mitte einer Luecke, die kaum groesser sein koennte.
CARD_PRESENT_MIN = 0.30


def with_offset(punkt, offset=(0, 0)):
    """Client-Punkt + Fenster-Offset -> Bildschirm-Punkt."""
    return (int(offset[0] + punkt[0]), int(offset[1] + punkt[1]))


def card_box(index):
    """Ausschnitt ``(x0, y0, x1, y1)`` der Karte auf Platz ``index`` (0..4)."""
    cx = CARD_SLOT_X[index]
    return (cx - CARD_HALF_W, CARD_SLOT_Y - CARD_HALF_H,
            cx + CARD_HALF_W, CARD_SLOT_Y + CARD_HALF_H)


def card_point(index, offset=(0, 0)):
    """Klickpunkt der Karte auf Platz ``index`` (0..4)."""
    return with_offset((CARD_SLOT_X[index], CARD_SLOT_Y), offset)


# -- "Sicherer Modus" -------------------------------------------------------
#
# Der Haken muss VOR dem Start raus (Vorgabe des Nutzers). Gemessen an Bild 17
# (Haken gesetzt): heller Anteil 0,136 in diesem Ausschnitt.
#
# ABSICHTLICH KEINE feste Helligkeits-Schwelle: es liegt kein einziges Bild mit
# LEEREM Kaestchen vor, eine Schwelle waere also geraten. Der Runner vergleicht
# stattdessen VORHER mit NACHHER (siehe interface/okey_runner._haken_entfernen)
# -- das braucht keinen Absolutwert und merkt zugleich, wenn der Klick gar
# nicht ankam.
SAFE_MODE_BOX = (509, 452, 543, 470)     # x0, y0, x1, y1
