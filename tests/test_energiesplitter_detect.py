# -*- coding: utf-8 -*-
"""Tests fuer das Erkennungs-Framework (energiesplitter/detect.py + geometry.py).

Headless mit ECHTEM cv2/numpy gegen die 26 echten Fixtures. Geprueft wird:

  * **Geometrie** 802x632 -> 800x600 (Client-Normierung, Kalibrier-Gate).
  * **NCC-Wortbild-Framework** (``match_word``/``find_npc_name``/``find_shop_item``):
    Treffer bei ECHTEN Bildern (Template aus einem Fixture extrahiert, in einem
    ANDEREN wiedergefunden), kein Treffer bei leerer/falscher Szene.
  * **Selektions-Ring**: Treffer am echten roten Ring, KEIN Treffer bei
    HP-Leiste / leerer Wiese / NPC-loser Szene (Ring-Form-Test).
  * **Phase-0-Gate** (``assets_ready``): meldet die noch fehlenden Assets
    (Wortbild-Templates, Item-Icons, gold_digits) ehrlich als ``missing``.
  * **NotReady-Pfade**: asset-gebundene Detektoren (``dialog_state``/``shop_open``/
    ``panel_is_bag``) liefern sauber None/False, solange ihre Marker-Templates
    fehlen; werden echte Marker-Templates injiziert, diskriminieren sie korrekt.

Die win32/pydirectinput-Abhaengigkeit fehlt hier bewusst: detect.py/geometry.py
sind REIN (nur numpy/cv2 + Datei-Lesen) und brauchen kein Stubbing.
"""

import os
import sys
import unittest

import cv2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from energiesplitter import detect as d      # noqa: E402
from energiesplitter import geometry as geo  # noqa: E402

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'fixtures', 'energiesplitter')


def _load(group, name):
    path = os.path.join(_FIX, group, name)
    img = cv2.imread(path)
    assert img is not None, 'fixture missing: %s' % path
    return img


def _alch_name_template():
    """Extrahiert ein tight 'Alchemist'-Wortbild aus einem echten Bild.

    Steht stellvertretend fuer das P0.2-Template ``npc_alchemist`` -> beweist das
    Gruen+NCC-Framework gegen echte Bilder, ohne ein Asset zu erfinden.
    """
    img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
    client = geo.to_client(img)
    # 'Alchemist'-Schriftzug oben-mitte (an der Gruen-Maske lokalisiert).
    gm = d._green_mask(client[104:122, 352:404])
    import numpy as np
    ys, xs = np.where(gm > 0)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    return client[104 + y0 - 1:104 + y1 + 2, 352 + x0 - 1:352 + x1 + 2]


def _laden_header_template():
    """Extrahiert das weisse 'Laden'-Header-Wort aus dem Alchemist-Shop."""
    img = _load('Einkauf_Hammer', 'Shopgeöffnetalchemist.png')
    client = geo.to_client(img)
    return client[22:40, 455:510]


# ---------------------------------------------------------------------------
class TestGeometry(unittest.TestCase):

    def test_to_client_normalises_802x632(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertEqual(img.shape[:2], (geo.RAW_H, geo.RAW_W))
        client = geo.to_client(img)
        self.assertEqual(client.shape[:2], (geo.GAME_H, geo.GAME_W))

    def test_to_client_passthrough_when_already_client(self):
        import numpy as np
        already = np.zeros((geo.GAME_H, geo.GAME_W, 3), dtype=np.uint8)
        out = geo.to_client(already)
        self.assertEqual(out.shape[:2], (geo.GAME_H, geo.GAME_W))

    def test_to_client_defensive_on_none_and_tiny(self):
        import numpy as np
        self.assertIsNone(geo.to_client(None))
        tiny = np.zeros((10, 10, 3), dtype=np.uint8)
        self.assertEqual(geo.to_client(tiny).shape[:2], (10, 10))  # unveraendert

    def test_crop_clamps_and_rejects_empty(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        client = geo.to_client(img)
        sub = geo.crop(client, (0, 0, 50, 50))
        self.assertEqual(sub.shape[:2], (50, 50))
        self.assertIsNone(geo.crop(client, (0, 0, 0, 0)))
        self.assertIsNone(geo.crop(None, (0, 0, 10, 10)))

    def test_is_calibrated_true_for_800x600_and_tolerant(self):
        class W:
            hwnd = None
        w = W(); w.w = 800; w.h = 600
        self.assertTrue(geo.is_calibrated(w))
        w.w = 800 + geo.GAME_SIZE_TOLERANCE; w.h = 600
        self.assertTrue(geo.is_calibrated(w))

    def test_is_calibrated_false_when_off_or_missing(self):
        class W:
            hwnd = None
        w = W(); w.w = 1024; w.h = 768
        self.assertFalse(geo.is_calibrated(w))
        self.assertFalse(geo.is_calibrated(object()))  # keine w/h-Attribute


# ---------------------------------------------------------------------------
class TestAssetsGate(unittest.TestCase):

    def test_hammer_gate_red_lists_missing(self):
        ready, missing = d.assets_ready('hammer')
        self.assertFalse(ready)
        # Wortbild-Templates de+en, Item-Icon, gold_digits muessen fehlen.
        self.assertIn('item:hammer', missing)
        self.assertIn('gold_digits', missing)
        self.assertIn('tpl:de/laden_oeffnen', missing)
        self.assertIn('tpl:en/laden_oeffnen', missing)

    def test_dagger_gate_red_includes_dagger_assets(self):
        ready, missing = d.assets_ready('dagger')
        self.assertFalse(ready)
        self.assertIn('item:dolch', missing)
        self.assertIn('item:energiesplitter', missing)
        self.assertIn('tpl:de/npc_waffenhaendler', missing)

    def test_unknown_mode_rejected(self):
        ready, missing = d.assets_ready('bogus')
        self.assertFalse(ready)
        self.assertEqual(missing, ['mode:bogus'])


# ---------------------------------------------------------------------------
class TestWordMatchFramework(unittest.TestCase):
    """NCC-Wortbild-Framework gegen echte Bilder (Templates zur Laufzeit extrahiert)."""

    def test_find_npc_name_hits_alchemist_across_frames(self):
        tpl = _alch_name_template()
        # Der gleiche In-Game-Schriftzug erscheint (an wandernder Position) in
        # mehreren Alchemist-Bildern -> hoher NCC-Treffer.
        hits = 0
        for name in ('metin2client_Fmx09flgeZ.png', 'metin2client_TYu62EaDYI.png',
                     'metin2client_s4nZUO3m1E.png', 'metin2client_jSBNb1MyFP.png'):
            img = _load('Alchemist', name)
            ok, pt, ncc = d.find_npc_name(img, tpl)
            if ok:
                hits += 1
                self.assertIsNotNone(pt)
                self.assertGreaterEqual(ncc, d.NCC_WORD)
        self.assertGreaterEqual(hits, 3, 'expected the Alchemist name in most frames')

    def test_find_npc_name_no_hit_in_non_alchemist_scene(self):
        tpl = _alch_name_template()
        for name in ('metin2client_2JJQT56i9r.png', 'metin2client_KwAggglQCf.png'):
            img = _load('Waffenschmied', name)
            ok, _pt, ncc = d.find_npc_name(img, tpl)
            self.assertFalse(ok)
            self.assertLess(ncc, d.NCC_WORD)

    def test_find_npc_name_defensive_none_template(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        ok, pt, ncc = d.find_npc_name(img, None)
        self.assertFalse(ok)
        self.assertIsNone(pt)

    def test_find_shop_item_hits_real_icon(self):
        img = _load('Einkauf_Hammer', 'Shopgeöffnetalchemist.png')
        client = geo.to_client(img)
        icon = client[80:104, 495:520]  # echtes Shop-Item-Icon (4. Slot)
        ok, pt, ncc = d.find_shop_item(img, icon, roi=(365, 75, 200, 35))
        self.assertTrue(ok)
        self.assertIsNotNone(pt)
        self.assertGreaterEqual(ncc, d.NCC_ITEM)

    def test_find_shop_item_no_hit_in_overworld(self):
        shop = _load('Einkauf_Hammer', 'Shopgeöffnetalchemist.png')
        icon = geo.to_client(shop)[80:104, 495:520]
        overworld = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        ok, _pt, ncc = d.find_shop_item(overworld, icon, roi=(365, 75, 200, 35))
        self.assertFalse(ok)
        self.assertLess(ncc, d.NCC_ITEM)

    def test_match_word_defensive_oversized_template(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        client = geo.to_client(img)
        import numpy as np
        toobig = np.zeros((client.shape[0] + 10, client.shape[1] + 10, 3),
                          dtype=np.uint8)
        ok, pt, ncc = d.match_word(client, toobig)
        self.assertFalse(ok)
        self.assertIsNone(pt)


# ---------------------------------------------------------------------------
class TestSelectionRing(unittest.TestCase):

    def test_ring_present_at_real_ring(self):
        # Echter roter Selektions-Ring (BlRG): Mitte ~ (505, 198). y_min hier 150,
        # weil DIESER Ring hoeher in der Szene liegt als der Default 240
        # (KALIBRIER-BAR -- live re-kalibrieren, P0.6).
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertTrue(d.selection_ring_present(img, (505, 198), y_min=150))

    def test_no_ring_on_hp_bar(self):
        # Die rote HP-Leiste (flach) darf NICHT als Ring durchgehen (FP-Schutz).
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertFalse(d.selection_ring_present(img, (430, 255), y_min=240))

    def test_no_ring_on_empty_grass(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertFalse(d.selection_ring_present(img, (250, 420), y_min=240))

    def test_no_ring_in_npcless_scenes(self):
        for name in ('metin2client_2JJQT56i9r.png', 'metin2client_KwAggglQCf.png',
                     'metin2client_VzkvyxJMNO.png', 'metin2client_jlJmS5asq6.png'):
            img = _load('Waffenschmied', name)
            self.assertFalse(d.selection_ring_present(img, (400, 350)),
                             'false ring in %s' % name)

    def test_ring_defensive_none_near(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertFalse(d.selection_ring_present(img, None))


# ---------------------------------------------------------------------------
class TestAssetBoundDetectorsNotReady(unittest.TestCase):
    """Ohne gebundelte Marker-Templates: sauberes NotReady (None/False), kein Crash."""

    def test_dialog_state_none_without_templates(self):
        img = _load('Einkauf_Hammer', 'erstgespräch1.png')
        self.assertIsNone(d.dialog_state(img))

    def test_shop_open_false_without_templates(self):
        img = _load('Einkauf_Hammer', 'Shopgeöffnetalchemist.png')
        self.assertFalse(d.shop_open(img))

    def test_panel_is_bag_false_without_templates(self):
        img = _load('Einkauf_Dolche', 'Inventar.png')
        self.assertFalse(d.panel_is_bag(img))

    def test_read_shop_stack_stub_none(self):
        # TODO-live-asset (P0.3): Shop-Stack-Digit-Templates fehlen -> None.
        img = _load('Einkauf_Hammer', 'Shopgeöffnetalchemist.png')
        slot = geo.to_client(img)[78:104, 372:400]
        self.assertIsNone(d.read_shop_stack(slot))

    def test_read_splitter_growth_stub_zero(self):
        # TODO-live-asset (P0.5): Splitter-Slot-Crop fehlt -> 0 (kein Zuwachs).
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertEqual(d.read_splitter_growth(img, img), 0)


# ---------------------------------------------------------------------------
class TestShopHeaderDiscriminationWithInjectedTemplate(unittest.TestCase):
    """Beweist: shop_open WIRD korrekt diskriminieren, sobald das Header-Template
    (P0.2) gebundelt ist -- hier via injiziertem ECHTEM 'Laden'-Crop."""

    def setUp(self):
        self._orig = d._load_template
        tpl = _laden_header_template()

        def fake(lang, word):
            if word == 'laden_header' and lang == 'de':
                return tpl
            return None
        d._load_template = fake

    def tearDown(self):
        d._load_template = self._orig

    def test_shop_open_true_in_open_shop(self):
        # Anderes Shop-Bild (Dolch-Shop) traegt denselben 'Laden'-Header.
        img = _load('Einkauf_Dolche', 'Shopgeöffnet.png')
        self.assertTrue(d.shop_open(img))

    def test_shop_open_false_in_overworld(self):
        img = _load('Alchemist', 'metin2client_BlRGzUUM3w.png')
        self.assertFalse(d.shop_open(img))


if __name__ == '__main__':
    unittest.main()
