"""puzzle_safety.py -- reine Sicherheits-/Plausibilitaets-Schicht des Puzzle-Bots.

Der Bot ist von Natur aus OPEN-LOOP: er liest EINEN Pixel fuer den Stein und 24
Pixel fuers Brett, entscheidet und klickt -- ohne jede Nachkontrolle. Dieses
Modul buendelt die *reinen* (bildfreien, zustandslosen) Bausteine, mit denen die
State-Machine in :mod:`puzzle` ihre Wahrnehmung und ihre Aktionen absichert:

  * Farb-Konfidenz: Distanz/Margin eines BGR-Werts zu den 6 Stein-Zentroiden
    (``centroid_metrics``) + ein margin-gegatetes Klassifikat (``confident_type``).
  * Footprint/Erwartung: welche Zellen ein Stein belegt (``footprint``,
    ``expected_board_after``) -- Grundlage der Closed-Loop-Verifikation.
  * Closed-Loop: Soll-/Ist-Brett vergleichen (``verify_placement``).
  * Endspiel: ist das Brett in EINEM Zug komplettierbar (``one_piece_completable``,
    ``piece_can_complete``) -- damit der Finish-Modus ein 1-Zug-Loch nicht durch
    einen fragmentierenden Stein zerstoert.

Alles rein stdlib, keine Bild-/numpy-Abhaengigkeit. Die Stein-FORMEN werden aus
:mod:`trained_solver` wiederverwendet (eine Quelle der Wahrheit), damit Solver
und Verifikation nie auseinanderlaufen.
"""

from math import sqrt

import trained_solver as _ts

ROWS = _ts.ROWS
COLS = _ts.COLS
_FULL_MASK = (1 << (ROWS * COLS)) - 1


# -- Farb-Konfidenz -------------------------------------------------------

def centroid_metrics(bgr, refs):
    """Distanz-Kennzahlen eines ``(b, g, r)`` zu den Referenz-Zentroiden.

    ``refs`` ist ein ``{piece_type: (b, g, r)}``-Dict (z.B. ``PIECE_REF_BGR``).
    Rueckgabe-Dict:
      * ``nearest`` / ``second``: Steintyp des naechsten / zweitnaechsten Zentroids
      * ``nearest_dist`` / ``second_dist``: euklidische Distanz (Farb-Einheiten)
      * ``margin``: ``second_dist - nearest_dist`` (>= 0; gross = eindeutig)
      * ``dists``: ``{piece_type: dist}`` fuer alle Zentroide
    Defensiv: leeres ``refs`` -> alle Felder ``None`` / leeres Dict.
    """
    b, g, r = bgr
    dists = {}
    for t, ref in refs.items():
        db = b - ref[0]
        dg = g - ref[1]
        dr = r - ref[2]
        dists[t] = sqrt(db * db + dg * dg + dr * dr)
    if not dists:
        return {'nearest': None, 'second': None, 'nearest_dist': None,
                'second_dist': None, 'margin': None, 'dists': {}}
    ordered = sorted(dists.items(), key=lambda kv: kv[1])
    nearest, nearest_dist = ordered[0]
    if len(ordered) > 1:
        second, second_dist = ordered[1]
        margin = second_dist - nearest_dist
    else:
        second, second_dist, margin = None, None, float('inf')
    return {'nearest': nearest, 'second': second, 'nearest_dist': nearest_dist,
            'second_dist': second_dist, 'margin': margin, 'dists': dists}


def confident_type(bgr, refs, tol=40, min_margin=30.0):
    """Steintyp NUR wenn die Messung *sicher* ist, sonst ``None``.

    Sicher heisst: der naechste Zentroid liegt auf ALLEN drei Kanaelen innerhalb
    ``tol``, UND der euklidische Abstand zum zweitnaechsten Zentroid ist um
    mindestens ``min_margin`` groesser (eindeutige Zuordnung, keine knappe
    Verwechslung). Genau das schliesst die in puzzle_detect dokumentierte, aber
    faktisch FALSCHE Disjunktheits-Annahme (kleinste Kanal-Luecke ist real 0,
    nicht 85) sauber ab: zwei farblich nahe Typen (z.B. 1<->6, Euklid ~90)
    werden nur akzeptiert, wenn die Messung klar bei einem liegt.
    """
    m = centroid_metrics(bgr, refs)
    nearest = m['nearest']
    if nearest is None:
        return None
    ref = refs[nearest]
    b, g, r = bgr
    within = (abs(b - ref[0]) <= tol and abs(g - ref[1]) <= tol
              and abs(r - ref[2]) <= tol)
    if not within:
        return None
    if m['margin'] is not None and m['margin'] < min_margin:
        return None
    return nearest


# -- Footprint / erwartetes Brett ----------------------------------------

def footprint(piece_type, anchor):
    """Belegte Zellen ``frozenset{(r, c)}`` beim Setzen von ``piece_type`` am
    Anker ``(x, y)`` (x=Zeile, y=Spalte) -- oder ``None`` bei out-of-bounds /
    unbekanntem Typ. Nutzt die Stein-Formen aus ``trained_solver``.
    """
    cells = _ts._FORMS.get(piece_type)
    if cells is None:
        return None
    try:
        x, y = int(anchor[0]), int(anchor[1])
    except (TypeError, ValueError, IndexError):
        return None
    out = set()
    for (dr, dc) in cells:
        r, c = x + dr, y + dc
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return None
        out.add((r, c))
    return frozenset(out)


def footprint_from_cells(form_cells, anchor):
    """Wie :func:`footprint`, aber fuer eine explizite Zell-Liste (z.B. den
    Deluxe-2x3-Stein ``deluxe.DELUXE_FORM``). ``None`` bei out-of-bounds."""
    try:
        x, y = int(anchor[0]), int(anchor[1])
    except (TypeError, ValueError, IndexError):
        return None
    out = set()
    for cell in form_cells:
        r, c = x + int(cell[0]), y + int(cell[1])
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return None
        out.add((r, c))
    return frozenset(out)


def expected_board_after(board, piece_type, anchor):
    """Neues Brett (Kopie) nachdem ``piece_type`` am Anker gesetzt wurde.

    Immutabel: gibt eine NEUE 4x6-Liste zurueck, ``board`` bleibt unberuehrt.
    ``None`` bei out-of-bounds ODER Ueberlappung mit bereits belegten Zellen.
    """
    fp = footprint(piece_type, anchor)
    if fp is None:
        return None
    new = [list(row) for row in board]
    for (r, c) in fp:
        if new[r][c]:
            return None  # Ueberlappung
        new[r][c] = 1
    return new


# -- Closed-Loop-Verifikation --------------------------------------------

def _occ_cells(board):
    return {(r, c) for r in range(ROWS) for c in range(COLS) if board[r][c]}


def verify_placement(prev_board, piece_type, anchor, actual_board):
    """Vergleicht das tatsaechlich gelesene Brett mit dem nach der Platzierung
    erwarteten und stuft das Ergebnis ein.

    Rueckgabe-Dict:
      * ``ok``: True, wenn das Ist-Brett exakt dem Soll entspricht
      * ``missing_footprint``: erwartete Stein-Zellen, die Ist-LEER sind
        (= der Stein liegt NICHT wie geplant -> starkes Fehlersignal)
      * ``unexpected``: Zellen, die sich ausserhalb des Footprints aenderten
        (schwaecheres Signal: Lese-Rauschen ODER Fehlplatzierung)
      * ``severity``: 'ok' | 'weak' | 'critical'
    ``anchor=None`` (kein interner Anker, z.B. Deluxe) -> nur Mengenvergleich
    ueber den Footprint via ``piece_type``-Form entfaellt; dann wird nur die
    Differenz prev->actual berichtet.
    """
    actual_occ = _occ_cells(actual_board)
    prev_occ = _occ_cells(prev_board)
    fp = footprint(piece_type, anchor) if anchor is not None else None

    if fp is not None:
        expected_occ = prev_occ | fp
        missing = sorted(c for c in fp if c not in actual_occ)
        unexpected = sorted((actual_occ ^ expected_occ) - set(missing))
    else:
        missing = []
        unexpected = sorted(actual_occ ^ prev_occ)

    if missing:
        severity = 'critical'
    elif unexpected:
        severity = 'weak'
    else:
        severity = 'ok'
    return {'ok': severity == 'ok', 'missing_footprint': missing,
            'unexpected': unexpected, 'severity': severity}


# -- Endspiel: 1-Zug-Komplettierbarkeit ----------------------------------

def piece_can_complete(board, piece_type):
    """True, wenn EINE Platzierung von ``piece_type`` das Brett VOLL macht."""
    placements = _ts._PLACE.get(piece_type)
    if not placements:
        return False
    occ = _ts._occ(board)
    for (_x, _y, m) in placements:
        if (occ & m) == 0 and (occ | m) == _FULL_MASK:
            return True
    return False


def one_piece_completable(board):
    """True, wenn IRGENDEIN Steintyp das Brett in einem Zug voll macht.

    Genau dann darf der Finish-Modus NICHT einen anderen (fragmentierenden)
    Stein erzwingen -- das war die im Log nachgewiesene Fehlentscheidung
    (ein Single zerstoerte ein in einem Zug per L-Stein fuellbares Loch).
    """
    return any(piece_can_complete(board, t) for t in _ts._FORMS)
