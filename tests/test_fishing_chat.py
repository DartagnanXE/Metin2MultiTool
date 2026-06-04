# -*- coding: utf-8 -*-
"""Validierung des Chat-OCR-Kerns (:mod:`fishing_chat`) gegen ECHTE Screenshots.

Faehrt :func:`fishing_chat.read_hook` gegen JEDES gelabelte ``FischOCR/*.png``
(ausser den ``Goldener*``-Dialog-Shots, die KEINE Chat-Zeile zeigen) und prueft
die korrekte Klassifikation. Dateiname == Ground Truth:

  * ``Lachs``               -> Fisch, Name "Lachs"
  * ``thunfisch``           -> Fisch, Name "Goldener Thunfisch"
  * ``Lotusfisch``          -> Fisch, Name "Lotusfisch"
  * ``Mandarinfisch[2/3]``  -> Fisch, Name "Mandarinfisch"
  * ``Spiegelkarpfen``      -> Fisch, Name "Spiegelkarpfen"
  * ``Zander``              -> Fisch, Name "Zander"
  * ``rotes Haarfärbemittel`` -> Item, Name "Rotes Haarfärbemittel"
  * ``nichterkannt``        -> NIETE (kein Name)
  * ``nochnichtsnurköderbefestigt`` -> KEIN_BISS (kind == NONE)

Reines ``numpy`` / ``PIL`` -> laeuft headless mit ``python3`` UND unter
``py.exe -m pytest``. Ohne numpy/PIL oder ohne die Screenshots wird sauber
geskippt. Das ``_crops/``-Unterverzeichnis ist Debug -> ignoriert.
"""

import os
import unittest

try:
    import numpy as np
    from PIL import Image
    _HAS_DEPS = True
except Exception:                       # pragma: no cover - headless ohne Deps
    _HAS_DEPS = False

import fishing_chat as fc


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_FISCH_DIR = os.path.join(_ROOT, 'FischOCR')


# Erwartung je Label: (kind, name | None). name=None -> egal/keiner.
# UNKNOWN-Sentinel ist NIE erlaubt fuer diese gelabelten, eindeutigen Shots.
_EXPECTED = {
    'Lachs.png': (fc.FISH, 'Lachs'),
    'thunfisch.png': (fc.FISH, 'Goldener Thunfisch'),
    'Lotusfisch.png': (fc.FISH, 'Lotusfisch'),
    'Mandarinfisch.png': (fc.FISH, 'Mandarinfisch'),
    'Mandarinfisch2.png': (fc.FISH, 'Mandarinfisch'),
    'Mandarinfisch3.png': (fc.FISH, 'Mandarinfisch'),
    'Spiegelkarpfen.png': (fc.FISH, 'Spiegelkarpfen'),
    'Zander.png': (fc.FISH, 'Zander'),
    'rotes Haarfärbemittel.png': (fc.ITEM, 'Rotes Haarfärbemittel'),
    'nichterkannt.png': (fc.NIETE, None),
    'nochnichtsnurköderbefestigt.png': (fc.NONE, None),
}


def _shots_present():
    return _HAS_DEPS and all(
        os.path.isfile(os.path.join(_FISCH_DIR, f)) for f in _EXPECTED)


def _load_bgr(path):
    """PNG -> BGR uint8 (genau das, was WindowCapture liefert)."""
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


@unittest.skipUnless(_shots_present(), 'numpy/PIL oder FischOCR-Screenshots fehlen')
class TestFishingChatRealLabels(unittest.TestCase):
    """Jedes gelabelte Chat-Bild muss korrekt klassifiziert werden."""

    @classmethod
    def setUpClass(cls):
        fc.reset_template_cache()       # frisch aus dem gebuendelten Ordner

    def _read(self, fname):
        return fc.read_hook(_load_bgr(os.path.join(_FISCH_DIR, fname)))

    def test_every_label_classifies_correctly(self):
        failures = []
        for fname, (exp_kind, exp_name) in sorted(_EXPECTED.items()):
            res = self._read(fname)
            ok = (res.kind == exp_kind)
            if exp_name is not None:
                ok = ok and res.name == exp_name and res.confident
            if not ok:
                failures.append('%s -> got %r (erwartet kind=%s name=%r)'
                                % (fname, res, exp_kind, exp_name))
        self.assertEqual(failures, [], 'Fehlklassifikationen:\n' + '\n'.join(failures))

    # -- Einzelfaelle (klarere Fehlermeldung je Bild) -------------------

    def test_fish_salmon(self):
        r = self._read('Lachs.png')
        self.assertEqual((r.kind, r.name, r.confident), (fc.FISH, 'Lachs', True))

    def test_fish_golden_tuna_name(self):
        r = self._read('thunfisch.png')
        self.assertEqual(r.kind, fc.FISH)
        self.assertEqual(r.name, 'Goldener Thunfisch')
        self.assertTrue(r.confident)

    def test_fish_lotus(self):
        r = self._read('Lotusfisch.png')
        self.assertEqual((r.kind, r.name), (fc.FISH, 'Lotusfisch'))

    def test_fish_mandarin_variants(self):
        for f in ('Mandarinfisch.png', 'Mandarinfisch2.png', 'Mandarinfisch3.png'):
            r = self._read(f)
            self.assertEqual((r.kind, r.name), (fc.FISH, 'Mandarinfisch'), f)

    def test_fish_mirror_carp(self):
        r = self._read('Spiegelkarpfen.png')
        self.assertEqual((r.kind, r.name), (fc.FISH, 'Spiegelkarpfen'))

    def test_fish_zander(self):
        r = self._read('Zander.png')
        self.assertEqual((r.kind, r.name), (fc.FISH, 'Zander'))

    def test_item_red_dye(self):
        r = self._read('rotes Haarfärbemittel.png')
        self.assertEqual(r.kind, fc.ITEM)
        self.assertEqual(r.name, 'Rotes Haarfärbemittel')
        self.assertTrue(r.confident)

    def test_niete(self):
        r = self._read('nichterkannt.png')
        self.assertEqual(r.kind, fc.NIETE)
        self.assertIsNone(r.name)
        self.assertFalse(r.is_bite)

    def test_no_bite_only_bait(self):
        r = self._read('nochnichtsnurköderbefestigt.png')
        self.assertEqual(r.kind, fc.NONE)
        self.assertFalse(r.is_bite)


@unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
class TestChatRegionBottomAnchor(unittest.TestCase):
    """Kalibrier-Fix: die Default-Chat-Region wird an den UNTEREN Frame-Rand
    verankert, damit DIESELBE Logik den 802x632-Referenz-Shot (mit Titelleiste)
    UND den 800x601-Live-Client (ohne Titelleiste, ~31px kuerzer) trifft.

    Der Live-Capture von ``WindowCapture`` ist der reine Client; eine fix aus
    632 gemessene y-Region laege darin ~31px zu tief (in der Hotbar) -> die
    Chat-Zeile wuerde komplett verfehlt (Regression, die dieser Fix behebt).
    """

    @classmethod
    def setUpClass(cls):
        fc.reset_template_cache()

    def test_reference_frame_region_is_unchanged(self):
        # Bit-Stabilitaet: auf dem 632er-Referenzframe MUSS die verankerte Region
        # exakt die alte CHAT_REGION sein -> alle Templates/Labels bleiben gueltig.
        self.assertEqual(fc.chat_region_for_frame(632), fc.CHAT_REGION)
        self.assertEqual(fc.chat_region_for_frame(632), (115, 579, 405, 596))

    def test_client_frame_region_shifts_up_by_titlebar(self):
        # 800x601-Client: y um die ~31px Titelleiste (632-601) nach OBEN gerueckt.
        self.assertEqual(fc.chat_region_for_frame(601), (115, 548, 405, 565))
        ref = fc.chat_region_for_frame(632)
        cli = fc.chat_region_for_frame(601)
        self.assertEqual(ref[1] - cli[1], 31)   # obere y-Kante
        self.assertEqual(ref[3] - cli[3], 31)   # untere y-Kante
        self.assertEqual((ref[0], ref[2]), (cli[0], cli[2]))  # x unveraendert

    def test_bad_height_falls_back_to_chat_region(self):
        # Defensiv: unbrauchbare Hoehe -> fixe CHAT_REGION, nie ein Crash.
        for bad in (0, -5, None, 'x', float('nan')):
            self.assertEqual(fc.chat_region_for_frame(bad), fc.CHAT_REGION)

    def test_explicit_region_is_respected(self):
        # Ein explizit uebergebenes region UEBERSCHREIBT den Auto-Anker.
        custom = (0, 0, 3, 3)
        # Auf rein schwarzem Bild -> NONE, aber ohne den Auto-Anker zu nehmen
        # (kein Crash, deterministisch).
        res = fc.read_hook(np.zeros((601, 800, 3), dtype=np.uint8), region=custom)
        self.assertEqual(res.kind, fc.NONE)

    @unittest.skipUnless(_shots_present(), 'FischOCR-Screenshots fehlen')
    def test_simulated_client_frame_reads_every_label(self):
        # Schluessel-Beleg: aus jedem 802x632-Label einen ECHTEN 800x601-Client
        # bauen (oben 31px Titelleiste + 1px-Rand wegschneiden -- genau das, was
        # WindowCapture fuer dieselbe Szene liefert). Die Chat-Zeile sitzt dann
        # bei y[548,565]; der Auto-Anker MUSS jeden Fisch/Item korrekt lesen.
        # Mit der alten fixen Region (y[579,596]) waere das NONE gewesen.
        title, border = 31, 1
        cases = {k: v for k, v in _EXPECTED.items() if v[1] is not None}
        failures = []
        for fname, (exp_kind, exp_name) in sorted(cases.items()):
            full = _load_bgr(os.path.join(_FISCH_DIR, fname))   # (632, 802)
            client = full[title:, border:border + 800]          # -> (601, 800)
            if client.shape[:2] != (601, 800):
                failures.append('%s: client shape %r' % (fname, client.shape[:2]))
                continue
            res = fc.read_hook(client)                          # Auto-Anker
            if not (res.kind == exp_kind and res.name == exp_name and res.confident):
                failures.append('%s -> %r (erwartet kind=%s name=%r)'
                                % (fname, res, exp_kind, exp_name))
        self.assertEqual(failures, [],
                         '601-Client-Fehlklassifikationen:\n' + '\n'.join(failures))

    def test_live_capture_region_lands_on_chat_row(self):
        # Optional: der echte Bot-Capture (live_capture.png, 800x601) liegt im
        # Repo-Root. Falls vorhanden: die verankerte Region MUSS die Chat-Textzeile
        # treffen (Wort-Segmentierung findet dort Text) -- NICHT mehr die Hotbar.
        path = os.path.join(_ROOT, 'live_capture.png')
        if not os.path.isfile(path):
            self.skipTest('live_capture.png fehlt')
        live = _load_bgr(path)
        if live.shape[:2] != (601, 800):
            self.skipTest('live_capture.png ist nicht 800x601')
        x0, y0, x1, y1 = fc.chat_region_for_frame(live.shape[0])
        self.assertEqual((y0, y1), (548, 565))
        binary = fc._binary_line(live[y0:y1, x0:x1])
        words = fc._segment_words(binary)
        # In der Chat-Zeile steht Text -> mindestens ein Wort-Segment, Tinte > 0.
        self.assertGreaterEqual(len(words), 1)
        self.assertGreater(int(binary.sum()), 0)
        # read_hook wirft auch hier nie.
        self.assertIn(fc.read_hook(live).kind,
                      (fc.NONE, fc.FISH, fc.ITEM, fc.NIETE))


@unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
class TestFishingChatRobustness(unittest.TestCase):
    """Der Kern wirft NIE und liefert bei Muell sauber NONE/UNKNOWN."""

    def test_none_input(self):
        self.assertEqual(fc.read_hook(None).kind, fc.NONE)

    def test_garbage_shapes_do_not_raise(self):
        for bad in (np.zeros((5,), dtype=np.uint8),
                    np.zeros((10, 10), dtype=np.uint8),
                    np.zeros((632, 802, 3), dtype=np.uint8),   # rein schwarz
                    np.full((632, 802, 3), 255, dtype=np.uint8)):  # rein weiss
            res = fc.read_hook(bad)
            self.assertIn(res.kind, (fc.NONE, fc.FISH, fc.ITEM, fc.NIETE))

    def test_black_screen_is_none(self):
        res = fc.read_hook(np.zeros((632, 802, 3), dtype=np.uint8))
        self.assertEqual(res.kind, fc.NONE)

    def test_segment_words_empty(self):
        self.assertEqual(fc._segment_words(None), [])
        self.assertEqual(fc._segment_words(np.zeros((10, 50), dtype=np.uint8)), [])

    def test_word_gap_threshold_groups_correctly(self):
        # Drei "Zeichen": Spalten 0-1, 3-4 (Luecke 1 -> selbes Wort), dann nach
        # Luecke 5 (> WORD_GAP) ein neues Wort bei 10-11.
        binary = np.zeros((4, 14), dtype=np.uint8)
        for c in (0, 1, 3, 4, 10, 11):
            binary[:, c] = 1
        words = fc._segment_words(binary)
        self.assertEqual(words, [(0, 5), (10, 12)])

    def test_best_match_margin_ignores_width_invalid_competitor(self):
        # Regression: die Margin in _best_match darf NUR gegen breitengueltige
        # Konkurrenten gerechnet werden. Ein breiten-verworfenes (geometrisch
        # unmoegliches) Template -- z.B. ein viel breiteres Wort, das per NCC auf
        # null-gepaddetem Array trotzdem hoch matcht -- darf die Margin des
        # korrekten, breitengueltigen Siegers NICHT druecken (sonst faellt ein
        # klarer Treffer faelschlich unter das Margin-Gate -> UNKNOWN/NONE).
        glyph = np.zeros((6, 8), dtype=np.uint8)
        glyph[1:5, 1:4] = 1
        glyph[0:2, 5:7] = 1

        best = glyph.copy()                     # breitengueltig, score ~1.0
        alt = glyph.copy()                      # breitengueltig, score < 1.0
        alt[5, 7] = 1
        alt[4, 0] = 1
        wide = np.zeros((6, 22), dtype=np.uint8)  # 22 >> 8 -> BREITEN-UNGUELTIG
        wide[1:5, 1:4] = 1                       # gleiche Tinte links -> score ~1.0
        wide[0:2, 5:7] = 1

        key, score, margin = fc._best_match(
            glyph, {'best': best, 'alt': alt, 'wide': wide})
        # Sieger ist der breitengueltige beste Treffer.
        self.assertEqual(key, 'best')
        # Margin gegen den breitengueltigen Zweitbesten ('alt'), NICHT gegen das
        # breiten-ungueltige 'wide' (das in der alten Logik margin -> 0 drueckte).
        self.assertGreater(margin, fc.NAME_MIN_MARGIN)
        self.assertAlmostEqual(margin, score - fc._match_score(glyph, alt),
                               places=5)

    def test_best_match_only_width_invalid_yields_zero_margin(self):
        # Gibt es NUR breitengueltig genau einen Kandidaten (alle anderen
        # breiten-ungueltig), ist die Margin sauber 0.0 -- kein Greifen auf einen
        # breiten-ungueltigen Score als "Zweitbester".
        glyph = np.zeros((6, 8), dtype=np.uint8)
        glyph[1:5, 1:4] = 1
        only = glyph.copy()
        wide = np.zeros((6, 30), dtype=np.uint8)
        wide[1:5, 1:4] = 1
        key, score, margin = fc._best_match(glyph, {'only': only, 'wide': wide})
        self.assertEqual(key, 'only')
        self.assertEqual(margin, score - (-1.0))

    def test_unknown_name_still_reports_bite(self):
        # Fisch-Satzbau mit Diskriminator "haette", aber Name = Vorlage, die in
        # KEINER Bibliothek ist -> kind=FISH, name=UNKNOWN, confident=False.
        # (Wir bauen das ueber read_hook mit leeren Name-Templates nach.)
        bgr = _load_bgr_if(os.path.join(_FISCH_DIR, 'Lachs.png'))
        if bgr is None:
            self.skipTest('Lachs.png fehlt')
        tmpl = dict(fc._load_templates())
        tmpl = {'disc': tmpl.get('disc', {}), 'name': {}}  # Namen leeren
        res = fc.read_hook(bgr, templates=tmpl)
        self.assertEqual(res.kind, fc.FISH)
        self.assertEqual(res.name, fc.UNKNOWN)
        self.assertFalse(res.confident)


def _load_bgr_if(path):
    if not os.path.isfile(path):
        return None
    return _load_bgr(path)


def _render_name(name, atlas):
    """Rendert ``name`` aus den Atlas-Glyphen (1px-Luecken, fehlende Zeichen +
    Leerzeichen ausgelassen) zu einem Binaerbild -- so wie die Chat-Schrift es
    zeichnet. ``None`` wenn kein Zeichen verfuegbar ist."""
    glyphs = [atlas[c] for c in name if c in atlas]
    if not glyphs:
        return None
    h = max(g.shape[0] for g in glyphs)
    w = sum(g.shape[1] for g in glyphs) + (len(glyphs) - 1)
    canvas = np.zeros((h, w), dtype=np.uint8)
    x = 0
    for g in glyphs:
        canvas[:g.shape[0], x:x + g.shape[1]] = g
        x += g.shape[1] + 1
    return canvas


@unittest.skipUnless(_HAS_DEPS, 'numpy/PIL fehlen')
class TestCharOcrUnits(unittest.TestCase):
    """Zeichen-OCR (liest JEDEN Namen ueber den gebuendelten Glyphen-Atlas +
    Fuzzy) -- self-contained ueber die GESHIPPTEN glyph__-PNGs, KEINE
    Screenshots noetig (laeuft auch in CI)."""

    def setUp(self):
        fc.reset_template_cache()
        fc.reset_known_names_cache()
        self.atlas = fc._load_templates().get('glyph', {})

    def test_glyph_filename_roundtrip(self):
        for ch in ['a', 'ä', 'ö', 'S', 'Z', ',', '.']:
            fn = fc.glyph_filename(ch)
            self.assertTrue(fn.startswith(fc.GLYPH_PREFIX))
            self.assertEqual(fc._glyph_char_from_filename(fn), ch)

    def test_levenshtein_basics(self):
        self.assertEqual(fc._levenshtein('abc', 'abc'), 0)
        self.assertEqual(fc._levenshtein('abc', 'abd'), 1)
        self.assertEqual(fc._levenshtein('', 'abc'), 3)
        self.assertEqual(fc._levenshtein('kitten', 'sitting'), 3)

    def test_atlas_shipped_with_core_chars(self):
        # Die geshippten glyph__-PNGs muessen den Kern-Zeichensatz enthalten.
        for ch in ['a', 'e', 's', 'r', 'n', 'i', 'l', 'k', 'w', 'S', 'K']:
            self.assertIn(ch, self.atlas, 'Atlas-Zeichen %r fehlt' % ch)

    def test_fuzzy_recovers_new_fish_from_partial_reads(self):
        names = fc._known_names()
        for read, expect in [('Kleiner?isch', 'Kleiner Fisch'),
                             ('KleinerRisch', 'Kleiner Fisch'),
                             ('S??wassergarnele', 'Süßwassergarnele'),
                             ('Suewassergarnele', 'Süßwassergarnele'),
                             ('wassergarnele', 'Süßwassergarnele')]:
            bn, sim, mg = fc._fuzzy_best_name(read, names)
            self.assertEqual(bn, expect, 'read=%r -> %r' % (read, bn))
            self.assertGreaterEqual(sim, fc.NAME_FUZZY_MIN_SIM)
            self.assertGreaterEqual(mg, fc.NAME_FUZZY_MIN_MARGIN)

    def test_fuzzy_rejects_garbage(self):
        names = fc._known_names()
        for read in ['xqzv', '????', '']:
            bn, sim, mg = fc._fuzzy_best_name(read, names)
            confident = (sim >= fc.NAME_FUZZY_MIN_SIM
                         and mg >= fc.NAME_FUZZY_MIN_MARGIN)
            self.assertFalse(confident, 'Muell %r faelschlich konfident' % read)

    def test_read_synthetic_render_roundtrips_new_fish(self):
        # Rendert die 2 NEUEN Fische aus dem geshippten Atlas, liest zeichenweise
        # zurueck und fuzzy-matcht -> der richtige offizielle Name muss gewinnen.
        if not self.atlas:
            self.skipTest('kein Glyphen-Atlas gebuendelt')
        names = fc._known_names()
        for name in ['Kleiner Fisch', 'Süßwassergarnele', 'Lachs', 'Zander']:
            canvas = _render_name(name, self.atlas)
            self.assertIsNotNone(canvas)
            read = fc._read_name_text(canvas, 0, canvas.shape[1], self.atlas)
            bn, sim, mg = fc._fuzzy_best_name(read, names)
            self.assertEqual(bn, name,
                             'render(%r) -> read=%r -> %r' % (name, read, bn))
            self.assertGreaterEqual(sim, fc.NAME_FUZZY_MIN_SIM)


@unittest.skipUnless(_shots_present(), 'numpy/PIL oder FischOCR-Screenshots fehlen')
class TestCharOcrFallbackRealShots(unittest.TestCase):
    """Fallback-Pfad an ECHTEN Shots: name__-Templates ENTFERNT -> nur der
    Glyphen-Atlas + Fuzzy muessen alle 7 gelabelten Namen erkennen (beweist die
    Zeichen-OCR auf echten Pixeln inkl. klebender Ligaturen)."""

    def setUp(self):
        fc.reset_template_cache()
        full = fc._load_templates()
        # Nur disc + glyph behalten, NAME-Templates leeren -> Fuzzy-Pfad erzwingen.
        self.only_glyph = {'disc': full.get('disc', {}), 'name': {},
                           'glyph': full.get('glyph', {})}

    def test_fallback_reads_all_seven_names(self):
        for fname, (kind, name) in _EXPECTED.items():
            if name is None:
                continue                     # Niete/Koeder haben keinen Namen
            bgr = _load_bgr(os.path.join(_FISCH_DIR, fname))
            res = fc.read_hook(bgr, region=fc.CHAT_REGION,
                               templates=self.only_glyph)
            self.assertEqual(res.kind, kind, fname)
            self.assertEqual(res.name, name,
                             '%s: Fuzzy las %r' % (fname, res.name))
            self.assertTrue(res.confident, fname)


if __name__ == '__main__':
    unittest.main(verbosity=2)
