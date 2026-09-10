# -*- coding: utf-8 -*-
"""Live-Runner fuer das Okey-Kartenspiel.

Spielt X Kartensets nacheinander: Eventuebersicht oeffnen, das Okey-Event
anklicken, den "Sicheren Modus" abwaehlen, starten, die Partie zu Ende
spielen, beenden -- und von vorn.

Der Ablauf folgt Schritt fuer Schritt der Beschreibung des Nutzers vom
2026-09-10. Jeder Schritt hat einen ERWARTETEN Bildzustand; passt er nicht,
wird nicht blind geklickt, sondern die volle Diagnose ins Log geschrieben und
ein Beweisbild abgelegt. Das ist dieselbe Linie wie beim Seherwettstreit-
Runner und aus demselben Grund: ein Fehlklick in der offenen Spielwelt ist
schlimmer als ein Stillstand.

WAS HIER BEWUSST NICHT PASSIERT: kein Lesen von Spielspeicher, keine
Injektion, keine Pakete -- nur Bildschirmfoto, Vergleich und ein Mausklick
ueber dieselben Windows-Aufrufe, die ein Mensch ausloest.
"""

import json
import time
from dataclasses import dataclass, field as _field

import constants
from debuglog import log
from i18n import t
from interface.config.paths import sibling_path
from okey import coords as C, flow, partie, vision
from okey.strategy import STAERKEN, STANDARD_STAERKE

try:                                    # pragma: no cover - nur Windows-Build
    import pydirectinput
    pydirectinput.FAILSAFE = False      # siehe fishingbot.py
except Exception:                       # pragma: no cover
    pydirectinput = None

_input = pydirectinput


def set_input_backend(backend):
    """Modulweiten Eingabe-Treiber tauschen (Multiclient-Naht)."""
    global _input
    _input = backend


try:                                    # pragma: no cover
    from windowcapture import WindowCapture
except Exception:                       # pragma: no cover
    WindowCapture = None


#: Protokolldatei neben der Konfiguration -- eine Zeile je gespieltem Set.
#: Damit ueberlebt die Statistik den Programmneustart; der Reiter zeigt die
#: laufende Sitzung, diese Datei die ganze Geschichte. Gleiches Muster wie beim
#: Seherwettstreit, damit es nicht zwei Arten gibt, dasselbe zu tun.
RESULTS_FILENAME = 'okey_results.jsonl'


def _protokollieren(spiel, staerke):
    """Ein Set in die Protokolldatei schreiben. Scheitert das, ist es egal --
    ein nicht geschriebener Statistik-Eintrag darf nie eine Partie kippen."""
    try:
        zeile = {'zeit': time.strftime('%Y-%m-%dT%H:%M:%S'),
                 'stufe': staerke, 'punkte': spiel.punkte,
                 'kombis': spiel.kombis, 'zuege': spiel.zuege,
                 'weggeworfen': spiel.weggeworfen, 'truhe': spiel.truhe,
                 'status': spiel.status, 'dauer_s': spiel.dauer_s}
        with open(sibling_path(RESULTS_FILENAME), 'a', encoding='utf-8') as f:
            f.write(json.dumps(zeile) + '\n')
    except Exception:
        log.event('-', t('okey.results_write_failed'))


# -- Zeiten (Sekunden) ------------------------------------------------------
FLOW_PACE_S = 0.35          # Render-Boden nach einem Fenster-Klick
WARTE_MAX_S = 6.0           # wie lange auf einen erwarteten Bildschirm
WARTE_SCHEIBE_S = 0.12      # Pruefabstand -- klein genug fuer den Not-Aus
PARK_POINT = (15, 200)      # Cursor-Parkplatz, fern aller Knoepfe


@dataclass
class OkeySpiel:
    punkte: int = 0
    kombis: int = 0
    zuege: int = 0
    weggeworfen: int = 0
    truhe: str = ''
    status: str = ''
    schritt: str = ''
    dauer_s: float = 0.0


@dataclass
class OkeySession:
    gespielt: int = 0
    punkte_gesamt: int = 0
    truhen: dict = _field(default_factory=lambda: {'gold': 0, 'silber': 0,
                                                   'bronze': 0})
    spiele: list = _field(default_factory=list)
    grund: str = ''
    fehler_schritt: str = ''
    dauer_s: float = 0.0


# -- Eingabe-Grundlagen -----------------------------------------------------

def _press_ctrl_e():
    """Strg+E mit ausdruecklichen Haltezeiten.

    DirectInput verschluckt Modifier-Kombinationen bei zu kurzem Druck -- das
    ist im Angel-Bot zweimal teuer bezahlt worden (v1.1.1/v1.1.2). Deshalb
    jede Phase mit eigenem Hold statt einer bequemen ``hotkey``-Zeile.
    """
    alt = _input.PAUSE
    _input.PAUSE = 0.1
    try:
        _input.keyDown('ctrl')
        time.sleep(0.06)
        _input.keyDown('e')
        time.sleep(0.06)
        _input.keyUp('e')
        time.sleep(0.06)
        _input.keyUp('ctrl')
    finally:
        _input.PAUSE = alt
    time.sleep(FLOW_PACE_S)


def _klick(wincap, punkt, rechts=False):
    """Client-Punkt anklicken (Fenster-Offset kommt hier dazu)."""
    x, y = C.with_offset(punkt, (wincap.offset_x, wincap.offset_y))
    if rechts:
        _input.rightClick(x, y)
    else:
        _input.click(x, y)


def _park(wincap):
    """Cursor von jedem Knopf wegfahren (reine Bewegung, nie ein Klick).

    Ein Knopf UNTER dem Zeiger wird im Hover-Zustand gezeichnet und matcht
    seine Schablone schlechter -- derselbe Effekt wie im Inventar.
    """
    try:
        _input.moveTo(wincap.offset_x + PARK_POINT[0],
                      wincap.offset_y + PARK_POINT[1])
    except Exception:
        pass


def _bild(wincap):
    try:
        return wincap.get_screenshot()
    except Exception:
        return None


def _warte_auf(wincap, pruefung, abort_fn=None, max_s=WARTE_MAX_S):
    """Warten, bis ``pruefung(bild)`` zutrifft -> ``(ok, letztes_bild)``.

    In kleinen Scheiben, damit der Not-Aus jederzeit greift -- dieselbe
    Lehre wie beim Inventar-Managen (F6 musste ueberall sofort wirken).
    """
    ende = time.time() + max_s
    img = None
    while time.time() < ende:
        if abort_fn is not None and abort_fn():
            return (False, img)
        img = _bild(wincap)
        if img is not None:
            try:
                if pruefung(img):
                    return (True, img)
            except Exception:
                pass
        time.sleep(WARTE_SCHEIBE_S)
    return (False, img)


def _diagnose(img, schritt):
    """Die volle Messreihe ins Log -- der Nutzer kann keine Dateien schicken."""
    d = flow.diagnose(img) if img is not None else {}
    kurz = {'flow_event_title': 'uebersicht', 'flow_okey_label': 'okeyzeile',
            'flow_okey_title': 'okeyfenster', 'flow_start_btn': 'start',
            'flow_ja_btn': 'ja', 'flow_hinweis': 'brett',
            'flow_beenden': 'beenden'}
    text = ' '.join('%s=%s' % (kurz[k], d[k]) for k in flow.ALL_TEMPLATES
                    if k in d)
    log.event('-', t('okey.diag', step=schritt,
                     thresh=d.get('_schwelle', flow.FLOW_NCC_MIN), body=text))
    try:
        import cv2
        pfad = sibling_path('okey_debug_%s.png' % schritt)
        cv2.imwrite(pfad, img)
        log.event('-', t('okey.debug_frame', path=pfad))
    except Exception:
        pass


# -- Der "Sicherer Modus"-Haken --------------------------------------------

def _haken_entfernen(wincap, abort_fn=None):
    """Den Haken "Sicherer Modus" abwaehlen -> ``(ok, notiz)``.

    OHNE feste Helligkeits-Schwelle, und das ist Absicht: es gibt kein Bild
    mit leerem Kaestchen, eine Schwelle waere also geraten. Stattdessen wird
    gemessen, geklickt und wieder gemessen. Faellt die Helligkeit deutlich,
    ist der Haken weg. Steigt sie, war er vorher schon weg -- dann hat der
    Klick ihn gesetzt und ein zweiter nimmt ihn wieder heraus. Bewegt sich
    nichts, kam der Klick nicht an, und DAS ist die eigentlich wichtige
    Erkenntnis: sie faellt hier auf statt spaeter als raetselhaftes Verhalten.
    """
    vorher = vision.safe_mode_ink(_bild(wincap))
    if vorher < 0:
        return (False, 'nicht-messbar')
    for versuch in range(3):
        if abort_fn is not None and abort_fn():
            return (False, 'abbruch')
        _klick(wincap, C.SAFE_MODE_CHECKBOX)
        time.sleep(FLOW_PACE_S)
        _park(wincap)
        time.sleep(0.10)
        nachher = vision.safe_mode_ink(_bild(wincap))
        log.event('0', t('okey.safe_mode', before='%.3f' % vorher,
                         after='%.3f' % nachher, attempt=versuch + 1))
        if nachher < vorher * 0.6:
            return (True, 'haken-raus')
        if nachher > vorher * 1.4:
            # Wir haben ihn gerade GESETZT -> er war schon raus. Zuruecknehmen.
            vorher = nachher
            continue
        # Keine Aenderung -> der Klick kam nicht an, noch einmal.
    return (False, 'unveraendert')


# -- Start- und Ende-Ablauf -------------------------------------------------

def _uebersicht_oeffnen(wincap, abort_fn=None):
    """Strg+E, bis die Eventuebersicht steht. Strg+E ist ein UMSCHALTER --
    deshalb erst nachsehen, sonst schliesst man sie versehentlich wieder."""
    img = _bild(wincap)
    if img is not None and flow.sichtbar(img, 'flow_event_title'):
        return (True, img)
    for versuch in range(3):
        if abort_fn is not None and abort_fn():
            return (False, img)
        log.event('0', t('okey.ctrl_e', attempt=versuch + 1))
        _press_ctrl_e()
        ok, img = _warte_auf(
            wincap, lambda i: flow.sichtbar(i, 'flow_event_title'),
            abort_fn, max_s=2.0)
        if ok:
            return (True, img)
    return (False, img)


def _spiel_starten(wincap, abort_fn=None):
    """Von der Spielwelt bis zum laufenden Brett -> ``(ok, fehlerschritt)``."""
    img = _bild(wincap)
    if img is not None and flow.brett_laeuft(img):
        log.event('0', t('okey.board_already'))
        return (True, '')

    if not flow.sichtbar(img, 'flow_okey_title'):
        ok, img = _uebersicht_oeffnen(wincap, abort_fn)
        if not ok:
            _diagnose(img, 'eventuebersicht')
            return (False, 'eventuebersicht')
        ok, punkt, dbg = flow.find_okey_row(img)
        if not ok:
            log.event('-', t('okey.row_missing', dbg=str(dbg)))
            _diagnose(img, 'okeyzeile')
            return (False, 'okeyzeile')
        log.event('0', t('okey.row_found', dbg=str(dbg)))
        _klick(wincap, punkt)
        time.sleep(FLOW_PACE_S)
        _park(wincap)
        ok, img = _warte_auf(
            wincap, lambda i: flow.sichtbar(i, 'flow_start_btn'), abort_fn)
        if not ok:
            _diagnose(img, 'okeyfenster')
            return (False, 'okeyfenster')

    haken_ok, notiz = _haken_entfernen(wincap, abort_fn)
    if not haken_ok:
        log.event('-', t('okey.safe_mode_failed', note=notiz))
        _diagnose(_bild(wincap), 'sicherermodus')
        return (False, 'sicherermodus')

    _klick(wincap, C.START_BUTTON)
    time.sleep(FLOW_PACE_S)
    _park(wincap)
    ok, img = _warte_auf(wincap, lambda i: flow.sichtbar(i, 'flow_ja_btn'),
                         abort_fn)
    if not ok:
        _diagnose(img, 'startdialog')
        return (False, 'startdialog')
    log.event('0', t('okey.confirm_start'))
    _klick(wincap, C.DIALOG_YES)
    time.sleep(FLOW_PACE_S)
    _park(wincap)
    ok, img = _warte_auf(wincap, flow.brett_laeuft, abort_fn)
    if not ok:
        _diagnose(img, 'spielbrett')
        return (False, 'spielbrett')
    return (True, '')


def _spiel_beenden(wincap, abort_fn=None):
    """"Beenden" + "Ja" -- damit die Truhe ausgezahlt wird.

    Steht der Beenden-Dialog schon (etwa weil eine vorige Sitzung mittendrin
    abgebrochen wurde), wird er nur bestaetigt. Sonst ginge ein Klick auf den
    Beenden-Knopf gegen das offene Dialogfenster -- wirkungslos, aber ein
    unnoetiger Klick an einer Stelle, an der gerade ein Fenster steht.
    """
    img = _bild(wincap)
    if flow.sichtbar(img, 'flow_ja_btn'):
        log.event('0', t('okey.confirm_end'))
        _klick(wincap, C.DIALOG_YES)
        time.sleep(FLOW_PACE_S)
        _park(wincap)
        return True
    ok, punkt, guete = flow.find_click(img, 'flow_beenden')
    if not ok:
        _diagnose(img, 'beenden')
        return False
    _klick(wincap, punkt)
    time.sleep(FLOW_PACE_S)
    _park(wincap)
    ok, img = _warte_auf(wincap, lambda i: flow.sichtbar(i, 'flow_ja_btn'),
                         abort_fn)
    if not ok:
        _diagnose(img, 'beendendialog')
        return False
    log.event('0', t('okey.confirm_end'))
    _klick(wincap, C.DIALOG_YES)
    time.sleep(FLOW_PACE_S)
    _park(wincap)
    return True


# -- Das Brett fuer den Partie-Ablauf --------------------------------------

class _LiveBrett(partie.Brett):
    """Verbindet den reinen Partie-Ablauf mit Maus und Bildschirm."""

    def __init__(self, wincap, abort_fn=None):
        self.wincap = wincap
        self._abort = abort_fn

    def bild(self):
        return _bild(self.wincap)

    def klick_karte(self, index, rechts=False):
        _klick(self.wincap, (C.CARD_SLOT_X[index], C.CARD_SLOT_Y),
               rechts=rechts)
        _park(self.wincap)

    def klick_stapel(self):
        _klick(self.wincap, C.DECK)
        _park(self.wincap)

    def schlafen(self, sekunden):
        rest = float(sekunden or 0)
        while rest > 0:                 # in Scheiben -> Not-Aus greift sofort
            if self.abbruch():
                return
            d = 0.05 if rest > 0.05 else rest
            time.sleep(d)
            rest -= d

    def abbruch(self):
        try:
            return bool(self._abort()) if self._abort else False
        except Exception:
            return False

    def melde(self, was, **werte):
        log.event('0', t('okey.trace', what=was, body=str(werte)))


# -- Session ----------------------------------------------------------------

def run_okey_session(cfg=None, decks=1, staerke=STANDARD_STAERKE,
                     on_game_done=None, abort_fn=None):
    """``decks`` Kartensets nacheinander spielen -> :class:`OkeySession`."""
    ses = OkeySession()
    t0 = time.time()
    if _input is None or WindowCapture is None:
        ses.grund = 'deps'
        log.event('-', t('okey.deps_missing'))
        return ses
    if staerke not in STAERKEN:
        staerke = STANDARD_STAERKE

    # MIT Fensternamen -- ``WindowCapture()`` ohne Argument wirft sofort
    # (windowcapture.py: ``def __init__(self, window_name)``); alle anderen
    # Runner uebergeben ebenfalls constants.GAME_NAME.
    wincap = WindowCapture(constants.GAME_NAME)
    log.event('0', t('okey.session_start', n=decks, level=staerke))

    while decks <= 0 or ses.gespielt < decks:
        if abort_fn is not None and abort_fn():
            ses.grund = 'abbruch'
            break
        s0 = time.time()
        ok, schritt = _spiel_starten(wincap, abort_fn)
        if not ok:
            ses.grund = 'fehler'
            ses.fehler_schritt = schritt
            log.event('-', t('okey.start_failed', step=schritt))
            break

        brett = _LiveBrett(wincap, abort_fn)
        bericht = partie.spielen(brett, staerke=staerke)

        # EIN SET OHNE EINEN EINZIGEN ZUG ist kein gespieltes Set, sondern ein
        # abgeraeumtes Brett, das faelschlich uebernommen wurde (alle Karten
        # verdeckt -> als "leer" gelesen). Frueher waere das als volles Set mit
        # 0 Punkten und Bronze-Truhe in Statistik und Protokoll gewandert.
        if bericht.status == 'fertig' and bericht.zuege == 0:
            ses.grund = 'fehler'
            ses.fehler_schritt = 'leeres-brett'
            log.event('-', t('okey.empty_board'))
            _spiel_beenden(wincap, abort_fn)
            break

        # RUNDE SCHLIESSEN, auch nach einem Fehler: sonst bliebe ein offenes
        # Brett zurueck, das der naechste Start uebernehmen wuerde -- mit
        # leerer Buchfuehrung. Nur nach einem Not-Aus nicht; da soll sofort
        # Schluss sein, und der Nutzer sitzt ohnehin davor.
        beendet = False
        if bericht.status != 'abbruch':
            beendet = _spiel_beenden(wincap, abort_fn)

        # Die Truhe zaehlt NUR bei tatsaechlich beendeter Runde -- nur dann
        # wurde sie ausgezahlt. Sie wird HIER bestimmt, vor der Protokollzeile,
        # damit Log, Protokolldatei und Reiter dieselbe Auskunft geben.
        truhe = partie.truhe_von(bericht.punkte) if beendet else ''
        spiel = OkeySpiel(punkte=bericht.punkte, kombis=bericht.kombis,
                          zuege=bericht.zuege,
                          weggeworfen=bericht.weggeworfen, truhe=truhe,
                          status=bericht.status, schritt=bericht.schritt,
                          dauer_s=round(time.time() - s0, 1))
        log.event('+' if bericht.status == 'fertig' else '-',
                  t('okey.game_done', points=bericht.punkte,
                    combos=bericht.kombis, chest=truhe or '-',
                    status=bericht.status, secs=spiel.dauer_s))

        ses.gespielt += 1
        ses.punkte_gesamt += bericht.punkte
        if beendet:
            ses.truhen[truhe] = ses.truhen.get(truhe, 0) + 1
        ses.spiele.append(spiel)
        _protokollieren(spiel, staerke)
        if on_game_done is not None:
            try:
                on_game_done(ses, spiel)
            except Exception:
                pass

        if bericht.status == 'abbruch':
            ses.grund = 'abbruch'
            break
        if bericht.status not in ('fertig', 'brett-weg'):
            ses.grund = 'fehler'
            ses.fehler_schritt = bericht.status
            break
        if not beendet:
            ses.grund = 'fehler'
            ses.fehler_schritt = 'beenden'
            log.event('-', t('okey.end_failed'))
            break

    if not ses.grund:
        ses.grund = 'fertig'
    ses.dauer_s = round(time.time() - t0, 1)
    log.event('0', t('okey.session_done', n=ses.gespielt,
                     points=ses.punkte_gesamt, gold=ses.truhen.get('gold', 0),
                     silver=ses.truhen.get('silber', 0),
                     bronze=ses.truhen.get('bronze', 0), reason=ses.grund))
    return ses
