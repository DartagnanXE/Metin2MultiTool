# -*- coding: utf-8 -*-
"""Build a labelled ``FischOCR/*.png`` reference frame from a small 2-line chat
crop (the kind a user pastes: top line "Du hast Wurm als Koeder ...", bottom line
"Es sieht aus, als ... ").

Why this exists: the bundled chat-OCR templates are extracted by
``extract_fishing_chat_templates.py`` from full 802x632 reference frames, reading
ONLY the bottom chat line at :data:`fishing_chat.CHAT_REGION` (x[115,405],
y[579,596]). A raw user crop is the wrong size/position for that pipeline. This
tool places the crop's BOTTOM (newest) chat line -- pixel-exact, no scaling, the
font is a fixed pixel font -- onto a black 802x632 canvas exactly inside
CHAT_REGION, so the existing extractor and the existing real-shot tests handle
the new fish with no special-casing.

It is pixel-faithful: the discriminator/name glyphs land byte-identical to a live
capture (verified: the disc word matches the bundled template at score 1.000),
which is the whole premise of the matcher.

Run from the repo root::

    python3 tools/synthesize_chat_reference.py

Reads ``FischOCR/_src_crops/<Name>.png`` (raw 2-line crops kept for provenance)
and writes ``FischOCR/<Name>.png`` (802x632). DEV tool; kept out of the EXE.
"""

import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fishing_chat import CHAT_REGION, INK_THRESHOLD  # noqa: E402

_SRC_DIR = os.path.join(_ROOT, 'FischOCR', '_src_crops')
_OUT_DIR = os.path.join(_ROOT, 'FischOCR')

# Reference frame size of the labelled shots: 802x632 = 800x600 client + ~31px
# Windows titlebar + 1px border (see fishing_chat calibration notes).
_FRAME_H, _FRAME_W = 632, 802

# Raw crops to lift into proper reference frames (file stem == output name).
_CROPS = [
    'Karpfen.png',
    'Aal.png',
    'Schwarzes Haarfärbemittel.png',
]


def _crop_to_bgr(path):
    """RGBA/RGB crop -> BGR uint8, transparent background composited over black
    (a live capture has the chat text light-on-dark, no alpha)."""
    img = Image.open(path).convert('RGBA')
    bg = Image.new('RGBA', img.size, (0, 0, 0, 255))
    rgb = np.asarray(Image.alpha_composite(bg, img).convert('RGB'), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _bottom_line_bbox(bgr):
    """Tight (y0, y1, x0, x1) bbox of the BOTTOM (last) ink row-band -- the
    newest chat line, which is the one the bot reads."""
    gray = 0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
    ink = gray > INK_THRESHOLD
    rows = ink.sum(axis=1)
    bands, i, n = [], 0, len(rows)
    while i < n:
        if rows[i] > 0:
            j = i
            while j < n and rows[j] > 0:
                j += 1
            bands.append((i, j))
            i = j
        else:
            i += 1
    if not bands:
        raise ValueError('no ink found in crop')
    y0, y1 = bands[-1]
    cols = np.where(ink[y0:y1, :].sum(axis=0) > 0)[0]
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    return y0, y1, x0, x1


def synthesize(name):
    src = os.path.join(_SRC_DIR, name)
    bgr = _crop_to_bgr(src)
    y0, y1, x0, x1 = _bottom_line_bbox(bgr)
    strip = bgr[y0:y1, x0:x1]
    h, w = strip.shape[:2]

    cx0, cy0, cx1, cy1 = CHAT_REGION              # (115, 579, 405, 596)
    if h > (cy1 - cy0) or w > (_FRAME_W - cx0):
        raise ValueError('%s: line %dx%d does not fit CHAT_REGION' % (name, w, h))

    canvas = np.zeros((_FRAME_H, _FRAME_W, 3), dtype=np.uint8)
    canvas[cy0:cy0 + h, cx0:cx0 + w] = strip      # left/top-anchored in CHAT_REGION

    out = os.path.join(_OUT_DIR, name)
    rgb = np.ascontiguousarray(canvas[:, :, ::-1])
    Image.fromarray(rgb, mode='RGB').save(out)
    print('wrote %-32s line=%dx%d  -> %s' % (name, w, h, out))


def main():
    for name in _CROPS:
        synthesize(name)


if __name__ == '__main__':
    main()
