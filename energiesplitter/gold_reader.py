# -*- coding: utf-8 -*-
"""6-stelliger Gold-Reader mit Tausenderpunkt (Template-NCC, defensiv).

Der Gold-Zaehler im Spiel ist deutlich groesser/anders gerendert als die
Stack-Zahlen im Inventar (``inventory/digits.py`` kann nur <=4 Stellen OHNE
Tausenderpunkt). Dieser Reader ist ein EIGENES Modul (erweitert ``digits.py``
NICHT) fuer Zahlen wie ``312.295``:

  * **Template-basiert:** je Glyph (Ziffern 0..9 + ``.``) eigene NCC-Vorlagen aus
    ``energiesplitter/gold_digits/`` (Dateien ``<glyph>__<tag>.png``, weisse
    Glyph-Maske auf Schwarz; ``dot`` = Tausenderpunkt). Wie ``digits.py`` per
    fixed-width try-all-n, damit die kleine, eng gesetzte Spielschrift KEINE
    fragile Luecken-Segmentierung braucht.
  * **Defensiv -> ``int | None``:** kein Bild/keine Vorlagen/zu schwacher Match/
    implausibler Wert -> ``None`` (der Bot stoppt dann, statt blind zu kaufen).
    Wirft NIE.
  * **Tausenderpunkt:** der Punkt ist eine eigene, niedrige Glyph-Klasse; beim
    Decodieren wird er erkannt und aus der Ziffernfolge entfernt (``312.295`` ->
    ``312295``). Plausibilitaet: 1..6 Ziffern, Ergebnis in ``[0, 99_999_999]``.

PHASE-0: Die mitgelieferten Vorlagen wurden aus EINEM echten Screenshot
(Alchemist-Shop, "312.295") bootstrap-extrahiert und decken NICHT alle Ziffern
0..9 ab. ``detect.assets_ready`` meldet ``gold_digits`` deshalb weiter als
fehlend (Gate bleibt rot); der Reader funktioniert aber nachweisbar fuer die
vorhandenen Glyphen (Test gegen das echte Bild). Voller 0..9-Satz beider
Shop-Zustaende = P0.3-Lieferung.
"""

import os

from . import geometry as _geo

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


GOLD_DIGIT_DIR = os.path.join('energiesplitter', 'gold_digits')

CANON_H = 14          # kanonische Glyph-Hoehe fuers Matching (Upscale der ~7px-Schrift)
WHITE_MIN = 150       # min(B,G,R), ab dem ein Pixel zum weissen Ziffernkern zaehlt
INK_THR = 0.30        # Weiss-Anteil, ab dem ein Pixel als Tinte gilt
MIN_INK_PX = 4        # weniger Tinte als das im ROI = keine Zahl -> None
MIN_CELL_W = 2        # eine Ziffernzelle schmaler als das (kanon. px) ist Schrott
MAX_DIGITS = 6        # Gold <= 6 Stellen
CONF_MIN = 0.42       # schwaechste Zell-NCC, um einen Read 'confident' zu nennen
DIGIT_BAND_H = 7      # gemessene Glyph-Hoehe der Gold-Schrift (KALIBRIER-BAR)
DIGIT_H_TOL = 2       # Toleranz um DIGIT_BAND_H; groesser = Rahmen/Artefakt (verworfen)
DOT_MAX_H = 3         # Glyph-Hoehe <= das = Tausenderpunkt (kein Ziffer-Match)
GAP_NATIVE = 1        # leere Spaltenbreite, die zwei Glyphen trennt (nativ)
VALUE_MAX = 99_999_999

_TEMPLATES = None     # {'0'..'9': [mask], 'dot': [mask]}


def _gold_dir():
    """Loest das gebundelte Gold-Digit-Verzeichnis cwd-unabhaengig auf."""
    base = resource_path(GOLD_DIGIT_DIR)
    if os.path.isdir(base):
        return base
    here = os.path.dirname(os.path.abspath(__file__))
    fallback = os.path.join(here, 'gold_digits')
    return fallback if os.path.isdir(fallback) else base


def _load_templates():
    """Laedt + cached ``{glyph: [mask, ...]}`` aus ``gold_digits/*.png``.

    Dateiname ``<glyph>__<tag>.png``; ``<glyph>`` = Ziffer oder ``dot``. Maske =
    Graustufe in ``0..1``, auf ``CANON_H`` hoehen-normiert. Kein Verzeichnis/
    keine Bibliothek -> ``{}`` (Reader liefert dann ``None``). Wirft nie.
    """
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    out = {}
    if np is None or _cv is None:
        _TEMPLATES = out
        return out
    base = _gold_dir()
    try:
        names = sorted(os.listdir(base))
    except Exception:
        _TEMPLATES = out
        return out
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
    """Liest den Gold-Wert aus ``roi=(x,y,w,h)`` (im 800x600-Client).

    ``bgr`` wird zuerst ``geometry.to_client``-normiert (Fixtures sind 802x632),
    dann der ROI ausgeschnitten und per Luecken-Segmentierung + Template-NCC
    dekodiert. Liefert ``int`` bei plausiblem, hinreichend sicherem Read; sonst
    ``None`` (leer / Vorlagen fehlen / zu schwacher Match / implausibel). Wirft NIE.
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


def templates_complete():
    """``True`` nur, wenn ALLE Ziffern 0..9 + ``dot`` als Vorlage vorliegen.

    Phase-0-Helfer fuer ``detect.assets_ready``: der gebootstrappte Satz ist
    unvollstaendig -> liefert ``False`` -> Gate bleibt korrekt rot.
    """
    templates = _load_templates()
    if not templates:
        return False
    needed = set(str(d) for d in range(10)) | {'dot'}
    return needed.issubset(set(templates.keys()))


__all__ = ['read_gold', 'templates_complete', 'ROI_GOLD']
ROI_GOLD = _geo.ROI_GOLD
