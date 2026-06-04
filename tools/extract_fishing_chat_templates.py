# -*- coding: utf-8 -*-
"""One-shot extractor: build the bundled chat-OCR template library from the
labelled reference screenshots in ``FischOCR/``.

The Metin2 chat font is a fixed pixel font, so a glyph renders byte-for-byte the
same every time it appears on the bottom chat line. We therefore do not need a
real OCR engine: we segment the bottom chat line of each labelled screenshot
into words (exactly the algorithm in :mod:`fishing_chat`), cut out the relevant
glyph run, binarise it (ink = pixel > 135) and save it as a tiny 1-bit PNG.

THREE kinds of template are produced into ``fishing_chat_templates/``:

  * ``disc__<key>.png`` -- the message-type discriminator: word index 4 of each
    sentence ("haette" -> fish, "hinge" -> item, "du" -> niete, "koeder" ->
    no-bite). word[4] is never clipped by the left crop edge (unlike word[0]).
  * ``name__<slug>.png`` -- a whole fish/item NAME bitmap, file stem = the
    official German Metin2 name. The PRIMARY (exact) name matcher.
  * ``glyph__<hex>.png`` -- a single CHARACTER bitmap (hex = the unicode code
    point, filename-safe for umlauts/punctuation). The per-character atlas that
    lets :mod:`fishing_chat` read ANY name it has never seen a screenshot of
    (segment -> match each char -> fuzzy-match against the known name list). This
    is what makes new fish (e.g. Kleiner Fisch, Süßwassergarnele) readable on the
    hook WITHOUT needing a dedicated chat screenshot per fish.

The atlas is built SELF-VALIDATING from the known sentence texts:

  * pass 1 -- extract glyphs only from words whose column-run count equals the
    letter count (clean separation). Word index 0 is skipped (clipped by the
    left crop edge -> garbage first glyph).
  * pass 2 -- recover glyphs from "sticky" off-by-one words (exactly one pair of
    characters touches): find the merged run by hypothesis search against the
    pass-1 atlas, then extract only the OTHER (clean) runs, width-validated
    against pass 1. The merged run itself is skipped -- never split -> no garbage.

Re-run from the repo root whenever the reference set changes::

    python3 tools/extract_fishing_chat_templates.py

It is a DEV tool (kept out of the shipped EXE); the *generated* PNGs are what
gets bundled. It is deliberately chatty and prints every template it writes.
"""

import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

# Allow "python3 tools/extract_fishing_chat_templates.py" from the repo root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fishing_chat import (  # noqa: E402  (after sys.path tweak)
    CHAT_REGION, INK_THRESHOLD, WORD_GAP, _binary_line, _segment_words,
    _crop_word_band, _crop_span_band, _slug, name_to_slug, _save_template_png,
    _match_score, GLYPH_PREFIX, glyph_filename,
)

_SRC_DIR = os.path.join(_ROOT, 'FischOCR')
_OUT_DIR = os.path.join(_ROOT, 'fishing_chat_templates')

# Reference screenshot -> (kind, official German name). 'fish' uses the
# "...haette {NAME} angebissen." frame (name = words[5 .. -2]); 'item' uses
# "...hinge {NAME} am Haken." (name = words[5 .. -3]).
_FISH_ITEM_SOURCES = {
    'Lachs.png': ('fish', 'Lachs'),
    'thunfisch.png': ('fish', 'Goldener Thunfisch'),
    'Lotusfisch.png': ('fish', 'Lotusfisch'),
    'Mandarinfisch.png': ('fish', 'Mandarinfisch'),
    'Mandarinfisch2.png': ('fish', 'Mandarinfisch'),
    'Mandarinfisch3.png': ('fish', 'Mandarinfisch'),
    'Spiegelkarpfen.png': ('fish', 'Spiegelkarpfen'),
    'Zander.png': ('fish', 'Zander'),
    'rotes Haarfärbemittel.png': ('item', 'Rotes Haarfärbemittel'),
}

# Discriminator: which reference's word[4] yields each branch glyph.
_DISC_SOURCES = {
    'haette': 'Lachs.png',                       # fish
    'hinge': 'rotes Haarfärbemittel.png',        # item
    'du': 'nichterkannt.png',                    # niete  (Etwas hat angebissen, aber DU ...)
    'koeder': 'nochnichtsnurköderbefestigt.png',  # no-bite (... als KOEDER am Haken ...)
}
_DISC_WORD_INDEX = 4

# Full ground-truth sentence per reference -- the glyph atlas is built from
# these. Word counts are validated at runtime (a wrong text just gets skipped).
_GLYPH_SOURCES = {
    'Lachs.png': 'Es sieht aus, als hätte Lachs angebissen.',
    'Lotusfisch.png': 'Es sieht aus, als hätte Lotusfisch angebissen.',
    'Mandarinfisch.png': 'Es sieht aus, als hätte Mandarinfisch angebissen.',
    'Spiegelkarpfen.png': 'Es sieht aus, als hätte Spiegelkarpfen angebissen.',
    'Zander.png': 'Es sieht aus, als hätte Zander angebissen.',
    'thunfisch.png': 'Es sieht aus, als hätte Goldener Thunfisch angebissen.',
    'rotes Haarfärbemittel.png':
        'Es sieht aus, als hinge Rotes Haarfärbemittel am Haken.',
    'nichterkannt.png':
        'Etwas hat angebissen, aber du kannst nicht erkennen, was es ist.',
    'nochnichtsnurköderbefestigt.png':
        'Du hast Wurm als Köder am Haken befestigt.',
}


def _load_bgr(path):
    """Load a PNG as the BGR uint8 image a capture would yield."""
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _line_and_words(path):
    bgr = _load_bgr(path)
    x0, y0, x1, y1 = CHAT_REGION
    region = bgr[y0:y1, x0:x1]
    binary = _binary_line(region)
    words = _segment_words(binary)
    return binary, words


def _name_region(words, kind):
    """(start_col, end_col) of the NAME run for a fish/item sentence."""
    if kind == 'fish':
        last = len(words) - 2            # exclude trailing "angebissen."
    else:
        last = len(words) - 3            # exclude trailing "am" + "Haken."
    return words[5][0], words[last][1]


def _runs_in_span(binary, a, b):
    """Column-runs (single characters) inside [a, b) as absolute (start, end)."""
    sub = binary[:, a:b]
    col = sub.sum(axis=0)
    runs, i, n = [], 0, int(col.shape[0])
    while i < n:
        if col[i] > 0:
            j = i
            while j < n and col[j] > 0:
                j += 1
            runs.append((a + i, a + j))
            i = j
        else:
            i += 1
    return runs


def _glyph_lines():
    """[(src, binary, words, text_words), ...] for sources whose segmented word
    count matches the ground-truth text (others are skipped as unreliable)."""
    out = []
    for src, text in _GLYPH_SOURCES.items():
        path = os.path.join(_SRC_DIR, src)
        if not os.path.exists(path):
            continue
        binary, words = _line_and_words(path)
        tw = text.split(' ')
        if len(words) == len(tw):
            out.append((src, binary, words, tw))
        else:
            print('  glyph: skip %-30s (img words=%d != text words=%d)'
                  % (src, len(words), len(tw)))
    return out


def _build_glyph_atlas():
    """Return ``{char: bitmap}`` -- one clean representative per character.

    pass 1: clean words (run count == letter count), word index 0 skipped.
    pass 2: sticky off-by-one words -> extract only the clean runs (merged run
    located by hypothesis search, then skipped), width-validated against pass 1.
    """
    lines = _glyph_lines()
    samples = defaultdict(list)

    # -- pass 1: clean words --------------------------------------------
    for _src, binary, words, tw in lines:
        for wi, ((a, b), wtext) in enumerate(zip(words, tw)):
            if wi == 0:                              # left-clipped first word
                continue
            runs = _runs_in_span(binary, a, b)
            if len(runs) == len(wtext):
                for (ra, rb), ch in zip(runs, wtext):
                    g = _crop_word_band(binary, (ra, rb))
                    if g is not None:
                        samples[ch].append(g)

    def known_width(ch):
        if not samples[ch]:
            return None
        return Counter(g.shape[1] for g in samples[ch]).most_common(1)[0][0]

    def representative(ch):
        w = known_width(ch)
        if w is None:
            return None
        for g in samples[ch]:
            if g.shape[1] == w:
                return g
        return None

    # -- pass 2: clean runs of sticky off-by-one words ------------------
    for _ in range(3):                               # iterate: more glyphs each round
        for _src, binary, words, tw in lines:
            for wi, ((a, b), wtext) in enumerate(zip(words, tw)):
                if wi == 0:
                    continue
                runs = _runs_in_span(binary, a, b)
                if len(runs) != len(wtext) - 1:      # only exact off-by-one
                    continue
                # Hypothesis: run k is the merge of wtext[k] + wtext[k+1].
                best_k, best_score = None, -1e9
                for k in range(len(runs)):
                    sc, cnt = 0.0, 0
                    for m in range(len(runs)):
                        ch = (wtext[m] if m < k
                              else (None if m == k else wtext[m + 1]))
                        rep = None if ch is None else representative(ch)
                        if rep is None:
                            continue
                        sc += _match_score(_crop_word_band(binary, runs[m]), rep)
                        cnt += 1
                    score = sc / cnt if cnt else -1e9
                    if score > best_score:
                        best_score, best_k = score, k
                if best_k is None or best_score < 0.6:
                    continue
                for m in range(len(runs)):
                    if m == best_k:                  # merged -> skip (no garbage)
                        continue
                    ch = wtext[m] if m < best_k else wtext[m + 1]
                    g = _crop_word_band(binary, runs[m])
                    if g is None:
                        continue
                    kw = known_width(ch)
                    if kw is not None and g.shape[1] != kw:
                        continue                     # width mismatch -> reject
                    if g.shape[1] not in [s.shape[1] for s in samples[ch]]:
                        samples[ch].append(g)

    return {ch: representative(ch) for ch in samples
            if representative(ch) is not None}


def main():
    os.makedirs(_OUT_DIR, exist_ok=True)
    written = 0

    # -- discriminator glyphs (word[4]) ---------------------------------
    # WICHTIG: exakt dieselbe Zeilen-Beschneidung (Band-Trim) wie zur Laufzeit
    # in fishing_chat, sonst stimmen Template- und Lauf-Glyph-Hoehen nicht
    # ueberein und der NCC-Score bricht ein.
    for key, src in _DISC_SOURCES.items():
        binary, words = _line_and_words(os.path.join(_SRC_DIR, src))
        glyph = _crop_word_band(binary, words[_DISC_WORD_INDEX])
        out = os.path.join(_OUT_DIR, 'disc__%s.png' % key)
        _save_template_png(glyph, out)
        gw = 0 if glyph is None else glyph.shape[1]
        print('disc  %-8s <- %-30s w=%d  -> %s' % (key, src, gw, out))
        written += 1

    # -- name glyphs (fish / item) --------------------------------------
    for src, (kind, name) in _FISH_ITEM_SOURCES.items():
        binary, words = _line_and_words(os.path.join(_SRC_DIR, src))
        a, b = _name_region(words, kind)
        glyph = _crop_span_band(binary, a, b)
        slug = name_to_slug(name)
        out = os.path.join(_OUT_DIR, 'name__%s.png' % slug)
        # Several sources may map to the same name (Mandarinfisch x3) -- the
        # bitmaps are identical, so the last write is fine + idempotent.
        _save_template_png(glyph, out)
        print('name  %-22s <- %-30s w=%d  -> %s' % (name, src, b - a, out))
        written += 1

    # -- character atlas (glyph__<hex>.png) -----------------------------
    atlas = _build_glyph_atlas()
    chars = ''.join(sorted(atlas, key=lambda c: (c.isupper(), c)))
    print('\nglyph atlas: %d chars -> %r' % (len(atlas), chars))
    for ch, bitmap in atlas.items():
        out = os.path.join(_OUT_DIR, glyph_filename(ch))
        _save_template_png(bitmap, out)
        written += 1

    print('\n%d template PNG(s) written to %s' % (written, _OUT_DIR))


if __name__ == '__main__':
    main()
