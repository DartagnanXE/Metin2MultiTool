"""Reine Bilderkennung des Angel-Minispiels als Mixin (kein eigener Zustand).

Beherbergt die drei Erkennungs-Methoden des FishingBot, die ausschliesslich aus
dem Capture lesen (Fisch-Position, Uhr/Minispiel, Tagesbelohnung) und dabei nur
auf bereits in :class:`fishingbot.FishingBot` definierte Klassen-/Instanz-Attribute
(``needle_img``, ``FISH_RANGE``, ``fish_pos_x`` ...) zugreifen.

Als Mixin herausgezogen, damit der zustandsbehaftete Cast-/State-Machine-Teil in
:mod:`fishingbot` schlank bleibt. ``FishingBot`` erbt von
:class:`FishingDetectMixin`; die Methodenaufloesung (``self.detect`` etc.) und
jeder ``self.``-Zugriff bleiben damit byte-identisch zur fruheren Single-Class.
"""

import math
import cv2 as cv
from time import time

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy kommt mit cv2; reiner Fallback
    np = None

from fishing_match import _match_template_max
from respath import resource_path


# -- Goldener-Thunfisch BESTAETIGUNGS-Dialog (nach dem Options-Klick) --------
#
# Nach dem Klick auf eine der drei Optionen (Freilassen/Aufschneiden/Koeder)
# antwortet der SERVER mit einem zweiten Fenster mit EINEM OK-Knopf (z.B. die
# Freilassen-Bonus-Meldung). Zwei harte Live-Befunde bestimmen das Design:
#   1. Das Fenster schwaerzt die Bildecken NICHT (max 125 statt 0) ->
#      detect_daily_reward sieht es nie; es braucht eine EIGENE Erkennung.
#   2. Das Fenster steht NICHT an fester Position: seine Hoehe haengt vom
#      Meldungstext ab und die Lage variiert (Live-Referenzen: OK-Mitte
#      (403,250) vs. (403,202) client). Fixe Koordinaten (v1.1.5) verfehlten
#      die zweite Variante -> der OK-Knopf wird jetzt per Template ueber den
#      GANZEN Frame GESUCHT (wie die Lagerfeuer-Label-Suche) und der Klick
#      geht auf den FUND, nicht auf eine Konstante.
#
# Erkennung = zwei Faktoren:
#   * Graustufen-NCC des OK-Knopf-Templates (images/golden_ok_knob.png,
#     20x32): Positives 0.81/1.00, staerkster Negativfall 0.61 -> Schwelle
#     0.70 mit Marge in beide Richtungen. Laeuft ohnehin nur im 10s-Fenster
#     nach dem Options-Klick.
#   * Leisten-Check: der Knopf sitzt auf einer breiten, FLACHEN Grau-Leiste;
#     beide Flanken (links/rechts vom Fund) muessen flach sein (std <= 12)
#     und duerfen weder schwarzes Loch noch ausgebrannte Flaeche sein.
#
# HELLIGKEITS-FENSTER BEWUSST WEIT (v1.6.12, 2026-08-18). Es stand auf
# 50..110 -- kalibriert an den drei Referenzen (gemessen 65,7 / 79,3 / 84,7).
# Das ist genau der Fehler, den dieses Projekt schon einmal teuer bezahlt hat:
# eine Schwelle an Stichproben statt an der Sache. Die Leiste ist
# HALBTRANSPARENT, ihre Helligkeit folgt also der Szene DAHINTER; an einer
# helleren Angelstelle waeren die 110 gerissen und der OK-Knopf waere -- bei
# perfekter Erkennung des Knopfes selbst -- ohne Klick geblieben. Genau die
# Beschwerde des Testers ("drueckt nicht mehr drauf"). Die eigentliche
# Unterscheidung leistet ohnehin die NCC-Schwelle (Positive 0,80/0,81/1,00
# gegen staerkstes Negativ 0,57 ueber alle 30 Referenzbilder) plus die
# Flachheit (Positive std <= 3,3 gegen Negative >= 8,7). Das Fenster soll nur
# noch "schwarzes Nichts" und "ausgebrannt weiss" ausschliessen.
GOLDEN_OK_TEMPLATE = 'images/golden_ok_knob.png'
GOLDEN_OK_NCC_MIN = 0.70
GOLDEN_OK_BAR_MEAN = (20.0, 200.0)
GOLDEN_OK_BAR_STD_MAX = 12.0

# -- Zweiter Pfad: die ENDEN der OK-Leiste (v1.6.13, User-Log 2026-09-02) ----
#
# Der Fall aus dem Log: Options-Klick 13:25:46, danach in 10 s KEIN OK-Klick,
# obwohl der Dialog stand. Am Screenshot gemessen: der OK-Knopf selbst kommt nur
# auf 0,68 -- unter der Schwelle -- weil der GILDENNAME der eigenen Figur in Pink
# quer ueber dem "OK" steht. Die Figur steht mittig im Bild, der Dialog ist
# halbtransparent, und der Client zeichnet Namensschilder UEBER den Dialog.
# Ob das passiert, haengt von Kamera und Standort ab -- genau das Muster "mal
# geht es, mal nicht".
#
# Was ein Namensschild NICHT erreicht, sind die ENDEN der Leiste: sie ist
# 280 px breit (Client x 260..539), Schilder sind ~150 px und haengen mittig an
# der Figur. Der Dialog-Rahmen steht ausserdem FEST (Client x 49..748, y ab 149;
# alle fuenf Referenzen identisch) -- nur die Leiste wandert in y mit der
# Textlaenge. Darum werden beide Enden per Template in SCHMALEN Spalten an
# fester x-Lage gesucht; ein Treffer braucht BEIDE Enden auf gleicher Hoehe.
#
# GEMESSEN (fuenf Dialoge, 25 Negative): schwaechstes Positiv 0,775 (beide
# Enden, |dy| <= 4), staerkstes Negativ 0,598 bei |dy| = 13 -- zwei getrennte
# Luecken. Kosten 0,15 ms je Frame gegen 4,7 ms der Vollbild-Suche. Helligkeit
# der Szene (+45, x1,5, -35) aendert die Werte um < 0,003.
#
# Der Knopf-Pfad bleibt als Rueckfall bestehen, jetzt auf den Mittelstreifen
# des festen Dialogs begrenzt (der Knopf sitzt in allen Referenzen bei x 403).
GOLDEN_OK_END_LEFT_TEMPLATE = 'images/golden_ok_end_left.png'
GOLDEN_OK_END_RIGHT_TEMPLATE = 'images/golden_ok_end_right.png'
GOLDEN_BAR_LEFT_X = 260       # Client-x des linken Leistenanfangs
GOLDEN_BAR_RIGHT_X = 539      # Client-x des rechten Leistenendes
GOLDEN_BAR_END_ANCHOR = (6, 17)   # Spalte im Template, die auf LEFT_X/RIGHT_X liegt
GOLDEN_BAR_END_DX = 8         # Suchspielraum in x je Seite (px)
GOLDEN_BAR_END_NCC_MIN = 0.70
GOLDEN_BAR_END_DY_MAX = 6     # beide Enden auf (fast) gleicher Hoehe
GOLDEN_PANEL_Y = (160, 445)   # y-Bereich des festen Dialog-Rahmens (Client)
GOLDEN_OK_X = 403             # Client-x der Knopf-Mitte (alle Referenzen)
GOLDEN_OK_X_HALF = 73         # halbe Breite des Mittelstreifens fuer den Knopf

# -- Dritter Pfad: FESTE GEOMETRIE (v1.6.13, auf Wunsch des Nutzers) ----------
#
# "Wenn die Bilder nicht gut erkennbar sind, mach die festen Koordinaten
# besser." Der Dialog-Rahmen steht fest, also laesst sich der Knopf auch OHNE
# Template finden: (1) der Rahmen ist da -- eine helle senkrechte Linie bei
# Client-x 49..53 und eine helle waagerechte bei y 149..153; (2) die OK-Leiste
# ist die hellste FLACHE Zeile in den beiden Spalten links und rechts der Mitte
# (x 270..340 und 460..530), wo nie ein Namensschild haengt. Geklickt wird
# (400, y) -- die Leiste ist 280 px breit, jeder Punkt darauf ist der Knopf.
#
# WARUM NICHT BLIND: ohne den Rahmen-Check traefe ein fester Klick die Welt,
# solange die Server-Antwort noch nicht da ist -- die Figur liefe los (Report
# 2026-07-22). Der Rahmen ist die billigste harte Evidenz dafuer, dass ein
# Dialog wirklich steht.
#
# GEMESSEN (fuenf Dialoge, 25 Negative): Rahmen-Kontrast links 41,6..55,1 /
# oben 37,1..55,5 gegen hoechstens 1,6 / 2,7 ohne Dialog. Leiste: Kontrast
# 19,7..41,9 bei std <= 9,7; ohne Dialog entweder texturiert (std >= 49) oder
# kontrastarm (<= 8,9). Das Optionsfenster traegt denselben Rahmen -- es wird
# davor ueber die schwarze Ecke (detect_daily_reward) behandelt.
GOLDEN_FRAME_LEFT_X = (47, 56)       # Suchbereich der linken Rahmenlinie
GOLDEN_FRAME_TOP_Y = (147, 156)      # Suchbereich der oberen Rahmenlinie
GOLDEN_FRAME_MIN = 15.0              # Mindest-Kontrast je Rahmenlinie
GOLDEN_BAND_COLS = ((270, 340), (460, 530))   # schildfreie Spalten
GOLDEN_BAND_Y = (175, 425)           # y-Suchbereich der Leistenmitte
GOLDEN_BAND_MIN_CONTRAST = 12.0
GOLDEN_BAND_MAX_STD = 14.0
GOLDEN_BAR_CENTER_X = 400            # Klick-x auf der Leiste

_golden_ok_cache = None
_golden_end_cache = None


def _golden_ok_template():
    """Das OK-Knopf-Template als Graustufen-Array (gecacht, soft). None = aus."""
    global _golden_ok_cache
    if _golden_ok_cache is not None:
        return _golden_ok_cache
    if np is None:
        return None
    tmpl = cv.imread(resource_path(GOLDEN_OK_TEMPLATE), cv.IMREAD_GRAYSCALE)
    if tmpl is None:
        return None
    _golden_ok_cache = tmpl
    return _golden_ok_cache


def _golden_end_templates():
    """Die beiden Enden-Templates als Graustufen (gecacht, soft). None = aus."""
    global _golden_end_cache
    if _golden_end_cache is not None:
        return _golden_end_cache
    if np is None:
        return None
    left = cv.imread(resource_path(GOLDEN_OK_END_LEFT_TEMPLATE),
                     cv.IMREAD_GRAYSCALE)
    right = cv.imread(resource_path(GOLDEN_OK_END_RIGHT_TEMPLATE),
                      cv.IMREAD_GRAYSCALE)
    if left is None or right is None:
        return None
    _golden_end_cache = (left, right)
    return _golden_end_cache


def _match_end(gray, tmpl, anchor_x, anchor_col):
    """Ein Leistenende in seiner schmalen Spalte suchen -> ``(score, y_mitte)``.

    ``anchor_x`` ist die Client-Spalte, auf der ``anchor_col`` des Templates
    liegen muss; gesucht wird +-GOLDEN_BAR_END_DX in x und ueber den ganzen
    Dialog-Rahmen in y. ``(0.0, None)`` wenn der Ausschnitt nicht ins Bild passt.
    """
    th, tw = tmpl.shape[0], tmpl.shape[1]
    x0 = anchor_x - anchor_col - GOLDEN_BAR_END_DX
    x1 = anchor_x - anchor_col + tw + GOLDEN_BAR_END_DX
    y0, y1 = GOLDEN_PANEL_Y
    if x0 < 0 or y0 < 0 or x1 > gray.shape[1] or y1 > gray.shape[0]:
        return (0.0, None)
    col = gray[y0:y1, x0:x1]
    if col.shape[0] <= th or col.shape[1] <= tw:
        return (0.0, None)
    res = cv.matchTemplate(col, tmpl, cv.TM_CCOEFF_NORMED)
    _mn, score, _mnl, loc = cv.minMaxLoc(res)
    return (float(score), int(y0 + loc[1] + th // 2))


def golden_bar_ends_find(gray):
    """Beide Enden der OK-Leiste -> ``(found, score, point, detail)``.

    ``score`` ist das SCHWAECHERE der beiden Enden (beide muessen tragen),
    ``point`` die Klick-Mitte ``(GOLDEN_OK_X, y)`` in Client-Koordinaten,
    ``detail`` ein Dict mit ``links``/``rechts``/``dy`` fuer die Diagnose.
    Rein, wirft nie; fehlende Templates -> ``(False, 0.0, None, {})``.
    """
    tm = _golden_end_templates()
    if tm is None or gray is None:
        return (False, 0.0, None, {})
    try:
        s_l, y_l = _match_end(gray, tm[0], GOLDEN_BAR_LEFT_X,
                              GOLDEN_BAR_END_ANCHOR[0])
        s_r, y_r = _match_end(gray, tm[1], GOLDEN_BAR_RIGHT_X,
                              GOLDEN_BAR_END_ANCHOR[1])
        score = min(s_l, s_r)
        detail = {'links': round(s_l, 3), 'rechts': round(s_r, 3),
                  'dy': (abs(y_l - y_r) if None not in (y_l, y_r) else None)}
        if y_l is None or y_r is None or score < GOLDEN_BAR_END_NCC_MIN:
            return (False, score, None, detail)
        if abs(y_l - y_r) > GOLDEN_BAR_END_DY_MAX:
            return (False, score, None, detail)
        return (True, score, (GOLDEN_OK_X, (y_l + y_r) // 2), detail)
    except Exception:
        return (False, 0.0, None, {})


def golden_panel_frame(gray):
    """Kontrast der beiden festen Rahmenlinien -> ``(links, oben)``.

    Jede Linie: hellste Spalte/Zeile im Suchbereich, gemessen gegen den Mittel-
    wert vier Pixel davor und dahinter. Ohne Dialog liegen beide nahe 0.
    Wirft nie -> ``(0.0, 0.0)`` im Zweifel.
    """
    try:
        y0, y1 = GOLDEN_PANEL_Y
        if gray is None or gray.shape[0] <= y1 + 40 or gray.shape[1] < 600:
            return (0.0, 0.0)
        g = gray.astype('float32')
        col = g[y0 + 10:y1 - 15, :].mean(axis=0)
        row = g[:, 60:600].mean(axis=1)
        lo, hi = GOLDEN_FRAME_LEFT_X
        links = max(float(col[x] - (col[x - 4] + col[x + 4]) / 2)
                    for x in range(lo, hi))
        lo, hi = GOLDEN_FRAME_TOP_Y
        oben = max(float(row[y] - (row[y - 4] + row[y + 4]) / 2)
                   for y in range(lo, hi))
        return (links, oben)
    except Exception:
        return (0.0, 0.0)


def golden_bar_band_find(gray):
    """Die OK-Leiste als hellste FLACHE Zeile in den schildfreien Spalten.

    :return: ``(y, kontrast, std)`` der besten Zeile -- der Aufrufer prueft
        gegen GOLDEN_BAND_MIN_CONTRAST / GOLDEN_BAND_MAX_STD. Wirft nie ->
        ``(None, 0.0, 999.0)`` im Zweifel.
    """
    try:
        y0, y1 = GOLDEN_BAND_Y
        if gray is None or gray.shape[0] <= y1 + 31 or gray.shape[1] < 540:
            return (None, 0.0, 999.0)
        g = gray.astype('float32')
        cols = [g[:, a:b] for a, b in GOLDEN_BAND_COLS]
        prof = sum(c.mean(axis=1) for c in cols) / len(cols)
        # Fenstermittel per Praefixsumme: band = 19 Zeilen um y, umfeld = je 18
        # Zeilen darueber (y-30..y-13) und darunter (y+13..y+30).
        csum = np.concatenate(([0.0], np.cumsum(prof, dtype='float64')))

        def fenster(a_off, b_off):
            ys = np.arange(y0, y1)
            return (csum[ys + b_off] - csum[ys + a_off]) / float(b_off - a_off)

        band = fenster(-9, 10)
        umfeld = (fenster(-30, -12) + fenster(13, 31)) / 2.0
        kontrast = band - umfeld
        i = int(np.argmax(kontrast))
        y = y0 + i
        std = float(np.hstack([c[y - 6:y + 7] for c in cols]).std())
        return (int(y), float(kontrast[i]), std)
    except Exception:
        return (None, 0.0, 999.0)


def golden_fixed_geometry_find(gray):
    """Pfad 3: Rahmen steht UND Leiste gefunden -> ``(found, score, point, detail)``.

    ``score`` ist der Leisten-Kontrast, ``point`` = (GOLDEN_BAR_CENTER_X, y).
    """
    links, oben = golden_panel_frame(gray)
    detail = {'rahmen_links': round(links, 1), 'rahmen_oben': round(oben, 1)}
    if links < GOLDEN_FRAME_MIN or oben < GOLDEN_FRAME_MIN:
        return (False, 0.0, None, detail)
    # Das OPTIONSFENSTER traegt denselben Rahmen und ebenfalls flache Balken --
    # seine Kennung ist die schwarze Bildecke (wie detect_daily_reward). Es ist
    # KEIN Bestaetigungs-Dialog; im Angel-Loop wird es vorher behandelt, aber
    # diese Funktion muss es auch allein sauber ablehnen.
    try:
        if not gray[10:15, 10:15].any():
            detail['optionsfenster'] = True
            return (False, 0.0, None, detail)
    except Exception:
        pass
    y, kontrast, std = golden_bar_band_find(gray)
    detail.update({'leiste_y': y, 'leiste_kontrast': round(kontrast, 1),
                   'leiste_std': round(std, 1)})
    if y is None or kontrast < GOLDEN_BAND_MIN_CONTRAST \
            or std > GOLDEN_BAND_MAX_STD:
        return (False, kontrast, None, detail)
    return (True, kontrast, (GOLDEN_BAR_CENTER_X, y), detail)


def golden_confirm_find(image_bgr):
    """Sucht den OK-Knopf des Bestaetigungs-Dialogs -- drei Pfade nacheinander.

    :return: ``(found, score, point)`` -- ``point`` ist die Knopf-MITTE in
        Client-Koordinaten (der Klickpunkt), ``None`` wenn nicht gefunden.
        ``score`` ist der NCC-Wert der Enden-Suche bzw. des Knopfs (der
        Geometrie-Pfad hat keinen NCC; seine Werte liefert
        :func:`golden_confirm_scores`). Rein, headless-testbar, wirft nie;
        fehlende Templates/numpy oder ein zu kleiner Frame -> kein Klick (die
        sichere Richtung).
    """
    if image_bgr is None or np is None:
        return (False, 0.0, None)
    try:
        img = np.asarray(image_bgr)
        if img.ndim != 3 or img.shape[2] < 3:
            return (False, 0.0, None)
        gray = cv.cvtColor(img[:, :, :3], cv.COLOR_BGR2GRAY)

        # PFAD 1 -- die Leisten-Enden (0,15 ms, unempfindlich gegen ein
        # Namensschild ueber dem "OK"; siehe Konstanten-Doku).
        found, score, point, _detail = golden_bar_ends_find(gray)
        if found:
            return (True, score, point)

        # PFAD 2 -- feste Geometrie: Rahmen steht + hellste flache Zeile in den
        # schildfreien Spalten (kein Template; siehe Konstanten-Doku).
        found, _k, point, _detail = golden_fixed_geometry_find(gray)
        if found:
            return (True, score, point)

        # PFAD 3 -- der Knopf selbst, im Mittelstreifen des festen Dialogs.
        tmpl = _golden_ok_template()
        if tmpl is None:
            return (False, score, None)
        th, tw = tmpl.shape[0], tmpl.shape[1]
        sx0 = max(0, GOLDEN_OK_X - GOLDEN_OK_X_HALF)
        sx1 = min(gray.shape[1], GOLDEN_OK_X + GOLDEN_OK_X_HALF)
        strip = gray[:, sx0:sx1]
        if strip.shape[0] <= th or strip.shape[1] <= tw:
            return (False, score, None)
        res = cv.matchTemplate(strip, tmpl, cv.TM_CCOEFF_NORMED)
        _mn, knob, _mnl, loc = cv.minMaxLoc(res)
        score = max(score, float(knob))
        if float(knob) < GOLDEN_OK_NCC_MIN:
            return (False, score, None)
        cx, cy = int(sx0 + loc[0] + tw // 2), int(loc[1] + th // 2)
        # Leisten-Check: beide Flanken flach + plausibel hell.
        for x0, x1 in ((cx - 48, cx - 24), (cx + 24, cx + 48)):
            y0, y1 = cy - 7, cy + 8
            if y0 < 0 or x0 < 0 or y1 > gray.shape[0] or x1 > gray.shape[1]:
                return (False, score, None)
            strip = gray[y0:y1, x0:x1].astype('float32')
            lo, hi = GOLDEN_OK_BAR_MEAN
            if not (lo <= float(strip.mean()) <= hi):
                return (False, score, None)
            if float(strip.std()) > GOLDEN_OK_BAR_STD_MAX:
                return (False, score, None)
        return (True, score, (cx, cy))
    except Exception:
        return (False, 0.0, None)


def golden_confirm_scores(image_bgr):
    """Alle Teil-Werte der Erkennung fuer EINE Diagnosezeile -> Dict.

    ``knopf`` = bester NCC des OK-Knopfs im Mittelstreifen, ``links``/``rechts``
    = die Enden, ``dy`` = ihr Hoehenversatz. Nur fuers Log, wenn ein erwarteter
    Dialog NICHT gefunden wurde -- damit der naechste Report entscheidbar ist
    ("nicht erkannt" gegen "geklickt, aber nicht angenommen"). Wirft nie.
    """
    out = {'knopf': None, 'links': None, 'rechts': None, 'dy': None,
           'rahmen_links': None, 'rahmen_oben': None}
    if image_bgr is None or np is None:
        return out
    try:
        img = np.asarray(image_bgr)
        gray = cv.cvtColor(img[:, :, :3], cv.COLOR_BGR2GRAY)
        _f, _s, _p, detail = golden_bar_ends_find(gray)
        out.update({k: detail.get(k) for k in ('links', 'rechts', 'dy')})
        _f, _s, _p, geo = golden_fixed_geometry_find(gray)
        out.update(geo)
        tmpl = _golden_ok_template()
        if tmpl is not None:
            sx0 = max(0, GOLDEN_OK_X - GOLDEN_OK_X_HALF)
            sx1 = min(gray.shape[1], GOLDEN_OK_X + GOLDEN_OK_X_HALF)
            res = cv.matchTemplate(gray[:, sx0:sx1], tmpl, cv.TM_CCOEFF_NORMED)
            out['knopf'] = round(float(cv.minMaxLoc(res)[1]), 3)
    except Exception:
        pass
    return out


def golden_confirm_present(image_bgr):
    """``True`` gdw. der Goldfisch-Bestaetigungs-Dialog im Frame steht."""
    return golden_confirm_find(image_bgr)[0]


class FishingDetectMixin:
    """Pure Erkennungs-Methoden (Fisch / Minispiel / Tagesbelohnung).

    Enthaelt KEINE eigenen Attribute und KEIN ``__init__`` -- saemtlicher
    Zustand (``needle_img``, ``FISH_RANGE``, ``fish_pos_x`` ...) lebt weiterhin
    auf :class:`fishingbot.FishingBot`. Reines Verhalten, per MRO eingemischt.
    """

    def _note_detect(self, grund, conf=None, dist=None, velo=None,
                     ref_alter=None):
        """Merkt sich, WARUM ``detect`` gerade so entschieden hat -- reine
        Diagnose fuer die Klick-Zeile im Debug-Log, KEINE Verhaltensaenderung.

        Wirft nie: schlaegt das Setzen fehl, fehlen im Log nur die Zusatzfelder.
        """
        try:
            self._last_detect_info = {
                'grund': grund, 'conf': conf, 'dist': dist,
                'velo': velo, 'ref_alter': ref_alter,
            }
        except Exception:
            pass

    def detect(self, haystack_img):

        # match the needle_image with the hasytack image (robust: ein abweichendes
        # Capture darf KEINEN cv2-Crash ausloesen -> dann "kein Fisch" (None)).
        ok, max_val, max_loc = _match_template_max(haystack_img, self.needle_img)
        if not ok:
            self._note_detect('vorlage-fehlt')
            return None

        # needle_image's dimensions
        needle_w = self.needle_img.shape[1]
        needle_h = self.needle_img.shape[0]

        # get the position of the match image
        top_left = max_loc
        bottom_right = (top_left[0] + needle_w, top_left[1] + needle_h)

        # Draw the circle of the fish limits
        cv.circle(haystack_img,
                (int(haystack_img.shape[1] / 2), int(haystack_img.shape[0] / 2)),
                self.FISH_RANGE, color=(0, 0, 255), thickness=1)

        # Only the max level of match is greater than 0.5
        if max_val > 0.5:
            pos_x = (top_left[0] + bottom_right[0])/2
            pos_y = (top_left[1] + bottom_right[1])/2

            if self.fish_last_time:
                dist = math.sqrt((pos_x - self.fish_pos_x)**2 + (self.fish_pos_y - pos_y)**2)
                cv.rectangle(haystack_img, top_left, bottom_right,
                            color=(0, 255, 0), thickness=2, lineType=cv.LINE_4)

                # Calculate the fish velocity
                velo = dist/(time() - self.fish_last_time)

                if velo == 0.0:
                    # Fund liegt EXAKT auf dem Bezugspunkt -> Ziel ruht.
                    self._note_detect('ruht', conf=max_val, dist=dist,
                                      velo=velo,
                                      ref_alter=time() - self.fish_last_time)
                    return (pos_x, pos_y, True)
                elif velo >= 150:

                    # With this velocity the fish position will be predict

                    pro = self.FISH_VELO_PREDICT / dist
                    destiny_x = int(pos_x + (pos_x - self.fish_pos_x) * pro)
                    destiny_y = int(pos_y + (pos_y - self.fish_pos_y) * pro)

                    # Draw the predict line

                    cv.line(haystack_img, (int(pos_x), int(pos_y)),
                            (destiny_x, destiny_y), (0, 255, 0),  thickness=3)

                    # Vorhalt: es wird BEWUSST FISH_VELO_PREDICT px neben dem
                    # Fund geklickt, in Richtung des Versatzes zum Bezugspunkt.
                    self._note_detect('vorhalt', conf=max_val, dist=dist,
                                      velo=velo,
                                      ref_alter=time() - self.fish_last_time)
                    return (destiny_x, destiny_y, False)

            # get the fish position and the time

            hatte_bezug = bool(self.fish_last_time)
            self.fish_pos_x = pos_x
            self.fish_pos_y = pos_y
            self.fish_last_time = time()
            # Fund da, aber kein Klick: entweder erster Fund dieser Runde oder
            # Totbereich (0 < velo < 150). Bezugspunkt wurde nachgezogen.
            self._note_detect('totbereich' if hatte_bezug else 'erster-fund',
                              conf=max_val)
            return None

        self._note_detect('kein-fisch', conf=max_val)
        return None

    def detect_minigame(self, haystack_img):
        # Robust gegen Form-/Typ-Abweichungen des Captures (kein Crash mehr).
        ok, max_val, _ = _match_template_max(haystack_img, self.needle_img_clock)
        if ok and max_val > self._best_minigame_conf:
            self._best_minigame_conf = max_val
        return ok and max_val > 0.9

    def detect_daily_reward(self, image):
        # Daily-reward popup leaves the top-left 5x5 patch all-black: True iff
        # every BGR channel in image[10:15, 10:15] is 0. A single numpy reduction
        # over the 75-element slice (with numpy's internal short-circuit) replaces
        # the old 25-step Python loop + per-pixel int() casts -- identical result.
        return not image[10:15, 10:15, :3].any()

    def detect_golden_confirm(self, image):
        """``(found, score, point)`` des Bestaetigungs-Dialog-OK-Knopfs.

        Duenner Mixin-Wrapper um :func:`golden_confirm_find` (Modul-Funktion,
        damit sie headless ohne FishingBot-Instanz testbar bleibt). ``point``
        ist die GEFUNDENE Knopf-Mitte (Client) -- der Dialog steht nicht an
        fester Position, geklickt wird der Fund; siehe Konstanten-Doku oben.
        """
        return golden_confirm_find(image)

    def golden_confirm_diag(self, image):
        """Teil-Werte der Erkennung fuer die Diagnosezeile (siehe
        :func:`golden_confirm_scores`). Wirft nie."""
        return golden_confirm_scores(image)
