# -*- coding: utf-8 -*-
"""Reine Vision/Erkennung fuer den Energiesplitter (NCC-Wortbild-Framework).

Im Projekt existiert KEIN freies OCR (verifiziert: 0 Treffer tesseract/easyocr;
``fishing_chat`` ist ein fester Pixel-Glyphen-Atlas). Text-/NPC-/Dialog-/Header-
Erkennung laeuft daher ueber **NCC-Wortbild-Templates** (de+en) -- ein bekanntes,
gerendertes Wort wird als Bild per ``cv2.matchTemplate(TM_CCOEFF_NORMED)`` gesucht.
Kein neues Dependency; cv2/numpy wie im restlichen Projekt.

Dieses Modul ist **rein** (numpy/cv2 + Template-Laden von Platte; kein win32/Maus/
i18n-Pflicht). Jede Funktion ist defensiv und wirft NIE -- ein abweichendes
Capture (Form/Typ) wird als 'nicht erkannt' behandelt, nicht als Absturz.

PHASE-0-STATUS (ehrlich): Die zu BUENDELNDEN Assets -- Wortbild-Templates in
``energiesplitter/templates/{de,en}/``, Item-Icons in ``inventory_icons/``
(hammer/dolch/energiesplitter), der vollstaendige Gold-Digit-Satz -- FEHLEN noch
(P0.1/P0.2/P0.3). Deshalb meldet :func:`assets_ready` sie als ``missing`` und das
Phase-0-Gate bleibt rot (kein Kauf/Drag). Das ERKENNUNGS-FRAMEWORK ist hier aber
voll implementiert und gegen die 26 echten Bilder getestet: Funktionen, die ein
Template als ARGUMENT bekommen (``find_npc_name``/``find_shop_item``/
``match_word``), werden im Test mit echten Crops belegt; die asset-gebundenen
Detektoren (``dialog_state``/``shop_open``/``panel_is_bag``) liefern sauber
``None``/``False`` (NotReady), solange ihre Marker-Templates fehlen.
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


# -- Asset-Verzeichnisse (cwd-unabhaengig) ----------------------------------
TEMPLATE_DIR = os.path.join('energiesplitter', 'templates')
ITEM_ICON_DIR = 'inventory_icons'

# Wortbild-Templates je Modus (Dateiname ohne .png; in de/ UND en/ erwartet).
HAMMER_WORDS = (
    'laden_oeffnen', 'weiter', 'ok', 'eine_neue_technik',
    'energiesplitter_extrahieren', 'laden_header', 'inventar_header',
    'ausruestung_header', 'npc_alchemist',
)
DAGGER_EXTRA_WORDS = ('npc_waffenhaendler', 'ein_neuer_duft')

# Item-Icons je Modus (Dateiname ohne .png in inventory_icons/).
HAMMER_ICONS = ('hammer',)
DAGGER_EXTRA_ICONS = ('dolch', 'energiesplitter')

# -- NCC-Schwellen (KALIBRIER-BAR; an Fixtures gemessen) --------------------
NCC_WORD = 0.80           # Wortbild-Treffer (NPC-Name / Dialogzeile)
NCC_HEADER = 0.70         # Panel-/Shop-Header
NCC_ITEM = 0.70           # Item-Icon im Shop
# Gruen-Maske fuer NPC-Namen (HSV-frei, BGR-Schwellen wie DESIGN).
GREEN_G_MIN = 120
GREEN_GR_DELTA = 25
GREEN_GB_DELTA = 25
# Ring-Glow-Maske: der Metin2-Selektions-Ring leuchtet saturiert orange-rot
# (gemessen: R~255, G~40-110, B~1-56) -- deutlich saettiger als die muddy-roten
# HP-Leisten/Traenke. Diese strenge Schwelle trennt den Ring von HUD-Rot
# (KALIBRIER-BAR; an den Alchemist-Ring-Bildern gemessen).
RED_R_MIN = 180
RED_RG_DELTA = 90
RED_RB_DELTA = 120
RING_MIN_PX = 40          # mind. Glow-Pixel im Such-Fenster, um einen Ring zu erwaegen
RING_NEAR_PX = 60         # Suchradius (Halbkante) um den NPC-Punkt
RING_MAX_FILL = 0.35      # max. Fuell-Grad der Glow-Bounding-Box (Ring duenn, ~0.1)


# ----------------------------------------------------------------------------
# Template-Laden
# ----------------------------------------------------------------------------
def _dir(rel):
    """Loest ein gebundeltes Verzeichnis cwd-unabhaengig auf (wie respath)."""
    base = resource_path(rel)
    if os.path.isdir(base):
        return base
    here = os.path.dirname(os.path.abspath(__file__))
    # rel kann 'energiesplitter/...' oder 'inventory_icons' sein -> relativ zum Repo.
    repo = os.path.dirname(here)
    cand = os.path.join(repo, rel)
    return cand if os.path.isdir(cand) else base


def _template_path(lang, word):
    return os.path.join(_dir(TEMPLATE_DIR), lang, word + '.png')


def _icon_path(name):
    return os.path.join(_dir(ITEM_ICON_DIR), name + '.png')


def _exists(path):
    try:
        return os.path.isfile(path)
    except Exception:
        return False


# ----------------------------------------------------------------------------
# NCC-Kernel (robust, wie fishing_match._match_template_max)
# ----------------------------------------------------------------------------
def _to_bgr(img):
    """Bringt ``img`` defensiv auf 3-Kanal-BGR (contiguous). ``None`` bei Fehler."""
    if img is None:
        return None
    try:
        a = np.ascontiguousarray(img)
        if a.ndim == 2:
            return _cv.cvtColor(a, _cv.COLOR_GRAY2BGR)
        if a.ndim == 3 and a.shape[2] == 4:
            return _cv.cvtColor(a, _cv.COLOR_BGRA2BGR)
        if a.ndim == 3 and a.shape[2] == 3:
            return a
        return None
    except Exception:
        return None


def match_word(haystack, template):
    """NCC eines Wortbild-/Icon-Templates in ``haystack`` -> ``(ok, pt, ncc)``.

    ``pt`` = oben-links des besten Treffers (im ``haystack``-Koordinatensystem).
    Defensiv: passt das Template nicht (groesser als Bild, falsche Kanalzahl) ->
    ``(False, None, 0.0)``. Wirft NIE.
    """
    if np is None or _cv is None:
        return (False, None, 0.0)
    img = _to_bgr(haystack)
    tpl = _to_bgr(template)
    if img is None or tpl is None:
        return (False, None, 0.0)
    if (tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]
            or img.shape[2] != tpl.shape[2]):
        return (False, None, 0.0)
    try:
        res = _cv.matchTemplate(img, tpl, _cv.TM_CCOEFF_NORMED)
        _minv, maxv, _minl, maxl = _cv.minMaxLoc(res)
        return (True, (int(maxl[0]), int(maxl[1])), float(maxv))
    except Exception:
        return (False, None, 0.0)


# ----------------------------------------------------------------------------
# Phase-0-Asset-Gate (rein)
# ----------------------------------------------------------------------------
def assets_ready(mode):
    """Prueft, ob ALLE fuer ``mode`` noetigen Assets gebundelt sind.

    ``mode`` in ``('hammer', 'dagger')``. Liefert ``(ready, missing)``: ``ready``
    nur True, wenn KEIN Artefakt fehlt. Jedes fehlende landet als Klartext-String
    in ``missing`` (z.B. ``'tpl:de/laden_oeffnen'``, ``'item:hammer'``,
    ``'gold_digits'``). Reine Dateisystem-Pruefung; wirft NIE.
    """
    missing = []
    m = (mode or '').lower()
    words = list(HAMMER_WORDS)
    icons = list(HAMMER_ICONS)
    if m == 'dagger':
        words += list(DAGGER_EXTRA_WORDS)
        icons += list(DAGGER_EXTRA_ICONS)
    elif m != 'hammer':
        return (False, ['mode:%s' % mode])
    for word in words:
        for lang in ('de', 'en'):
            if not _exists(_template_path(lang, word)):
                missing.append('tpl:%s/%s' % (lang, word))
    for icon in icons:
        if not _exists(_icon_path(icon)):
            missing.append('item:%s' % icon)
    try:
        from . import gold_reader as _gr
        if not _gr.templates_complete():
            missing.append('gold_digits')
    except Exception:
        missing.append('gold_digits')
    return (len(missing) == 0, missing)


# ----------------------------------------------------------------------------
# NPC-Name (Gruen-Maske + Wortbild-NCC)
# ----------------------------------------------------------------------------
def _green_mask(bgr):
    """Binaere Gruen-Maske (uint8 0/255) fuer NPC-Namen (DESIGN-Schwellen)."""
    b = bgr[:, :, 0].astype(np.int16)
    g = bgr[:, :, 1].astype(np.int16)
    r = bgr[:, :, 2].astype(np.int16)
    m = ((g > GREEN_G_MIN) & (g - r > GREEN_GR_DELTA) & (g - b > GREEN_GB_DELTA))
    return (m.astype(np.uint8)) * 255


def find_npc_name(bgr, word_template, roi=None, thresh=NCC_WORD):
    """Sucht den gruenen NPC-Schriftzug ``word_template`` in der Szene.

    ``bgr`` wird ``geometry.to_client``-normiert; im Szenen-ROI wird eine
    Gruen-Maske gebildet und ``word_template`` (selbst gruen-maskiert) per NCC
    gesucht. Liefert ``(ok, pt, ncc)`` mit ``pt`` im CLIENT-Koordinatensystem
    (NPC-Punkt = Treffer-Mitte). ``word_template`` None / kein Treffer >= thresh
    -> ``(False, None, ncc)``. KEIN Blind-Fallback auf den groessten Cluster.
    Wirft NIE.
    """
    if np is None or _cv is None or bgr is None or word_template is None:
        return (False, None, 0.0)
    client = _geo.to_client(bgr)
    roi = roi if roi is not None else _geo.ROI_SCENE
    region = _geo.crop(client, roi)
    if region is None:
        return (False, None, 0.0)
    tpl = _to_bgr(word_template)
    if tpl is None:
        return (False, None, 0.0)
    try:
        region_m = _cv.cvtColor(_green_mask(region), _cv.COLOR_GRAY2BGR)
        # Template ebenfalls maskieren, falls es ein Roh-Crop ist (gruener Text
        # auf Szene); ist es bereits eine Maske, bleibt es naeherungsweise gleich.
        tpl_m = _cv.cvtColor(_green_mask(tpl), _cv.COLOR_GRAY2BGR)
    except Exception:
        return (False, None, 0.0)
    ok, pt, ncc = match_word(region_m, tpl_m)
    if not ok or pt is None or ncc < thresh:
        return (False, None, ncc)
    rx, ry, _, _ = roi
    th, tw = tpl_m.shape[:2]
    center = (rx + pt[0] + tw // 2, ry + pt[1] + th // 2)
    return (True, center, ncc)


# ----------------------------------------------------------------------------
# Selektions-Ring (Rot-Maske + Ring-Form)
# ----------------------------------------------------------------------------
def _red_mask(bgr):
    b = bgr[:, :, 0].astype(np.int16)
    g = bgr[:, :, 1].astype(np.int16)
    r = bgr[:, :, 2].astype(np.int16)
    m = ((r > RED_R_MIN) & (r - g > RED_RG_DELTA) & (r - b > RED_RB_DELTA))
    return m


def selection_ring_present(bgr, near, y_min=240):
    """``True``, wenn um ``near=(x,y)`` ein roter Selektions-Ring liegt.

    Sucht im Fenster ``RING_NEAR_PX`` um ``near`` (nur Zeilen ``>= y_min``, damit
    Titel-X (y<32) und obere HUD-Elemente NICHT fehl-triggern) rote Pixel und
    verlangt eine RING-Form: genug rote Pixel, die einen Rand bilden (Loch in der
    Mitte = innen weniger Rot als am Rand). Liefert defensiv ``False`` bei
    fehlendem/ungueltigem ``near``. Wirft NIE.
    """
    if np is None or bgr is None or near is None:
        return False
    try:
        client = _geo.to_client(bgr)
        H, W = client.shape[:2]
        cx, cy = int(near[0]), int(near[1])
        x0 = max(0, cx - RING_NEAR_PX); x1 = min(W, cx + RING_NEAR_PX)
        y0 = max(int(y_min), cy - RING_NEAR_PX); y1 = min(H, cy + RING_NEAR_PX)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return False
        win = client[y0:y1, x0:x1]
        rm = _red_mask(win)
        total = int(rm.sum())
        if total < RING_MIN_PX:
            return False
        hh, ww = rm.shape
        ys, xs = np.where(rm)
        if len(xs) == 0:
            return False
        span_x = int(xs.max() - xs.min() + 1)
        span_y = int(ys.max() - ys.min() + 1)
        bbox_area = max(1, span_x * span_y)
        fill = total / bbox_area
        # Ring-Form (Ellipse, an echten Bildern gemessen):
        #   * grosse Spannweite in BEIDEN Achsen (Durchmesser ~ Fenster) -- eine
        #     flache HP-Leiste (span_y ~ 3) oder ein verstreuter HUD-Rot-Fleck
        #     (span_y klein) faellt durch;
        #   * niedriger Fuell-Grad (duenner Ring-Rand, kein solider Block) -- die
        #     HP-Leiste hat fill ~ 0.9, der Ring ~ 0.1.
        if span_x < ww // 2 or span_y < hh // 2:
            return False
        return fill <= RING_MAX_FILL
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Dialog-Zustand / Shop / Panel -- asset-gebunden (NotReady ohne Templates)
# ----------------------------------------------------------------------------
def _load_template(lang, word):
    """Laedt ein gebundeltes Wortbild-Template als BGR, oder ``None``."""
    if _cv is None:
        return None
    path = _template_path(lang, word)
    if not _exists(path):
        return None
    try:
        return _cv.imread(path, _cv.IMREAD_COLOR)
    except Exception:
        return None


def _word_in_region(bgr, roi, word, thresh):
    """``(ok, ncc)``: sucht ``word`` (de ODER en) im ROI per NCC. NotReady -> None.

    Liefert ``None``, wenn KEIN Sprach-Template gebundelt ist (Phase-0) -> der
    Aufrufer kann NotReady von 'nicht vorhanden' unterscheiden.
    """
    region = _geo.crop(_geo.to_client(bgr), roi)
    if region is None:
        return None
    best = None
    for lang in ('de', 'en'):
        tpl = _load_template(lang, word)
        if tpl is None:
            continue
        ok, _pt, ncc = match_word(region, tpl)
        if ok and (best is None or ncc > best):
            best = ncc
    if best is None:
        return None  # kein Template -> NotReady
    return (best >= thresh, best)


def dialog_state(bgr):
    """``'locked'`` | ``'unlocked'`` | ``None`` per NCC-Marker-Templates.

    LOCKED  = Zeile ``eine_neue_technik`` vorhanden (Erstgespraech),
    UNLOCKED = Zeile ``energiesplitter_extrahieren`` vorhanden. Fehlen BEIDE
    Marker-Templates (Phase-0) ODER ist kein Dialog erkennbar -> ``None``
    (NotReady/kein Dialog). Wirft NIE.
    """
    if bgr is None:
        return None
    unlocked = _word_in_region(bgr, _geo.ROI_DIALOG, 'energiesplitter_extrahieren',
                               NCC_WORD)
    locked = _word_in_region(bgr, _geo.ROI_DIALOG, 'eine_neue_technik', NCC_WORD)
    if unlocked is None and locked is None:
        return None  # keine Marker-Templates gebundelt -> NotReady
    if unlocked is not None and unlocked[0]:
        return 'unlocked'
    if locked is not None and locked[0]:
        return 'locked'
    return None


def shop_open(bgr):
    """``True``, wenn ein Shop offen ist (``laden_header``-NCC). NotReady -> False.

    Fehlt das Header-Template (Phase-0), liefert die Funktion ``False`` (sicher:
    'nicht offen' -> kein Kauf), NICHT True. Wirft NIE.
    """
    if bgr is None:
        return False
    res = _word_in_region(bgr, _geo.ROI_PANEL_HEADER, 'laden_header', NCC_HEADER)
    return bool(res is not None and res[0])


def panel_is_bag(bgr):
    """``True``, wenn das rechte Panel die Tasche (``inventar_header``) ist.

    Unterscheidet Inventar von Ausruestungsfenster per Header-NCC. NotReady
    (kein Template) -> ``False`` (sicher: nicht als Tasche behandeln). Wirft NIE.
    """
    if bgr is None:
        return False
    inv = _word_in_region(bgr, _geo.ROI_PANEL_HEADER, 'inventar_header', NCC_HEADER)
    return bool(inv is not None and inv[0])


# ----------------------------------------------------------------------------
# Shop-Item / Stack / Splitter-Wachstum
# ----------------------------------------------------------------------------
def find_shop_item(bgr, item_template, roi=None, thresh=NCC_ITEM):
    """Sucht ``item_template`` (Item-Icon) im Shop -> ``(ok, pt, ncc)``.

    ``pt`` = Icon-Mitte im CLIENT-Koordinatensystem. Ohne Template / kein Treffer
    -> ``(False, None, ncc)``. Wirft NIE. (Phase-0: das Hammer-/Dolch-Icon fehlt
    in ``inventory_icons/`` -> der Bot ruft das erst nach P0.1 mit echtem Template.)
    """
    if np is None or _cv is None or bgr is None or item_template is None:
        return (False, None, 0.0)
    client = _geo.to_client(bgr)
    region = _geo.crop(client, roi) if roi is not None else client
    if region is None:
        return (False, None, 0.0)
    ok, pt, ncc = match_word(region, item_template)
    if not ok or pt is None or ncc < thresh:
        return (False, None, ncc)
    ox, oy = (roi[0], roi[1]) if roi is not None else (0, 0)
    tpl = _to_bgr(item_template)
    th, tw = tpl.shape[:2]
    center = (ox + pt[0] + tw // 2, oy + pt[1] + th // 2)
    return (True, center, ncc)


def read_shop_stack(slot_bgr):
    """Liest die Stack-Groesse auf einem Shop-Slot -> ``int | None``.

    PHASE-0-STUB: Die Shop-Stack-Zahl steht in EINER anderen Geometrie/Font als
    der Inventar-Zaehler; ohne kalibrierte Shop-Digit-Crops (P0.3) ist ein
    confidenter Read nicht moeglich. Liefert daher defensiv ``None`` (NotReady) ->
    der Aufrufer (Bot) waehlt den kleinsten sicheren Stack ODER stoppt, kauft NIE
    auf Basis einer geratenen Menge. Wirft NIE.
    # TODO-live-asset: Shop-Stack-Digit-Templates + ROI kalibrieren (P0.3).
    """
    return None


def read_splitter_growth(before, after):
    """Zuwachs am Splitter-Slot zwischen ``before`` und ``after`` -> ``int``.

    PHASE-0: Ohne Splitter-Icon/Verarbeitungs-Crop (P0.5) kann der reale Stack-
    Wert nicht gelesen werden. Liefert defensiv ``0`` (Fallback 'kein messbarer
    Zuwachs') -> die 1:1-Verifikation (``verify_process``) verlangt einen
    POSITIVEN Zuwachs und stoppt damit sicher, statt blind zu dekrementieren.
    Wirft NIE.
    # TODO-live-asset: Splitter-Slot-ROI + Stack-Diff kalibrieren (P0.5).
    """
    return 0


# ----------------------------------------------------------------------------
# Vertrags-API fuer den Bot (bot.py ruft genau diese Namen). Defensiv und
# NotReady-bewusst: ohne Live-Assets/Kalibrierung (Phase-0) liefern sie sicher
# None/0/False (konsistent zur GATE-Semantik) und werfen NIE -- sie scharfen
# KEINE Gold-Aktion (Item-Icons/Lattice fehlen -> echte Messung erst nach P0).
# ----------------------------------------------------------------------------
def load_template(key):
    """Laedt ein NCC-Template per Schluessel als BGR -> ``ndarray | None``.

    Reihenfolge: erst ein Item-Icon ``inventory_icons/<key>.png``, dann ein
    Wortbild-Template (``de`` bevorzugt, sonst ``en``). Fehlt beides (Phase-0:
    Item-Icons/Wortbilder noch nicht gebundelt) -> ``None`` (der Detektor
    behandelt None defensiv als 'kein Treffer'). Wirft nie.
    """
    if _cv is None or not key:
        return None
    icon = _icon_path(key)
    if _exists(icon):
        try:
            img = _cv.imread(icon, _cv.IMREAD_COLOR)
            if img is not None:
                return img
        except Exception:
            pass
    for lang in ('de', 'en'):
        tpl = _load_template(lang, key)
        if tpl is not None:
            return tpl
    return None


def item_template_available(item):
    """``True``, wenn das Item-Icon ``inventory_icons/<item>.png`` gebundelt ist.

    Reine Dateisystem-Pruefung -- KEINE Messung. Phase-0: die Crops fehlen noch
    (User-Lieferung P0.1), daher ``False`` -> der Bot stoppt 'item_template_
    missing', statt einen Bestand zu raten. Wirft nie.
    """
    if not item:
        return False
    return _exists(_icon_path(item))


def count_item(bgr, item):
    """Zaehlt Exemplare von ``item`` im Inventar -> ``int``.

    PHASE-0-STUB: Ohne Item-Icon (P0.1) und kalibriertes Inventar-Lattice (P0.4)
    ist KEINE messbare Zaehlung moeglich. Liefert defensiv ``0`` (NotReady) ->
    der Dolch-Modus stoppt sauber ('done', 0 Haemmer), statt blind zu draggen.
    Wirft nie.
    # TODO-live-asset: Item-Icon + Inventar-Lattice -> Treffer pro Slot zaehlen.
    """
    return 0


def free_slot_count(bgr):
    """Zaehlt freie (leere) Inventar-Slots -> ``int``.

    PHASE-0-STUB: Das leere-Slot-Erkennen braucht das kalibrierte Inventar-
    Lattice + ein Leer-Slot-Muster (P0.4). Liefert defensiv ``0`` (NotReady) ->
    der Bot behandelt das wie 'kein Platz' und kauft NICHT. Wirft nie.
    # TODO-live-asset: Inventar-Lattice + Leer-Slot-Maske (P0.4).
    """
    return 0


def inventory_signature(bgr):
    """Kompakte Signatur des Inventars (fuer Diff vor/nach einem Kauf).

    PHASE-0-STUB: Ohne kalibriertes Lattice (P0.4) gibt es kein stabiles
    Slot-Raster, an dem sich ein Diff bilden liesse. Liefert defensiv ``None``
    (NotReady) -> ``diff_landing_slot`` liefert dann ``None`` und der Kauf wird
    nicht in einen Drag ueberfuehrt. Wirft nie.
    # TODO-live-asset: Lattice-basierte Slot-Signatur (P0.4).
    """
    return None


def diff_landing_slot(before, after):
    """Bestimmt den Slot, in dem ein gekauftes Item gelandet ist (Diff).

    PHASE-0-STUB: Braucht zwei vergleichbare ``inventory_signature``-Werte
    (die Phase-0 ``None`` sind). Liefert defensiv ``None`` (NotReady) -> der Bot
    behandelt den Lande-Slot als unbekannt und draggt NICHT. Wirft nie.
    # TODO-live-asset: Signatur-Diff -> veraenderter Slot (P0.4).
    """
    return None


def find_inventory_item(bgr, item):
    """Sucht ``item`` im Inventar -> ``(ok: bool, slot)``.

    PHASE-0-STUB: Ohne Item-Icon (P0.1) und Lattice (P0.4) ist kein Treffer
    bestimmbar. Liefert defensiv ``(False, None)`` (NotReady) -> der Drag-Pfad
    findet keine verifizierte Quelle und stoppt 'drag_unsafe' (KEIN Drag).
    Wirft nie.
    # TODO-live-asset: Item-Icon-NCC ueber das Inventar-Lattice (P0.1/P0.4).
    """
    return (False, None)


def slot_is(bgr, slot, item):
    """``True``, wenn auf ``slot`` das Icon ``item`` liegt (Drag-Ziel-Check).

    PHASE-0-STUB: Verlangt Item-Icon (P0.1) + Lattice (P0.4), um den Slot-
    Inhalt zu klassifizieren. Liefert defensiv ``False`` (NotReady) -> der Drag
    wird als unsicher abgebrochen (Quelle/Ziel nicht bestaetigt). Wirft nie.
    # TODO-live-asset: Slot-Crop -> Item-Icon-NCC (P0.1/P0.4).
    """
    return False


def read_shop_stack_sizes(bgr):
    """Liest die zur Laufzeit angebotenen Stack-Groessen aus dem Shop -> tuple.

    PHASE-0-STUB: Die Stack-Zahlen brauchen kalibrierte Shop-Digit-Crops (P0.3,
    vgl. :func:`read_shop_stack`). Liefert defensiv ``None`` (NotReady) -> der
    Bot faellt auf das gemessene Shop-Bild-Tupel zurueck (siehe
    ``_read_shop_stack_sizes`` in bot.py). Wirft nie.
    # TODO-live-asset: Shop-Stack-Digit-Templates + Slot-ROIs (P0.3).
    """
    return None


__all__ = [
    'assets_ready', 'match_word', 'find_npc_name', 'selection_ring_present',
    'dialog_state', 'shop_open', 'panel_is_bag', 'find_shop_item',
    'read_shop_stack', 'read_splitter_growth',
    'load_template', 'item_template_available', 'count_item',
    'free_slot_count', 'inventory_signature', 'diff_landing_slot',
    'find_inventory_item', 'slot_is', 'read_shop_stack_sizes',
    'HAMMER_WORDS', 'DAGGER_EXTRA_WORDS', 'HAMMER_ICONS', 'DAGGER_EXTRA_ICONS',
    'NCC_WORD', 'NCC_HEADER', 'NCC_ITEM',
]
