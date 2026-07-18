"""Deluxe-Puzzlestein: Magenta-Erkennung + deterministische 2x3-Platzierung.

Die DELUXE-Box (eigener Slot UEBER der Standard-Box) liefert beim Oeffnen EINEN
Spezialstein: ein VOLLES 2x3-Rechteck (6 Zellen), Farbe knall-MAGENTA. Dieser
Stein ist NICHT Teil des trainierten MDP (trained_solver) und auch nicht des
Greedy-/Eroeffnungsbuch-Pfads (tetris.py): er hat eine feste Form und wird
deterministisch GREEDY in das erste freie 2x3-Loch gesetzt.

Dieses Modul ist bewusst REINE Python-Standardbibliothek (kein numpy/cv2/win32/
pydirectinput) -> es ist headless unter WSL/Linux importier- und testbar, anders
als puzzle.py. Es buendelt:

  * :data:`DELUXE_PIECE_TYPE`  -- der neue Steintyp (7), disjunkt zu 1..6.
  * :data:`DELUXE_REF_BGR`     -- gemessenes Magenta am Farb-Sample (B,G,R).
  * :func:`is_magenta`         -- Toleranzfenster um das Magenta (hoher B/R,
                                  sehr niedriger G), kollidiert NICHT mit den
                                  sechs echten Steinfarben.
  * :func:`find_free_2x3`      -- erstes freies, top-links verankertes 2x3-Loch
                                  im 4x6-Brett (oder ``None``).
  * :data:`DELUXE_FORM`        -- die 6 belegten Zellen relativ zum Anker.
  * :func:`read_deluxe_count`  -- Stack-Zahl der DELUXE-Box per Inventar-OCR
                                  (>= 1 -> Box vorhanden). STRIKT defensiv -> 0.

Der Modus 'Deluxe SOFORT' (``force_deluxe=True``, siehe puzzle.py) setzt die
Gold-/Deluxe-Box FRUEH auf das erste freie 2x3 (``find_free_2x3``), hoechstens
1x pro Brett. Die fruehere V3-Reservat-Strategie (ein festes 2x3 freihalten) ist
per Monte-Carlo widerlegt und entfernt.

Brettkonvention identisch zu puzzle.set_puzzle_state / trained_solver:
``board[i][j]``, i=Zeile 0..3, j=Spalte 0..5, truthy=belegt.
"""

# Neuer Steintyp fuer den Deluxe-Stein. Bewusst 7 (disjunkt zu den echten
# Typen 1..6 in piece.py) -> Piece(7) ergibt einen LEEREN, ungueltigen Stein
# (is_valid False), sodass der Deluxe-Stein NIE versehentlich durch den
# Greedy-/MDP-Solver laeuft. Die deterministische Platzierung passiert ueber
# find_free_2x3 in puzzle.play_game.
DELUXE_PIECE_TYPE = 7

# Gemessenes Magenta am Stein-Farb-Sample-Punkt als (B, G, R): R und B hoch,
# G praktisch 0. Spiegelbild der PIECE_REF_BGR-Zentroide der anderen Typen.
DELUXE_REF_BGR = (251, 28, 232)

# Volles 2x3-Rechteck (2 Zeilen, 3 Spalten), Zellen relativ zum Anker (dr, dc).
# Reihenfolge zeilenweise -- identisches Format wie trained_solver._FORMS.
DELUXE_FORM = ((0, 0), (0, 1), (0, 2),
               (1, 0), (1, 1), (1, 2))

# Brett-Dimensionen (wie ROWS/COLS in trained_solver / Tetris.board).
_ROWS = 4
_COLS = 6

# Toleranzfenster um DELUXE_REF_BGR. Bewusst WEIT in B/R (>= 200) und ENG in G
# (<= 80): das Magenta hat extrem hohen B und R bei nahezu null G. Geprueft
# gegen die sechs echten Steinfarben (PIECE_REF_BGR) -- keiner faellt hinein,
# und das echte Magenta faellt in KEINES der sechs engen Steinfenster:
#   Typ3 (250,250,25): G zu hoch.  Typ2 (250,107,0): G zu hoch + R zu niedrig.
# So bleibt der Deluxe-Typ kollisionsfrei.
_MAGENTA_MIN_B = 200
_MAGENTA_MIN_R = 200
_MAGENTA_MAX_G = 80


def is_magenta(b, g, r):
    """True, wenn ``(b, g, r)`` in das Magenta-Deluxe-Fenster faellt.

    Hoher Blau- UND Rotkanal bei sehr niedrigem Gruenkanal. Defensiv: nimmt
    ints/floats, wirft nie (reiner Vergleich)."""
    try:
        return (b >= _MAGENTA_MIN_B and r >= _MAGENTA_MIN_R
                and g <= _MAGENTA_MAX_G)
    except TypeError:
        return False


def find_free_2x3(board):
    """Anker ``(x, y)`` des ERSTEN freien, top-links verankerten 2x3-Lochs.

    Scannt zeilenweise (x aussen 0..2, y innen 0..3) und liefert den ersten
    Anker, an dem alle sechs Zellen des 2x3-Rechtecks leer sind. Passt KEIN
    2x3-Block, kommt ``None`` zurueck (Aufrufer verwirft den Stein dann).

    Der Anker passt zu ``Tetris.insert_piece(x, y, ...)`` (x=Zeile, y=Spalte).
    Defensiv: kein/zu kleines/kaputtes Brett -> ``None`` (nie Crash)."""
    if not board:
        return None
    try:
        for x in range(_ROWS - 1):          # 0..2 (Hoehe 2 passt bis Zeile 2)
            row0 = board[x]
            row1 = board[x + 1]
            for y in range(_COLS - 2):      # 0..3 (Breite 3 passt bis Spalte 3)
                if (not row0[y] and not row0[y + 1] and not row0[y + 2]
                        and not row1[y] and not row1[y + 1] and not row1[y + 2]):
                    return (x, y)
    except (IndexError, TypeError):
        return None
    return None


def read_deluxe_count(screenshot_bgr, center=(503, 271)):
    """Liest die Stack-ZAHL der DELUXE-Box aus einem Vollbild-Screenshot.

    Schneidet einen 32x32-Slot zentriert auf ``center`` (Fenster-INHALT-
    Koordinate, Default = ``PuzzleBot.PUZZLE_DELUXE_BOX``) aus dem BGR-Screenshot
    aus, konvertiert ihn nach RGB und liest die aufgedruckte Stueckzahl per
    ``inventory.digits.read_count`` (font-unabhaengiges OCR). Rueckgabe: die
    erkannte Anzahl als ``int`` (``>= 1`` -> Deluxe-Box vorhanden), ``0`` wenn
    keine Zahl/Box erkennbar ist.

    STRIKT defensiv -- darf den Bot-Loop NIE kippen: jeder Fehler (kein numpy,
    kaputtes/zu kleines Bild, OCR-Fehlschlag) -> ``0``. Eine UNSICHERE OCR-
    Lesung (``confident=False``) wird als ``0`` gewertet (lieber kein Force-
    Deluxe als ein faelschlich geoeffneter, leerer Box-Klick).

    Verwendet ``inventory.grid.extract_slot`` fuer den BGR->RGB-Zuschnitt (mit
    Rand-Klemmung) -- exakt das Format, das ``read_count`` erwartet."""
    if screenshot_bgr is None:
        return 0
    try:
        # Lazy-Import: inventory zieht numpy/PIL -- nur hier, damit deluxe.py
        # ansonsten reine stdlib bleibt (headless importierbar/testbar).
        from inventory.grid import extract_slot
        from inventory.digits import read_count
        from inventory.constants import SLOT_PX
    except Exception:
        return 0
    try:
        half = SLOT_PX // 2
        cx, cy = int(center[0]), int(center[1])
        # 32x32-Box (x, y, w, h) zentriert auf center; extract_slot klemmt an
        # den Bildrand + repliziert fehlende Raender -> immer ein volles Slot.
        box = (cx - half, cy - half, SLOT_PX, SLOT_PX)
        slot_rgb = extract_slot(screenshot_bgr, box)
        if slot_rgb is None:
            return 0
        result = read_count(slot_rgb)
        if result is None:
            return 0
        value = getattr(result, 'value', None)
        confident = getattr(result, 'confident', False)
        # read_count liefert fuer einen Slot OHNE aufgedruckte Zahl value=1,
        # n_digits=0, confident=True ("einzelnes, ungestapeltes Item"). Fuer die
        # DELUXE-Box ist das genau der "1 Box, keine Stack-Zahl"-Fall -> als 1
        # gewertet (Spec: value>=1 -> Box da). ACHTUNG (live zu kalibrieren): ein
        # leerer/dunkler Slot an falscher Position liest sich ebenfalls als 1 ->
        # die Box-Klick-Position/Schwelle muss am echten Client geprueft werden.
        # Unsichere Lesung / kein int -> 0 (lieber kein Force-Deluxe).
        if value is None or not confident:
            return 0
        return int(value)
    except Exception:
        return 0
