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
