# -*- coding: utf-8 -*-
"""One-shot extractor: build the bundled chat-OCR template library from the
labelled reference screenshots in ``FischOCR/``.

The Metin2 chat font is a fixed pixel font, so a NAME (or the discriminator
word) renders byte-for-byte the same every time it appears on the bottom chat
line. We therefore do not need a real OCR engine: we segment the bottom chat
line of each labelled screenshot into words (exactly the algorithm in
:mod:`fishing_chat`), cut out the relevant glyph run, binarise it (ink = pixel
> 135) and save it as a tiny 1-bit PNG. :mod:`fishing_chat` later loads these
and matches an unknown name-bitmap against them (masked NCC / mean-abs-diff,
same idea as the inventory matcher).

Two kinds of template are produced into ``fishing_chat_templates/``:

  * ``disc__<key>.png`` -- the message-type discriminator: word index 4 of each
    sentence ("haette" -> fish, "hinge" -> item, "du" -> niete, "koeder" ->
    no-bite). All four word[4] glyphs are mutually distinct, and word[4] is
    never clipped by the left crop edge (unlike word[0]), which makes it the
    most reliable branch signal.
  * ``name__<slug>.png`` -- a fish/item NAME bitmap, file stem = the official
    German Metin2 name (ground truth). These are matched to classify the catch.

Re-run from the repo root whenever the reference set changes::

    python3 tools/extract_fishing_chat_templates.py

It is a DEV tool (kept out of the shipped EXE); the *generated* PNGs are what
gets bundled. It is deliberately chatty and prints every template it writes.
"""

import os
import sys

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

    print('\n%d template PNG(s) written to %s' % (written, _OUT_DIR))


if __name__ == '__main__':
    main()
