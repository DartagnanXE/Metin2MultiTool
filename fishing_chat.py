# -*- coding: utf-8 -*-
"""Chat-OCR-Kern: liest die unterste (neueste) Chat-Zeile des Metin2-Angelns und
sagt, WAS gerade am Haken haengt -- Fisch, Item, Niete oder (noch) nichts.

Warum kein echtes OCR? Die Metin2-Chat-Schrift ist ein fester Pixel-Font: ein
NAME (und die Satz-Bausteine) rendert IMMER bit-genau gleich. Deshalb genuegt ein
robuster Pixel-Vergleich gegen eine kleine, aus echten Screenshots extrahierte
Vorlagen-Bibliothek (maskiertes NCC / mean-abs-diff -- dieselbe Idee wie der
Inventar-Matcher). Reines ``numpy`` / ``PIL`` (``cv2`` optional), KEIN Tesseract.

Pipeline (an echten Daten verifiziert)::

    Capture (BGR) --crop--> Graustufen --> Binaer(>135=Tinte)
        --Spaltenprojektion--> Zeichen-Segmente --gruppieren(Luecke>3=Wortgrenze)-->
        Woerter
    Wort[4] (nie vom linken Rand beschnitten) -> Nachrichtentyp:
        "haette" -> Fisch    NAME = Woerter[5 .. -2]   (vor "angebissen.")
        "hinge"  -> Item     NAME = Woerter[5 .. -3]   (vor "am Haken.")
        "du"     -> NIETE    (kein Name)
        "koeder" -> KEIN_BISS (nur Koeder befestigt -> warten)
    NAME-Bitmap gegen Vorlagen matchen -> sicherer Treffer ODER UNKNOWN.

KALIBRIERUNG (verifiziert): es gibt ZWEI Frame-Groessen. Die gelabelten
Referenz-Shots (FischOCR/*.png) sind 802x632 = VOLLBILD MIT ~31px Windows-
Titelleiste + 1px-Rand; dort liegt die unterste Chat-Zeile in x[115,405],
y[579,596] (darueber ab ~y597 die Hotbar -- nicht reinrutschen). Der LIVE-Capture
von :class:`windowcapture.WindowCapture` ist dagegen der reine CLIENT-Bereich
(800x601, OHNE Titelleiste) -- also ~31px kuerzer; die Chat-Zeile liegt dort bei
y[548,565]. Damit DIESELBE Region beide trifft, wird die y-Region an den UNTEREN
Frame-Rand verankert (``y = frame_height - Konstante``, siehe
:func:`chat_region_for_frame`): bit-stabil auf 632, automatisch passend auf 601.

ROBUSTHEIT (kritisch): Lieber UNKNOWN als ein falscher Name. Der Aufrufer angelt
UNKNOWN ganz normal -- so wird NIE versehentlich ein gewollter Fisch abgebrochen.
Wie der restliche Bestandscode wirft hier nichts: jede Stufe faellt defensiv auf
ein "kein/unsicherer Treffer"-Ergebnis zurueck.
"""

import os

import numpy as np

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:                       # pragma: no cover - headless ohne Pillow
    _HAS_PIL = False

try:
    from respath import resource_path
except Exception:                       # pragma: no cover - standalone import
    def resource_path(rel):
        return rel


# -- Ergebnis-Typen ------------------------------------------------------

# kind-Werte des Lese-Ergebnisses.
FISH = 'fish'
ITEM = 'item'
NIETE = 'niete'
NONE = 'none'

# Sentinel-Name, wenn ein Biss erkannt wurde, der Name aber NICHT sicher ist.
# Der Aufrufer behandelt diesen wie einen normalen Fang (nicht abbrechen).
UNKNOWN = 'UNKNOWN'


# -- Kalibrierung / Algorithmus-Konstanten (verifiziert) -----------------

# Unterste Chat-Zeile -- Referenz im 802x632-VOLLBILD (Fenster INKL. ~31px
# Windows-Titelleiste + 1px-Rand): x in [115,405], y in [579,596]. Exklusiv-Ende
# wie Slicing. Das ist die Geometrie der gelabelten FischOCR/*.png (alle 802x632)
# und wird vom Template-Extraktor 1:1 so verwendet -> hier UNVERAENDERT lassen.
CHAT_REGION = (115, 579, 405, 596)

# AUTO-Anker an den UNTEREN Rand des Frames (Kalibrier-Fix). Der Live-Capture von
# WindowCapture ist der CLIENT-Bereich (800x601, OHNE Titelleiste), die
# Referenz-Shots dagegen 802x632 (VOLLBILD MIT ~31px Titelleiste + 1px-Rand).
# Eine fixe y-Region (aus 632 gemessen) liegt im 601er-Client ~31px ZU TIEF und
# verfehlt die Chat-Zeile komplett (read_hook -> NONE). Loesung: die y-Grenzen
# RELATIV zum unteren Rand verankern (y = frame_height - Konstante). So passt
# EINE Region automatisch auf BEIDE Frames:
#   * H=632 (Referenz) -> y[579,596]  == CHAT_REGION (Templates bleiben gueltig)
#   * H=601 (Live-Client) -> y[548,565] (trifft die Chat-Textzeile)
# Die Konstanten sind die Abstaende der CHAT_REGION-y-Grenzen zum unteren Rand
# des 632er-Referenzframes (632-579=53 oben, 632-596=36 unten) -> bit-stabil auf
# dem Referenzframe, automatisch mitskaliert auf jeden anderen Frame.
_CHAT_REF_FRAME_H = 632
CHAT_X0 = CHAT_REGION[0]                              # 115 (linke Spalte, fix)
CHAT_X1 = CHAT_REGION[2]                              # 405 (rechte Spalte, fix)
CHAT_BOTTOM_OFFSET_TOP = _CHAT_REF_FRAME_H - CHAT_REGION[1]     # 53 -> obere y-Kante
CHAT_BOTTOM_OFFSET_BOT = _CHAT_REF_FRAME_H - CHAT_REGION[3]     # 36 -> untere y-Kante


def chat_region_for_frame(height, width=None):
    """Liefert die an den UNTEREN Frame-Rand verankerte Chat-Region
    ``(x0, y0, x1, y1)`` fuer ein Bild der gegebenen ``height`` (und optional
    ``width``). Exklusiv-Ende wie Slicing.

    Verankert die y-Grenzen relativ zum unteren Rand (``y = height -
    Konstante``), damit DIESELBE Region sowohl die 802x632-Referenz-Shots
    (y[579,596] == :data:`CHAT_REGION`) als auch den 800x601-Live-Client
    (y[548,565]) trifft -- der Live-Capture hat keine Titelleiste und ist daher
    ~31px kuerzer.

    Wirft NIE: bei unbrauchbarer ``height`` faellt die Funktion auf die fixe
    :data:`CHAT_REGION` zurueck (defensiver Bestandscode-Stil). Die y-Werte
    werden zusaetzlich in ``[0, height]`` geklemmt; ``read_hook`` clampt die
    Region ohnehin nochmals gegen die echte Bildgroesse.
    """
    try:
        h = int(height)
    except Exception:
        return CHAT_REGION
    if h <= 0:
        return CHAT_REGION
    y0 = h - CHAT_BOTTOM_OFFSET_TOP
    y1 = h - CHAT_BOTTOM_OFFSET_BOT
    # In den Frame klemmen (sehr kleine Frames degenerieren sonst zu negativ).
    y0 = max(0, min(y0, h))
    y1 = max(0, min(y1, h))
    return (CHAT_X0, y0, CHAT_X1, y1)

# Binarisierung: Pixel-Helligkeit > 135 zaehlt als Tinte (heller Chat-Text auf
# dunklem Grund).
INK_THRESHOLD = 135

# Zeichen-Segmente zu Woertern gruppieren: eine Luecke von HOECHSTENS so vielen
# Spalten gehoert noch zum selben Wort; eine groessere ist eine Wortgrenze. An
# echten Daten gemessen: Zeichenluecken im Wort = 1px, Wortabstaende = 4px ->
# Schwelle 3 trennt sauber.
WORD_GAP = 3

# Index des Diskriminator-Worts (5. Wort) -- bei JEDER Nachricht vorhanden und
# nie vom linken Crop-Rand beschnitten (im Gegensatz zu Wort[0]).
DISC_WORD_INDEX = 4

# Match-Schwellen fuer den maskierten Pixel-Vergleich (NCC in [-1,1]). Bewusst
# streng: lieber UNKNOWN als ein falscher Name.
DISC_MIN_SCORE = 0.55       # Diskriminator (haette/hinge/du/koeder)
DISC_MIN_MARGIN = 0.05      # Bester muss klar vor dem Zweitbesten liegen
NAME_MIN_SCORE = 0.80       # NAME-Treffer
NAME_MIN_MARGIN = 0.06      # Abstand Bester vs. Zweitbester

_TEMPLATE_DIR = 'fishing_chat_templates'

# Per-Zeichen-Atlas (``glyph__<hex>.png``). Damit liest :func:`read_hook` auch
# einen NAMEN, fuer den es KEIN whole-name-Template gibt: Name-Region in Zeichen
# segmentieren, jedes gegen den Atlas matchen, den zusammengesetzten String
# gegen die bekannten offiziellen Namen FUZZY-matchen. So wird ein NEUER Fisch
# am Haken lesbar OHNE eigenen Chat-Screenshot -- sein Name muss nur in
# ITEM_NAMES stehen. (Build: tools/extract_fishing_chat_templates.py.)
GLYPH_PREFIX = 'glyph__'

# Zeichen-Match-Boden: ein Name-Lauf, der gegen JEDES Atlas-Glyph schlechter als
# das hier scort, wird als '?' (unbekanntes Zeichen) gelesen -- der Fuzzy-
# Abgleich vertraegt einzelne solche Stellen.
GLYPH_MIN_SCORE = 0.30

# Fuzzy-NAME-Annahme (Zeichen-OCR-Fallback). Bewusst streng: lieber UNKNOWN
# (Aufrufer angelt normal weiter) als ein falscher Name. An echten Daten haben
# ALLE korrekten Treffer Aehnlichkeit >= 0.79 bei klarem Abstand zum Zweitbesten.
NAME_FUZZY_MIN_SIM = 0.72
NAME_FUZZY_MIN_MARGIN = 0.10


# -- Ergebnis-Container --------------------------------------------------

class HookResult:
    """Was die unterste Chat-Zeile aussagt. Reiner Wert (kein Verhalten).

    Felder:
      * ``kind``      -- :data:`FISH` / :data:`ITEM` / :data:`NIETE` / :data:`NONE`.
      * ``name``      -- offizieller DE-Name bei sicherem Treffer, :data:`UNKNOWN`
                         bei erkanntem-aber-unsicherem Biss, sonst ``None``.
      * ``confident`` -- ``True`` nur bei einem SICHEREN Namens-Treffer.
      * ``score`` / ``margin`` -- Diagnose-Werte des NAME-Matchs (0.0 wenn n/a).
    """

    __slots__ = ('kind', 'name', 'confident', 'score', 'margin')

    def __init__(self, kind=NONE, name=None, confident=False,
                 score=0.0, margin=0.0):
        self.kind = kind
        self.name = name
        self.confident = bool(confident)
        self.score = float(score)
        self.margin = float(margin)

    @property
    def is_bite(self):
        """True bei Fisch ODER Item (etwas haengt am Haken)."""
        return self.kind in (FISH, ITEM)

    def as_dict(self):
        return {'kind': self.kind, 'name': self.name,
                'confident': self.confident,
                'score': self.score, 'margin': self.margin}

    def __repr__(self):
        return ('HookResult(kind=%r, name=%r, confident=%r, score=%.3f, '
                'margin=%.3f)' % (self.kind, self.name, self.confident,
                                  self.score, self.margin))

    def __eq__(self, other):
        return (isinstance(other, HookResult)
                and other.kind == self.kind and other.name == self.name
                and other.confident == self.confident)


# -- Low-Level-Bildverarbeitung ------------------------------------------

def _to_gray(region_bgr):
    """BGR/BGRA/Gray-Region -> float32-Graustufen (BT.601). Wirft nie -> None
    bei kaputter Eingabe.

    Capture liefert BGR (Windows GDI), darum BGR-Gewichte: 0.114*B + 0.587*G
    + 0.299*R.
    """
    try:
        arr = np.asarray(region_bgr)
        if arr.ndim == 2:
            return arr.astype(np.float32)
        if arr.ndim == 3 and arr.shape[2] >= 3:
            b = arr[:, :, 0].astype(np.float32)
            g = arr[:, :, 1].astype(np.float32)
            r = arr[:, :, 2].astype(np.float32)
            return 0.114 * b + 0.587 * g + 0.299 * r
        return None
    except Exception:
        return None


def _binary_line(region_bgr):
    """Region -> uint8-Binaerbild (1 = Tinte, sonst 0). ``None`` bei Fehler."""
    gray = _to_gray(region_bgr)
    if gray is None:
        return None
    try:
        return (gray > INK_THRESHOLD).astype(np.uint8)
    except Exception:
        return None


def _segment_words(binary):
    """Spalten-Projektion -> Wort-Spannen ``[(start, end_exklusiv), ...]``.

    Zeichen = zusammenhaengende Spalten mit Tinte; Woerter = Zeichen, deren
    Luecke <= :data:`WORD_GAP` ist. Defensiv: ``[]`` bei leerer/kaputter
    Eingabe.
    """
    if binary is None:
        return []
    try:
        col = binary.sum(axis=0)
    except Exception:
        return []
    n = int(col.shape[0]) if hasattr(col, 'shape') else 0
    if n == 0:
        return []

    # Zeichen-Segmente: Laeufe von Spalten mit Tinte.
    chars = []
    i = 0
    while i < n:
        if col[i] > 0:
            j = i
            while j < n and col[j] > 0:
                j += 1
            chars.append((i, j))
            i = j
        else:
            i += 1
    if not chars:
        return []

    # Zu Woertern gruppieren.
    words = []
    cur_start, cur_end = chars[0]
    for a, b in chars[1:]:
        if a - cur_end <= WORD_GAP:
            cur_end = b
        else:
            words.append((cur_start, cur_end))
            cur_start, cur_end = a, b
    words.append((cur_start, cur_end))
    return words


def _crop_word_band(binary, span):
    """Schneidet die Wort-Spanne aus und beschneidet auf die belegten Zeilen
    (Tinte), damit Templates lage-/hoehenrobust verglichen werden. ``None`` bei
    leerer Auswahl."""
    if binary is None or span is None:
        return None
    try:
        a, b = int(span[0]), int(span[1])
        sub = binary[:, a:b]
        rows = np.where(sub.sum(axis=1) > 0)[0]
        if rows.size == 0:
            return None
        return sub[rows[0]:rows[-1] + 1, :]
    except Exception:
        return None


def _crop_span_band(binary, start, end):
    """Wie :func:`_crop_word_band`, aber fuer einen freien Spaltenbereich
    (NAME-Region, die mehrere Woerter umfasst)."""
    return _crop_word_band(binary, (start, end))


# -- maskierter Pixel-Vergleich (NCC) ------------------------------------

def _match_score(glyph, template):
    """Maskierter Normalisierter-Kreuzkorrelations-Score in [-1, 1] zwischen
    zwei 1-Bit-Glyphen.

    Bringt beide defensiv auf dieselbe Hoehe/Breite (Padding statt Skalierung,
    Pixel-Font!) und korreliert die zentrierten Vektoren. Liefert -1.0 bei
    Fehler / Entartung. Form-Mismatch wird nicht bestraft ueber die Breite
    hinaus -- darum den Breiten-Gate separat im Aufrufer.
    """
    try:
        if glyph is None or template is None:
            return -1.0
        a = np.asarray(glyph, dtype=np.float32)
        t = np.asarray(template, dtype=np.float32)
        if a.size == 0 or t.size == 0:
            return -1.0
        h = max(a.shape[0], t.shape[0])
        w = max(a.shape[1], t.shape[1])
        a = _pad_to(a, h, w)
        t = _pad_to(t, h, w)
        av = a.ravel() - a.mean()
        tv = t.ravel() - t.mean()
        denom = float(np.linalg.norm(av) * np.linalg.norm(tv))
        if denom <= 1e-6:
            return -1.0
        return float(np.dot(av, tv) / denom)
    except Exception:
        return -1.0


def _pad_to(arr, h, w):
    """Null-padded ``arr`` (oben-links verankert) auf genau ``h x w``."""
    out = np.zeros((h, w), dtype=arr.dtype)
    hh = min(h, arr.shape[0])
    ww = min(w, arr.shape[1])
    out[:hh, :ww] = arr[:hh, :ww]
    return out


def _best_match(glyph, templates, width_tol=0.30):
    """(key, best_score, margin) des besten Template-Treffers fuer ``glyph``.

    ``templates`` = ``{key: bitmap}``. Ein Kandidat wird nur gewertet, wenn die
    Breite (Pixel-Font!) innerhalb ``width_tol`` relativ passt -- so kann ein
    kurzer Name nicht faelschlich in einem langen "stecken". ``margin`` =
    Abstand des Besten zum naechstbesten breitengueltigen Kandidaten. Bewusst
    NUR gegen breitengueltige Alternativen: breiten-verworfene Templates sind
    geometrisch unmoegliche Treffer (Pixel-Font); sie duerfen die Margin nicht
    druecken (sonst wuerde ein korrekter, eindeutiger Treffer faelschlich unter
    das Margin-Gate fallen und als UNKNOWN/NONE gelten).

    Rueckgabe ``(None, -1.0, 0.0)`` wenn nichts passt.
    """
    if glyph is None or not templates:
        return (None, -1.0, 0.0)
    gw = glyph.shape[1] if glyph.ndim == 2 else 0
    scores = []
    for key, tmpl in templates.items():
        if tmpl is None:
            continue
        score = _match_score(glyph, tmpl)
        tw = tmpl.shape[1] if tmpl.ndim == 2 else 0
        width_ok = True
        if gw > 0 and tw > 0:
            rel = abs(gw - tw) / float(max(gw, tw))
            width_ok = rel <= width_tol
        scores.append((score, key, width_ok))
    if not scores:
        return (None, -1.0, 0.0)
    # Bester gueltiger (breitenkonform) Treffer.
    valid = [(s, k) for (s, k, ok) in scores if ok]
    if not valid:
        return (None, -1.0, 0.0)
    valid.sort(reverse=True)
    best_score, best_key = valid[0]
    # Margin NUR gegen den naechstbesten BREITENGUELTIGEN Kandidaten -- ein
    # breiten-verworfenes Template ist ein unmoeglicher Treffer und darf die
    # Margin nicht druecken (sonst faellt ein klarer Treffer faelschlich durch).
    second_best = valid[1][0] if len(valid) > 1 else -1.0
    margin = best_score - second_best
    return (best_key, best_score, margin)


# -- Vorlagen-Bibliothek (lazy, gecached) --------------------------------

_TEMPLATES_CACHE = None


def _load_template_png(path):
    """1-Bit-Template-PNG -> uint8-Bitmap (1 = Tinte). ``None`` bei Fehler."""
    if not _HAS_PIL:
        return None
    try:
        img = Image.open(path).convert('L')
        arr = np.asarray(img)
        return (arr > 127).astype(np.uint8)
    except Exception:
        return None


def _load_templates():
    """Laedt + cached die gebuendelten Vorlagen.

    Rueckgabe ``{'disc': {key: bitmap}, 'name': {german_name: bitmap},
    'glyph': {char: bitmap}}``. Fehlt der Ordner oder Pillow, sind die Dicts
    leer -> alles wird sauber zu NONE/UNKNOWN (kein Crash).
    """
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return _TEMPLATES_CACHE
    disc, name, glyph = {}, {}, {}
    try:
        base = resource_path(_TEMPLATE_DIR)
        files = os.listdir(base) if os.path.isdir(base) else []
        for fname in files:
            if not fname.lower().endswith('.png'):
                continue
            bitmap = _load_template_png(os.path.join(base, fname))
            if bitmap is None:
                continue
            if fname.startswith('disc__'):
                disc[fname[len('disc__'):-4]] = bitmap
            elif fname.startswith(GLYPH_PREFIX):
                ch = _glyph_char_from_filename(fname)
                if ch is not None:
                    glyph[ch] = bitmap
            elif fname.startswith('name__'):
                name[_slug_to_name(fname[len('name__'):-4])] = bitmap
    except Exception:
        pass
    _TEMPLATES_CACHE = {'disc': disc, 'name': name, 'glyph': glyph}
    return _TEMPLATES_CACHE


def reset_template_cache():
    """Vergisst die gecachten Vorlagen (Tests / nach Re-Extraktion)."""
    global _TEMPLATES_CACHE
    _TEMPLATES_CACHE = None


# -- Name <-> Slug (dateinamen-sicher, verlustfrei) ----------------------

def _slug(text):
    """Kleinbuchstaben-ASCII-Slug (Umlaute entfaltet, Nicht-Wort -> '_')."""
    repl = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
            'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue'}
    out = []
    for ch in str(text):
        if ch in repl:
            out.append(repl[ch])
        elif ch.isalnum():
            out.append(ch.lower())
        else:
            out.append('_')
    slug = ''.join(out)
    while '__' in slug:
        slug = slug.replace('__', '_')
    return slug.strip('_')


def glyph_filename(ch):
    """Einzelzeichen -> dateinamen-sicherer Atlas-PNG-Name ``glyph__<hex>.png``
    (hex = Unicode-Codepoint, daher Umlaute/Satzzeichen unproblematisch)."""
    return '%s%04x.png' % (GLYPH_PREFIX, ord(ch))


def _glyph_char_from_filename(fname):
    """``glyph__<hex>.png`` -> das Zeichen (``None`` bei kaputtem Namen)."""
    try:
        return chr(int(fname[len(GLYPH_PREFIX):-4], 16))
    except Exception:
        return None


# Slug -> offizieller DE-Name. Eindeutige Rueck-Abbildung, damit der Slug im
# Dateinamen stehen kann, das Ergebnis aber den korrekten Anzeigenamen traegt.
_SLUG_TO_NAME = {}
_NAME_TO_SLUG = {}


def _register_name(name):
    slug = _slug(name)
    _SLUG_TO_NAME[slug] = name
    _NAME_TO_SLUG[name] = slug
    return slug


def name_to_slug(name):
    """Offizieller Name -> Datei-Slug (registriert die Rueck-Abbildung)."""
    return _register_name(name)


def _slug_to_name(slug):
    """Datei-Slug -> offizieller Name (Fallback: Slug selbst)."""
    return _SLUG_TO_NAME.get(slug, slug)


def _build_name_registry():
    """Registriert den vollen offiziellen DE-Namensraum (Slug<->Name), damit
    geladene ``name__<slug>.png`` IMMER den korrekten Anzeigenamen liefern --
    auch fuer Namen ausserhalb der aktuellen Referenz-Screenshots."""
    names = set()
    try:
        from interface.inventory_manage import ITEM_NAMES
        for _key, (_en, de) in ITEM_NAMES.items():
            names.add(de)
    except Exception:
        pass
    # Plus Sonderfaelle, die im Chat als eigener Name auftauchen koennen.
    names.update({'Goldener Thunfisch', 'Rotes Haarfärbemittel'})
    for name in names:
        _register_name(name)


_build_name_registry()


# -- Hilfen fuer den Extraktor (Schreiben von Templates) -----------------

def _save_template_png(bitmap, path):
    """Speichert eine 1-Bit-Glyph-Bitmap (1=Tinte) als kleines PNG. Wirft nie."""
    if not _HAS_PIL or bitmap is None:
        return False
    try:
        arr = (np.asarray(bitmap) > 0).astype(np.uint8) * 255
        Image.fromarray(arr, mode='L').save(path)
        return True
    except Exception:
        return False


# -- Zeichen-OCR: liest JEDEN Namen, auch ohne whole-name-Template -------

def _char_runs(binary, a, b):
    """Spaltenlaeufe (= einzelne Zeichen) in ``[a, b)`` als absolute
    ``(start, end)``. Defensiv: ``[]`` bei kaputter Eingabe."""
    try:
        sub = binary[:, int(a):int(b)]
        col = sub.sum(axis=0)
        runs, i, n = [], 0, int(col.shape[0])
        while i < n:
            if col[i] > 0:
                j = i
                while j < n and col[j] > 0:
                    j += 1
                runs.append((int(a) + i, int(a) + j))
                i = j
            else:
                i += 1
        return runs
    except Exception:
        return []


def _read_name_text(binary, start, end, atlas):
    """Liest die NAME-Region ``[start, end)`` zeichenweise gegen den Glyphen-
    ``atlas`` und gibt den ROH erkannten String zurueck (jeder Spaltenlauf ein
    Zeichen, bestes maskiertes NCC; unter :data:`GLYPH_MIN_SCORE` -> '?').
    Wort-Luecken werden NICHT als Leerzeichen kodiert -- der Fuzzy-Abgleich
    normalisiert Leerzeichen ohnehin weg. Wirft nie -> '' bei jedem Problem."""
    try:
        if not atlas or binary is None:
            return ''
        out = []
        for (ra, rb) in _char_runs(binary, start, end):
            glyph = _crop_word_band(binary, (ra, rb))
            best_c, best_s = '?', -1.0
            for ch, tmpl in atlas.items():
                s = _match_score(glyph, tmpl)
                if s > best_s:
                    best_s, best_c = s, ch
            out.append(best_c if best_s >= GLYPH_MIN_SCORE else '?')
        return ''.join(out)
    except Exception:
        return ''


def _levenshtein(a, b):
    """Edit-Distanz (iterativ, zwei Zeilen)."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        ai = a[i - 1]
        for j in range(1, n + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (0 if ai == b[j - 1] else 1))
        prev = cur
    return prev[n]


def _norm_for_fuzzy(text):
    """Vergleichsform: Leerzeichen weg + lowercase (robust gegen l/L-
    Verwechslung im Pixel-Font und gegen Wortabstaende)."""
    return ''.join(str(text).split()).lower()


_KNOWN_NAMES_CACHE = None


def _known_names():
    """Cached Liste der offiziellen DE-Namen (ITEM_NAMES + Sonderfaelle), gegen
    die der Zeichen-OCR-Lesestring gefuzzy-matcht wird. Defensiv: bei Import-
    fehler nur die Sonderfaelle (-> Zeichen-OCR liefert dann hoechstens diese,
    sonst UNKNOWN, NIE ein falscher Name)."""
    global _KNOWN_NAMES_CACHE
    if _KNOWN_NAMES_CACHE is not None:
        return _KNOWN_NAMES_CACHE
    names, seen = [], set()

    def add(nm):
        if nm and nm not in seen:
            seen.add(nm)
            names.append(nm)

    try:
        from interface.inventory_manage import ITEM_NAMES
        for _key, (_en, de) in ITEM_NAMES.items():
            add(de)
    except Exception:
        pass
    add('Goldener Thunfisch')
    add('Rotes Haarfärbemittel')
    _KNOWN_NAMES_CACHE = names
    return names


def reset_known_names_cache():
    """Vergisst die gecachte Namensliste (Tests)."""
    global _KNOWN_NAMES_CACHE
    _KNOWN_NAMES_CACHE = None


def _fuzzy_best_name(text, candidates):
    """``(best_name, similarity, margin)`` des aehnlichsten offiziellen Namens
    zum roh gelesenen ``text`` (normalisierte Aehnlichkeit
    ``1 - Levenshtein/maxlen``). ``margin`` = Abstand zum Zweitbesten.
    ``(None, 0.0, 0.0)`` wenn nichts taugt."""
    r = _norm_for_fuzzy(text)
    if not r or not candidates:
        return (None, 0.0, 0.0)
    scored = []
    for name in candidates:
        key = _norm_for_fuzzy(name)
        if not key:
            continue
        sim = 1.0 - _levenshtein(r, key) / float(max(len(r), len(key)))
        scored.append((sim, name))
    if not scored:
        return (None, 0.0, 0.0)
    scored.sort(key=lambda x: x[0], reverse=True)
    best_sim, best_name = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return (best_name, best_sim, best_sim - second)


# -- Klassifikation ------------------------------------------------------

def _classify_words(binary, words, templates):
    """Kernlogik: aus Binaerzeile + Woertern ein :class:`HookResult` ableiten."""
    # Jede bekannte Nachricht hat >= 5 Woerter -> Wort[4] existiert. Weniger ->
    # weder Biss noch bekannte Meldung.
    if len(words) <= DISC_WORD_INDEX:
        return HookResult(NONE)

    disc_templates = templates.get('disc', {})
    name_templates = templates.get('name', {})

    disc_glyph = _crop_word_band(binary, words[DISC_WORD_INDEX])
    disc_key, disc_score, disc_margin = _best_match(disc_glyph, disc_templates)

    # Diskriminator unsicher -> defensiv "nichts" (warten / normal weiterangeln).
    if (disc_key is None or disc_score < DISC_MIN_SCORE
            or disc_margin < DISC_MIN_MARGIN):
        return HookResult(NONE)

    if disc_key == 'du':
        return HookResult(NIETE)
    if disc_key == 'koeder':
        return HookResult(NONE)

    if disc_key == 'haette':
        kind = FISH
        last = len(words) - 2            # vor "angebissen."
    elif disc_key == 'hinge':
        kind = ITEM
        last = len(words) - 3            # vor "am" + "Haken."
    else:
        return HookResult(NONE)

    # Plausibilitaet: der Name braucht mindestens ein Wort (Index 5 .. last).
    if last < 5 or last >= len(words):
        # Biss erkannt, aber Struktur unklar -> als Biss MIT UNKNOWN behandeln,
        # damit der Aufrufer normal angelt (nie faelschlich abbrechen).
        return HookResult(kind, UNKNOWN, confident=False)

    name_start = words[5][0]
    name_end = words[last][1]
    name_glyph = _crop_span_band(binary, name_start, name_end)
    name_key, name_score, name_margin = _best_match(name_glyph, name_templates)

    if (name_key is not None and name_score >= NAME_MIN_SCORE
            and name_margin >= NAME_MIN_MARGIN):
        return HookResult(kind, name_key, confident=True,
                          score=name_score, margin=name_margin)

    # FALLBACK: whole-name-Template unsicher -> Zeichen-OCR. Liest die NAME-
    # Region zeichenweise gegen den Glyphen-Atlas und fuzzy-matcht gegen die
    # bekannten offiziellen Namen. So werden auch Fische OHNE eigenes
    # name__-Template erkannt (ihr Name muss nur in ITEM_NAMES stehen) -- kein
    # Chat-Screenshot pro Fisch noetig. Bleibt streng: lieber UNKNOWN.
    glyph_atlas = templates.get('glyph', {})
    if glyph_atlas:
        read = _read_name_text(binary, name_start, name_end, glyph_atlas)
        fname, sim, fmargin = _fuzzy_best_name(read, _known_names())
        if (fname is not None and sim >= NAME_FUZZY_MIN_SIM
                and fmargin >= NAME_FUZZY_MIN_MARGIN):
            return HookResult(kind, fname, confident=True,
                              score=sim, margin=fmargin)

    # Biss sicher, Name unsicher -> UNKNOWN (Aufrufer angelt normal weiter).
    return HookResult(kind, UNKNOWN, confident=False,
                      score=max(name_score, 0.0), margin=max(name_margin, 0.0))


# -- Oeffentliche API ----------------------------------------------------

def read_hook(screenshot_bgr, region=None, templates=None):
    """Liest die unterste Chat-Zeile des ``screenshot_bgr`` (Fenster-Capture,
    BGR) und liefert ein :class:`HookResult`.

    ``screenshot_bgr`` ist das, was :class:`windowcapture.WindowCapture`
    zurueckgibt -- BGR ``(h, w, 3)`` uint8 des CLIENT-Bereichs (800x601, OHNE
    Titelleiste). ``region=None`` (Default) verankert den Crop AUTOMATISCH an den
    unteren Frame-Rand (:func:`chat_region_for_frame`), sodass dieselbe Logik den
    800x601-Live-Client UND die 802x632-Referenz-Shots trifft. Ein explizit
    uebergebenes ``region`` (Tupel) wird unveraendert benutzt (Tests/Extraktor/
    Kalibrierung). ``templates`` ueberschreibt die Vorlagen (Tests). Wirft NIE:
    bei jedem Problem -> ``HookResult(NONE)``.

    Garantie (Aufrufer-Vertrag): ``kind == FISH``/``ITEM`` heisst "etwas haengt
    am Haken"; ``name`` ist dann ENTWEDER ein sicherer offizieller Name
    (``confident=True``) ODER :data:`UNKNOWN` (``confident=False``). Niete ->
    ``kind == NIETE``; nichts Relevantes -> ``kind == NONE``.
    """
    try:
        if screenshot_bgr is None:
            return HookResult(NONE)
        arr = np.asarray(screenshot_bgr)
        if arr.ndim < 2:
            return HookResult(NONE)
        h = arr.shape[0]
        w = arr.shape[1]
        # Default-Region an den UNTEREN Rand des konkreten Frames ankern (Fix
        # fuer den ~31px-Titelleisten-Versatz Live-Client vs. Referenz-Shot).
        # Ein explizit uebergebenes region wird respektiert.
        if region is None:
            region = chat_region_for_frame(h, w)
        x0, y0, x1, y1 = region
        # Region defensiv in das Bild clampen (abweichende Capture-Groesse).
        x0 = max(0, min(int(x0), w))
        x1 = max(0, min(int(x1), w))
        y0 = max(0, min(int(y0), h))
        y1 = max(0, min(int(y1), h))
        if x1 <= x0 or y1 <= y0:
            return HookResult(NONE)
        region_img = arr[y0:y1, x0:x1]
        binary = _binary_line(region_img)
        words = _segment_words(binary)
        tmpl = templates if templates is not None else _load_templates()
        return _classify_words(binary, words, tmpl)
    except Exception:
        return HookResult(NONE)


__all__ = [
    'FISH', 'ITEM', 'NIETE', 'NONE', 'UNKNOWN',
    'CHAT_REGION', 'INK_THRESHOLD', 'WORD_GAP', 'DISC_WORD_INDEX',
    'GLYPH_PREFIX', 'GLYPH_MIN_SCORE', 'NAME_FUZZY_MIN_SIM',
    'NAME_FUZZY_MIN_MARGIN',
    'chat_region_for_frame',
    'HookResult', 'read_hook',
    'reset_template_cache', 'reset_known_names_cache', 'name_to_slug',
    'glyph_filename',
    # fuer den Extraktor / Tests:
    '_binary_line', '_segment_words', '_save_template_png', '_slug',
    '_match_score', '_read_name_text', '_levenshtein', '_fuzzy_best_name',
    '_known_names', '_char_runs',
]
