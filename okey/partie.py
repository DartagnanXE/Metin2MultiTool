# -*- coding: utf-8 -*-
"""Eine Okey-Partie zu Ende spielen -- der Ablauf, ohne Maus und Fenster.

Dieses Modul kennt kein pydirectinput und keinen Bildschirm. Es bekommt ein
:class:`Brett` gereicht (Bild holen, Karte klicken, Stapel klicken, schlafen)
und treibt damit die Partie. Genau diese Trennung macht den Ablauf ohne
laufendes Spiel pruefbar: die Tests reichen ein Papp-Brett herein.

DIE KARTENZAEHLUNG IST DIE EIGENE BUCHFUEHRUNG, NICHT DER BILDSCHIRM.
Jede der 24 Karten ist zu jedem Zeitpunkt an genau einer von drei Stellen:
verbraucht, offen auf dem Feld, oder noch im Stapel. Also gilt immer

    Stapel = 24 - verbraucht - offen

Das ist keine Schaetzung, sondern eine Identitaet -- und sie ist der Grund,
warum die Strategie so stark spielt (sie weiss, was noch kommen kann). Die
Zahl auf dem Bildschirm wird nur als GEGENPROBE gelesen: weicht sie ab, ist
etwas falsch erkannt worden, und der Ablauf haelt lieber an.

WAS BEI EINEM NICHT ANGENOMMENEN ZUG PASSIERT: Der Nutzer hat beschrieben,
dass falsch gewaehlte Dreier wieder nach oben zurueckwandern. Unsere Zuege
sind per Konstruktion gueltig (die Kombinationen kommen aus der geprueften
Tabelle). Wandern sie trotzdem zurueck, stimmt etwas Grundsaetzliches nicht --
Koordinaten, Erkennung, falsches Fenster. Dann wird abgebrochen statt weiter
zu klicken.
"""

from collections import namedtuple

from . import flow, vision
from .combos import card_id, mask_of, playable
from .strategy import StellungsFehler, naechster_zug

#: Reissleine. Eine Partie hat hoechstens 8 Kombinationen und 24 Karten;
#: mehr als 40 Zuege kann es selbst mit lauter Einzel-Wegwerfen nicht geben.
MAX_ZUEGE = 40

#: Wie oft ein einzelner Klick wiederholt wird, wenn er nicht ankam.
KLICK_VERSUCHE = 3

#: Wie oft ein unklares Feld neu gelesen wird (Animation laeuft noch).
LESE_VERSUCHE = 4

#: Wartezeiten (Sekunden). Klein gehalten -- die Zuege sollen fluessig wirken.
NACH_KLICK_S = 0.18
NACH_STAPEL_S = 0.25
NACH_KOMBI_S = 0.55         # die Abrechnung der Dreiergruppe animiert

Bericht = namedtuple('Bericht',
                     'status punkte kombis zuege weggeworfen schritt '
                     'bildschirm_punkte')


class Brett(object):
    """Was der Ablauf vom Spiel braucht. Die Live-Fassung steht im Runner."""

    def bild(self):                       # pragma: no cover - Schnittstelle
        raise NotImplementedError

    def klick_karte(self, index, rechts=False):   # pragma: no cover
        raise NotImplementedError

    def klick_stapel(self):               # pragma: no cover
        raise NotImplementedError

    def schlafen(self, sekunden):         # pragma: no cover
        raise NotImplementedError

    def abbruch(self):                    # pragma: no cover
        return False

    def melde(self, was, **werte):        # pragma: no cover
        """Debug-Spur. Der Runner haengt hier das Log ein."""


def _offen(feld):
    """Die erkannten Karten mit ihrem Platz -> ``[(index, (wert, farbe))]``."""
    return [(i, k) for i, k in enumerate(feld) if isinstance(k, tuple)]


def _feld_lesen(brett):
    """Das Feld lesen, bis es eindeutig ist -> ``(feld, guete_ok)``.

    Ein ``'?'`` heisst "Platz belegt, aber nicht lesbar" -- typisch waehrend
    einer Animation. Dann lieber ein paar Millisekunden warten und noch einmal
    hinsehen, statt auf eine geratene Karte zu klicken.
    """
    feld = ['?'] * 5
    for versuch in range(LESE_VERSUCHE):
        img = brett.bild()
        if img is None:
            return (feld, False)
        feld = vision.read_field(img)
        if '?' not in feld:
            return (feld, True)
        brett.melde('feld-unklar', versuch=versuch + 1,
                    diag=vision.field_diag(img))
        brett.schlafen(NACH_KLICK_S)
    return (feld, False)


def _nachziehen(brett, verbraucht):
    """Leere Plaetze aus dem Stapel auffuellen -> das gelesene Feld.

    Der Stapelvorrat kommt aus der Buchfuehrung (siehe Modulkopf), nicht vom
    Bildschirm. Die Bildschirmzahl wird nur zur Kontrolle danebengelegt.
    """
    # Acht Durchgaenge, und die Zahl ist nicht beliebig: Beim ERSTEN Zug einer
    # Partie liegen alle fuenf Plaetze verdeckt (Bild 19 des Nutzers zeigt fuenf
    # Rueckseiten und "X 24"). Deckt der Stapel je Klick nur EINE Karte auf,
    # braucht es fuenf Klicks plus einen Durchgang, der das Ergebnis bestaetigt.
    # Sechs waere damit exakt aufgebraucht -- ein einziger verschluckter Klick
    # und die Partie liefe mit vier Karten weiter. Acht laesst Luft.
    for _ in range(8):
        if brett.abbruch():
            break
        feld, ok = _feld_lesen(brett)
        if not ok:
            return feld
        belegt = len(_offen(feld))
        rest = 24 - len(verbraucht) - belegt
        if belegt >= 5 or rest <= 0:
            return feld
        brett.melde('nachziehen', belegt=belegt, stapel_rest=rest)
        brett.klick_stapel()
        brett.schlafen(NACH_STAPEL_S)
    return _feld_lesen(brett)[0]


def _karte_klicken(brett, karte, rechts=False):
    """Eine bestimmte KARTE anklicken -> ``'ok'``/``'abbruch'``/``'unlesbar'``/
    ``'abgelehnt'``.

    Der GRUND und nicht nur ja/nein: ein verdecktes Fenster ist etwas anderes
    als ein Klick, den das Spiel nicht annimmt. Frueher liefen beide unter
    "Zug abgelehnt", und der Reiter zeigte dem Nutzer bei einem verdeckten
    Fenster die falsche Ursache an.

    Der Platz wird ueber die Identitaet der Karte bestimmt, nicht gemerkt.

    Vor jedem Klick wird neu gelesen und der Platz frisch bestimmt. Das kostet
    eine Aufnahme und macht den Ablauf unempfindlich dagegen, dass die
    verbliebenen Karten nach einem Klick nachruecken -- ob sie das tun, ist
    aus den Bildern des Nutzers nicht ableitbar, und ein gemerkter Platz waere
    dann der falsche.
    """
    unlesbar = False
    for versuch in range(KLICK_VERSUCHE):
        if brett.abbruch():
            return 'abbruch'
        feld, lesbar = _feld_lesen(brett)
        if not lesbar:
            # UNLESBAR heisst NICHT "die Karte ist weg". Eine ausgefallene
            # Aufnahme (verdecktes oder minimiertes Fenster) liefert fuenfmal
            # '?', und die Karte waere dann "nicht gefunden" -- der Ablauf
            # buchte sie als verbraucht, obwohl sie noch oben liegt. Genau das
            # bricht die Identitaet "Stapel = 24 - verbraucht - offen". Also
            # noch einmal hinsehen statt Erfolg zu melden.
            brett.melde('feld-unlesbar-beim-klick', karte='%d%s' % karte,
                        versuch=versuch + 1)
            unlesbar = True
            brett.schlafen(NACH_KLICK_S)
            continue
        plaetze = [i for i, k in _offen(feld) if k == karte]
        if not plaetze:
            # Die Karte liegt nicht (mehr) oben. Beim zweiten Durchgang ist
            # das der Beweis, dass der Klick angekommen ist. Schon beim ersten
            # zaehlt es als erledigt -- das ZIEL ist erreicht, und die
            # Gegenprobe nach der Kombination faengt einen echten Fehler
            # ohnehin ab. Frueher gab dieser Fall "abgelehnt" zurueck und
            # haette eine Partie wegen eines Wimpernschlags Timing beendet.
            if versuch == 0:
                brett.melde('karte-schon-weg', karte='%d%s' % karte)
            return 'ok'
        brett.klick_karte(plaetze[0], rechts=rechts)
        brett.melde('klick', karte='%d%s' % karte, platz=plaetze[0] + 1,
                    rechts=rechts, versuch=versuch + 1)
        brett.schlafen(NACH_KLICK_S)
        feld, lesbar = _feld_lesen(brett)
        if not lesbar:
            unlesbar = True
        elif karte not in [k for _i, k in _offen(feld)]:
            return 'ok'
    return 'unlesbar' if unlesbar else 'abgelehnt'


def _nichts_mehr_zu_holen(karten, verbraucht):
    """Stapel leer UND keine Kombination mehr moeglich -> die Partie ist aus.

    Ohne diese Pruefung wuerde die Strategie am Rundenende weiter "wegwerfen"
    empfehlen -- das ist rechnerisch nicht falsch (verlieren kann man nichts),
    im Spiel aber sinnlos: nachgezogen wird nichts mehr. Schlimmer noch: sollte
    der Client das Entfernen bei leerem Stapel gar nicht annehmen, meldete der
    Ablauf am Ende JEDER Partie einen "abgelehnten Zug" -- ein Fehler, der
    keiner ist. Also lieber sauber aufhoeren und "Beenden" druecken.
    """
    if 24 - len(verbraucht) - len(karten) > 0:
        return False
    return not playable(mask_of(card_id(*k) for k in karten))


def _truhe(punkte):
    """Welche Truhe gibt es fuer diese Punktzahl? (Wiki-Regel)"""
    if punkte >= 400:
        return 'gold'
    if punkte >= 300:
        return 'silber'
    return 'bronze'


def spielen(brett, staerke='beste', rng=None):
    """Eine Partie zu Ende spielen -> :class:`Bericht`.

    ``status`` ist einer von: ``'fertig'`` (nichts mehr spielbar),
    ``'abbruch'`` (Not-Aus), ``'brett-weg'`` (Fenster verschwunden),
    ``'unlesbar'``, ``'zug-abgelehnt'``, ``'stellungsfehler'``.
    """
    verbraucht = []
    punkte = kombis = zuege = weggeworfen = 0
    status, schritt = 'fertig', ''

    for _ in range(MAX_ZUEGE):
        if brett.abbruch():
            status, schritt = 'abbruch', 'vor-zug'
            break
        img = brett.bild()
        if img is None or not flow.brett_laeuft(img):
            status, schritt = 'brett-weg', 'vor-zug'
            break

        feld = _nachziehen(brett, verbraucht)
        if brett.abbruch():
            status, schritt = 'abbruch', 'nachziehen'
            break
        if '?' in feld:
            status, schritt = 'unlesbar', 'feld'
            break
        karten = [k for _i, k in _offen(feld)]
        if len(karten) < 3 or _nichts_mehr_zu_holen(karten, verbraucht):
            status = 'fertig'
            break

        try:
            zug = naechster_zug(karten, verbraucht, staerke=staerke, rng=rng)
        except StellungsFehler as fehler:
            brett.melde('stellungsfehler', text=str(fehler))
            status, schritt = 'stellungsfehler', str(fehler)
            break

        rechts = (zug.art == 'wegwerfen')
        brett.melde('zug', art=zug.art, punkte=zug.punkte,
                    karten=' '.join('%d%s' % k for k in zug.karten),
                    grund=zug.begruendung)
        for karte in zug.karten:
            wie = _karte_klicken(brett, karte, rechts=rechts)
            if wie != 'ok':
                # Not-Aus und verdecktes Fenster sind KEINE abgelehnten Zuege.
                # Ohne diese Unterscheidung zeigte der Reiter nach jedem Stop
                # -- und bei jedem verdeckten Fenster -- dieselbe, falsche
                # Ursache an.
                if wie == 'abbruch' or brett.abbruch():
                    status, schritt = 'abbruch', 'im-zug'
                elif wie == 'unlesbar':
                    status, schritt = 'unlesbar', 'klick auf %d%s' % karte
                else:
                    status, schritt = 'zug-abgelehnt', '%d%s' % karte
                break
        if status != 'fertig':
            break

        if not rechts:
            brett.schlafen(NACH_KOMBI_S)
            # Gegenprobe: keine der drei Karten darf oben zurueckliegen.
            feld_danach, _ok = _feld_lesen(brett)
            zurueck = [k for _i, k in _offen(feld_danach) if k in zug.karten]
            if zurueck:
                brett.melde('kombi-zurueckgewiesen',
                            karten=' '.join('%d%s' % k for k in zurueck))
                status, schritt = 'zug-abgelehnt', 'kombi-zurueck'
                break
            punkte += zug.punkte
            kombis += 1
        else:
            weggeworfen += 1

        verbraucht.extend(zug.karten)
        zuege += 1
        if len(verbraucht) >= 24:
            status = 'fertig'
            break

    schirm = None
    try:
        img = brett.bild()
        if img is not None:
            schirm = vision.read_points(img)
    except Exception:
        schirm = None
    if schirm is not None and schirm != punkte:
        brett.melde('punkte-weichen-ab', gerechnet=punkte, bildschirm=schirm)

    return Bericht(status=status, punkte=punkte, kombis=kombis, zuege=zuege,
                   weggeworfen=weggeworfen, schritt=schritt,
                   bildschirm_punkte=schirm)


def truhe_von(punkte):
    """Oeffentlicher Zugang zur Truhen-Einstufung."""
    return _truhe(punkte)
