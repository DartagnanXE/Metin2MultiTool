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

KALIBRIERUNG (verifiziert, NICHT neu herleiten): die Screenshots/Capture sind
802x632 (Spielfenster inkl. Windows-Titelleiste); Screenshot-Pixel == Spiel-
Koordinaten 1:1. Die unterste Chat-Zeile liegt in x[115,405], y[579,596];
DARUEBER beginnt ab ~y597 die Hotbar (nicht reinrutschen).

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

# Unterste Chat-Zeile: x in [115,405], y in [579,596]. Exklusiv-Ende wie Slicing.
CHAT_REGION = (115, 579, 405, 596)

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

    Rueckgabe ``{'disc': {key: bitmap}, 'name': {german_name: bitmap}}``. Fehlt
    der Ordner oder Pillow, sind die Dicts leer -> alles wird sauber zu NONE/
    UNKNOWN (kein Crash).
    """
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return _TEMPLATES_CACHE
    disc, name = {}, {}
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
            elif fname.startswith('name__'):
                name[_slug_to_name(fname[len('name__'):-4])] = bitmap
    except Exception:
        pass
    _TEMPLATES_CACHE = {'disc': disc, 'name': name}
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

    # Biss sicher, Name unsicher -> UNKNOWN (Aufrufer angelt normal weiter).
    return HookResult(kind, UNKNOWN, confident=False,
                      score=max(name_score, 0.0), margin=max(name_margin, 0.0))


# -- Oeffentliche API ----------------------------------------------------

def read_hook(screenshot_bgr, region=CHAT_REGION, templates=None):
    """Liest die unterste Chat-Zeile des ``screenshot_bgr`` (volles Fenster-
    Capture, BGR) und liefert ein :class:`HookResult`.

    ``screenshot_bgr`` ist das, was :class:`windowcapture.WindowCapture`
    zurueckgibt -- BGR ``(h, w, 3)`` uint8, Pixel == Spielkoordinaten. ``region``
    ueberschreibt den Crop (Tests/Kalibrierung). ``templates`` ueberschreibt die
    Vorlagen (Tests). Wirft NIE: bei jedem Problem -> ``HookResult(NONE)``.

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
        x0, y0, x1, y1 = region
        h = arr.shape[0]
        w = arr.shape[1]
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
    'HookResult', 'read_hook',
    'reset_template_cache', 'name_to_slug',
    # fuer den Extraktor / Tests:
    '_binary_line', '_segment_words', '_save_template_png', '_slug',
]
