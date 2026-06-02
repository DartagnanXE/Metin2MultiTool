# -*- coding: utf-8 -*-
"""Generate the bundled stack-number digit templates -> ``inventory_digits/``.

The highest-trust templates are REAL glyphs extracted from calibration
screenshots whose stack numbers are KNOWN. ``einsbis20GRO.png`` /
``einsbis20KLEIN.png`` are purpose-made: their inventory rows 5..8 hold the
counts 1..20 (slot 26=1 .. slot 45=20) and row 0 cols 1..4 hold 200 baits, in
the game's LARGE and SMALL stack fonts at the SAME positions. From them we
extract every digit 0-9 in both fonts -- the synthetic Consolas fallback alone
mis-reads 4/7/8/9 (its shapes do not match the in-game bitmap font), which is
exactly why real glyphs are needed.

A small SYNTHETIC set (Consolas) is still emitted as a last-resort fallback for
a font we have never seen; the matcher takes the BEST template per digit, so the
real glyphs win wherever they apply and the reader's confidence gate flags the
rest.

Run (from repo root)::

    py.exe tools/gen_digit_templates.py
"""
import os

import numpy as np
from PIL import Image, ImageFont, ImageDraw

CANON_H = 16
WHITE_MIN = 150
PITCH = 32
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'inventory_digits')
_SRC = r'C:\Users\leonl\Downloads\testordner'

# Real calibration shots: (path, origin_x, origin_y, font-tag). Both auto-align
# to (629, 243) on a 32px pitch.
REAL_SHOTS = [
    (os.path.join(_SRC, 'einsbis20GRO.png'), 629, 243, 'gro'),
    (os.path.join(_SRC, 'einsbis20KLEIN.png'), 629, 243, 'klein'),
]

# Known slot -> value map shared by both shots: rows 5..8 = 1..20, row0 c1..4=200.
KNOWN = {(r, c): r_base + c + 1
         for r, r_base in zip(range(5, 9), (0, 5, 10, 15))
         for c in range(5)}
KNOWN.update({(0, 1): 200, (0, 2): 200, (0, 3): 200, (0, 4): 200})

SYNTH_FONTS = [('consola', r'C:\Windows\Fonts\consola.ttf')]


def load_rgb(p):
    return np.asarray(Image.open(p).convert('RGB'))


def band_graywhite(img, ox, oy, r, c):
    x0 = ox + c * PITCH
    y0 = oy + r * PITCH
    band = img[y0 + 13:y0 + 32, x0:x0 + 32, :].astype(np.int32)
    mn = band.min(axis=2)
    return np.clip((mn - WHITE_MIN) / (255.0 - WHITE_MIN), 0, 1)


def ink_bbox(mask, thr=0.25):
    ys, xs = np.where(mask > thr)
    if len(xs) == 0:
        return None
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1


def norm_cell(mask):
    bb = ink_bbox(mask)
    if bb is None:
        return None
    x0, x1, y0, y1 = bb
    crop = mask[y0:y1, x0:x1]
    new_w = max(2, int(round(crop.shape[1] * CANON_H / max(1, crop.shape[0]))))
    im = Image.fromarray((crop * 255).astype(np.uint8)).resize(
        (new_w, CANON_H), Image.BILINEAR)
    return np.asarray(im, dtype=np.uint8)


def save(mask_u8, digit, tag, seen):
    if mask_u8 is None:
        return
    idx = seen.get((digit, tag), 0)
    seen[(digit, tag)] = idx + 1
    suffix = tag if idx == 0 else '%s%d' % (tag, idx)
    Image.fromarray(mask_u8, mode='L').save(
        os.path.join(OUT_DIR, '%s__%s.png' % (digit, suffix)))


def extract_real(path, ox, oy, tag, seen):
    img = load_rgb(path)
    for (r, c), val in sorted(KNOWN.items()):
        mask = band_graywhite(img, ox, oy, r, c)
        bb = ink_bbox(mask)
        if bb is None:
            continue
        x0, x1, _, _ = bb
        s = str(val)
        cw = (x1 - x0) / len(s)
        for i, ch in enumerate(s):
            cs = int(round(x0 + i * cw)); ce = int(round(x0 + (i + 1) * cw))
            save(norm_cell(mask[:, cs:ce]), ch, 'real_' + tag, seen)


def render_digit_mask(d, fontpath, size=64):
    font = ImageFont.truetype(fontpath, size)
    canvas = Image.new('L', (size * 2, size * 3), 0)
    ImageDraw.Draw(canvas).text((size, size), str(d), fill=255, font=font)
    return norm_cell(np.asarray(canvas, dtype=np.float32) / 255.0)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for f in os.listdir(OUT_DIR):
        if f.endswith('.png'):
            os.remove(os.path.join(OUT_DIR, f))
    seen = {}
    for path, ox, oy, tag in REAL_SHOTS:
        if os.path.exists(path):
            extract_real(path, ox, oy, tag, seen)
        else:
            print('skip (missing):', path)
    for tag, fp in SYNTH_FONTS:
        if os.path.exists(fp):
            for d in range(10):
                save(render_digit_mask(d, fp), str(d), tag, seen)
    by_digit = {}
    for f in os.listdir(OUT_DIR):
        if f.endswith('.png'):
            by_digit[f[0]] = by_digit.get(f[0], 0) + 1
    print('wrote %d templates' % sum(by_digit.values()))
    print('per digit:', {k: by_digit[k] for k in sorted(by_digit)})


if __name__ == '__main__':
    main()
