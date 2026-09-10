# -*- coding: utf-8 -*-
"""Wo ist das Okey-Fenster gerade -- und was steht darauf?

Reine Erkennung, klickt nie. Jedes Element wird per Template-Vergleich im
GANZEN Bild gesucht statt an einer festen Stelle geprueft: das kostet kaum
etwas und macht den Ablauf unempfindlich gegen ein verschobenes Fenster.

WARUM DIE SCHABLONEN NUR DEN SCHRIFTZUG ZEIGEN, NICHT DIE GANZE PLATTE:
Die vier Zeilen der Eventuebersicht haben denselben Rahmen und unterscheiden
sich nur im Text. Gemessen am 2026-09-10 an Bild 16:

    Schablone            "Okey-Event"   staerkste FREMDE Zeile   Abstand
    nur Schriftzug 69x15     1,000              0,425             0,575
    Text + Rand    95x21     1,000              0,656             0,344
    ganze Platte  177x24     1,000              0,736             0,264

Je mehr Rahmen mitgeschnitten wird, desto aehnlicher werden sich die Zeilen --
der Rahmen ist ja identisch. Deshalb der enge Schnitt.

DIE SCHWELLE 0,80 ist gemessen, nicht geraten. Ueber alle zwoelf Bilder des
Nutzers (16..27) liegt der staerkste Treffer eines NICHT vorhandenen Elements
bei 0,674; der schwaechste Treffer eines vorhandenen bei 0,979. 0,80 sitzt in
dieser Luecke und laesst einem echten Treffer Luft, falls ein anderer Client
etwas anders zeichnet (andere Kantenglaettung, anderer Patch).
"""

import os

try:
    import cv2 as cv
except Exception:                       # pragma: no cover
    cv = None

from . import templates_dir

#: Mindest-Uebereinstimmung. Herleitung siehe Modulkopf.
FLOW_NCC_MIN = 0.80

#: Alle Schablonen des Ablaufs -- zugleich die Reihenfolge im Diagnose-Log.
ALL_TEMPLATES = (
    'flow_event_title',      # "Eventuebersicht" -> die Uebersicht ist offen
    'flow_okey_label',       # "Okey-Event"      -> DIE anzuklickende Zeile
    'flow_okey_title',       # "Okey-Kartenspiel"-> das Spielfenster ist offen
    'flow_start_btn',        # "Start"           -> Vorfenster
    'flow_ja_btn',           # "Ja"              -> ein Dialog steht
    'flow_hinweis',          # Hinweiszeile      -> das Spielbrett laeuft
    'flow_beenden',          # "Beenden"         -> Runde kann beendet werden
)

_cache = {}


def _tpl(name):
    if name not in _cache:
        if cv is None:
            _cache[name] = None
        else:
            pfad = os.path.join(templates_dir(), name + '.png')
            _cache[name] = cv.imread(pfad, cv.IMREAD_COLOR)
    return _cache[name]


def find(bgr, name, thresh=FLOW_NCC_MIN):
    """Bestes Vorkommen der Schablone -> ``(ok, (x, y), guete)``. Wirft nie."""
    try:
        tpl = _tpl(name)
        if tpl is None or bgr is None:
            return (False, (0, 0), 0.0)
        if bgr.shape[0] < tpl.shape[0] or bgr.shape[1] < tpl.shape[1]:
            return (False, (0, 0), 0.0)
        res = cv.matchTemplate(bgr, tpl, cv.TM_CCOEFF_NORMED)
        _mn, mx, _ml, loc = cv.minMaxLoc(res)
        return (mx >= thresh, (int(loc[0]), int(loc[1])), float(mx))
    except Exception:
        return (False, (0, 0), 0.0)


def center(name, pos):
    """Klick-Mitte eines gefundenen Treffers."""
    tpl = _tpl(name)
    if tpl is None:
        return pos
    h, w = tpl.shape[:2]
    return (pos[0] + w // 2, pos[1] + h // 2)


def find_click(bgr, name, thresh=FLOW_NCC_MIN):
    """Wie :func:`find`, liefert aber gleich die Klick-Mitte."""
    ok, pos, guete = find(bgr, name, thresh)
    return (ok, center(name, pos) if ok else (0, 0), guete)


def sichtbar(bgr, name, thresh=FLOW_NCC_MIN):
    """Kurzform: ist das Element da?"""
    return find(bgr, name, thresh)[0]


def find_okey_row(bgr):
    """Klickziel der Okey-Zeile in der Eventuebersicht.

    Zwei Bedingungen, und beide muessen erfuellt sein: der Schriftzug
    "Okey-Event" wurde gefunden UND die Eventuebersicht ist ueberhaupt offen.
    Die zweite Bedingung ist kein Zierrat -- ohne sie koennte ein zufaellig
    aehnlicher Bildausschnitt irgendwo in der Spielwelt einen Klick ausloesen.
    Der Nutzer hat ausdruecklich gesagt: in die Zeile klicken, NICHT auf
    "Ansehen" -- das oeffnet nur die Beschreibung.

    :return: ``(ok, punkt, diagnose)``
    """
    ok_l, pos_l, ncc_l = find(bgr, 'flow_okey_label')
    ok_t, _pt, ncc_t = find(bgr, 'flow_event_title')
    dbg = {'zeile': round(ncc_l, 3), 'uebersicht': round(ncc_t, 3)}
    if not ok_t:
        dbg['grund'] = 'uebersicht-nicht-offen'
        return (False, (0, 0), dbg)
    if not ok_l:
        dbg['grund'] = 'okey-zeile-nicht-gefunden'
        return (False, (0, 0), dbg)
    return (True, center('flow_okey_label', pos_l), dbg)


def brett_laeuft(bgr):
    """Steht das Spielbrett? (Hinweiszeile unter den Auswahlplaetzen)

    Die Hinweiszeile ist der verlaesslichste Anker: sie steht auf JEDEM
    Brett-Bild (gemessen 1,000 auf allen neun) und auf keinem anderen
    (hoechstens 0,386). Die Karten selbst taugen NICHT dazu -- am Rundenende
    liegen dort Rueckseiten, die zu Recht als "leer" gelesen werden.
    """
    return sichtbar(bgr, 'flow_hinweis')


def diagnose(bgr):
    """ROHE Bestwerte ALLER Schablonen -- auch unterhalb der Schwelle.

    Genau das macht einen Fehlschlag im Log lesbar: liegt EIN Wert knapp
    darunter, zeichnet der Client dieses Element anders; sind alle niedrig,
    ist der erwartete Bildschirm gar nicht da (Klick verschluckt, falsches
    oder verdecktes Fenster).
    """
    out = {'_schwelle': FLOW_NCC_MIN}
    for name in ALL_TEMPLATES:
        out[name] = round(find(bgr, name, thresh=2.0)[2], 3)
    return out
