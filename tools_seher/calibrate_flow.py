#!/usr/bin/env python3
"""Kalibrierung des Start-/End-Flows (Eventuebersicht -> Spiel -> Belohnung).

Extrahiert die Flow-Templates aus den sauberen Fixtures und VERIFIZIERT
jedes sofort: Selbst-Match (NCC ~1.0), Match auf der Busy-Variante
(andere Fensterposition/ueberlappende Fenster) und False-Positive-Check
auf einem unverwandten Fixture. Druckt die Trefferkoordinaten.
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
    rgb = np.asarray(Image.open(os.path.join(FIX, name)).convert('RGB'))
    return rgb[:, :, ::-1].copy()


def match(img, tpl):
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _mn, mx, _ml, loc = cv2.minMaxLoc(res)
    return float(mx), loc


# (Template-Name, Quelle, (x, y, w, h), Busy-Fixture, Negativ-Fixture)
SPECS = [
    ('flow_event_title', 'seher_flow_overview_single.png', (405, 81, 84, 16),
     'seher_flow_overview_multi.png', 'seher_flow_info.png'),
    # Label MIT Plate-Rahmen (Text allein matcht auch Fenstertitel!)
    ('flow_seher_label', 'seher_flow_overview_single.png', (310, 135, 150, 22),
     'seher_flow_overview_multi.png', 'seher_flow_info.png'),
    ('flow_ansehen', 'seher_flow_overview_single.png', (500, 145, 65, 14),
     'seher_flow_overview_multi.png', 'seher_flow_info.png'),
    ('flow_start_btn', 'seher_flow_info.png', (370, 428, 65, 18),
     'seher_flow_info_busy.png', 'seher_flow_overview_single.png'),
    ('flow_ja_btn', 'seher_flow_confirm.png', (340, 305, 45, 17),
     'seher_flow_confirm_busy.png', 'seher_flow_info.png'),
    ('flow_reward_ok', 'seher_flow_reward.png', (372, 314, 62, 20),
     None, 'seher_flow_overview_single.png'),
    ('flow_menu_charwechsel', 'seher_flow_escmenu.png', (350, 316, 100, 15),
     None, 'seher_flow_overview_single.png'),
    ('flow_menu_beenden', 'seher_flow_escmenu.png', (360, 405, 80, 15),
     None, 'seher_flow_overview_single.png'),
]


def main():
    os.makedirs(TPL, exist_ok=True)
    ok_all = True
    for name, src, (x, y, w, h), busy, neg in SPECS:
        img = load(src)
        tpl = img[y:y + h, x:x + w]
        cv2.imwrite(os.path.join(TPL, name + '.png'), tpl)
        ncc_self, loc_self = match(img, tpl)
        line = f'{name:24s} self={ncc_self:.4f}@{loc_self}'
        if busy:
            ncc_b, loc_b = match(load(busy), tpl)
            line += f'  busy={ncc_b:.4f}@{loc_b}'
            if ncc_b < 0.88:
                ok_all = False
                line += '  <-- BUSY-MATCH SCHWACH'
        ncc_n, _ = match(load(neg), tpl)
        line += f'  negativ={ncc_n:.4f}'
        if ncc_n > 0.80:
            ok_all = False
            line += '  <-- FALSE-POSITIVE-RISIKO'
        print(line)

    # Zeilen-Logik: in der Multi-Uebersicht muss das zur Seher-Zeile
    # gehoerende "Ansehen" gefunden werden (3 Kandidaten!).
    multi = load('seher_flow_overview_multi.png')
    lab = cv2.imread(os.path.join(TPL, 'flow_seher_label.png'))
    ans = cv2.imread(os.path.join(TPL, 'flow_ansehen.png'))
    ncc_l, loc_l = match(multi, lab)
    res = cv2.matchTemplate(multi, ans, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= 0.85)
    rows = sorted(set(int(v) for v in ys))
    print(f'\nMulti-Uebersicht: Seher-Label @{loc_l} (ncc {ncc_l:.3f}); '
          f'Ansehen-Kandidaten-Zeilen: {rows}')
    same_row = [(int(x2), int(y2)) for y2, x2 in zip(ys, xs)
                if abs(int(y2) - loc_l[1]) <= 10]
    print(f'Ansehen in Seher-Zeile (+-10px): {same_row[:3]}')
    if not same_row:
        ok_all = False

    print('\nGESAMT:', 'OK' if ok_all else 'PROBLEME — Boxen nachjustieren')
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
