"""Skalierbare Board-Geometrie fuer VARIABLE Fenster-/Board-Groessen.

Referenz ist die bewaehrte 800x600-Geometrie (Board 260x170, PUZZLE_WINDOW_SIZE).
Alle Schluesselpunkte (24 Zell-Sample/Klickpunkte, Stein-Farb-Sample, Buttons)
sind in Referenzkoordinaten definiert. Fuer eine manuell markierte Board-Groesse
``(w, h)`` werden ALLE Punkte linear mit ``(w/260, h/170)`` skaliert.

Bei der Referenzgroesse (260, 170) ist die Abbildung die IDENTITAET
(``round((15+32*j) * 260/260) == 15+32*j``) -> der Default-Pfad in puzzle.py
bleibt damit byte-identisch zum bisherigen Verhalten (kein Verhalten geaendert,
solange keine abweichende Groesse gesetzt wird).

Reine Python-Standardbibliothek -> headless per ``unittest`` testbar.
"""

# (Breite, Hoehe) der Referenz = PuzzleBot.PUZZLE_WINDOW_SIZE bei 800x600.
REF_SIZE = (260, 170)

# Raster-Geometrie (Referenz), identisch zu puzzle.set_puzzle_state / calibration.
GRID_ROWS = 4
GRID_COLS = 6
GRID_ORIGIN = 15
GRID_STEP = 32

# Spannweite der 24 Zellmitten in Referenzkoordinaten: von Mitte Zelle(0,0)
# bis Mitte Zelle(GRID_ROWS-1, GRID_COLS-1). SPAN_X = 5 Spaltenschritte = 160,
# SPAN_Y = 3 Zeilenschritte = 96. Genutzt von crop_from_grid_corners /
# pixel_to_ref, um die im Overlay markierte Raster-Bounding-Box (2 Eckgriffe
# auf Zelle(0,0) und Zelle(3,5)) konsistent in das 15+32-in-260-Modell
# umzurechnen.
SPAN_X = GRID_STEP * (GRID_COLS - 1)   # 160
SPAN_Y = GRID_STEP * (GRID_ROWS - 1)   # 96

# Weitere Schluesselpunkte in Referenzkoordinaten (260x170):
REF_COLOR_SAMPLE = (110, 150)   # Stein-Farb-Sample (PUZZLE_GET_NEW_PIECE_COLOR)
REF_GET_PIECE = (230, 85)       # "Neuer Stein" / Feld-voll-Pixel (PUZZLE_GET_NEW_PIECE)
REF_CONFIRM = (100, 90)         # Bestaetigen / Wegwerfen (PUZZLE_COMFIRM)
REF_CAKE = (120, 90)            # Belohnung (PUZZLE_COMFIRM + 20 in x)


def scale_point(ref_point, size):
    """Skaliert einen Referenzpunkt ``(rx, ry)`` auf die Board-Groesse ``size``.

    Bei ``size == REF_SIZE`` ist das Ergebnis exakt der Referenzpunkt (Identitaet).
    """
    w, h = size
    rx, ry = ref_point
    return (int(round(rx * w / REF_SIZE[0])), int(round(ry * h / REF_SIZE[1])))


def cell_ref(i, j):
    """Referenzkoordinate des Sample-/Klickpunkts der Zelle ``(i, j)``."""
    return (GRID_ORIGIN + GRID_STEP * j, GRID_ORIGIN + GRID_STEP * i)


def cell_point(i, j, size):
    """Skalierter Sample-/Klickpunkt der Zelle ``(i, j)`` fuer ``size``."""
    return scale_point(cell_ref(i, j), size)


def grid_points(size):
    """Die 24 skalierten Rasterpunkte, Zeile fuer Zeile (i aussen, j innen)."""
    return [cell_point(i, j, size)
            for i in range(GRID_ROWS) for j in range(GRID_COLS)]


def color_sample(size, ref=None):
    """Skalierter Stein-Farb-Sample-Punkt.

    ``ref=None`` (Default) nutzt die Referenzkonstante ``REF_COLOR_SAMPLE`` ->
    byte-identisch zum bisherigen Verhalten. Wird ein kalibrierter
    ``ref``-Override (260x170-Referenzkoordinate, z.B. aus pixel_to_ref)
    uebergeben, wird dieser statt der Konstante mit ``size`` skaliert.
    """
    return scale_point(ref if ref is not None else REF_COLOR_SAMPLE, size)


def get_piece_point(size, ref=None):
    """Skalierter 'Neuer Stein' / Feld-voll-Punkt.

    ``ref=None`` (Default) -> ``REF_GET_PIECE`` (byte-stabil); sonst der
    kalibrierte Referenz-Override.
    """
    return scale_point(ref if ref is not None else REF_GET_PIECE, size)


def confirm_point(size, ref=None):
    """Skalierter Bestaetigen-/Wegwerfen-Punkt.

    ``ref=None`` (Default) -> ``REF_CONFIRM`` (byte-stabil); sonst der
    kalibrierte Referenz-Override.
    """
    return scale_point(ref if ref is not None else REF_CONFIRM, size)


def cake_point(size, ref=None):
    """Skalierter Belohnungs-Punkt.

    ``ref=None`` (Default) -> ``REF_CAKE`` (byte-stabil); sonst der
    kalibrierte Referenz-Override.
    """
    return scale_point(ref if ref is not None else REF_CAKE, size)


def crop_from_grid_corners(grid_tl, grid_br):
    """Leitet Board-CROP ``(offset, size)`` aus 2 Raster-Eckgriffen ab.

    ``grid_tl`` = Pixel-Position (Fensterinhalt) der Mitte Zelle(0,0),
    ``grid_br`` = Pixel-Position der Mitte Zelle(GRID_ROWS-1, GRID_COLS-1).

    Konsistent zum 15+32-in-260-Modell: der Skalenfaktor ergibt sich aus der
    gemessenen Spannweite ueber SPAN_X/SPAN_Y; daraus folgen Offset (so dass
    ``cell_point(0,0,size)+offset == grid_tl``) und Groesse (``260*scaleX`` x
    ``170*scaleY``). Bei Default-Markierung (Spannweite 160x96) ist scale=1 ->
    offset/size exakt der bewaehrte Default -> byte-stabil.

    Rueckgabe ``((ox, oy), (w, h))`` (zwei Int-Paare) oder ``None`` bei
    degenerierter Eingabe (Null-/Negativ-Spannweite -> Division gegen ~0).
    """
    span_x = grid_br[0] - grid_tl[0]
    span_y = grid_br[1] - grid_tl[1]
    if span_x <= 0 or span_y <= 0:
        return None
    scale_x = span_x / SPAN_X
    scale_y = span_y / SPAN_Y
    offset = (int(round(grid_tl[0] - GRID_ORIGIN * scale_x)),
              int(round(grid_tl[1] - GRID_ORIGIN * scale_y)))
    size = (int(round(REF_SIZE[0] * scale_x)),
            int(round(REF_SIZE[1] * scale_y)))
    return (offset, size)


def pixel_to_ref(point, grid_tl, grid_br):
    """Normiert einen Fensterinhalt-Pixel auf eine 260x170-Referenzkoordinate.

    Inverse zu ``scale_point``+Offset bzgl. der markierten Raster-Bounding-Box
    ``grid_tl``/``grid_br``: bestimmt die relative Lage von ``point`` innerhalb
    der Spannweite und bildet sie auf ``GRID_ORIGIN + rel*SPAN`` ab. Das
    Ergebnis ist auflousungs-/groessenunabhaengig und kann als ref-Override an
    die Sonderpunkt-Funktionen gegeben werden.

    Rueckgabe ``(refx, refy)`` (Float-Paar) oder ``None`` bei degenerierter
    Eingabe (Null-/Negativ-Spannweite).
    """
    span_x = grid_br[0] - grid_tl[0]
    span_y = grid_br[1] - grid_tl[1]
    if span_x <= 0 or span_y <= 0:
        return None
    rel_x = (point[0] - grid_tl[0]) / span_x
    rel_y = (point[1] - grid_tl[1]) / span_y
    return (GRID_ORIGIN + rel_x * SPAN_X, GRID_ORIGIN + rel_y * SPAN_Y)
