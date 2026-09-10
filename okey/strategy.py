# -*- coding: utf-8 -*-
"""Die EINE Schnittstelle, die der Bot benutzt.

Alles andere in diesem Paket ist Analyse-Werkzeug: Loeser, Messstaende,
Vergleiche. Hier steht nur, was im Spiel gebraucht wird -- welchen Zug man in
einer Stellung machen soll.

Die Stellung wird als Karten beschrieben, nicht als Bitmaske, damit die
Bilderkennung spaeter direkt ihr Ergebnis einreichen kann:

    zug = naechster_zug(feld=[(7,'R'), (4,'G'), (3,'B'), (6,'R'), (1,'B')],
                        verbraucht=[(2,'R'), (8,'G')])
    if zug.art == 'spielen':
        # zug.karten anklicken, dann bestaetigen
    else:
        # zug.karten[0] mit Rechtsklick wegwerfen

Der Rest-Deck-Inhalt wird NICHT uebergeben -- er ergibt sich aus
"alle 24 Karten minus Feld minus verbraucht". Genau das ist der Grund, warum
diese Strategie ueberhaupt so stark spielt: sie zaehlt mit.
"""

from collections import namedtuple

from .combos import card_id, card_of, mask_of, popcount
from .engine import FULL_DECK
from .solver import make_base_smart, pimc_action, rollout_action, smart_action

VOLL_MASKE = (1 << 24) - 1

#: Die vier ausgelieferten Spielstaerken, von stark nach schnell. Die
#: gemessenen Zahlen stehen in :data:`STUFEN_TABELLE` -- dort und nur dort,
#: damit die Oberflaeche keine zweite, abweichende Wahrheit erzaehlt.
STAERKEN = ('beste', 'stark', 'schnell', 'sofort')

#: Voreinstellung. Auf Wunsch des Nutzers (2026-09-08) die staerkste Variante:
#: Okey hat kein Zeitlimit, und 0,42 s Bedenkzeit je Klick faellt im Spiel nicht
#: auf -- eine ganze Partie kostet damit rund 5 s.
STANDARD_STAERKE = 'beste'

Zug = namedtuple('Zug', 'art karten punkte begruendung')


class StellungsFehler(ValueError):
    """Die uebergebene Stellung ist unmoeglich (doppelte oder unbekannte Karte)."""


def _pruefe(feld, verbraucht):
    """Stellung auf Plausibilitaet pruefen -> ``(feld_maske, deck_maske)``.

    Lieber hier hart scheitern als im Spiel einen Unsinns-Klick senden: eine
    doppelt erkannte Karte ist das typische Symptom einer verrutschten
    Bilderkennung, und sie wuerde die Kartenzaehlung still verfaelschen.
    """
    alle = list(feld) + list(verbraucht)
    for karte in alle:
        if tuple(karte) not in FULL_DECK:
            raise StellungsFehler('unbekannte Karte: %r' % (karte,))
    ids = [card_id(*k) for k in alle]
    if len(set(ids)) != len(ids):
        doppelt = sorted({i for i in ids if ids.count(i) > 1})
        raise StellungsFehler(
            'Karte doppelt gesehen: %s -- Bilderkennung pruefen'
            % ', '.join('%d%s' % card_of(i) for i in doppelt))
    if len(feld) > 5:
        raise StellungsFehler('mehr als 5 Feldkarten: %d' % len(feld))
    feld_maske = mask_of(card_id(*k) for k in feld)
    verbraucht_maske = mask_of(card_id(*k) for k in verbraucht)
    deck_maske = VOLL_MASKE & ~feld_maske & ~verbraucht_maske
    return feld_maske, deck_maske


def naechster_zug(feld, verbraucht=(), staerke=STANDARD_STAERKE, rng=None):
    """Der empfohlene Zug in dieser Stellung.

    :param feld: die 5 offenen Karten als ``[(wert, farbe), ...]``,
        Farbe ``'R'``/``'B'``/``'G'``.
    :param verbraucht: alle Karten, die in dieser Partie schon gespielt oder
        weggeworfen wurden. Wird das weggelassen, spielt die Strategie ohne
        Kartenzaehlung und damit deutlich schwaecher.
    :param staerke: eine aus :data:`STAERKEN`.
    :return: :class:`Zug` mit ``art`` = ``'spielen'`` oder ``'wegwerfen'``,
        ``karten`` = die anzuklickenden Karten, ``punkte`` = die Punkte des
        Zuges (0 beim Wegwerfen).
    :raises StellungsFehler: bei einer unmoeglichen Stellung.
    """
    if staerke not in STAERKEN:
        raise ValueError('unbekannte Staerke: %r' % (staerke,))
    feld_maske, deck_maske = _pruefe(feld, verbraucht)
    deck_rest = popcount(deck_maske)

    if staerke == 'sofort':
        art, maske, punkte = smart_action(feld_maske, deck_maske, deck_rest)
        wie = 'Faustregel'
    elif staerke == 'stark':
        # Dieselbe Mechanik wie 'schnell', nur mit fuenfmal so vielen
        # Probepartien und einer breiteren Kandidatenliste. Fuellt die Luecke
        # zwischen 0,03 s und 0,42 s je Zug, die sonst zwischen den Stufen
        # klaffte.
        art, maske, punkte = rollout_action(
            feld_maske, deck_maske, make_base_smart(), rollouts=240, rng=rng,
            top_k=12)
        wie = '240 simulierte Partien je Zug'
    elif staerke == 'schnell':
        art, maske, punkte = rollout_action(
            feld_maske, deck_maske, make_base_smart(), rollouts=48, rng=rng,
            top_k=8)
        wie = '48 simulierte Partien je Zug'
    else:
        # top_k=12 statt 6: die Beschraenkung der Kandidatenliste war eine
        # Sparmassnahme, die hier nichts spart (gemessen 4,72 gegen 4,69 s je
        # Partie) und im Turnier vom 2026-09-08 nominal 2,9 Punkte kostete --
        # statistisch nicht gesichert, aber es gibt keinen Grund, gute Zuege
        # vorher auszusortieren.
        #
        # samples=16 und NICHT mehr: 32 Stichproben brachten bei doppelter
        # Rechenzeit +1,7 Punkte (95 %: -4,8 bis +8,1), also nichts. Das
        # Verfahren ist auskonvergiert -- seine Grenze ist die eingebaute
        # Verzerrung (siehe exact.py), nicht die Stichprobenzahl.
        art, maske, punkte = pimc_action(
            feld_maske, deck_maske, samples=16, rng=rng, top_k=12)
        wie = '16 durchgerechnete Kartenfolgen je Zug'

    karten = [card_of(i) for i in range(24) if maske & (1 << i)]
    return Zug(art=('spielen' if art == 'play' else 'wegwerfen'),
               karten=karten, punkte=punkte,
               begruendung='%s, %d Karten im Deck' % (wie, deck_rest))


def partie_spielen(zieh_stellung, klick, staerke=STANDARD_STAERKE, rng=None):
    """Eine ganze Partie treiben -- der Ablauf, den der Live-Runner braucht.

    :param zieh_stellung: ``() -> [(wert, farbe), ...]`` liefert die aktuell
        offenen Karten (aus der Bilderkennung).
    :param klick: ``(zug) -> None`` fuehrt den Zug im Spiel aus.
    :return: die Liste der gespielten Zuege.

    Die Buchfuehrung ueber verbrauchte Karten passiert hier, damit der Runner
    sie nicht selbst fuehren muss -- sie ist die Grundlage der Kartenzaehlung
    und wurde deshalb bewusst nicht dem Aufrufer ueberlassen.
    """
    verbraucht = []
    zuege = []
    while True:
        feld = list(zieh_stellung())
        if len(feld) < 3:
            return zuege
        zug = naechster_zug(feld, verbraucht, staerke=staerke, rng=rng)
        klick(zug)
        zuege.append(zug)
        verbraucht.extend(zug.karten)
        if len(verbraucht) >= 24:
            return zuege
