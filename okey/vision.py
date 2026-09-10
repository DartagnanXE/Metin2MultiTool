# -*- coding: utf-8 -*-
"""Bilderkennung des Okey-Events -- was steht gerade auf dem Bildschirm?

Rein lesend: dieses Modul klickt nie, es beantwortet nur Fragen. Alle Funktionen
sind defensiv (werfen nie) und liefern im Zweifel "nicht erkannt" -- der Runner
wartet dann lieber einen Frame laenger, statt blind zu klicken.

DIE KARTENERKENNUNG hat zwei voneinander unabhaengige Teile, und das ist Absicht:

  * FARBE ueber den Farbton. Gemessen (2026-09-10): Blau 102, Gelb 25, jeweils
    bei Saettigung ueber 200. Zwischen den drei Farben liegen riesige Luecken --
    das ist der robusteste Teil der Erkennung.
  * WERT ueber die Ziffer. Sie steht dunkel auf kraeftigem Grund und laesst sich
    sauber freistellen; verglichen wird gegen Schablonen in ``okey_templates/``.

Wird die Ziffer NICHT sicher erkannt, gilt die ganze Karte als unbekannt. Die
Strategie bekommt dann bewusst kein Halbwissen serviert -- eine falsch gelesene
Karte waere schlimmer als eine fehlende, weil sie die Kartenzaehlung dauerhaft
verdirbt (siehe strategy.naechster_zug, das solche Stellungen abweist).
"""

import os

try:
    import cv2 as cv
    import numpy as np
except Exception:                       # pragma: no cover
    cv = None
    np = None

from . import coords as C, templates_dir

#: Mindest-Uebereinstimmung der Ziffer. Darunter gilt die Karte als unbekannt.
DIGIT_MIN_SCORE = 0.62

#: Schwellenfaktor fuer die Tinte (Anteil des Ausschnitt-Mittelwerts).
#:
#: 0,55 statt 0,62 -- und das ist kein Feinschliff, sondern ein echter Fehler,
#: den die erste Fassung hatte: bei 0,62 zog die BLAUE Karte Rahmen-Pixel mit in
#: die Maske (Rahmen 23x28 statt 17x26 bei der gelben), die normierte Bitmaske
#: verzerrte sich, und dieselbe Ziffer 7 kam auf einer blauen Karte auf Guete
#: 1,00, auf einer gelben nur auf 0,377 -- also unerkannt. Bei 0,55 liefern
#: BEIDE Farben exakt 16x25 (gemessen 2026-09-10). Die Schablonen muessen
#: farbunabhaengig sein, sonst braeuchte man 24 statt 8.
INK_FACTOR = 0.55

#: Mindest-Uebereinstimmung im Zaehler-Schriftschnitt. Etwas strenger als bei
#: den Karten: die Ziffern sind winzig, eine Verwechslung waere hier eine
#: falsche ZAHL -- und die Gegenprobe soll lieber schweigen als irren.
COUNTER_MIN_SCORE = 0.70

_digit_cache = None


def _digit_templates():
    """Die Ziffer-Schablonen 1..8 als Bitmasken (gecacht). ``{}`` = keine da."""
    global _digit_cache
    if _digit_cache is not None:
        return _digit_cache
    if cv is None:
        return {}
    out = {}
    for wert in range(1, 9):
        pfad = os.path.join(templates_dir(), 'ziffer_%d.png' % wert)
        bild = cv.imread(pfad, cv.IMREAD_GRAYSCALE)
        if bild is not None:
            out[wert] = bild
    _digit_cache = out
    return out


def fehlende_ziffern():
    """Welche Werte 1..8 haben noch KEINE Schablone? (Diagnose fuers Log.)"""
    da = _digit_templates()
    return [v for v in range(1, 9) if v not in da]


# ---------------------------------------------------------------------------
# Karten
# ---------------------------------------------------------------------------

def _farbe_von(hsv_box):
    """Farbton-Mehrheit eines Kartenausschnitts -> ``'R'|'B'|'G'`` oder None."""
    H = hsv_box[:, :, 0].astype(int)
    S = hsv_box[:, :, 1].astype(int)
    V = hsv_box[:, :, 2].astype(int)
    kraeftig = (S >= C.CARD_MIN_SAT) & (V >= C.CARD_MIN_VAL)
    if kraeftig.mean() < C.CARD_PRESENT_MIN:
        return None
    h = H[kraeftig]
    for name, (lo, hi) in C.COLOR_HUES.items():
        if lo <= hi:
            treffer = (h >= lo) & (h <= hi)
        else:
            # Rot laeuft ueber den Nullpunkt des Farbkreises.
            treffer = (h >= lo) | (h <= hi)
        if treffer.mean() > 0.5:
            return name
    return None


def _ziffer_maske(bgr_box):
    """Die Ziffer freistellen -> 16x24-Bitmaske, oder ``None``.

    Der Kartenrahmen ist ebenfalls dunkel, deshalb wird nur die INNENFLAECHE
    betrachtet. Die Schwelle haengt am Mittelwert des Ausschnitts, nicht an
    einem festen Grauwert -- so bleibt sie unabhaengig davon, wie hell die
    Kartenfarbe gerade gerendert wird.
    """
    g = cv.cvtColor(bgr_box, cv.COLOR_BGR2GRAY)
    if g.shape[0] < 20 or g.shape[1] < 14:
        return None
    inner = g[8:-8, 6:-6]
    if inner.size == 0:
        return None
    tinte = (inner < inner.mean() * INK_FACTOR).astype(np.uint8)
    ys, xs = np.nonzero(tinte)
    if len(xs) < 20:
        return None
    cut = tinte[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return cv.resize(cut * 255, (16, 24), interpolation=cv.INTER_AREA)


def _wert_von(bgr_box):
    """``(wert, guete)`` der Ziffer -- ``(None, guete)``, wenn unsicher."""
    schablonen = _digit_templates()
    if not schablonen:
        return (None, 0.0)
    maske = _ziffer_maske(bgr_box)
    if maske is None:
        return (None, 0.0)
    bester, beste = None, 0.0
    for wert, vorlage in schablonen.items():
        res = cv.matchTemplate(maske, vorlage, cv.TM_CCOEFF_NORMED)
        s = float(res.max())
        if s > beste:
            bester, beste = wert, s
    if beste < DIGIT_MIN_SCORE:
        return (None, beste)
    return (bester, beste)


def read_field(bgr):
    """Die fuenf offenen Kartenplaetze lesen.

    :return: Liste mit fuenf Eintraegen -- ``(wert, farbe)`` fuer eine erkannte
        Karte, ``'leer'`` fuer einen freien Platz, ``'?'`` fuer belegt-aber-
        nicht-lesbar. Wirft nie.
    """
    if cv is None or bgr is None:
        return ['?'] * 5
    out = []
    for i in range(5):
        try:
            x0, y0, x1, y1 = C.card_box(i)
            box = bgr[y0:y1, x0:x1]
            if box.size == 0:
                out.append('?')
                continue
            farbe = _farbe_von(cv.cvtColor(box, cv.COLOR_BGR2HSV))
            if farbe is None:
                out.append('leer')
                continue
            wert, _guete = _wert_von(box)
            out.append((wert, farbe) if wert else '?')
        except Exception:
            out.append('?')
    return out


def field_diag(bgr):
    """Rohwerte je Platz fuers Debug-Log (Farbe, Ziffer, Guete)."""
    if cv is None or bgr is None:
        return []
    zeilen = []
    for i in range(5):
        try:
            x0, y0, x1, y1 = C.card_box(i)
            box = bgr[y0:y1, x0:x1]
            hsv = cv.cvtColor(box, cv.COLOR_BGR2HSV)
            S = hsv[:, :, 1].astype(int)
            V = hsv[:, :, 2].astype(int)
            anteil = float(((S >= C.CARD_MIN_SAT) & (V >= C.CARD_MIN_VAL)).mean())
            farbe = _farbe_von(hsv)
            wert, guete = _wert_von(box)
            zeilen.append({'platz': i + 1, 'belegt': round(anteil, 2),
                           'farbe': farbe or '-', 'wert': wert or '-',
                           'guete': round(guete, 3)})
        except Exception:
            zeilen.append({'platz': i + 1, 'belegt': -1.0})
    return zeilen


# ---------------------------------------------------------------------------
# Zahlen (Rest-Karten, Punkte)
# ---------------------------------------------------------------------------

_counter_cache = None


def _counter_templates():
    """Ziffern 0..9 des ZAEHLER-Schriftschnitts (klein, hell auf dunkel)."""
    global _counter_cache
    if _counter_cache is not None:
        return _counter_cache
    if cv is None:
        return {}
    out = {}
    for z in range(10):
        pfad = os.path.join(templates_dir(), 'zaehler', 'z_%d.png' % z)
        bild = cv.imread(pfad, cv.IMREAD_GRAYSCALE)
        if bild is not None:
            out[z] = bild
    _counter_cache = out
    return out


def _zahl_lesen(bgr, box):
    """Eine mehrstellige Zahl aus einem dunklen Feld lesen -> int oder None.

    EIGENER SCHRIFTSCHNITT: Die Ziffern hier sind winzig (gemessen 7x14) und
    HELL auf dunklem Grund -- die Karten-Schablonen (17x26, dunkel auf hell)
    passen darauf nicht. Erste Fassung versuchte genau das und lieferte
    durchgaengig ``None``.

    DIESE ZAHLEN SIND NUR EINE GEGENPROBE, keine Grundlage. Der Bot fuehrt
    Rest-Karten und Punkte selbst Buch -- er weiss ja, welche Karten er gesehen
    und welche Kombinationen er gespielt hat. Stimmt der Bildschirm nicht mit
    der eigenen Rechnung ueberein, ist etwas schiefgelaufen (falsch gelesene
    Karte) und der Runner haelt an. Ist die Zahl nicht lesbar, laeuft er auf
    der eigenen Buchfuehrung weiter und vermerkt das im Log.

    Von den zehn Ziffern liegen bisher 0/1/3/4/9 als Schablone vor (aus den
    Bildern des Nutzers); die uebrigen tauchten dort nicht auf. Eine Zahl mit
    einer unbekannten Ziffer gibt sauber ``None`` statt zu raten.
    """
    if cv is None or bgr is None:
        return None
    try:
        x0, y0, x1, y1 = box
        feld = bgr[y0:y1, x0:x1]
        if feld.size == 0:
            return None
        g = cv.cvtColor(feld, cv.COLOR_BGR2GRAY)
        hell = (g > 130).astype(np.uint8)
        n, lab, stats, _c = cv.connectedComponentsWithStats(hell, 8)
        stellen = []
        for k in range(1, n):
            x, y, w, h, a = stats[k]
            if a < 5 or h < 6 or w < 3:
                continue
            teil = (lab[y:y + h, x:x + w] == k).astype(np.uint8) * 255
            stellen.append((x, cv.resize(teil, (10, 16),
                                         interpolation=cv.INTER_NEAREST)))
        if not stellen:
            return 0            # leeres Feld = 0 (kommt am Spielende vor)
        schablonen = _counter_templates()
        if not schablonen:
            return None
        ziffern = []
        for _x, maske in sorted(stellen):
            bester, beste = None, 0.0
            for z, vorlage in schablonen.items():
                punkte = float(cv.matchTemplate(maske, vorlage,
                                                cv.TM_CCOEFF_NORMED).max())
                if punkte > beste:
                    bester, beste = z, punkte
            if bester is None or beste < COUNTER_MIN_SCORE:
                return None     # unbekannte Ziffer -> lieber nichts sagen
            ziffern.append(bester)
        return int(''.join(str(z) for z in ziffern))
    except Exception:
        return None


def read_deck_count(bgr):
    """Wie viele Karten liegen noch im Stapel? (``None`` = nicht lesbar)"""
    return _zahl_lesen(bgr, C.DECK_COUNT_BOX)


def read_points(bgr):
    """Aktuelle Punktzahl (``None`` = nicht lesbar)."""
    return _zahl_lesen(bgr, C.POINTS_BOX)


def safe_mode_ink(bgr):
    """Anteil heller Pixel im Kaestchen "Sicherer Modus" (0,0 .. 1,0).

    Nur ein Messwert, keine Deutung: gesetzt oder nicht entscheidet der Runner
    aus dem Vergleich vorher/nachher. Gemessen mit Haken: 0,136.
    ``-1.0`` heisst "nicht messbar".
    """
    if cv is None or bgr is None:
        return -1.0
    try:
        x0, y0, x1, y1 = C.SAFE_MODE_BOX
        feld = bgr[y0:y1, x0:x1]
        if feld.size == 0:
            return -1.0
        g = cv.cvtColor(feld, cv.COLOR_BGR2GRAY)
        return float((g > 150).mean())
    except Exception:
        return -1.0
