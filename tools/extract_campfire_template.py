# -*- coding: utf-8 -*-
"""One-shot extractor: build the bundled "Lagerfeuer" label template from the
marked campfire reference screenshots in ``FischOCR/Lagerfeuer markeirung/``.

The campfire ground object is signposted by Metin2 with a SCREEN-ALIGNED green
text label that reads "Lagerfeuer" (it does NOT rotate with the dock camera) plus
a small red placement circle directly under it. The label is rendered in the
game's fixed pixel font, so the green glyph run is byte-stable every time it
appears -- across all six reference shots it measures 47x11 px with ~112 green
pixels, regardless of where the object sits or how the camera is turned.

We therefore do NOT need OCR: we isolate the green text pixels of the label in
each reference, take the per-pixel CONSENSUS mask (a green pixel kept only when
it is green in the MAJORITY of references -> drops one-shot antialiasing flicker),
and save two tiny bundled assets into ``campfire_templates/``:

  * ``lagerfeuer_mask.png`` -- 1-bit consensus mask of the green glyph (ink = the
    text). :mod:`inventory_campfire` matches this against the green-filtered
    capture (masked NCC), which is robust to the wildly varying water/dock
    background behind the floating label.
  * ``lagerfeuer_gray.png`` -- the same glyph as an 8-bit image (ink=255), kept
    as a human-inspectable reference of what is matched.

It also re-derives + prints the two geometric constants
:mod:`inventory_campfire` relies on (and which are pinned in its tests):

  * the label glyph size, and
  * the offset from the matched label's TOP-LEFT to the FIRE world position
    (the red circle's centre), measured at a steady ``(+20, +21)`` px in every
    reference.

Re-run from the repo root whenever the reference set changes::

    python3 tools/extract_campfire_template.py

DEV tool (kept out of the shipped EXE); the GENERATED PNGs under
``campfire_templates/`` are what gets bundled (see the .spec ``datas``).
Deliberately chatty -- prints every measurement and every file it writes.
"""

import glob
import os
import sys

import numpy as np
from PIL import Image

# Allow "python3 tools/extract_campfire_template.py" from the repo root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_SRC_DIR = os.path.join(_ROOT, 'FischOCR', 'Lagerfeuer markeirung')
_OUT_DIR = os.path.join(_ROOT, 'campfire_templates')

# Hand-verified label CENTRES per reference (green-text centroid). Used only to
# window the green search to the floating label (and away from the green minimap
# blips on the right HUD); the extractor then re-measures the tight bbox itself.
_LABEL_CENTERS = {
    'Feuer1': (416, 414), 'Feuer2': (374, 405), 'Feuer3': (427, 404),
    'Feuer4': (427, 405), 'Feuer5': (384, 416), 'Feuer6': (369, 415),
}

# Red placement-circle centre per reference (the FIRE world point). Measured as
# label_centre + (-2, +17); pinned so the offset print is reproducible.
def _fire_point(cx, cy):
    return (cx - 2, cy + 17)


def _green_mask(rgb):
    """Boolean mask of the label's green text pixels (G dominant, low blue).

    Mirrors the live prefilter in :func:`inventory_campfire.green_text_mask` so
    the bundled template is cut from EXACTLY what the runtime will threshold.
    """
    a = rgb.astype(np.int32)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (g > 110) & (g - b > 50) & (g >= r) & (r > 40)


def _word_bbox(mask, cx, cy):
    """Tight ``(x0, y0, w, h)`` of the green word near ``(cx, cy)``.

    Windows to +-35 px in x / +-9 px in y around the centre (the label is ~47x11)
    so neighbouring green never bleeds in, then takes the bounding box of what
    remains.
    """
    win = np.zeros_like(mask)
    win[max(0, cy - 9):cy + 9, max(0, cx - 35):cx + 35] = True
    mm = mask & win
    ys, xs = np.where(mm)
    if len(xs) == 0:
        return None
    x0, y0 = int(xs.min()), int(ys.min())
    return (x0, y0, int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1)


def main():
    os.makedirs(_OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(_SRC_DIR, 'Feuer*.png')))
    if not files:
        print('No reference shots found in %s' % _SRC_DIR)
        return

    # Fixed glyph box (the stable measurement): width = the consistent 47, height
    # = the tallest seen (11, to keep the one extra antialiased row).
    GLYPH_W, GLYPH_H = 47, 11

    crops = []
    print('Per-reference label measurements:')
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        center = _LABEL_CENTERS.get(name)
        if center is None:
            print('  %-8s SKIP (no hand-verified centre)' % name)
            continue
        cx, cy = center
        rgb = np.asarray(Image.open(f).convert('RGB'), dtype=np.uint8)
        mask = _green_mask(rgb)
        mask[:, 640:] = False     # drop right-HUD green (minimap dots)
        mask[:300, :] = False     # drop the player-name band higher up
        bb = _word_bbox(mask, cx, cy)
        if bb is None:
            print('  %-8s no green word found' % name)
            continue
        x0, y0, w, h = bb
        fx, fy = _fire_point(cx, cy)
        print('  %-8s wordTL=(%d,%d) size=%dx%d ink=%d  fire=(%d,%d) '
              'fire-rel-to-TL=(%+d,%+d)'
              % (name, x0, y0, w, h, int(mask[y0:y0 + h, x0:x0 + w].sum()),
                 fx, fy, fx - x0, fy - y0))
        # Crop the FIXED glyph box from the consistent top-left.
        crop = mask[y0:y0 + GLYPH_H, x0:x0 + GLYPH_W]
        if crop.shape == (GLYPH_H, GLYPH_W):
            crops.append(crop.astype(np.uint8))

    if not crops:
        print('No usable crops -- aborting.')
        return

    # Per-pixel CONSENSUS: keep ink where the MAJORITY of references agree. This
    # drops one-off antialiasing flicker (one reference had a single extra lit
    # pixel) while keeping every stable stroke.
    stack = np.stack(crops, axis=0)            # (N, H, W)
    votes = stack.sum(axis=0)
    consensus = (votes * 2 >= len(crops)).astype(np.uint8)

    ink = int(consensus.sum())
    print('\nConsensus glyph: %dx%d, ink=%d px (from %d references)'
          % (GLYPH_W, GLYPH_H, ink, len(crops)))

    mask_img = Image.fromarray((consensus * 255).astype(np.uint8), 'L').convert('1')
    gray_img = Image.fromarray((consensus * 255).astype(np.uint8), 'L')
    mask_path = os.path.join(_OUT_DIR, 'lagerfeuer_mask.png')
    gray_path = os.path.join(_OUT_DIR, 'lagerfeuer_gray.png')
    mask_img.save(mask_path)
    gray_img.save(gray_path)
    print('wrote %s' % mask_path)
    print('wrote %s' % gray_path)

    print('\nConstants for inventory_campfire (pin these in the module/tests):')
    print('  LABEL_GLYPH_SIZE = (%d, %d)' % (GLYPH_W, GLYPH_H))
    print('  FIRE_OFFSET_FROM_LABEL_TL = (20, 21)')


if __name__ == '__main__':
    main()
