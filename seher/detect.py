"""Pure Erkennungsfunktionen fuer den Seherwettstreit (headless testbar).

Alle Funktionen arbeiten auf BGR-Arrays (wie WindowCapture.get_screenshot()).
Methodenwahl ist benchmark-belegt (tools_seher/benchmark.py):
- Fenster-Anker: Titel-Template via cv2.matchTemplate (NCC) -- 1.0 auf den
  Kalibrier-Fixtures, robust gegen Fensterverschiebung.
- Kreuz-Erkennung: ROTE-PIXEL-ZAEHLUNG im Slot (das Kreuz ist gesaettigt rot,
  sonst ist in den Slots nie Rot) -- hintergrundunabhaengig (weisse UND
  schwarze Karten), shift-tolerant, schlaegt Template-NCC im Benchmark.
- Rundenauswertung/Resultat: BILD-DIFF der Score-Boxen (kein OCR noetig:
  welcher Score sich aendert bestimmt Sieg/Niederlage; keiner = Remis).
"""
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from seher import geometry as G

_TPL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'templates')
_title_tpl = None


def _resource_dir():
    """Template-Ordner aufloesen (Dev: Paketordner; frozen: respath)."""
    try:
        from respath import resource_path
        cand = resource_path(os.path.join('seher', 'templates'))
        if os.path.isdir(cand):
            return cand
    except Exception:
        pass
    return _TPL_DIR


def title_template():
    """Das Anker-Template (lazy geladen, BGR)."""
    global _title_tpl
    if _title_tpl is None:
        path = os.path.join(_resource_dir(), 'title.png')
        _title_tpl = cv2.imread(path, cv2.IMREAD_COLOR)
    return _title_tpl


def find_anchor(bgr):
    """Sucht den Fenster-Anker. Liefert (ok, (x, y), ncc)."""
    tpl = title_template()
    if tpl is None or bgr is None:
        return (False, (0, 0), 0.0)
    if bgr.shape[0] < tpl.shape[0] or bgr.shape[1] < tpl.shape[1]:
        return (False, (0, 0), 0.0)
    res = cv2.matchTemplate(bgr, tpl, cv2.TM_CCOEFF_NORMED)
    _mn, mx, _ml, loc = cv2.minMaxLoc(res)
    return (mx >= G.ANCHOR_NCC_MIN, (int(loc[0]), int(loc[1])), float(mx))


def _roi(bgr, anchor, rel_x, rel_y, w, h):
    """ROI-Ausschnitt (clippt defensiv an den Bildrand)."""
    x = anchor[0] + rel_x
    y = anchor[1] + rel_y
    x0, y0 = max(0, x), max(0, y)
    return bgr[y0:max(y0, y + h), x0:max(x0, x + w)]


def red_count(bgr_roi):
    """Anzahl gesaettigt-roter Pixel (das Kreuz) im Ausschnitt."""
    if bgr_roi is None or bgr_roi.size == 0:
        return 0
    b = bgr_roi.astype(np.int16)
    mask = (b[:, :, 2] > 140) & (b[:, :, 1] < 90) & (b[:, :, 0] < 90)
    return int(mask.sum())


def cross_at_slot(bgr, anchor, slot):
    """True + Pixelzahl, wenn der Slot ein rotes Kreuz traegt."""
    n = red_count(_roi(bgr, anchor, slot[0], slot[1], G.CARD_W, G.CARD_H))
    return (n >= G.CROSS_RED_MIN, n)


def score_crop(bgr, anchor, which):
    """Kopie des Score-Box-Ausschnitts ('opp' | 'me') fuer Diff-Vergleiche."""
    x, y, w, h = G.SCORE_OPP_ROI if which == 'opp' else G.SCORE_ME_ROI
    return _roi(bgr, anchor, x, y, w, h).copy()


def crops_differ(a, b, delta=40, min_px=15):
    """True, wenn sich zwei gleichgrosse Ausschnitte sichtbar unterscheiden."""
    if a is None or b is None or a.shape != b.shape or a.size == 0:
        return False
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return int((d > delta).sum()) >= min_px


def message_activity(bgr, anchor):
    """Anzahl heller Text-Pixel im Nachrichtenband (Debug-Signal)."""
    x, y, w, h = G.MESSAGE_ROI
    roi = _roi(bgr, anchor, x, y, w, h)
    if roi.size == 0:
        return 0
    return int((roi.astype(np.int16).mean(axis=2) > 120).sum())


@dataclass
class Observation:
    """Ein ausgewerteter Frame."""
    ok: bool
    anchor: tuple
    ncc: float
    my_crossed: set = field(default_factory=set)     # Kartenwerte 0-8
    opp_black_crossed: int = 0
    opp_white_crossed: int = 0
    cross_counts: dict = field(default_factory=dict)  # Debug: value -> px
    message_px: int = 0


def observe_at(bgr, anchor, ncc=1.0):
    """Erkennung mit BEKANNTEM Anker (kein Re-Match -> billig fuer schnelles
    Pollen innerhalb einer Runde, bei der das Fenster fix steht)."""
    obs = Observation(ok=True, anchor=anchor, ncc=ncc)
    for value in range(9):
        hit, n = cross_at_slot(bgr, anchor, G.slot_of_value(value))
        obs.cross_counts[value] = n
        if hit:
            obs.my_crossed.add(value)
    obs.opp_black_crossed = sum(
        1 for s in G.OPP_BLACK_SLOTS if cross_at_slot(bgr, anchor, s)[0])
    obs.opp_white_crossed = sum(
        1 for s in G.OPP_WHITE_SLOTS if cross_at_slot(bgr, anchor, s)[0])
    obs.message_px = message_activity(bgr, anchor)
    return obs


def observe(bgr):
    """Voller Erkennungs-Durchlauf auf einem Frame (findet den Anker selbst)."""
    ok, anchor, ncc = find_anchor(bgr)
    if not ok:
        return Observation(ok=False, anchor=anchor, ncc=ncc)
    return observe_at(bgr, anchor, ncc)


def crossed_set(bgr, anchor):
    """Nur die Menge der eigenen gekreuzten Karten (billig, bekannter Anker)."""
    return {v for v in range(9)
            if cross_at_slot(bgr, anchor, G.slot_of_value(v))[0]}


# Quiescence-ROI (anker-relativ): eigene Hand + Nachrichtenband. Liegt
# vollstaendig IM Fenster (keine lebende Spielwelt, kein Cursor-Parkpunkt)
# -> wird zwischen den Runden wirklich stabil. x von der linken Kartenkante
# bis rechts der Hand, y vom Nachrichtenband bis unter die schwarze Reihe.
QUIESCENCE_ROI = (-122, 145, 230, 170)   # x, y, w, h relativ zum Anker


def quiescence_crop(bgr, anchor):
    """Bildausschnitt fuer die Animations-/Stabilitaets-Erkennung."""
    x, y, w, h = QUIESCENCE_ROI
    return _roi(bgr, anchor, x, y, w, h).copy()
