"""Erzeugt das mitgelieferte Kalibrier-Referenzbild ``images/calibration_reference.png``.

Aus einem sauberen Puzzle-Screenshot (``Puzzlebilder/cleanboardandboxes.png``)
wird ein ANNOTIERTES Vorlage-Bild gebaut: die **24 Rasterpunkte** der 4x6-
Zellmitten und die **4 Sonderpunkte** (``color`` / ``getpiece`` / ``confirm`` /
``cake``) werden farbig markiert und beschriftet. Das Bild dient als visuelle
Referenz/Vorschau fuer das resizable Mark-Overlay (``overlay_mark``) und
dokumentiert, WAS der Nutzer beim Kalibrieren markiert.

Die 24 Rasterpunkte werden NICHT blind aus der 260x170-Referenzgeometrie
skaliert (deren Seitenverhaeltnis weicht vom realen Screenshot ab), sondern auf
die im Bild tatsaechlich erkannten Zell-Mittelpunkte gelegt: das Raster wird
ueber seine horizontalen/vertikalen Trennlinien detektiert und die Zellmitten
als Linien-Mittelpunkte bestimmt. Schlaegt die Detektion fehl (untypisches
Bild), wird auf eine konservative Standard-Board-Box zurueckgefallen.

Die 4 Sonderpunkte werden ueber die bewaehrte ``geometry.scale_point``-Maschine
aus ihren 260x170-REF-Konstanten in die erkannte Board-Pixelbox abgebildet --
genau die Abbildung, die ``puzzle.py`` zur Laufzeit nutzt.

Aufruf::

    python3 make_reference.py            # nutzt Default-Quelle/-Ziel
    python3 make_reference.py SRC DST    # explizite Pfade

Bewusst defensiv: PIL ist erforderlich (reines Build-/Vorlagen-Tool, kein
Laufzeitpfad des Bots), numpy wird WEICH genutzt (Fallback ohne Detektion),
``cv2`` wird gar nicht gebraucht und nur optional/weich beruehrt, damit das
Modul ``py_compile``-bar und in headless-CI importierbar bleibt.
"""

import os
import sys

import geometry

# numpy weich: die Rasterlinien-Detektion nutzt es, ist aber optional. Ohne
# numpy faellt das Tool auf eine feste Standard-Board-Box zurueck.
try:
    import numpy as np
except Exception:  # pragma: no cover - Fallback ohne Detektion
    np = None

# PIL ist fuer dieses Vorlagen-Tool erforderlich (kein Bot-Laufzeitpfad).
from PIL import Image, ImageDraw, ImageFont


# -- Pfade -----------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.normpath(
    os.path.join(_HERE, '..', 'Puzzlebilder', 'cleanboardandboxes.png'))
DEFAULT_DST = os.path.join(_HERE, 'images', 'calibration_reference.png')


# -- Stil ------------------------------------------------------------------

# Farben (RGB) der 4 Sonderpunkte + lesbare Kurz-Labels.
KEYPOINT_STYLE = {
    'color':    ('color',    (245, 158, 11)),   # Amber  - Stein-Farb-Sample
    'getpiece': ('getpiece', (59, 130, 246)),   # Blue   - Feld-voll / neuer Stein
    'confirm':  ('confirm',  (34, 197, 94)),    # Green  - Bestaetigen/Wegwerfen
    'cake':     ('cake',     (236, 72, 153)),   # Pink   - Belohnung
}

GRID_DOT_RADIUS = 4
GRID_DOT_FILL = (45, 212, 191)        # Teal
GRID_DOT_OUTLINE = (248, 250, 252)    # fast Weiss

KEYPOINT_RADIUS = 7

# REF-Konstanten der Sonderpunkte (aus geometry, mit defensivem Fallback).
REF_KEYPOINTS = {
    'color':    getattr(geometry, 'REF_COLOR_SAMPLE', (110, 150)),
    'getpiece': getattr(geometry, 'REF_GET_PIECE', (230, 85)),
    'confirm':  getattr(geometry, 'REF_CONFIRM', (100, 90)),
    'cake':     getattr(geometry, 'REF_CAKE', (120, 90)),
}


def _load_font(size):
    """Liefert eine TrueType-Schrift, faellt auf die PIL-Default-Schrift zurueck."""
    for name in ('DejaVuSans.ttf', 'Arial.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# -- Raster-Detektion ------------------------------------------------------

def _detect_grid_lines(rgb):
    """Detektiert die vertikalen/horizontalen Rasterlinien des Boards.

    Erwartet ein numpy-RGB-Array ``(H, W, 3)``. Beschraenkt sich auf die linke
    Board-Haelfte (die rechten Belohnungs-Boxen werden ausgeblendet). Liefert
    ``(xs, ys)`` mit je 6 bzw. 4 Zell-Mittelpunkten oder ``None``, wenn die
    erwartete Linienzahl (7 vertikale, 5 horizontale) nicht gefunden wird.
    """
    if np is None:
        return None
    try:
        gray = rgb.astype('float32').mean(axis=2)
        height, width = gray.shape

        # Rechte Boxen ausblenden: dort steigt die Spaltenhelligkeit DAUERHAFT
        # an (anders als eine einzelne helle Rasterlinie). Erst wenn ein ganzes
        # Fenster oberhalb der Schwelle liegt, gilt der Board-Bereich als zu
        # Ende -- so wird die letzte Rasterlinie nicht faelschlich abgeschnitten.
        col_mean_full = gray.mean(axis=0)
        board_level = float(np.median(col_mean_full[:int(width * 0.5)]))
        window = 12
        threshold = board_level * 2.5
        board_right = width
        for x in range(int(width * 0.6), width - window):
            if bool(np.all(col_mean_full[x:x + window] > threshold)):
                board_right = x
                break
        # Etwas Sicherheitsmarge, damit der helle Box-Rahmen ausgeschlossen
        # bleibt (er liegt direkt vor den Boxen).
        board_right = max(int(width * 0.5), board_right - 25)

        board = gray[:, :board_right]
        col = board.mean(axis=0)
        row = board.mean(axis=1)

        xs_lines = _line_peaks(col)
        ys_lines = _line_peaks(row)

        if len(xs_lines) != geometry.GRID_COLS + 1:
            return None
        if len(ys_lines) != geometry.GRID_ROWS + 1:
            return None

        xs = [(xs_lines[k] + xs_lines[k + 1]) / 2.0
              for k in range(geometry.GRID_COLS)]
        ys = [(ys_lines[k] + ys_lines[k + 1]) / 2.0
              for k in range(geometry.GRID_ROWS)]
        return xs, ys
    except Exception:
        return None


def _line_peaks(profile):
    """Findet helle Linien-Peaks in einem 1D-Helligkeitsprofil.

    Ein Peak ist ein lokales Maximum oberhalb einer Schwelle (Mittel + 20% der
    Spannweite), mit Mindestabstand zum vorigen Peak. Robust gegen Rauschen.
    """
    prof = np.asarray(profile, dtype='float32')
    if prof.size < 3:
        return []
    thr = float(prof.mean() + (prof.max() - prof.mean()) * 0.2)
    min_dist = max(10, int(prof.size * 0.04))
    peaks = []
    for x in range(1, prof.size - 1):
        if prof[x] >= prof[x - 1] and prof[x] >= prof[x + 1] and prof[x] > thr:
            if not peaks or (x - peaks[-1]) >= min_dist:
                peaks.append(x)
    return peaks


def _board_box_from_lines(xs, ys, img_size):
    """Leitet aus den Zellmitten die Board-Pixelbox ``(bx, by, bw, bh)`` ab.

    Aus ``gridTL``/``gridBR`` (erste/letzte Zellmitte) wird ueber das 15+32-in-
    260-Modell die Crop-Box rekonstruiert -- dieselbe Logik wie im Overlay.
    """
    grid_tl = (xs[0], ys[0])
    grid_br = (xs[-1], ys[-1])
    span_x = grid_br[0] - grid_tl[0]
    span_y = grid_br[1] - grid_tl[1]
    ref_span_x = geometry.GRID_STEP * (geometry.GRID_COLS - 1)   # 160
    ref_span_y = geometry.GRID_STEP * (geometry.GRID_ROWS - 1)   # 96
    scale_x = span_x / ref_span_x
    scale_y = span_y / ref_span_y
    origin = geometry.GRID_ORIGIN
    ref_w, ref_h = geometry.REF_SIZE
    bx = grid_tl[0] - origin * scale_x
    by = grid_tl[1] - origin * scale_y
    return (bx, by, ref_w * scale_x, ref_h * scale_y)


def _fallback_board_box(img_size):
    """Konservative Board-Box, falls die Linien-Detektion scheitert.

    Nimmt die linken ~75% der Bildbreite (Board) mit etwas Rand als Board.
    """
    width, height = img_size
    bx = width * 0.01
    by = height * 0.01
    bw = width * 0.75
    bh = height * 0.97
    return (bx, by, bw, bh)


# -- Punkt-Berechnung ------------------------------------------------------

def _grid_screen_points(xs, ys):
    """Die 24 Rasterpunkte als (label_i, label_j, x, y) aus erkannten Mitten."""
    points = []
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            points.append((i, j, x, y))
    return points


def _grid_points_from_box(box):
    """Fallback: 24 Rasterpunkte ueber geometry.scale_point in die Board-Box."""
    bx, by, bw, bh = box
    points = []
    for i in range(geometry.GRID_ROWS):
        for j in range(geometry.GRID_COLS):
            rx, ry = geometry.cell_ref(i, j)
            x = bx + rx * bw / geometry.REF_SIZE[0]
            y = by + ry * bh / geometry.REF_SIZE[1]
            points.append((i, j, x, y))
    return points


def _keypoint_screen_point(ref, box):
    """REF-Sonderpunkt -> Board-Pixel ueber dieselbe Skalierung wie puzzle.py."""
    bx, by, bw, bh = box
    x = bx + ref[0] * bw / geometry.REF_SIZE[0]
    y = by + ref[1] * bh / geometry.REF_SIZE[1]
    return (x, y)


# -- Zeichnen --------------------------------------------------------------

def _draw_dot(draw, x, y, radius, fill, outline, width=1):
    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 fill=fill, outline=outline, width=width)


def _draw_label(draw, x, y, text, color, font, img_w, img_h):
    """Zeichnet ein kleines Label nahe ``(x, y)``, im Bild gehalten."""
    if font is None:
        return
    # Label rechts-oberhalb des Punktes; bei Bildrand nach innen klappen.
    lx = x + 8
    ly = y - 14
    top = 0
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        top = bbox[1]
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = (len(text) * 6, 10)
    if lx + tw > img_w:
        lx = x - 8 - tw
    if ly < 0:
        ly = y + 8
    # Lesehilfe (dunkler Kasten) hinter der Schrift fuer Kontrast.
    pad = 2
    draw.rectangle([lx - pad, ly - pad, lx + tw + pad, ly + th + pad],
                   fill=(16, 20, 24))
    # ``top`` korrigiert den Schrift-Innenversatz, damit der Text im Kasten sitzt.
    draw.text((lx, ly - top), text, fill=color, font=font)


def build_reference(src_path=DEFAULT_SRC, dst_path=DEFAULT_DST):
    """Baut das annotierte Referenzbild und speichert es nach ``dst_path``.

    :return: der Zielpfad (``dst_path``).
    :raises FileNotFoundError: wenn die Quelle fehlt.
    """
    if not os.path.exists(src_path):
        raise FileNotFoundError(
            'Quellbild nicht gefunden: {}'.format(src_path))

    img = Image.open(src_path).convert('RGB')
    img_w, img_h = img.size
    draw = ImageDraw.Draw(img)
    font = _load_font(11)

    # 1) Raster bestimmen: bevorzugt aus erkannten Linien, sonst Fallback-Box.
    detected = None
    if np is not None:
        detected = _detect_grid_lines(np.asarray(img))

    if detected is not None:
        xs, ys = detected
        grid_points = _grid_screen_points(xs, ys)
        box = _board_box_from_lines(xs, ys, (img_w, img_h))
        source = 'detected grid lines'
    else:
        box = _fallback_board_box((img_w, img_h))
        grid_points = _grid_points_from_box(box)
        source = 'fallback board box'

    # 2) Board-Crop-Rahmen leicht andeuten (Orientierung).
    bx, by, bw, bh = box
    draw.rectangle([bx, by, bx + bw, by + bh], outline=(20, 184, 166), width=1)

    # 3) 24 Rasterpunkte markieren + beschriften (R0C0 .. R3C5).
    for (i, j, x, y) in grid_points:
        _draw_dot(draw, x, y, GRID_DOT_RADIUS, GRID_DOT_FILL,
                  GRID_DOT_OUTLINE, width=1)
    # Eckpunkte zusaetzlich beschriften, damit die Vorlage selbsterklaerend ist.
    corners = {(0, 0): 'TL (0,0)',
               (0, geometry.GRID_COLS - 1): 'TR (0,5)',
               (geometry.GRID_ROWS - 1, 0): 'BL (3,0)',
               (geometry.GRID_ROWS - 1, geometry.GRID_COLS - 1): 'BR (3,5)'}
    for (i, j, x, y) in grid_points:
        if (i, j) in corners:
            _draw_label(draw, x, y, corners[(i, j)], (248, 250, 252),
                        font, img_w, img_h)

    # 4) 4 Sonderpunkte markieren + beschriften.
    for key in ('color', 'getpiece', 'confirm', 'cake'):
        label, color = KEYPOINT_STYLE[key]
        x, y = _keypoint_screen_point(REF_KEYPOINTS[key], box)
        # Auf dem Bild halten (Vorlage soll alle Marker zeigen).
        x = min(max(x, KEYPOINT_RADIUS), img_w - KEYPOINT_RADIUS)
        y = min(max(y, KEYPOINT_RADIUS), img_h - KEYPOINT_RADIUS)
        _draw_dot(draw, x, y, KEYPOINT_RADIUS, None, color, width=2)
        # Fadenkreuz fuer praezise Lage.
        draw.line([x - KEYPOINT_RADIUS - 3, y, x + KEYPOINT_RADIUS + 3, y],
                  fill=color, width=1)
        draw.line([x, y - KEYPOINT_RADIUS - 3, x, y + KEYPOINT_RADIUS + 3],
                  fill=color, width=1)
        _draw_label(draw, x, y, label, color, font, img_w, img_h)

    # 5) Titel-Zeile oben links.
    if font is not None:
        title = 'Calibration reference  -  24 grid points + 4 special points'
        draw.rectangle([0, 0, img_w, 16], fill=(16, 20, 24))
        draw.text((4, 2), title, fill=(248, 250, 252), font=font)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    img.save(dst_path)
    print('Wrote {} ({}x{}, grid from {}).'.format(
        dst_path, img_w, img_h, source))
    return dst_path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    src = argv[0] if len(argv) >= 1 else DEFAULT_SRC
    dst = argv[1] if len(argv) >= 2 else DEFAULT_DST
    try:
        build_reference(src, dst)
        return 0
    except Exception as exc:
        print('make_reference failed: {}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
