"""Puzzle-Board-Erkennung: liefert den Offset des 260x170-Boards im Fenster.

Drei Modi (vgl. REDESIGN_SPEC.md §3), gewaehlt vom UI und persistiert:

* ``default`` -- aktuelles Verhalten, feste Position (270, 227).
* ``auto``    -- cv2-Template-Matching bei FESTER Board-Groesse (Single-Scale)
                 leitet den Offset ab; bei Misserfolg -> Fallback Default + Log.
* ``mark``    -- nutzt den per Overlay (overlay_mark.py) markierten, gespeicherten
                 Offset; fehlt/ungueltig -> Fallback Default + Log.

Vertrag (FROZEN, von puzzle.py/Integration konsumiert):

    resolve_offset(mode, screenshot=None, saved_offset=None,
                   default_offset=(270, 227)) -> tuple[int, int]

  * Rueckgabe IMMER ein 2-int-Tupel ``(x, y)`` im gueltigen Fensterinhalt.
  * Wirft NIEMALS. Liefert NIEMALS ``None`` (anders als calibration.find_puzzle_offset,
    das hier nur als Verifikations-Helfer wiederverwendet wird).

Bewusst defensiv und dependency-leicht:

* ``cv2``/``numpy`` werden WEICH importiert. Die Pfade ``default``/``mark`` und die
  gesamte Clamp-/Fallback-Logik funktionieren OHNE cv2 -- nur der ``auto``-Pfad
  braucht cv2; fehlt es, faellt ``auto`` sauber auf Default zurueck. Dadurch ist
  das Modul wie der Rest des Projekts headless per ``unittest`` testbar
  (Mock-Screenshot), ohne Capture-/GUI-Stack.
* Form-/Region-Pruefungen werden aus ``calibration`` WIEDERVERWENDET (nicht neu
  erfunden): ``validate_puzzle_region`` und ``find_puzzle_offset``.

Bildkonvention (wie puzzle.py): ``screenshot`` hat Form ``(Hoehe, Breite, 3)``,
Zugriff ``img[y, x]``, Kanalreihenfolge BGR. Der Offset ``(x, y)`` ist die
linke-obere Ecke des Boards IM Fensterinhalt (nach WindowCapture-Rand-Crop).
"""

import calibration
from respath import resource_path
from i18n import t

# Logging weich einbinden -- ein fehlender/kaputter Logger darf die Erkennung
# nie stoppen (gleiche Disziplin wie windowcapture.py/debuglog.py).
try:
    from debuglog import log
except Exception:  # pragma: no cover - reiner Fallback
    log = None

# cv2/numpy weich einbinden: nur der auto-Pfad braucht sie.
try:
    import cv2 as cv
except Exception:  # pragma: no cover - auto faellt dann auf Default zurueck
    cv = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


# -- Konstanten (an puzzle.py / REDESIGN_SPEC ausgerichtet) ----------------

# Board-Groesse (Breite, Hoehe), identisch zu PuzzleBot.PUZZLE_WINDOW_SIZE.
BOARD_SIZE = calibration.DEFAULT_EXPECTED_SIZE          # (260, 170)

# Standard-/Fallback-Offset, identisch zu PuzzleBot.PUZZLE_WINDOW_POSITION.
DEFAULT_OFFSET = (270, 227)

# Erkennungsmodi.
MODE_DEFAULT = 'default'
MODE_AUTO = 'auto'
MODE_MARK = 'mark'
VALID_MODES = (MODE_DEFAULT, MODE_AUTO, MODE_MARK)

# Template-Matching-Schwelle -- gleiche Konvention wie die Truhen-Suche in
# puzzle.try_to_put_chest (TM_CCOEFF_NORMED, Schwelle 0.7).
MATCH_THRESHOLD = 0.7

# Bevorzugter Pfad des Board-Templates (von D zu buendeln, vgl. spec §6 datas).
BOARD_TEMPLATE_PATH = 'images/puzzle_board.png'

# Konservative Obergrenze fuer den Fensterinhalt (800x600 abzueglich Rand/Titel,
# vgl. windowcapture.WindowCapture: border=8, titlebar=30 -> ~784x562). Wird nur
# als Clamp-Grenze genutzt, wenn KEIN echter Screenshot vorliegt, aus dem sich
# die tatsaechliche Groesse ableiten laesst.
CONTENT_WIDTH = 784
CONTENT_HEIGHT = 562


# -- interne Helfer --------------------------------------------------------

def _log_event(message, **fields):
    """Strukturierte Log-Zeile (State 0), schluckt Logger-Fehler still."""
    if log is None:
        return
    try:
        log.event(0, message, **fields)
    except Exception:
        pass


def _as_int_pair(value):
    """Wandelt ``value`` defensiv in ``(int, int)`` oder gibt ``None`` zurueck."""
    try:
        x = int(value[0])
        y = int(value[1])
        return (x, y)
    except Exception:
        return None


def _bounds(screenshot):
    """Liefert die zulaessige Clamp-Grenze ``(max_x, max_y)`` der linken-oberen
    Board-Ecke, sodass das Board komplett ins Bild passt.

    Bevorzugt die tatsaechliche Form von ``screenshot`` (calibration._shape,
    funktioniert mit numpy UND Listen); sonst die konservativen
    Inhalts-Defaults.
    """
    board_w, board_h = BOARD_SIZE
    full_w, full_h = CONTENT_WIDTH, CONTENT_HEIGHT
    if screenshot is not None:
        h, w = calibration._shape(screenshot)
        if h is not None and w is not None and h > 0 and w > 0:
            full_w, full_h = w, h
    max_x = max(0, full_w - board_w)
    max_y = max(0, full_h - board_h)
    return max_x, max_y


def _clamp_offset(offset, screenshot=None):
    """Begrenzt ``offset`` so, dass das Board vollstaendig im Bild liegt.

    Gibt ``None`` zurueck, wenn ``offset`` nicht in ein int-Paar wandelbar ist
    (der Aufrufer entscheidet dann ueber den Fallback).
    """
    pair = _as_int_pair(offset)
    if pair is None:
        return None
    max_x, max_y = _bounds(screenshot)
    x = min(max(pair[0], 0), max_x)
    y = min(max(pair[1], 0), max_y)
    return (x, y)


def _safe_default(default_offset, screenshot=None):
    """Garantiert ein gueltiges Default-Tupel (clamped, nie None)."""
    clamped = _clamp_offset(default_offset, screenshot)
    if clamped is not None:
        return clamped
    # Selbst der uebergebene Default war unbrauchbar -> harter Modul-Default.
    clamped = _clamp_offset(DEFAULT_OFFSET, screenshot)
    return clamped if clamped is not None else DEFAULT_OFFSET


def _region_ok(screenshot, offset):
    """Prueft via calibration, ob der Crop an ``offset`` plausibel das Board zeigt.

    Reine WIEDERVERWENDUNG von calibration.validate_puzzle_region. Bei fehlendem
    Bild/Fehler defensiv ``False``. Ein leeres Startbrett gilt als gueltig (die
    Inhalts-Heuristiken sind dort nur noch Advisories, vgl. Blocker B).
    """
    try:
        if screenshot is None:
            return False
        x, y = offset
        crop = calibration._crop(screenshot, x, y, BOARD_SIZE[0], BOARD_SIZE[1])
        if crop is None:
            return False
        return calibration.validate_puzzle_region(crop, BOARD_SIZE).ok
    except Exception:
        return False


def _load_template():
    """Laedt das Board-Template via resource_path. ``None`` wenn nicht ladbar."""
    if cv is None:
        return None
    try:
        return cv.imread(resource_path(BOARD_TEMPLATE_PATH))
    except Exception:
        return None


def _match_template(screenshot, template):
    """Single-Scale TM_CCOEFF_NORMED-Match (Board-Groesse ist fix).

    Rueckgabe ``(max_val, (x, y))`` der besten Trefferposition oder ``None`` bei
    fehlendem cv2/Bild/Template oder Form-Fehler. Spiegelt die Truhen-Suche in
    puzzle.try_to_put_chest.
    """
    if cv is None or screenshot is None or template is None:
        return None
    try:
        result = cv.matchTemplate(screenshot, template, cv.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv.minMaxLoc(result)
        return float(max_val), (int(max_loc[0]), int(max_loc[1]))
    except Exception:
        return None


def _resolve_auto(screenshot, default_offset):
    """auto-Pfad: Template-Match -> abgeleiteter, verifizierter, geclampter Offset.

    Bei JEDEM Misserfolg (kein cv2, kein Template, schwacher Match, unplausible
    Region) -> Default-Fallback + Log. Wirft nie, liefert nie None.
    """
    safe = _safe_default(default_offset, screenshot)

    if cv is None:
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_no_cv2'), offset=safe)
        return safe

    if screenshot is None:
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_no_screenshot'), offset=safe)
        return safe

    template = _load_template()
    if template is None:
        # Kein Template -> bekannte Standardposition wenigstens verifizieren
        # (calibration.find_puzzle_offset prueft genau diese Stelle).
        verified = calibration.find_puzzle_offset(screenshot)
        pair = _clamp_offset(verified, screenshot) if verified else None
        if pair is not None:
            _log_event(t('detect.auto_template_missing_verified'),
                       mode=MODE_AUTO, offset=pair)
            return pair
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_template_missing_implausible',
                            path=BOARD_TEMPLATE_PATH),
                   offset=safe)
        return safe

    match = _match_template(screenshot, template)
    if match is None:
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_match_failed'),
                   offset=safe)
        return safe

    max_val, loc = match
    if max_val < MATCH_THRESHOLD:
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_match_too_weak',
                            max_val='{:.3f}'.format(max_val),
                            threshold=MATCH_THRESHOLD),
                   offset=safe)
        return safe

    candidate = _clamp_offset(loc, screenshot)
    if candidate is None:
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_match_pos_unusable'), offset=safe)
        return safe

    # Treffer zusaetzlich per Region-Plausibilitaet absichern, bevor er den
    # bewaehrten Default ersetzt. Schlaegt das fehl -> lieber Default.
    if not _region_ok(screenshot, candidate):
        _log_event(t('detect.fallback'), mode=MODE_AUTO,
                   reason=t('detect.reason_region_implausible',
                            candidate=candidate,
                            max_val='{:.3f}'.format(max_val)),
                   offset=safe)
        return safe

    _log_event(t('detect.auto_ok'), mode=MODE_AUTO, offset=candidate,
               max_val=round(max_val, 3))
    return candidate


def _resolve_mark(screenshot, saved_offset, default_offset):
    """mark-Pfad: gespeicherten Offset validieren/clampen; sonst Default + Log."""
    safe = _safe_default(default_offset, screenshot)

    if saved_offset is None:
        _log_event(t('detect.fallback'), mode=MODE_MARK,
                   reason=t('detect.reason_no_mark_offset'), offset=safe)
        return safe

    raw = _as_int_pair(saved_offset)
    candidate = _clamp_offset(saved_offset, screenshot)
    if raw is None or candidate is None:
        _log_event(t('detect.fallback'), mode=MODE_MARK,
                   reason=t('detect.reason_mark_offset_unreadable',
                            saved_offset=saved_offset),
                   offset=safe)
        return safe

    # M1-Fix: Liegt der gespeicherte Offset AUSSERHALB des gueltigen Bereichs
    # (Clamp veraendert ihn), ist die Markierung ungueltig -> Default-Fallback
    # + Log, statt den Offset still zu klemmen (das verletzte den Mark-Kontrakt).
    if candidate != raw:
        _log_event(t('detect.fallback'), mode=MODE_MARK,
                   reason=t('detect.reason_mark_offset_out_of_bounds', raw=raw),
                   offset=safe)
        return safe

    _log_event(t('detect.mark'), mode=MODE_MARK, offset=candidate)
    return candidate


# -- oeffentliche API ------------------------------------------------------

def resolve_offset(mode, screenshot=None, saved_offset=None,
                   default_offset=DEFAULT_OFFSET):
    """Liefert den ``(x, y)``-Offset der linken-oberen Board-Ecke im Fenster.

    :param mode: ``'default'`` | ``'auto'`` | ``'mark'`` (unbekannt -> default).
    :param screenshot: voller Fenster-Screenshot (numpy-Array ODER verschachtelte
        Liste) oder ``None``. Fuer ``auto`` noetig; sonst Fallback.
    :param saved_offset: ``(x, y)`` aus der Config (mark) oder ``None``.
    :param default_offset: Fallback-Offset (Default ``(270, 227)``).
    :return: 2-int-Tupel ``(x, y)``, vollstaendig im Fensterinhalt geclampt.

    Garantien: wirft NIE, liefert NIE ``None``.
    """
    try:
        normalized = str(mode).lower() if mode is not None else MODE_DEFAULT

        if normalized == MODE_AUTO:
            return _resolve_auto(screenshot, default_offset)
        if normalized == MODE_MARK:
            return _resolve_mark(screenshot, saved_offset, default_offset)
        if normalized != MODE_DEFAULT:
            _log_event(t('detect.unknown_mode'),
                       mode=normalized)
        return _safe_default(default_offset, screenshot)
    except Exception as exc:
        # Letzte Sicherung: selbst bei unerwartetem Fehler nie crashen/None.
        if log is not None:
            try:
                log.error(t('detect.resolve_error'), exc=exc)
            except Exception:
                pass
        try:
            return _safe_default(default_offset, screenshot)
        except Exception:
            return DEFAULT_OFFSET
