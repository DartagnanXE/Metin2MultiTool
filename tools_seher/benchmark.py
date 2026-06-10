#!/usr/bin/env python3
"""Benchmark der Erkennungsmethoden fuer den Seherwettstreit.

Vergleicht pro Teilproblem mehrere Kandidaten unter Stoerungen
(Helligkeit +-15 %, Gauss-Rauschen sigma=6, Anker-Jitter +-2 px) auf den
beiden realen Fixtures (Fenster an ZWEI verschiedenen Positionen):

1. FENSTER-ANKER:   Titel-Template-NCC (Peak-Staerke + Peak-Separation)
2. KREUZ-ERKENNUNG: (A) Rote-Pixel-Zaehlung  (B) Kreuz-Template-NCC
                    (C) Slot-Helligkeitsabfall
3. RUNDEN-RESULTAT: Score-Box-Bilddiff (statt OCR; fuer OCR fehlen
                    Glyphen dieser Schrift -- Diff braucht keine)

Ground Truth: seher_start.png = 0 Kreuze; seher_round1.png = eigenes
Kreuz auf Karte 0 + Kreuz auf weissem Gegner-Back Slot 0, Score 1:0.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seher import detect, geometry as G  # noqa: E402

FIX = os.path.join(ROOT, 'tests', 'fixtures')
rng = np.random.default_rng(7)


def load(name):
    rgb = np.asarray(Image.open(os.path.join(FIX, name)).convert('RGB'))
    return rgb[:, :, ::-1].copy()


def perturbations(bgr):
    """Original + Helligkeit +-15 % + Rauschen sigma=6."""
    out = [('orig', bgr)]
    for f, tag in ((0.85, 'dunkel-15%'), (1.15, 'hell+15%')):
        out.append((tag, np.clip(bgr.astype(np.float32) * f, 0, 255)
                    .astype(np.uint8)))
    noise = rng.normal(0, 6, bgr.shape)
    out.append(('rauschen-s6', np.clip(bgr.astype(np.float32) + noise, 0, 255)
                .astype(np.uint8)))
    return out


def bench_anchor():
    print('== 1. FENSTER-ANKER (Titel-Template, NCC) ==')
    tpl = detect.title_template()
    worst_peak, worst_sep = 1.0, 1.0
    for name in ('seher_start.png', 'seher_round1.png'):
        for tag, img in perturbations(load(name)):
            res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _ml, loc = cv2.minMaxLoc(res)
            # Peak-Separation: bester Treffer ausserhalb 20px um den Peak
            masked = res.copy()
            y0 = max(0, loc[1] - 20)
            x0 = max(0, loc[0] - 20)
            masked[y0:loc[1] + 20, x0:loc[0] + 20] = -1
            second = float(masked.max())
            worst_peak = min(worst_peak, mx)
            worst_sep = min(worst_sep, mx - second)
            print(f'  {name:22s} {tag:12s} peak={mx:.4f} '
                  f'zweitbester={second:.4f} sep={mx - second:.4f}')
    print(f'  -> schlechtester Peak {worst_peak:.4f}, '
          f'schlechteste Separation {worst_sep:.4f} '
          f'(Schwelle {G.ANCHOR_NCC_MIN})\n')


def all_slot_samples():
    """(bild, anker, slot, ist_kreuz) fuer alle 36 Slots beider Fixtures."""
    samples = []
    for name, truths in (
            ('seher_start.png', set()),
            ('seher_round1.png', {('my', 0), ('opp_white', 0)})):
        base = load(name)
        ok, anchor, _ = detect.find_anchor(base)
        assert ok
        for tag, img in perturbations(base):
            for v in range(9):
                samples.append((tag, img, anchor, G.slot_of_value(v),
                                ('my', v) in truths))
            for k, s in enumerate(G.OPP_BLACK_SLOTS):
                samples.append((tag, img, anchor, s,
                                ('opp_black', k) in truths))
            for k, s in enumerate(G.OPP_WHITE_SLOTS):
                samples.append((tag, img, anchor, s,
                                ('opp_white', k) in truths))
    return samples


def bench_cross():
    print('== 2. KREUZ-ERKENNUNG (A rote Pixel / B Template-NCC / '
          'C Helligkeit) ==')
    cross_tpl = cv2.imread(os.path.join(ROOT, 'seher', 'templates',
                                        'cross.png'), cv2.IMREAD_COLOR)
    jitters = [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (2, 2)]
    scores = {'A': {'pos': [], 'neg': []}, 'B': {'pos': [], 'neg': []},
              'C': {'pos': [], 'neg': []}}
    for tag, img, anchor, slot, truth in all_slot_samples():
        for jx, jy in jitters:
            x = anchor[0] + slot[0] + jx
            y = anchor[1] + slot[1] + jy
            roi = img[y:y + G.CARD_H, x:x + G.CARD_W]
            a = detect.red_count(roi)
            ok_b, b, _ = (cv2.matchTemplate(roi, cross_tpl,
                                            cv2.TM_CCOEFF_NORMED), 0, 0) \
                if False else (None, 0, 0)
            # B: NCC des Kreuz-Templates im leicht groesseren Umfeld
            pad = img[y - 4:y + G.CARD_H + 4, x - 4:x + G.CARD_W + 4]
            try:
                res = cv2.matchTemplate(pad, cross_tpl, cv2.TM_CCOEFF_NORMED)
                b = float(res.max())
            except Exception:
                b = 0.0
            c = 255 - float(roi.astype(np.float32).mean())
            key = 'pos' if truth else 'neg'
            scores['A'][key].append(a)
            scores['B'][key].append(b)
            scores['C'][key].append(c)
    for m, desc in (('A', 'rote Pixel (Schwelle 80)'),
                    ('B', 'Kreuz-Template-NCC'),
                    ('C', 'Slot-Dunkelheit (255-mean)')):
        pos, neg = scores[m]['pos'], scores[m]['neg']
        sep = min(pos) - max(neg)
        print(f'  Methode {m} ({desc}): pos min={min(pos):.3f} '
              f'max={max(pos):.3f} | neg min={min(neg):.3f} '
              f'max={max(neg):.3f} | TRENNUNG={sep:.3f} '
              f'{"OK" if sep > 0 else "VERSAGT"}')
    print()


def bench_score():
    print('== 3. RUNDEN-RESULTAT (Score-Box-Bilddiff statt OCR) ==')
    start = load('seher_start.png')
    round1 = load('seher_round1.png')
    _ok, a0, _ = detect.find_anchor(start)
    _ok, a1, _ = detect.find_anchor(round1)
    # Positiv: Gegner-Score 0 -> 1 (muss als Aenderung feuern)
    c_start = detect.score_crop(start, a0, 'opp')
    c_round = detect.score_crop(round1, a1, 'opp')
    pos = detect.crops_differ(c_start, c_round)
    # Negativ: gleiche Box, nur Rauschen/Helligkeit (darf NICHT feuern)
    negs = []
    for tag, img in perturbations(start)[1:]:
        _ok2, a2, _ = detect.find_anchor(img)
        negs.append(detect.crops_differ(c_start,
                                        detect.score_crop(img, a2, 'opp')))
    # Eigener Score 0 -> 0 zwischen den Fixtures (darf NICHT feuern)
    same = detect.crops_differ(detect.score_crop(start, a0, 'me'),
                               detect.score_crop(round1, a1, 'me'))
    print(f'  0->1 erkannt: {pos} (soll True) | '
          f'Stoerungen feuern: {negs} (soll alle False) | '
          f'0->0 zwischen Fixtures: {same} (soll False)')
    print('  OCR-Alternative: fuer diese Schrift existiert kein Glyphensatz '
          '(nur 0/1 in den Fixtures) -> Diff braucht keinen und erkennt '
          'jede Aenderung 0-9.\n')


if __name__ == '__main__':
    bench_anchor()
    bench_cross()
    bench_score()
