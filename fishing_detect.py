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
#     mit plausibler Helligkeit (mean 50..110 -- die Dialog-Transparenz
#     dimmt die Leiste je Szene: gemessen 65..85). Killt zufaellige
#     Texture-Treffer in unbekannten Szenen.
GOLDEN_OK_TEMPLATE = 'images/golden_ok_knob.png'
GOLDEN_OK_NCC_MIN = 0.70
GOLDEN_OK_BAR_MEAN = (50.0, 110.0)
GOLDEN_OK_BAR_STD_MAX = 12.0

_golden_ok_cache = None


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


def golden_confirm_find(image_bgr):
    """Sucht den OK-Knopf des Bestaetigungs-Dialogs im ganzen Frame.

    :return: ``(found, score, point)`` -- ``point`` ist die Knopf-MITTE in
        Client-Koordinaten (der Klickpunkt), ``None`` wenn nicht gefunden.
        Rein, headless-testbar, wirft nie; fehlendes Template/numpy oder ein
        zu kleiner Frame -> ``(False, 0.0, None)`` (kein Klick -- die sichere
        Richtung).
    """
    tmpl = _golden_ok_template()
    if tmpl is None or image_bgr is None or np is None:
        return (False, 0.0, None)
    try:
        img = np.asarray(image_bgr)
        if img.ndim != 3 or img.shape[2] < 3:
            return (False, 0.0, None)
        gray = cv.cvtColor(img[:, :, :3], cv.COLOR_BGR2GRAY)
        th, tw = tmpl.shape[0], tmpl.shape[1]
        if gray.shape[0] <= th or gray.shape[1] <= tw:
            return (False, 0.0, None)
        res = cv.matchTemplate(gray, tmpl, cv.TM_CCOEFF_NORMED)
        _mn, score, _mnl, loc = cv.minMaxLoc(res)
        score = float(score)
        if score < GOLDEN_OK_NCC_MIN:
            return (False, score, None)
        cx, cy = int(loc[0] + tw // 2), int(loc[1] + th // 2)
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


def golden_confirm_present(image_bgr):
    """``True`` gdw. der Goldfisch-Bestaetigungs-Dialog im Frame steht."""
    return golden_confirm_find(image_bgr)[0]


class FishingDetectMixin:
    """Pure Erkennungs-Methoden (Fisch / Minispiel / Tagesbelohnung).

    Enthaelt KEINE eigenen Attribute und KEIN ``__init__`` -- saemtlicher
    Zustand (``needle_img``, ``FISH_RANGE``, ``fish_pos_x`` ...) lebt weiterhin
    auf :class:`fishingbot.FishingBot`. Reines Verhalten, per MRO eingemischt.
    """

    def detect(self, haystack_img):

        # match the needle_image with the hasytack image (robust: ein abweichendes
        # Capture darf KEINEN cv2-Crash ausloesen -> dann "kein Fisch" (None)).
        ok, max_val, max_loc = _match_template_max(haystack_img, self.needle_img)
        if not ok:
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
                    return (pos_x, pos_y, True)
                elif velo >= 150:

                    # With this velocity the fish position will be predict

                    pro = self.FISH_VELO_PREDICT / dist
                    destiny_x = int(pos_x + (pos_x - self.fish_pos_x) * pro)
                    destiny_y = int(pos_y + (pos_y - self.fish_pos_y) * pro)

                    # Draw the predict line

                    cv.line(haystack_img, (int(pos_x), int(pos_y)),
                            (destiny_x, destiny_y), (0, 255, 0),  thickness=3)

                    return (destiny_x, destiny_y, False)

            # get the fish position and the time

            self.fish_pos_x = pos_x
            self.fish_pos_y = pos_y
            self.fish_last_time = time()

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
