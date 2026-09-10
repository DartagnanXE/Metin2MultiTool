# -*- coding: utf-8 -*-
"""Alle gueltigen Kombinationen des 24-Karten-Decks, einmal vorberechnet.

Karten werden als Zahl 0..23 dargestellt: ``id = (wert-1)*3 + farbe``, Feld und
Deck als 24-Bit-Maske. Damit wird aus "welche Kombination liegt im Feld?" ein
paar Bit-Operationen statt zehn Listen-Vergleiche -- der entscheidende Hebel,
weil die Dynamische Programmierung diese Frage millionenfach stellt.

Es gibt GENAU 170 gueltige Kombinationen:
    8 Drillinge (je Wert 1..8, zwingend dreifarbig)
  + 18 farbreine Reihen (6 Startwerte x 3 Farben)
  + 144 gemischte Reihen (6 Startwerte x 27 Farbmuster - 3 farbreine)
Das ist die vollstaendige Zugmenge des Spiels -- mehr kann nie auftreten.
"""

from .engine import COLORS, VALUES, combo_points

_NUM_COLORS = len(COLORS)


def card_id(value, color):
    """``(wert, farbe)`` -> Karten-Id 0..23."""
    return (value - 1) * _NUM_COLORS + COLORS.index(color)


def card_of(cid):
    """Karten-Id -> ``(wert, farbe)``."""
    return (cid // _NUM_COLORS + 1, COLORS[cid % _NUM_COLORS])


def card_name(cid):
    """Karten-Id -> kurze Anzeige, z.B. ``'7R'``."""
    v, c = card_of(cid)
    return '%d%s' % (v, c)


def _build_combos():
    """Alle gueltigen 3er-Kombinationen als ``(maske, punkte, (ids...))``."""
    out = []
    for a in range(24):
        for b in range(a + 1, 24):
            for c in range(b + 1, 24):
                karten = [card_of(a), card_of(b), card_of(c)]
                p = combo_points(karten)
                if p:
                    out.append(((1 << a) | (1 << b) | (1 << c), p, (a, b, c)))
    out.sort(key=lambda t: -t[1])
    return tuple(out)


#: Alle 170 Kombinationen, absteigend nach Punkten.
ALL_COMBOS = _build_combos()

#: Je Karte die Kombinationen, an denen sie beteiligt ist (fuer Heuristiken).
COMBOS_BY_CARD = tuple(
    tuple(k for k in ALL_COMBOS if k[0] & (1 << cid)) for cid in range(24))

_playable_cache = {}

#: Obergrenze des Zwischenspeichers. Er ist fuer FELD-Masken gedacht (hoechstens
#: 5 Karten, also 55.455 moegliche) -- die wiederholen sich staendig und der
#: Speicher zahlt sich aus. Ruft jemand die Funktion mit grossen Masken auf,
#: waechst er dagegen unbegrenzt: genau das ist am 2026-09-08 passiert
#: (``card_potential`` fragte mit Feld+Restdeck ab), 1,4 Mio. Eintraege nach 300
#: Partien, 514 MB, danach Absturz des Interpreters. Die Grenze ist das
#: Sicherheitsnetz dagegen; die eigentliche Ursache ist behoben.
PLAYABLE_CACHE_MAX = 200_000


def playable(field_mask):
    """Die im Feld spielbaren Kombinationen -> ``((maske, punkte, ids), ...)``.

    Absteigend nach Punkten, gecacht (dieselben Felder treten in der Suche sehr
    oft auf). Der Speicher wird geleert, wenn er :data:`PLAYABLE_CACHE_MAX`
    ueberschreitet -- lieber neu rechnen als unbegrenzt wachsen.
    """
    hit = _playable_cache.get(field_mask)
    if hit is None:
        hit = tuple(k for k in ALL_COMBOS if k[0] & field_mask == k[0])
        if len(_playable_cache) >= PLAYABLE_CACHE_MAX:
            _playable_cache.clear()
        _playable_cache[field_mask] = hit
    return hit


def best_points(field_mask):
    """Punkte der besten spielbaren Kombination (0 = keine)."""
    p = playable(field_mask)
    return p[0][1] if p else 0


def mask_of(cids):
    """Karten-Ids -> Bitmaske."""
    m = 0
    for c in cids:
        m |= 1 << c
    return m


def ids_of(mask):
    """Bitmaske -> Tupel der Karten-Ids (aufsteigend)."""
    return tuple(i for i in range(24) if mask & (1 << i))


def popcount(mask):
    return bin(mask).count('1')
