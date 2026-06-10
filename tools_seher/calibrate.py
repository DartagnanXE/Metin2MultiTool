#!/usr/bin/env python3
"""Kalibrierung der Seherwettstreit-Erkennung aus den 800x600-Fixtures.

Leitet die komplette Fenster-Geometrie aus zwei realen Screenshots ab
(tests/fixtures/seher_start.png = frisches Spiel, seher_round1.png = nach
einer Runde, Fenster um (+55,+78) verschoben). Extrahiert die Templates
(Titelzeile als Anker, rotes Kreuz) nach seher/templates/ und druckt den
GEOMETRY-Block fuer seher/geometry.py. Verifiziert alles auf BEIDEN
Fixtures (das Fenster wandert -> alles muss anker-relativ stimmen).
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, 'tests', 'fixtures')
TPL = os.path.join(ROOT, 'seher', 'templates')


def load(name):
    """Fixture als BGR-Array (wie WindowCapture.get_screenshot())."""
    rgb = np.asarray(Image.open(os.path.join(FIX, name)).convert('RGB'))
    return rgb[:, :, ::-1].copy()


def white_row_origin(bgr, row_count):
    """Findet die linkeste helle Karte einer Reihe mit `row_count` Karten."""
    from scipy import ndimage
    gray = bgr.astype(int).mean(axis=2)
    lab, _n = ndimage.label(gray > 170)
    blobs = []
    for sl in ndimage.find_objects(lab):
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if 34 < w < 46 and 42 < h < 56:
            blobs.append((sl[1].start, sl[0].start))
    rows = {}
    for x, y in blobs:
        rows.setdefault(y // 8, []).append((x, y))
    for group in rows.values():
        if len(group) == row_count:
            group.sort()
            return group[0]
    raise SystemExit(f'weisse Reihe mit {row_count} Karten nicht gefunden')


def main():
    os.makedirs(TPL, exist_ok=True)
    start = load('seher_start.png')
    round1 = load('seher_round1.png')

    # --- Referenzpunkte: weisse Gegner-Rueckseiten (4) + eigene weisse (4)
    wb_s = white_row_origin(start, 4)      # weisse backs im Start-Fixture
    print('weisse Backs start:', wb_s)
    # round1 hat ein Kreuz auf einem weissen Back -> Reihe evtl. nur 3 helle
    # Karten; eigene weisse Reihe (1,3,5,7) ist in beiden vollstaendig hell.

    # Eigene weisse Reihe (4 Karten) liegt ~119px unter den weissen Backs.
    # Wir nehmen sie als zweiten Referenzpunkt zur Verifikation.

    # --- Titel-Template aus dem Start-Fixture schneiden -----------------
    # Titeltext liegt (gemessen) bei dy=-79 ueber den weissen Backs,
    # dx +104..+170 relativ zur linken Back-Kante.
    tx0 = wb_s[0] + 96
    ty0 = wb_s[1] - 87
    title = start[ty0:ty0 + 18, tx0:tx0 + 152]
    cv2.imwrite(os.path.join(TPL, 'title.png'), title)

    # --- Anker-Match auf beiden Fixtures ---------------------------------
    anchors = {}
    for name, img in (('start', start), ('round1', round1)):
        res = cv2.matchTemplate(img, title, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, loc = cv2.minMaxLoc(res)
        anchors[name] = loc
        print(f'Anker {name}: pos={loc} ncc={mx:.4f}')
    ax, ay = anchors['start']
    shift = (anchors['round1'][0] - ax, anchors['round1'][1] - ay)
    print('Fenster-Verschiebung round1-start:', shift, '(erwartet ~(55,78))')

    # --- Schwarze Reihen praezise via Spaltenprofil ----------------------
    def row_x0(img, y_band, expect_n, anchor):
        """Linke Kante der ersten Karte einer Reihe (Ornament-Kanten >110)."""
        band = img.astype(int).mean(axis=2)[y_band[0]:y_band[1], :]
        cols = (band > 110).sum(axis=0)
        xs = np.where(cols > 6)[0]
        return int(xs.min())

    # Bands relativ zum Anker (aus den Messungen): schwarze Backs dy +24..+74,
    # eigene schwarze Karten dy +249..+299 (verifizieren wir gleich).
    for name, img in (('start', start), ('round1', round1)):
        a = anchors[name]
        bb_x0 = row_x0(img, (a[1] + 26, a[1] + 72), 5, a)
        mb_x0 = row_x0(img, (a[1] + 251, a[1] + 297), 5, a)
        print(f'{name}: schwarze Backs x0={bb_x0} (rel {bb_x0 - a[0]}), '
              f'eigene schwarze x0={mb_x0} (rel {mb_x0 - a[0]})')

    # --- Rotes Kreuz finden + Template schneiden (round1) ----------------
    b = round1.astype(int)
    red = ((b[:, :, 2] > 140) & (b[:, :, 1] < 90) & (b[:, :, 0] < 90))
    from scipy import ndimage
    lab, _n = ndimage.label(red)
    for sl in ndimage.find_objects(lab):
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if w > 20 and h > 20:
            a = anchors['round1']
            print(f'Kreuz: x={sl[1].start} y={sl[0].start} w={w} h={h} '
                  f'(rel zum Anker: {sl[1].start - a[0]},{sl[0].start - a[1]}) '
                  f'rote Pixel={int(red[sl].sum())}')
            cy, cx = sl[0].start, sl[1].start
            cross = round1[cy:cy + h, cx:cx + w]
    cv2.imwrite(os.path.join(TPL, 'cross.png'), cross)

    # --- Score-Boxen: dunkle Boxen im rechten Panel -----------------------
    # Panel rechts vom Spielfeld; Digits hell auf fast-schwarz. Wir suchen die
    # hellen Ziffern-Cluster im Bereich rechts der Karten.
    for name, img in (('start', start), ('round1', round1)):
        a = anchors[name]
        gray = img.astype(int).mean(axis=2)
        region = gray[a[1]:a[1] + 320, a[0] + 130:a[0] + 260]
        dark = (region < 30).astype(np.uint8)
        # Boxen = breite zusammenhaengende dunkle Bloecke
        rowsum = dark.sum(axis=1)
        bands = []
        in_band = None
        for y, v in enumerate(rowsum):
            if v > 80 and in_band is None:
                in_band = y
            elif v <= 80 and in_band is not None:
                if y - in_band > 18:
                    bands.append((in_band, y))
                in_band = None
        print(f'{name}: dunkle Score-Baender (rel zum Anker, x+130..+260):',
              bands)


if __name__ == '__main__':
    sys.exit(main())
