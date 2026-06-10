# -*- coding: utf-8 -*-
"""Tests fuer die Goldfisch-Bestaetigungs-Erkennung (fishing_detect).

Das Bestaetigungs-Fenster (nach dem Options-Klick, z.B. die Freilassen-Bonus-
Meldung) schwaerzt die Bildecken NICHT -> ``detect_daily_reward`` sieht es nie;
``golden_confirm_present`` erkennt es ueber die Knopf-Leisten-Templates. Diese
Tests pinnen:

  * die ECHTE Referenz (FischOCR/GoldenerThunfischAuswahlbestaetigen.png)
    liest OPEN, das 3-Optionen-Fenster und ein normaler Angel-Frame NICHT,
  * Shift-Toleranz (+-2px Session-Versatz),
  * defensive Pfade (None/zu kleiner Frame/fehlende Templates -> False).

Reines fishing_detect -- KEIN fishingbot-Import (der zieht pydirectinput,
Windows-only); headless lauffaehig.
"""

import os
import unittest

try:
    import numpy as np
except Exception:                       # pragma: no cover
    np = None

try:
    from PIL import Image
except Exception:                       # pragma: no cover
    Image = None

import fishing_detect as fd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHOTS = {
    'confirm': os.path.join(_REPO_ROOT, 'FischOCR',
                            'GoldenerThunfischAuswahlbestätigen.png'),
    'confirm_buff': os.path.join(_REPO_ROOT, 'FischOCR',
                                 'GoldenThunfischBuffBestaetigen.png'),
    'options': os.path.join(_REPO_ROOT, 'FischOCR',
                            'GoldenerThunfisch3Optionen.png'),
    'fishing': os.path.join(_REPO_ROOT, 'FischOCR', 'Lachs.png'),
}


def _shots_present():
    return all(os.path.isfile(p) for p in _SHOTS.values())


def _load_client_bgr(path):
    """Referenz-Shot als BGR-Client-Array (Full-Window -> Rand/Titel weg)."""
    img = np.asarray(Image.open(path).convert('RGB'))
    if img.shape[0] > 615:
        img = img[31:, 1:]
    return img[:, :, ::-1].copy()


@unittest.skipUnless(np is not None and Image is not None,
                     'numpy/PIL required')
class TestGoldenConfirmDefensive(unittest.TestCase):
    def test_none_and_tiny_frames_false(self):
        self.assertFalse(fd.golden_confirm_present(None))
        self.assertFalse(fd.golden_confirm_present(
            np.zeros((50, 50, 3), dtype=np.uint8)))

    def test_blank_frame_false(self):
        self.assertFalse(fd.golden_confirm_present(
            np.zeros((601, 800, 3), dtype=np.uint8)))

    def test_missing_template_false(self):
        orig = fd._golden_ok_cache
        try:
            fd._golden_ok_cache = None
            orig_path = fd.GOLDEN_OK_TEMPLATE
            fd.GOLDEN_OK_TEMPLATE = 'images/does_not_exist.png'
            try:
                self.assertEqual(
                    fd.golden_confirm_find(
                        np.zeros((601, 800, 3), dtype=np.uint8)),
                    (False, 0.0, None))
            finally:
                fd.GOLDEN_OK_TEMPLATE = orig_path
        finally:
            fd._golden_ok_cache = orig


@unittest.skipUnless(np is not None and Image is not None and _shots_present(),
                     'real reference shots not present')
class TestGoldenConfirmOnRealShots(unittest.TestCase):
    def test_confirm_window_detected_at_reference_point(self):
        found, score, point = fd.golden_confirm_find(
            _load_client_bgr(_SHOTS['confirm']))
        self.assertTrue(found)
        self.assertEqual(point, (403, 250))

    def test_buff_variant_detected_at_shifted_point(self):
        # Der Dialog steht NICHT fest: die Buff-Variante sitzt ~48px hoeher --
        # genau der Fall, den die fixe v1.1.5-Koordinate verfehlte.
        found, score, point = fd.golden_confirm_find(
            _load_client_bgr(_SHOTS['confirm_buff']))
        self.assertTrue(found)
        self.assertEqual(point[0], 403)
        self.assertLess(abs(point[1] - 202), 4)

    def test_options_window_not_detected(self):
        # Das 3-OPTIONEN-Fenster darf NICHT als Bestaetigung gelten (dort waere
        # der OK-Klick ein Klick zwischen die Optionsfelder).
        self.assertFalse(fd.golden_confirm_present(
            _load_client_bgr(_SHOTS['options'])))

    def test_plain_fishing_frame_not_detected(self):
        self.assertFalse(fd.golden_confirm_present(
            _load_client_bgr(_SHOTS['fishing'])))

    def test_shift_tolerance(self):
        # Versatz (Session-Drift) ist trivial: die Suche laeuft ueber den
        # ganzen Frame -- der Fundpunkt wandert einfach mit.
        frame = _load_client_bgr(_SHOTS['confirm'])
        shifted = np.zeros_like(frame)
        shifted[2:, :-2] = frame[:-2, 2:]
        found, _score, point = fd.golden_confirm_find(shifted)
        self.assertTrue(found)
        self.assertEqual(point, (403 - 2, 250 + 2))


if __name__ == '__main__':
    unittest.main()
