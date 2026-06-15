# -*- coding: utf-8 -*-
"""Yang-Reader unten rechts (RECHTE Zahl) -- Template-NCC, defensiv.

Waehrung = **YANG** (Grundwahrheit 2026-06-15). Unten rechts stehen ZWEI Zahlen:
die LINKE ist *Won* (1 Won = 100 Mio Yang, muss erst getauscht werden) und wird
fuer Ausgaben IGNORIERT; die RECHTE Zahl ist das rohe Yang (deutsches Format mit
``.`` als Tausendertrenner, z.B. ``207.295``). Dieser Reader liest die RECHTE
Zahl aus der ROI ``calibration.yang_roi()`` (== ``geometry.ROI_GOLD``).

Der Yang-Zaehler ist groesser/anders gerendert als die Stack-Zahlen im Inventar
(``inventory/digits.py`` kann nur <=4 Stellen OHNE Tausenderpunkt). Dieser Reader
ist ein EIGENES Modul (erweitert ``digits.py`` NICHT):

  * **Template-basiert:** je Glyph (Ziffern 0..9 + ``.``) eigene NCC-Vorlagen.
    Primaere Quelle = ``energiesplitter/templates/yang_digits/`` (aus beiden
    Inventar-Fixtures extrahiert), zusaetzlich der Alt-Satz
    ``energiesplitter/gold_digits/`` (Glyph-Union, damit auch der alte
    Shop-Screenshot ``312.295`` weiter dekodiert). Dateien ``<glyph>__<tag>.png``
    (weisse Glyph-Maske auf Schwarz; ``dot`` = Tausenderpunkt). Luecken-
    Segmentierung statt fragiler Fix-Segmente.
  * **Defensiv -> ``int | None``:** kein Bild/keine Vorlagen/fehlende Ziffer/zu
    schwacher Match/implausibler Wert -> ``None`` (der Bot stoppt dann, statt
    blind zu kaufen). Wirft NIE.
  * **Tausenderpunkt:** der Punkt ist eine eigene, niedrige Glyph-Klasse; beim
    Decodieren wird er erkannt und aus der Ziffernfolge entfernt (``207.295`` ->
    ``207295``). Plausibilitaet: 1..6 Ziffern, Ergebnis in ``[0, 99_999_999]``.

PHASE-0 (ehrlich): Die Belegbilder decken nur die in den Yang-Zahlen
vorkommenden Ziffern ab -- vorhanden sind ``0,1,2,3,5,7,9`` + ``dot``, es FEHLEN
``4, 6, 8`` (kein Beleg). Eine Zahl mit fehlender Ziffer -> ``None`` (Stopp statt
Blind-Kauf), und ``templates_complete()`` bleibt deshalb ``False`` -> das
Phase-0-Gate (``detect.assets_ready``) meldet ``gold_digits`` weiter als fehlend
(bleibt korrekt rot). TODO-live-asset (P0.3): Belegbilder fuer 4/6/8 nachliefern.
"""

import os

from . import geometry as _geo

try:  # pragma: no cover - Kalibrierung (ROI/Grid); defensiv fuer Import-Robustheit
    from . import calibration as _cal
except Exception:  # pragma: no cover
    _cal = None

try:  # pragma: no cover
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:  # pragma: no cover
    import cv2 as _cv
except Exception:  # pragma: no cover
    _cv = None

try:  # pragma: no cover
    from respath import resource_path
except Exception:  # pragma: no cover
    def resource_path(rel):
        return rel


# Glyph-Verzeichnisse (relativ zum Repo-Root fuer resource_path; absolut als
# Fallback ueber __file__). Reihenfolge = Lade-Reihenfolge; die yang_digits sind
# die primaere, an den Inventar-Fixtures gemessene Quelle.
YANG_DIGIT_DIR = os.path.join('energiesplitter', 'templates', 'yang_digits')
GOLD_DIGIT_DIR = os.path.join('energiesplitter', 'gold_digits')
DIGIT_DIRS = (YANG_DIGIT_DIR, GOLD_DIGIT_DIR)

CANON_H = 14          # kanonische Glyph-Hoehe fuers Matching (Upscale der ~7px-Schrift)
WHITE_MIN = 150       # min(B,G,R), ab dem ein Pixel zum weissen Ziffernkern zaehlt
INK_THR = 0.30        # Weiss-Anteil, ab dem ein Pixel als Tinte gilt
MIN_INK_PX = 4        # weniger Tinte als das im ROI = keine Zahl -> None
MIN_CELL_W = 2        # eine Ziffernzelle schmaler als das (kanon. px) ist Schrott
MAX_DIGITS = 6        # Gold <= 6 Stellen
# Schwaechste Zell-NCC, ab der ein Read 'confident' ist. An den echten Yang-/
# Gold-Glyphen gemessen: KORREKTE Ziffer ~1.000, zweitbeste (inkl. der NICHT
# vorhandenen 4/6/8, die auf den naechsten Nachbarn fallen) <= ~0.60. Floor 0.85
# sitzt sicher in dieser Luecke -> eine fehlende/uneindeutige Ziffer -> None
# (kein Blind-Kauf), die belegten Ziffern bleiben weit ueber der Schwelle.
CONF_MIN = 0.85
DIGIT_BAND_H = 7      # gemessene Glyph-Hoehe der Gold-Schrift (KALIBRIER-BAR)
DIGIT_H_TOL = 2       # Toleranz um DIGIT_BAND_H; groesser = Rahmen/Artefakt (verworfen)
DOT_MAX_H = 3         # Glyph-Hoehe <= das = Tausenderpunkt (kein Ziffer-Match)
GAP_NATIVE = 1        # leere Spaltenbreite, die zwei Glyphen trennt (nativ)
VALUE_MAX = 99_999_999

_TEMPLATES = None     # {'0'..'9': [mask], 'dot': [mask]}


def _resolve_dir(rel):
    """Loest ein gebundeltes Digit-Verzeichnis cwd-unabhaengig auf (resource_path
    zuerst, dann ``__file__``-relativ). Wirft nie."""
    base = resource_path(rel)
    if os.path.isdir(base):
        return base
    here = os.path.dirname(os.path.abspath(__file__))
    fallback = os.path.join(here, *rel.split(os.sep)[1:])
    return fallback if os.path.isdir(fallback) else base


def _digit_dirs():
    """Existierende Glyph-Verzeichnisse (yang_digits primaer, gold_digits Alt)."""
    out = []
    for rel in DIGIT_DIRS:
        d = _resolve_dir(rel)
        if os.path.isdir(d):
            out.append(d)
    return out


def _load_templates():
    """Laedt + cached ``{glyph: [mask, ...]}`` aus den Digit-Verzeichnissen.

    Liest die Glyph-Union aus ``templates/yang_digits/`` (primaer) UND
    ``gold_digits/`` (Alt-Satz). Dateiname ``<glyph>__<tag>.png``; ``<glyph>`` =
    Ziffer oder ``dot``. Maske = Graustufe in ``0..1``, auf ``CANON_H``
    hoehen-normiert. Kein Verzeichnis/keine Bibliothek -> ``{}`` (Reader liefert
    dann ``None``). Wirft nie.
    """
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    out = {}
    if np is None or _cv is None:
        _TEMPLATES = out
        return out
    for base in _digit_dirs():
        try:
            names = sorted(os.listdir(base))
        except Exception:
            continue
        for name in names:
            if not name.lower().endswith('.png') or '__' not in name:
                continue
            glyph = name.split('__', 1)[0]
            if glyph != 'dot' and not (len(glyph) == 1 and glyph.isdigit()):
                continue
            path = os.path.join(base, name)
            try:
                arr = _cv.imread(path, _cv.IMREAD_GRAYSCALE)
                if arr is None:
                    continue
                arr = arr.astype(np.float32) / 255.0
                norm = _norm_to_canon(arr)
                if norm is None:
                    continue
            except Exception:
                continue
            out.setdefault(glyph, []).append(norm)
    _TEMPLATES = out
    return out


def _white_mask(band_bgr):
    """Weiss-Anteil ``0..1`` eines BGR-Bands (hoch nur, wo alle Kanaele hoch)."""
    arr = np.asarray(band_bgr, dtype=np.float32)
    if arr.ndim == 2:
        mn = arr
    else:
        mn = arr.min(axis=2)
    return np.clip((mn - WHITE_MIN) / (255.0 - WHITE_MIN), 0.0, 1.0)


def _ink_bbox(mask):
    ys, xs = np.where(mask > INK_THR)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1


def _norm_to_canon(mask):
    """Crop auf Tinte + auf ``CANON_H`` Hoehe skalieren (Seitenverhaeltnis). ``None`` leer."""
    bb = _ink_bbox(mask)
    if bb is None:
        return None
    x0, x1, y0, y1 = bb
    crop = mask[y0:y1, x0:x1]
    new_w = max(MIN_CELL_W,
                int(round(crop.shape[1] * CANON_H / max(1, crop.shape[0]))))
    im = _cv.resize((crop * 255).astype('uint8'), (new_w, CANON_H),
                    interpolation=_cv.INTER_LINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0


def _ncc(a, b):
    """Normalisierte Kreuzkorrelation (b auf a-Groesse gebracht)."""
    if b.shape != a.shape:
        b = _cv.resize((b * 255).astype('uint8'), (a.shape[1], a.shape[0]),
                       interpolation=_cv.INTER_LINEAR).astype(np.float32) / 255.0
    a = a - a.mean(); b = b - b.mean()
    da = float(np.sqrt((a * a).sum())); db = float(np.sqrt((b * b).sum()))
    if da < 1e-6 or db < 1e-6:
        return 0.0
    return float((a * b).sum() / (da * db))


def _classify_cell(cellmask, templates):
    """Bestes ``(digit, score)`` fuer eine normierte Ziffern-Zelle, oder ``None``.

    Klassifiziert NUR gegen Ziffern-Vorlagen (der Tausenderpunkt wird separat per
    Glyph-Hoehe erkannt, siehe ``_decode``) -> eine schmale Ziffer kann nicht
    faelschlich als ``dot`` gelesen werden.
    """
    cn = _norm_to_canon(cellmask)
    if cn is None:
        return None
    best_g, best_s = None, -1.0
    for glyph, tmpls in templates.items():
        if glyph == 'dot':
            continue
        s = max(_ncc(cn, tm) for tm in tmpls)
        if s > best_s:
            best_s, best_g = s, glyph
    if best_g is None:
        return None
    return best_g, best_s


def _segment(mask):
    """Zerlegt eine Tinten-Maske in Glyph-Spalten-Spans (Luecken-Segmentierung).

    Die Gold-Schrift ist in der nativen Aufloesung durch leere Spalten getrennt
    (gemessen). Liefert ``[(x0, x1), ...]`` der Tinten-Laeufe. Wirft nie.
    """
    col = (mask > INK_THR).sum(0)
    spans = []
    inrun = False
    start = 0
    for i, c in enumerate(col):
        if c > 0 and not inrun:
            start = i; inrun = True
        elif c == 0 and inrun:
            spans.append((start, i)); inrun = False
    if inrun:
        spans.append((start, len(col)))
    return spans


def _decode(mask, templates):
    """Luecken-Segmentierung -> ``(text, weakest_score)`` (Ziffern + '.').

    Jeder Span wird klassifiziert; Spans mit Glyph-Hoehe ausserhalb der Ziffern-
    band-Toleranz (z.B. der Fenster-Rahmen) werden VERWORFEN, nicht falsch als
    Ziffer gelesen. Sehr niedrige Spans (<= DOT_MAX_H) sind der Tausenderpunkt.
    """
    spans = _segment(mask)
    if not spans:
        return '', 0.0
    glyphs, scores = [], []
    for x0, x1 in spans:
        seg = mask[:, x0:x1]
        ys = np.where((seg > INK_THR).any(1))[0]
        if len(ys) == 0:
            continue
        gh = int(ys.max() - ys.min() + 1)
        if gh <= DOT_MAX_H:
            glyphs.append('.'); scores.append(1.0)
            continue
        if abs(gh - DIGIT_BAND_H) > DIGIT_H_TOL:
            # Hoehe passt zu keiner Ziffer (Rahmen/Artefakt) -> verwerfen.
            continue
        m = _classify_cell(seg, templates)
        if m is None or m[0] == 'dot':
            return '', 0.0
        glyphs.append(m[0]); scores.append(m[1])
    if not scores:
        return '', 0.0
    # Nur Ziffern-Scores zaehlen fuer das Confidence-Gate (Punkt ist formfrei).
    digit_scores = [s for g, s in zip(glyphs, scores) if g != '.']
    weak = min(digit_scores) if digit_scores else 0.0
    return ''.join(glyphs), weak


def read_gold(bgr, roi):
    """Liest die Yang-/Zahl aus ``roi=(x,y,w,h)`` (im 800x600-Client).

    ``bgr`` wird zuerst ``geometry.to_client``-normiert (Fixtures sind 802x632),
    dann der ROI ausgeschnitten und per Luecken-Segmentierung + Template-NCC
    dekodiert. Liefert ``int`` bei plausiblem, hinreichend sicherem Read; sonst
    ``None`` (leer / Vorlagen fehlen / fehlende Ziffer / zu schwacher Match /
    implausibel). Wirft NIE.

    Hinweis: Der ROI deckt sich mit der RECHTEN Yang-Zahl (``geometry.ROI_GOLD``
    == ``calibration.yang_roi()``); der Name ``read_gold`` bleibt nur aus
    Rueckwaerts-Kompatibilitaet (Bot/Tests). Fuer neuen Code: ``read_yang``.
    """
    if np is None or _cv is None or bgr is None or roi is None:
        return None
    templates = _load_templates()
    if not templates:
        return None
    client = _geo.to_client(bgr)
    sub = _geo.crop(client, roi)
    if sub is None:
        return None
    try:
        mask = _white_mask(sub)
        if int((mask > INK_THR).sum()) < MIN_INK_PX:
            return None
        text, weak = _decode(mask, templates)
    except Exception:
        return None
    digits = text.replace('.', '')
    if not digits.isdigit() or not (1 <= len(digits) <= MAX_DIGITS):
        return None
    if weak < CONF_MIN:
        return None
    try:
        value = int(digits)
    except Exception:
        return None
    if value < 0 or value > VALUE_MAX:
        return None
    return value


def read_yang(bgr, roi=None):
    """Liest die RECHTE Yang-Zahl (rohes Yang) als ``int`` oder ``None``.

    Primaere oeffentliche API dieses Moduls. ``roi=None`` -> die kalibrierte
    Yang-ROI ``calibration.yang_roi()`` (Fallback ``geometry.ROI_GOLD``, beide
    identisch). Won (LINKE Zahl) wird NICHT gelesen -- der ROI deckt nur die
    rechte Zahl ab. Defensiv: alles Unsichere/Implausible -> ``None`` (der Bot
    stoppt dann, statt blind zu kaufen). Wirft NIE.
    """
    if roi is None:
        roi = _yang_roi()
    return read_gold(bgr, roi)


def _yang_roi():
    """Kalibrierte Yang-ROI; faellt defensiv auf ``geometry.ROI_GOLD`` zurueck."""
    if _cal is not None:
        try:
            r = _cal.yang_roi()
            if r is not None:
                return r
        except Exception:
            pass
    return _geo.ROI_GOLD


def templates_complete():
    """``True`` nur, wenn ALLE Ziffern 0..9 + ``dot`` als Vorlage vorliegen.

    Phase-0-Helfer fuer ``detect.assets_ready``: der Belegsatz ist unvollstaendig
    (es fehlen 4/6/8) -> liefert ``False`` -> Gate bleibt korrekt rot, bis die
    fehlenden Ziffern-Templates nachgeliefert sind.
    """
    templates = _load_templates()
    if not templates:
        return False
    needed = set(str(d) for d in range(10)) | {'dot'}
    return needed.issubset(set(templates.keys()))


def _grid_present():
    """``True``, wenn die Inventar-Grid-Geometrie aufloesbar ist (Slot 1 -> Pixel).

    Reiner Kalibrier-Check (calibration.slot_center): liefert ``False``, wenn die
    Kalibrierung fehlt/keinen plausiblen Punkt ergibt. Wirft nie.
    """
    if _cal is None:
        return False
    try:
        c = _cal.slot_center(1)
    except Exception:
        return False
    return (isinstance(c, (tuple, list)) and len(c) == 2
            and all(isinstance(v, int) for v in c)
            and c[0] > 0 and c[1] > 0)


def is_calibrated(bgr, roi=None):
    """``True`` nur, wenn das Yang LESBAR ist UND das Grid vorhanden ist.

    Kalibrier-Selbstcheck auf einem konkreten Frame ``bgr`` (kein WindowCapture):
    1. ``read_yang(bgr, roi)`` liefert einen plausiblen Wert (RECHTE Zahl lesbar),
    2. ``calibration.slot_center(1)`` loest in einen gueltigen Pixel auf (Grid da).
    Schlaegt eines fehl -> ``False`` (defensiv; nie raten). Read-only, wirft nie.

    Abgrenzung: ``geometry.is_calibrated(wincap)`` prueft die FENSTER-Groesse
    (~800x600) -- das hier prueft die INHALTLICHE Lesbarkeit am echten Frame.
    """
    try:
        if read_yang(bgr, roi) is None:
            return False
        return _grid_present()
    except Exception:  # pragma: no cover - defensiv
        return False


__all__ = ['read_yang', 'read_gold', 'is_calibrated', 'templates_complete',
           'ROI_GOLD', 'ROI_YANG']
ROI_GOLD = _geo.ROI_GOLD
ROI_YANG = _geo.ROI_GOLD
