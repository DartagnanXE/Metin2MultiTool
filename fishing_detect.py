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
# antwortet der SERVER mit einem zweiten Fenster (z.B. die Freilassen-Bonus-
# Meldung) mit EINEM OK-Knopf. Dieses Fenster schwaerzt die Bildecken NICHT
# (gemessen: max 125 statt 0) -> detect_daily_reward sieht es nie; es braucht
# eine EIGENE Erkennung. Signatur = die Knopf-LEISTE des Dialogs: ein flacher
# ~80er-Graustreifen (Zeilen ~238..258 client) mit scharfen Dunkel-Kanten
# darueber/darunter. Zwei Template-Patches FLANKIEREN den OK-Knopf (der Knopf
# selbst ist ausgespart -- Cursor-Hover macht ihn heller), beide muessen
# matchen. Gemessen auf den FischOCR-Referenzen (client = full-frame -(1,31)):
# Selbst-Match 0.0; naechster Negativfall (3-Optionen-Fenster) 27..29; Angel-
# Frame einseitig 18.5, beidseitig >=67 -> Schwelle 8 mit grossem Abstand.
GOLDEN_CONFIRM_PATCH_Y = (230, 266)
GOLDEN_CONFIRM_PATCH_X = ((340, 386), (425, 471))
GOLDEN_CONFIRM_TEMPLATES = ('images/golden_confirm_bar_l.png',
                            'images/golden_confirm_bar_r.png')
GOLDEN_CONFIRM_MAD_MAX = 8.0
GOLDEN_CONFIRM_SHIFT = 3

_golden_confirm_cache = None


def _golden_confirm_templates():
    """Die beiden Leisten-Templates als BGR-float-Arrays (gecacht, soft).

    ``cv.imread`` liefert BGR -- exakt die Kanal-Ordnung des Live-Captures, so
    vergleicht :func:`golden_confirm_present` ohne Konvertierung. ``None`` wenn
    eine Datei fehlt/unlesbar ist (dann gibt es schlicht keine Erkennung).
    """
    global _golden_confirm_cache
    if _golden_confirm_cache is not None:
        return _golden_confirm_cache
    if np is None:
        return None
    out = []
    for rel in GOLDEN_CONFIRM_TEMPLATES:
        img = cv.imread(resource_path(rel), cv.IMREAD_COLOR)
        if img is None:
            return None
        out.append(img.astype('float32'))
    _golden_confirm_cache = tuple(out)
    return _golden_confirm_cache


def golden_confirm_present(image_bgr):
    """``True`` gdw. der Goldfisch-Bestaetigungs-Dialog im Frame steht.

    Beide Leisten-Patches muessen ihr Template innerhalb +-Shift treffen
    (mean-abs-diff <= Schwelle). Rein, headless-testbar, wirft nie; fehlende
    Templates/numpy oder ein zu kleiner Frame -> ``False`` (keine Erkennung,
    also auch kein Klick -- die sichere Richtung).
    """
    templates = _golden_confirm_templates()
    if templates is None or image_bgr is None or np is None:
        return False
    img = np.asarray(image_bgr)
    if img.ndim != 3 or img.shape[2] < 3:
        return False
    y0, y1 = GOLDEN_CONFIRM_PATCH_Y
    h, w = img.shape[0], img.shape[1]
    rad = GOLDEN_CONFIRM_SHIFT
    for (x0, _x1), tmpl in zip(GOLDEN_CONFIRM_PATCH_X, templates):
        th, tw = tmpl.shape[0], tmpl.shape[1]
        best = 1e9
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                ay0, ax0 = y0 + dy, x0 + dx
                if ay0 < 0 or ax0 < 0 or ay0 + th > h or ax0 + tw > w:
                    continue
                patch = np.asarray(img[ay0:ay0 + th, ax0:ax0 + tw, :3],
                                   dtype=np.float32)
                mad = float(np.abs(patch - tmpl).mean())
                if mad < best:
                    best = mad
        if best > GOLDEN_CONFIRM_MAD_MAX:
            return False
    return True


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
        """``True`` gdw. der Goldfisch-BESTAETIGUNGS-Dialog im Frame steht.

        Duenner Mixin-Wrapper um :func:`golden_confirm_present` (Modul-Funktion,
        damit sie headless ohne FishingBot-Instanz testbar bleibt). Dieses
        zweite Fenster schwaerzt die Ecken NICHT -> detect_daily_reward sieht
        es nie; siehe die Konstanten-Doku oben.
        """
        return golden_confirm_present(image)
