import pydirectinput
pydirectinput.PAUSE = 0.1  # KEYBOARD needs this hold to register in-game; 0.05 was too short for keys (fishing didn't cast). = pydirectinput default (what v1.1.0 used). Mouse-only flows (scan) lower it per-op to 0.05.
# Fail-Safe AUS: pydirectinput wirft sonst FailSafeException, sobald der Cursor
# beim Klick auch nur EINMAL als (0,0) gelesen wird (transient bei Szenenwechsel/
# Fokusverlust/Dialog) -> ein einziges solches Lesen killt die GANZE Session
# ("Stop due to exception", Live-Crash-Report 2026-07-22). Der Bot hat mit F6
# einen eigenen Not-Aus; der Ecken-Not-Aus ist fuer von Hand laufende Skripte
# gedacht, nicht fuer einen Bot, der die Maus bewusst ueber den ganzen Screen
# fuehrt. pydirectinput ist prozess-global -> hier gesetzt (fruehester Importeur
# im Angel-Prozess) wirkt es modulweit fuer alle Klick-/Tastenpfade.
pydirectinput.FAILSAFE = False
import cv2 as cv

# DEBUG-Klick-Tracker (reines Diagnose-Logging; veraendert KEINEN Klick). Soft-
# Import wie im restlichen Projekt: schlaegt er fehl, angelt der Bot unveraendert
# weiter (click_tracker ist stdlib-only, sollte immer laden).
try:
    import click_tracker
except Exception:  # pragma: no cover
    click_tracker = None


# -- Input-Backend (Multiclient-Naht, Build-Schritt 6) ---------------------
# Single-Client (Default): _DirectBackend ruft pydirectinput FORM-EXAKT wie
# bisher -> byte- UND test-identisch (Tests patchen ``fishingbot.pydirectinput``;
# die Methoden loesen den Namen zur Laufzeit auf, der Patch greift weiter).
# Multiclient (eigener Worker-Prozess): set_input_backend() ersetzt _input durch
# einen Lease-gebundenen Backend (CursorClient). WICHTIG: zusammengehoerige
# Tastendruecke (keyDown+keyUp) laufen ueber EINE Methode (.key) -> EIN Lease,
# damit kein anderer Client mitten in den Tastendruck graetscht (Atomizitaet).
class _DirectBackend:
    def set_pause(self, value):
        pydirectinput.PAUSE = value

    def click(self, x, y, button='left', tag='other'):
        # DEBUG-Tracking VOR dem physischen Klick: jeden Klick ms-genau + mit
        # Kontext protokollieren (``tag`` = Pfad-Label des Aufrufers). Reines
        # Logging -- veraendert den Klick NICHT und wirft nie.
        if click_tracker is not None:
            click_tracker.record_click(button, x, y, tag=tag)
        # Form-exakt: ohne button (= Default 'left') KEIN button-kwarg senden,
        # damit bestehende Test-Assertions auf die Aufrufform unveraendert gelten.
        if button == 'left':
            pydirectinput.click(x=x, y=y)
        else:
            pydirectinput.click(x=x, y=y, button=button)

    def key(self, key):
        pydirectinput.keyDown(key)
        pydirectinput.keyUp(key)


_input = _DirectBackend()


def set_input_backend(backend):
    """Ersetzt das Input-Backend (Multiclient-Worker). Default = _DirectBackend."""
    global _input
    _input = backend


# Koeder-Nachlegen laeuft NICHT ueber _input (das kennt nur click/key), sondern
# braucht moveTo/mouseDown/mouseUp (gehaltener Drag, refill.py). Single-Client =
# None -> direkt das Modul ``pydirectinput`` (byte-identisch, weiter test-patchbar
# ueber ``fishingbot.pydirectinput``). Multiclient-Worker setzt hier ein
# lease-gebundenes Screen-Backend (cursor_client.LeasedScreenCursor) -> der Drag
# laeuft als EIN Lease-Burst statt roh am falschen Fenster (Finding #1).
_refill_backend = None


def set_refill_backend(backend):
    """Ersetzt das Refill-Input-Backend (Multiclient). Default None = pydirectinput."""
    global _refill_backend
    _refill_backend = backend


import cv2 as cv  # noqa: E402  (nach dem Input-Backend-Block; bewusst)
from time import time, sleep
import random
import os
from windowcapture import WindowCapture
from hsvfilter import HsvFilter
from i18n import t
from respath import resource_path
import constants
import mount

# Reine Such-/Logging-Primitive (zustandslos) leben in fishing_match; HIER in den
# Namespace re-importiert, damit (a) die Detect-Methoden sie als bare globale
# Namen aufloesen und (b) Tests, die ``fishingbot._match_template_max`` direkt
# aufrufen, unveraendert funktionieren.
from fishing_match import _flog, _match_template_max  # noqa: F401  (re-export)
from fishing_detect import FishingDetectMixin

# Globales Stop-Signal (Responsiveness): die schweren Refill-Ops pollen es ueber
# interruptible-sleeps + ein Zeitbudget und brechen bei F6 sofort ab. Default ist
# das NIE-gesetzte NULL_SIGNAL -> ohne Injektion aendert sich nichts (byte-stabil).
import stop_signal as _stopsig

# Chat-OCR-Kern + reine Whitelist-Entscheidung. Defensiv (soft) importiert -- die
# Whitelist ist opt-in (Default AUS), und ein fehlender Import darf das Angeln NIE
# brechen: dann bleibt die Whitelist einfach wirkungslos (es wird alles geangelt).
try:
    import fishing_chat as _fc
    import fishing_whitelist as _wl
except Exception:                       # pragma: no cover - defensiver Import
    _fc = None
    _wl = None

# Koeder-Nachlegen-Engine (opt-in, Default AUS). Soft importiert -- ein fehlender
# Import (z. B. fehlendes numpy headless) darf das Angeln NIE brechen: dann bleibt
# das Nachlegen einfach wirkungslos. Die gesamte Logik (Quickslot-Leer-Erkennung,
# Inventar-Scan + Drag) liegt fertig in interface/refill.py -- HIER nur der
# gedrosselte Trigger im Angel-Lauf.
try:
    from interface import refill as _refill
except Exception:                       # pragma: no cover - defensiver Import
    _refill = None


class FishingBot(FishingDetectMixin):

    #properties
    fish_pos_x = None
    fish_pos_y = None
    fish_last_time = None
    botting = False

    # Zuletzt ZUGESTELLTER Minispiel-Klick (Screen-Koordinaten) + Zeitpunkt --
    # Basis der Echo-Sperre. None = in dieser Runde noch nicht geklickt.
    _last_click_pos = None
    _last_click_time = 0.0
    # Diagnose: letzte detect()-Begruendung + Klick-Bilanz der laufenden Runde.
    _last_detect_info = None
    _click_stats = None

    FISH_RANGE = 74
    FISH_VELO_PREDICT = 30

    # ECHO-KLICK-SPERRE (User-Report 2026-07-25 "der Char laeuft vor").
    # BEFUND aus zwei Live-Logs, 10 vollstaendige Runden ausgemessen: der LETZTE
    # Klick jeder Runde springt im Median nur 4,6 px gegenueber dem vorherigen --
    # alle uebrigen Klicks springen im Median 48,6 px (Faktor 10,5). 8/10 Runden
    # enden mit einem Sprung <= 10 px, zeitlicher Abstand 0,42-0,59 s, und 0,2-1,2 s
    # spaeter meldet der Bot "Minigame finished".
    # DEUTUNG: Der Fisch haengt da bereits am Haken. Die Uhr rendert waehrend der
    # Fang-Animation weiter (Konfidenz 0,99) -> ``detected_end`` bleibt True und der
    # Uhr-Re-Check (:meth:`_minigame_recheck_gone`) greift NICHT. Der Nachzuegler
    # trifft keinen Fisch mehr, faellt durchs Overlay in die Welt -> Klick-to-Move.
    # SCHWELLEN: Abstand allein trennt NICHT sauber (legitime Zwischen-Spruenge
    # gehen bis 3,2 px runter, verdaechtige End-Echos bis 10 px hoch) -- deshalb
    # Abstand UND kurzes Zeitfenster. Die Fehlerrichtung ist asymmetrisch und
    # rechtfertigt die Ueberlappung: ein faelschlich unterdrueckter Klick kostet nur
    # Frames (der naechste feuert, sobald der Fisch sich > Radius bewegt), ein
    # faelschlich erlaubter kostet einen Weltklick. Das Fenster ist begrenzt, damit
    # ein wirklich ruhender Fisch weiterhin nachgeklickt wird.
    FISH_ECHO_RADIUS_PX = 12
    FISH_ECHO_WINDOW_S = 1.5

    # BAIT_POSITION = (473, 750)
    # FISH_POSITION = (440, 750)

    FILTER_CONFIG = [49, 0, 58, 134, 189, 189, 0, 0, 0, 0]

    # Golden-Tuna-Dialog: 3 senkrecht gestapelte Knoepfe. 1 = Freilassen,
    # 2 = Aufschneiden, 3 = Als Koeder benutzen. Knoepfe sind gleichmaessig (DY)
    # gestapelt.
    #
    # KOORDINATEN-SYSTEM (kritisch): der Bot KLICKT in CLIENT-Koordinaten --
    # ``self.wincap.offset_{x,y}`` ist der CLIENT-Ursprung (Fensterecke + 8px
    # Rand + 30px Titelleiste), und der Klick ist ``offset + (X, Y)``. Die
    # Referenz-Screenshots (FischOCR/GoldenerThunfisch*.png) sind aber das
    # VOLLBILD 802x632 = Client + ~31px Titelleiste + 1px-Rand. Die DARAUS
    # gemessenen Knopf-Mitten sind also FULL-FRAME und liegen, 1:1 als
    # Client-Koordinate benutzt, ~31px ZU TIEF (und 1px zu weit rechts) -> der
    # Klick verfehlt den Knopf. Darum die Full-Frame-Messung in CLIENT umrechnen:
    # CLIENT = FULL_FRAME - (1, 31).
    #   gemessen FULL-FRAME : X=400, Y={Freilassen:268, Aufschneiden:300,
    #                         Koeder:332} (DY=32), Confirm-OK (400,277)
    #   -> CLIENT           : X=399, Y={237, 269, 301} (DY unveraendert=32),
    #                         Confirm-OK (399,246)
    # Klickpositionen werden geloggt (fishing.golden_tuna_clicked/_confirmed).
    GOLDEN_TUNA_X = 399                          # 400 (full-frame) - 1
    GOLDEN_TUNA_DY = 32                          # relativer Abstand (frame-unabh.)
    GOLDEN_TUNA_Y = {1: 269 - GOLDEN_TUNA_DY,   # 237 (Feld 1, oben:  Freilassen)
                     2: 269,                    # 269 (Feld 2, mitte: Aufschneiden)
                     3: 269 + GOLDEN_TUNA_DY}   # 301 (Feld 3, unten: Koeder)

    # Nach dem Options-Klick antwortet der SERVER mit einem Bestaetigungs-
    # Dialog mit EINEM OK-Knopf (z.B. die Freilassen-Bonus-Meldung). Der
    # Dialog steht NICHT an fester Position (Hoehe haengt vom Text ab, Lage
    # variiert: OK-Mitte (403,250) vs. (403,202) auf den Live-Referenzen) --
    # geklickt wird darum der per Template-SUCHE gefundene Knopf
    # (fishing_detect.golden_confirm_find), keine Konstante.

    # Wie lange nach dem Options-Klick auf das Bestaetigungs-Fenster gewartet
    # wird (Sekunden). Das Fenster kommt erst mit der SERVER-Antwort -- der
    # alte Sofort-Klick 0.1s nach dem Options-Klick feuerte praktisch immer,
    # BEVOR es existierte (-> Dialog blieb offen, Bot haengte). Jetzt klickt
    # der Loop OK erst, wenn detect_golden_confirm den Dialog WIRKLICH sieht
    # (Template der Knopf-Leiste), innerhalb dieses Zeitfensters.
    GOLDEN_CONFIRM_WAIT_S = 10.0

    # Absolute Obergrenze (Sekunden ab dem Options-Klick), bis zu der ueberhaupt
    # auf Bestaetigungs-Dialoge geachtet wird -- Backstop, falls je ein Dialog
    # klebt (sonst koennte die Fenster-Verlaengerung unten endlos verlaengern).
    GOLDEN_CONFIRM_MAX_S = 25.0
    # Mindestabstand zwischen zwei OK-Klicks. Der Server tauscht Dialog 1 -> 2
    # nicht instant; ohne Cooldown wuerde der Loop 60x/s auf denselben Dialog
    # klicken und im Moment des Schliessens einmal in die Welt treffen.
    GOLDEN_CONFIRM_CLICK_COOLDOWN_S = 1.0
    # Wie lange nach der LETZTEN Modal-Evidenz (Popup ODER erkannter Dialog) noch
    # keine Weltklicks gesendet werden. BEWUSST kurz: die Sperre haengt an
    # TATSAECHLICHER Evidenz pro Frame, nicht am generoesen Klick-Fenster -- sonst
    # wuerde ein spurioeser/klebender daily-False-Positive (reine schwarze Ecke:
    # Lade-/Teleport-/DC-Screen; detect_daily_reward ist absichtlich simpel) das
    # Angeln 10-25s blockieren. Die Grace ueberbrueckt nur die Server-Luecke
    # Options-Klick -> Dialog-erscheint und den Frame-Flacker zwischen Dialogen.
    GOLDEN_SUPPRESS_GRACE_S = 3.0

    # set position of the fish windows
    # this value can be diferent by the sizes of the game window

    FISH_WINDOW_SIZE = (280, 226)
    FISH_WINDOW_POSITION = (95, 80)

    wincap = None

    # Load the needle image

    # WICHTIG: resource_path() -- in der gepackten EXE liegen die Bilder im
    # PyInstaller-Bundle (sys._MEIPASS), NICHT im Arbeitsverzeichnis. Ein nackter
    # Pfad 'images/..' laedt dort None -> matchTemplate erkennt NIE etwas (das
    # Minispiel wird nie gespielt). Mit resource_path laden die Vorlagen auch aus
    # der EXE -- wie es das Puzzle (fish_jigsaw_chest) schon richtig macht.
    needle_img = cv.imread(resource_path('images/fiss.jpg'), cv.IMREAD_UNCHANGED)
    needle_img_clock = cv.imread(resource_path('images/clock.jpg'), cv.IMREAD_UNCHANGED)

    # Limit time

    initial_time = None

    end_time_enable = False

    end_time = 0

    # for fps

    loop_time = time()

    # The mouse click cooldown

    timer_mouse = time()

    # The timer beteween the states

    timer_action = time()

    bait_time = 2
    throw_time = 2
    game_time = 2

    # Anti-Erkennungs-Jitter: RELATIVE (multiplikative) Streuung der drei Zyklus-
    # Wartezeiten (Koeder/Auswurf/Minigame-Delay). Bricht die maschinen-praezise
    # Periodizitaet (jeder Zyklus exakt gleich getaktet = der eigentliche Bot-
    # Fingerabdruck laut Recherche), OHNE den Bot zu drosseln: zentriert auf 1.0
    # -> im Schnitt keine Aenderung der eingestellten Zeit; relativ -> skaliert
    # mit ihr (0.1s -> +-0.015s, 2.0s -> +-0.3s). Das Minigame-Klicken bleibt
    # UNBERUEHRT (seine "danebens" entstehen schon natuerlich aus der Tracking-
    # Latenz). ``_TIMING_JITTER = 0`` schaltet es exakt ab (byte-stabil fuer Tests).
    _TIMING_JITTER = 0.15                 # +-15% (<= die vom User gesetzte 20%-Grenze)
    _jitter_rolled_for = None
    _action_deadline_val = 0.0

    def _roll_deadline(self, base):
        """Gejitterte Wartezeit fuer den AKTUELLEN State -- EINMAL pro State-
        Eintritt gewuerfelt (nicht jeden Frame neu, sonst flackert die Schwelle).
        ``base`` = die eingestellte Zeit; Rueckgabe = ``base * uniform(1-j, 1+j)``.
        ``_TIMING_JITTER == 0`` -> exakt ``base`` (deterministisch)."""
        if self._jitter_rolled_for != self.state:
            self._jitter_rolled_for = self.state
            j = self._TIMING_JITTER
            factor = random.uniform(1.0 - j, 1.0 + j) if j else 1.0
            self._action_deadline_val = float(base) * factor
        return self._action_deadline_val

    # Konfigurierbare In-Game-Tasten (Default = bisheriges Verhalten '2'/'1').
    # Werden von hack._on_start aus der Config injiziert, BEVOR set_to_begin
    # laeuft. Default-Werte halten das Verhalten byte-stabil.
    bait_key = '2'
    cast_key = '1'

    # Mount-Animation-Cancel (Default AUS -> byte-stabil). Wird in set_to_begin
    # aus den values ('-MOUNT-'/'-MOUNTKEY-') gelesen. Nach einem bestaetigten
    # Minispiel-Ende drueckt der Bot die Taste, wartet 0.1s, drueckt erneut
    # (auf-/absteigen) -> bricht die Fang-Animation ab -> schneller neu auswerfen.
    mount_enabled = False
    mount_key = '3'

    # Counter-Hook: einmal pro bestaetigtem Fang aufgerufen (von hack.py gesetzt).
    # None -> kein Hook (FishingBot bleibt von stats.py entkoppelt).
    on_catch = None

    # Golden-Tuna: welches der 3 Dialogfelder geklickt wird (Default 3 = Koeder).
    golden_tuna_action = 3

    # Deadline (time()), bis zu der nach einem Golden-Tuna-Options-Klick auf
    # den Bestaetigungs-Dialog gewartet wird. 0.0 = nichts scharf.
    _golden_confirm_until = 0.0

    # Absolute Deadline (time()) fuer das Bestaetigungs-Fenster (Backstop gegen
    # endlose Verlaengerung) + Zeitpunkt des letzten OK-Klicks (Cooldown).
    _golden_confirm_hard = 0.0
    _last_confirm_click = 0.0
    # Weltklick-Sperre bis (time()): an tatsaechlicher Modal-Evidenz + kurzer
    # Grace, NICHT am Klick-Fenster (siehe GOLDEN_SUPPRESS_GRACE_S). 0.0 = frei.
    _golden_suppress_until = 0.0

    # Angel-Whitelist (opt-in). Default AUS -> angelt ALLES -> byte-stabil.
    #   * whitelist_enabled: nur True schaltet die Pruefung scharf.
    #   * whitelist_states: {DE-Name: KEEP|REMOVE|CAMPFIRE} aus der Inventar-
    #     Verwaltung (vom RunLoop injiziert). Fehlt ein Name -> gilt als KEEP.
    # Bei einem Biss wird NUR der kleine Chat-Streifen via fishing_chat.read_hook
    # gelesen; ist der Fang als REMOVE markiert (oder eine Niete), wird das
    # Minispiel SOFORT abgebrochen + neu ausgeworfen. UNGEWOLLT/unsicher ->
    # weiterangeln (nie versehentlich einen gewollten Fisch abbrechen).
    whitelist_enabled = False
    whitelist_states = None

    # Zuletzt fuer die Whitelist gelesener Biss -- verhindert mehrfaches
    # Auswerten/Loggen desselben Bisses pro Wurf (Reset bei jedem neuen Auswerfen).
    _whitelist_decided = False
    # Letzte geloggte Chat-Erkennung (kind, name, conf) -- Dedup fuers Diagnose-Log.
    _whitelist_last_sig = None

    # Koeder-Nachlegen (opt-in). Default AUS -> der Bot prueft den Koeder-Slot
    # NIE -> byte-stabil. Erkennt der Bot den Koeder-Quickslot (= der bait_key-
    # Slot) leer, legt er EINEN Koeder aus dem Inventar nach; ist keiner mehr da,
    # stoppt er. Die Live-Infrastruktur (Inventar-DB + Kalibrierung) injiziert der
    # RunLoop separat auf die Instanz (analog whitelist_states):
    #   * bait_refill_db:    inventory.itemdb.ItemDB (None -> Engine baut/nutzt
    #     den Bundle-Default selbst defensiv);
    #   * bait_refill_calib: Kalibrierungs-Dict (None -> DEFAULT_CALIBRATION);
    #   * inventory_hotkey:  Spiel-Taste, die das Inventar oeffnet (Default 'i').
    # Der optionale on_bait_empty-Hook (vom RunLoop gesetzt) zeigt ein Popup
    # "Koeder leer", wenn gestoppt wird -- entkoppelt (None -> nur Log).
    bait_refill_enabled = False
    bait_refill_db = None
    bait_refill_calib = None
    inventory_hotkey = 'i'
    on_bait_empty = None
    # Drossel: nicht jeden Frame pruefen -- nur, wenn seit der letzten Pruefung
    # mind. _BAIT_REFILL_INTERVAL s vergangen sind (und ohnehin nur kurz vorm
    # Baiten in State 0). 0.0 = "noch nie geprueft" -> erste Pruefung sofort.
    _last_bait_check = 0.0
    _BAIT_REFILL_INTERVAL = 5.0
    # Diagnose-Drossel (getrennt vom Pruef-Throttle): gezielte Debug-Zeilen fuers
    # Nachlegen (aktiv-aber-blockiert / Slot als belegt gelesen), damit ein
    # "legt nicht nach obwohl leer"-Report am naechsten Log ablesbar ist, ohne
    # den Loop zuzuspammen. 0.0 = noch nie diagnostiziert.
    _last_bait_diag = 0.0
    _BAIT_DIAG_INTERVAL = 30.0

    # Dieselbe Drossel fuer die Meldung "Chat-Zone verdeckt". Ohne sie sieht ein
    # zugedeckter Chat im Log genauso aus wie ein leerer -- der Live-Report
    # "Fische werden nicht mehr ausgelesen" war genau dieser Fall.
    _last_obstructed_log = 0.0

    # Globales Stop-Signal (vom RunLoop injiziert). Default = NIE-gesetztes
    # NULL_SIGNAL -> die Refill-Naps blockieren wie bisher, ein Stop bricht sie
    # nie ab (byte-stabil). Mit echtem Signal pollt jede Refill-Nap es und bricht
    # bei F6 in <1 Slice ab.
    stop_signal = _stopsig.NULL_SIGNAL
    # GEBUNDENE Obergrenze fuer EINEN Refill-Versuch (Inventar oeffnen + bis zu 4
    # Seiten scannen + draggen). Auch ohne Stop endet die Op spaetestens hier mit
    # klarem Log -> nie ein stiller Haenger. Grosszuegig (4 Seiten + Drag dauern
    # real ~2-3 s); 20 s ist eine reine Sicherheits-Decke.
    _BAIT_REFILL_BUDGET = 20.0

    # -- KOEDER-RUECKMELDUNG (immer aktiv, kein Schalter) ----------------
    # Bis v1.6.5 hat der Bot den Koeder-Tastendruck gesendet und Erfolg
    # ANGENOMMEN. Lehnt der Client ab -- "Du kannst diese Aktion nicht
    # ausfuehren, waehrend du angelst." --, warf er OHNE Koeder aus und meldete
    # danach "Kein Biss": der Fehler war unsichtbar. Der Client quittiert jeden
    # Druck in derselben Chat-Zeile, die der Bot ohnehin liest
    # (fishing_chat.read_action_feedback, am echten Client verifiziert), also
    # wird die Antwort jetzt gelesen und beantwortet statt ignoriert.
    _bait_pending_since = 0.0    # >0 -> Druck abgesetzt, Antwort noch offen
    _bait_ok = 0                 # vom Client bestaetigte Koeder-Druecke
    _bait_blocked = 0            # abgelehnte ("waehrend du angelst")
    _bait_blocked_streak = 0     # in Folge -- nur fuer die Warn-Zeile
    _bait_casts = 0              # Wuerfe insgesamt (Nenner der Bilanz)
    # Fingerabdruck der zuletzt GEWERTETEN Chat-Zeile. Die Zeile bleibt im Spiel
    # stehen -- ohne diese Sperre wuerde dieselbe Ablehnung immer wieder zaehlen.
    _bait_last_feedback_sig = None
    # So lange nach dem Druck wird auf die Antwort gewartet; danach gilt "keine
    # Aussage" und der Lauf geht unveraendert weiter -- der Sensor darf den
    # Angel-Loop nie ausbremsen, nur informieren.
    _BAIT_FEEDBACK_WINDOW_S = 3.0
    # Wartezeit nach einer Ablehnung, bevor neu gekoedert wird. Bewusst nicht
    # "geraten und fertig": nach dem Warten prueft derselbe Sensor erneut, ein zu
    # kurzer Wert kostet also nur einen weiteren -- protokollierten -- Versuch.
    _BAIT_RETRY_WAIT_S = 1.5
    # Nach so vielen abgelehnten Versuchen in Folge einmal deutlich warnen
    # (haengt der Char dauerhaft im Angel-Zustand, ist das kein Zufall mehr).
    _BAIT_BLOCKED_WARN_AT = 5
    # Bilanz-Zeile alle N Wuerfe -> im Log ist laufend ablesbar, ob es sauber
    # laeuft, ohne dass der Nutzer etwas einschalten oder auswerten muss.
    _BAIT_BALANCE_EVERY = 25
    # KEINE Wartezeit mehr nach einem Whitelist-Abbruch -- siehe
    # :meth:`_abort_minigame`. Der Bot koedert sofort neu (v1.6.5-Tempo); eine
    # Ablehnung durch den Client faengt der Sensor aus v1.6.6 ab
    # (``_BAIT_RETRY_WAIT_S`` + Koeder-Bilanz), statt sie durch eine Pause bei
    # JEDEM Abbruch praeventiv zu erkaufen.
    #
    # Historie, damit die Zahl nicht ein drittes Mal zurueckkommt: v1.6.6 fuehrte
    # 1,0 s ein, v1.6.8 ersetzte sie durch einen selbstregelnden Wert (0,4-2,0),
    # der asymmetrisch nach OBEN lief und am Deckel klebte, v1.6.9 setzte auf
    # 1,0 s zurueck. Alle drei Varianten haben dasselbe Problem: sie bezahlen bei
    # jedem Abbruch fuer einen Fall, der nur manchmal eintritt -- und im
    # Live-Log des Testers enden 56 % aller Zyklen im Abbruch.

    # This is the filter parameters, this help to find the right image
    hsv_filter = HsvFilter(*FILTER_CONFIG)

    state = 0

    # Selbstdiagnose: erschien in der aktuellen Angel-Runde ein echtes Minispiel
    # (Uhr)? + Zaehler aufeinanderfolgender Runden OHNE Biss -> klare Warnung
    # statt stummem Endlos-Loop, wenn nichts Echtes erkannt wird.
    _bite_seen_this_cycle = False
    _casts_without_bite = 0
    _best_minigame_conf = 0.0   # beste Uhr-Trefferguete dieser Runde (Diagnose)

    # Die reinen Erkennungs-Methoden detect / detect_minigame / detect_daily_reward
    # liefert der FishingDetectMixin (oben eingemischt) -- gleiche Methoden-
    # aufloesung, gleicher self.-Zustand. Hier verbleibt die zustandsbehaftete
    # Cast-/State-Machine.

    def _on_cycle_end(self):
        """Nach JEDER Angel-Runde aufrufen: zaehlt aufeinanderfolgende Runden
        OHNE erkanntes Minispiel/Biss und WARNT klar, sobald der Bot nur noch
        ins Leere wirft (kein echtes Spiel / falsche Position / Angel nicht
        ausgeworfen). Stoppt NICHT -- auf echtem Spiel sind einzelne Leer-
        Auswuerfe normal -- meldet aber unmissverstaendlich, dass nichts
        Echtes erkannt wird, statt stumm weiterzuloopen.
        """
        # Beste Uhr-Trefferguete der Runde melden (Diagnose: >0.90 = erkannt;
        # 0.5-0.9 = Uhr da, aber Schwelle zu hoch; ~0 = Capture/Position falsch).
        _flog(3, t('fishing.minigame_confidence',
                   conf='{:.2f}'.format(self._best_minigame_conf)))
        # Klick-Bilanz der Runde: EINE Zeile, die zeigt wie viele Klicks ueber
        # welchen Erkennungs-Pfad kamen und wie viele die Sperren abgefangen
        # haben. Damit ist im Log sofort sichtbar, ob die Echo-Sperre greift.
        try:
            stats = getattr(self, '_click_stats', None)
            if stats:
                _flog(3, 'Klick-Bilanz dieser Runde',
                      **{k: str(v) for k, v in sorted(stats.items())})
        except Exception:
            pass
        self._click_stats = {}
        # Echo-Sperre rundenweise zuruecksetzen: der erste Klick der NAECHSTEN
        # Runde darf nie wegen der vorigen unterdrueckt werden (das Zeitfenster
        # allein wuerde meist reichen, der Reset macht es unabhaengig davon).
        self._last_click_pos = None
        if self._bite_seen_this_cycle:
            self._casts_without_bite = 0
        else:
            self._casts_without_bite += 1
            if (self._casts_without_bite == 3
                    or self._casts_without_bite % 10 == 0):
                _flog('-', t('fishing.no_bite_streak',
                             n=self._casts_without_bite))
        self._bite_seen_this_cycle = False
        self._best_minigame_conf = 0.0
        # Whitelist pro Runde frisch auswerten (der naechste Auswurf bringt einen
        # neuen Biss).
        self._whitelist_decided = False

    def _fire_on_catch(self):
        """Ruft den (optionalen) Counter-Hook genau einmal pro Fang. Wirft nie --
        hack.py setzt ``on_catch``; ist er None, passiert nichts (Entkopplung)."""
        callback = self.on_catch
        if callback is None:
            return
        try:
            callback()
        except Exception:
            pass

    # -- Angel-Whitelist ---------------------------------------------------

    def _whitelist_active(self):
        """True nur, wenn die Whitelist scharf ist UND die Bausteine importiert
        werden konnten. Wirft nie."""
        return bool(self.whitelist_enabled) and _fc is not None and _wl is not None

    def _read_hook(self, screenshot):
        """Liest NUR den kleinen Chat-Streifen (schnell) -> HookResult oder None.
        Defensiv: jeder Fehler -> None (Whitelist greift dann nicht)."""
        try:
            return _fc.read_hook(screenshot)
        except Exception:
            return None

    def _abort_minigame(self):
        """Bricht den aktuellen Angel-Versuch SOFORT ab und startet den Zyklus neu.

        KEIN Klick mehr (die alte FISH_WINDOW_CLOSE-Koordinate war eine falsche
        Altlast, ~55px neben dem Minispielfenster). Stattdessen: ESC druecken
        (raeumt ein evtl. offenes Minispiel weg), dann -- falls Mount aktiv -- die
        Mount-Cancel-Sequenz (auf-/absteigen, setzt den Figuren-Zustand sauber
        zurueck), und auf State 0 stellen, sodass der naechste Tick Koeder setzt +
        neu auswirft. Gibt den genutzten Weg fuers Logging zurueck. Wirft nie."""
        how = 'esc'
        try:
            _input.key('esc')                 # keyDown+keyUp atomar (ein Lease)
        except Exception:
            # Geht ESC nicht, reicht der State-Reset unten -> naechster Zyklus
            # wirft ohnehin neu aus.
            how = 'recast_only'
        # Falls Mount aktiviert: wie nach einem Fang auf-/absteigen -> sauberer
        # Neustart (Pferd -> Koeder -> Auswerfen).
        if self.mount_enabled:
            try:
                self._do_mount_cancel(mount.mount_cancel_steps(self.mount_key))
            except Exception:
                pass
        # SOFORT von vorne -- exakt das v1.6.5-Verhalten: den Timer so weit
        # ZURUECK-datieren, dass der naechste Tick INSTANT neu koedert (kein
        # bait_time-Vorlauf, keine zusaetzliche Abbruch-Pause).
        #
        # WARUM DIE PAUSE AUS v1.6.6 WIEDER WEG DARF: Sie kam, weil ESC, Koeder-
        # und Wurf-Taste sonst in DERSELBEN Sekunde standen (Live-Log
        # 2026-07-30, 07:31:04) und der Client mit "Du kannst diese Aktion nicht
        # ausfuehren, waehrend du angelst" ablehnte -- der Koeder kam nie an, der
        # Wurf lief ins Leere ("Kein Biss"). DERSELBE Release hat aber den SENSOR
        # dafuer bekommen: :func:`fishing_chat.read_action_feedback` liest genau
        # diese Ablehnung, und :meth:`_check_bait_feedback` koedert danach erneut
        # (``_BAIT_RETRY_WAIT_S``) und protokolliert es. Blind warten UND messen
        # ist doppelt gemoppelt -- nur zahlt die Pause JEDER Abbruch, waehrend
        # die Ablehnung bloss manchmal kommt.
        #
        # Am Live-Log des Testers gemessen (2026-08-11, v1.6.9): 56 % aller
        # Zyklen enden im Abbruch; die Pause kostete dort rund eine Sekunde je
        # Zyklus. Deshalb ist die Fehlerrichtung hier die guenstige: tritt die
        # Ablehnung doch auf, kostet sie EINEN protokollierten Wiederholungs-
        # versuch statt einer Pause bei jedem Abbruch -- und sie steht in der
        # Koeder-Bilanz, statt wie bis v1.6.5 unbemerkt zu bleiben.
        self.state = 0
        self.timer_action = time() - self._instant_recast_backdate()
        self._bait_pending_since = 0.0   # alter Druck ist mit dem ESC erledigt
        self._on_cycle_end()
        return how

    def _instant_recast_backdate(self):
        """Sekunden, um die der Timer nach einem Abbruch ZURUECK-datiert wird.

        Muss die groesste eingestellte Phasenzeit inklusive Jitter-Maximum
        ueberschreiten, damit der naechste Tick garantiert sofort koedert:

          * Der Jitter (+-15 %) hebt die State-0-Schwelle ueber die eingestellte
            Zeit. v1.6.5 rechnete nur ``max(...) + 1.0`` und verfehlte "sofort"
            bei grossen Zeiten knapp (bait_time 9 -> Schwelle bis 10,35 gegen
            10,0 Rueckdatierung).
          * Die Zeiten kommen als GUI-Werte und koennen TEXT sein -- deshalb
            dieselbe ``float()``-Konvertierung wie in :meth:`_roll_deadline`.
            Ohne sie stuerbe die Multiplikation mit einem TypeError, den
            :meth:`_apply_whitelist` schluckt: der State bliebe auf 3 stehen und
            der Bot haenge bis zum 15-s-Notausstieg im Minispiel.

        Wirft nie -- im Zweifel ein grosszuegiger Festwert, der jede sinnvolle
        Einstellung abdeckt.
        """
        try:
            groesste = max(float(self.bait_time), float(self.throw_time),
                           float(self.game_time))
            return groesste * (1.0 + self._TIMING_JITTER) + 1.0
        except Exception:
            return 60.0

    def _apply_whitelist(self, screenshot):
        """Wertet beim Biss den Chat-Streifen aus und bricht ab, falls der Fang
        unerwuenscht (REMOVE) oder eine Niete ist. Gibt True zurueck, wenn das
        Minispiel abgebrochen wurde (Aufrufer soll diese Runde nicht weiterspielen).

        Streng defensiv: ohne aktive Whitelist / bei jedem Fehler -> False.
        UNGEWOLLT/unsicher -> NIE abbrechen.
        """
        if not self._whitelist_active() or self._whitelist_decided:
            return False
        try:
            result = self._read_hook(screenshot)
            if result is None:
                return False

            kind = getattr(result, 'kind', _fc.NONE)
            # DIAGNOSE (temporaer): jede NEUE Chat-Erkennung loggen -> zeigt im
            # Live-Test, ob read_hook den Chat-Streifen ueberhaupt trifft
            # (Region/OCR korrekt). Dedup ueber die Signatur, kein Spam.
            sig = (kind, str(getattr(result, 'name', '')),
                   bool(getattr(result, 'confident', False)))
            if sig != self._whitelist_last_sig:
                self._whitelist_last_sig = sig
                _flog(self.state, 'WL-DBG kind=%s name=%r conf=%s'
                      % (kind, sig[1], sig[2]))
            if kind == _fc.NONE:
                # Leer WEIL nichts am Haken -- oder weil ein Overlay die Zeile
                # zudeckt? Ohne diese Unterscheidung sieht beides im Log gleich
                # aus (genau der Live-Report "Fische werden nicht ausgelesen").
                self._obstructed_diag(screenshot)
                # Noch nichts Sicheres am Haken -> naechsten Frame abwarten.
                return False

            decision = _wl.decide(result, states=self.whitelist_states,
                                  enabled=True)
            self._whitelist_decided = True

            if decision == _wl.ABORT:
                how = self._abort_minigame()
                name = str(getattr(result, 'name', '?'))
                if kind == _fc.NIETE:
                    _flog(0, t('fishing.whitelist_abort_niete', how=how))
                else:
                    _flog(0, t('fishing.whitelist_abort', name=name, how=how))
                return True

            # Gewollt -> nur bei sicherem Namen einmal vermerken (UNKNOWN still).
            if getattr(result, 'confident', False):
                _flog(3, t('fishing.whitelist_keep',
                           name=str(getattr(result, 'name', '?'))))
            return False
        except Exception:
            return False

    # -- Koeder-Nachlegen --------------------------------------------------

    def _bait_refill_active(self):
        """True nur, wenn das Nachlegen scharf ist UND die Engine importiert
        werden konnte UND ein Fenster-Capture existiert. Wirft nie."""
        return (bool(self.bait_refill_enabled) and _refill is not None
                and self.wincap is not None)

    def _bait_slot(self):
        """Quick-slot (1..8) des Koeders aus ``bait_key`` oder ``None``.

        Der Koeder liegt laut Spec in einem Quickslot; ``bait_key`` ist die Taste,
        die ihn wirft -- also genau der zu pruefende Slot. Eine Taste, die kein
        Quickslot ist (sollte die Validierung verhindern), liefert ``None`` ->
        kein Nachlegen. Wirft nie."""
        try:
            return _refill.quickslot_index(self.bait_key)
        except Exception:
            return None

    def _refill_sleep(self, seconds):
        """Interruptible Nap fuers Nachlegen: schlaeft ``seconds`` ueber das
        Stop-Signal (``StopSignal.wait``) und kehrt SOFORT zurueck, sobald ein
        Stop ansteht. Gibt ``False`` zurueck, wenn ein Stop die Nap abgeschnitten
        hat (Aufrufer bricht ab). Faellt ohne Signal auf ``time.sleep`` zurueck.
        Wirft nie."""
        sig = getattr(self, 'stop_signal', None)
        if sig is not None:
            try:
                return sig.wait(seconds)
            except Exception:
                pass
        try:
            sleep(seconds)
        except Exception:
            pass
        return True

    def _refill_should_stop(self):
        """Predicate fuer die Refill-Engine: True, sobald ein Stop ansteht
        (Stop-Signal gesetzt ODER botting bereits geraeumt). Wirft nie."""
        try:
            sig = getattr(self, 'stop_signal', None)
            if sig is not None and sig.stopped:
                return True
            return not self.botting
        except Exception:
            return False

    def _maybe_refill_bait(self, screenshot):
        """Gedrosselt: ist der Koeder-Quickslot leer, EINEN Koeder nachlegen.

        Streng defensiv + opt-in (Default AUS -> sofort raus -> byte-stabil).
        Prueft hoechstens alle ``_BAIT_REFILL_INTERVAL`` s (Aufruf nur kurz vorm
        Baiten in State 0) auf dem ohnehin geholten ``screenshot`` -- kein Extra-
        Capture, keine Last. Das Inventar muss beim Angeln OFFEN sein (kein
        I-Druck -- das Inventar wird nicht geoeffnet/geschlossen). Bei leerem Slot:
          * aus dem offenen Inventar ``refill.refill_from_inventory`` einen Koeder
            in den Quickslot ziehen;
          * Ergebnis ``'dragged'`` -> Log "nachgelegt";
          * ``'empty'`` (kein Koeder mehr im Inventar) -> Bot stoppen
            (``botting=False``) + klares Log und optionalen Popup-Hook
            (``on_bait_empty``);
          * ``'error'`` -> Log + diesmal ohne Nachlegen weiter (kein Stop).
        Wirft nie -- ein Vision-/Input-Fehler darf den Angel-Loop nie kippen.
        """
        if not self._bait_refill_active():
            # Der Nutzer WILL nachlegen (Schalter an), aber es ist blockiert
            # (Engine nicht importiert / kein Fenster-Capture) -> gedrosselt
            # melden, sonst haengt der Bot stumm mit leerem Slot. Bewusst still,
            # wenn das Nachlegen einfach ausgeschaltet ist (kein Spam).
            if self.bait_refill_enabled:
                self._bait_diag('bait-refill AN, aber inaktiv',
                                engine=(_refill is not None),
                                wincap=(self.wincap is not None))
            return
        now = time()
        too_soon = (self._last_bait_check > 0
                    and now - self._last_bait_check < self._BAIT_REFILL_INTERVAL)
        if too_soon:
            return
        self._last_bait_check = now
        try:
            slot = self._bait_slot()
            if slot is None:
                self._bait_diag('bait-refill: bait_key ist kein Quickslot',
                                bait_key=self.bait_key)
                return
            if not _refill.quickslot_is_empty(screenshot, slot):
                # Slot gilt als BELEGT -> nicht nachlegen. Beim Report "leer, legt
                # trotzdem nicht nach" verraet die gemessene (mean/std/bright) am
                # Slot-Pixel, ob der Punkt fuers Fenster falsch sitzt oder die
                # Schwellen nicht greifen (gedrosselt, kein Spam).
                stats = _refill.quickslot_probe_stats(screenshot, slot)
                if stats is not None:
                    self._bait_diag('bait-refill: Slot als belegt gelesen',
                                    slot=slot, mean=round(stats[0], 1),
                                    std=round(stats[1], 1), bright=stats[2])
                return   # Koeder noch da -> nichts tun (haeufigster Fall)

            _flog(self.state, t('fishing.bait_refill_empty_slot'))
            ox = int(getattr(self.wincap, 'offset_x', 0) or 0)
            oy = int(getattr(self.wincap, 'offset_y', 0) or 0)
            target = _refill.quickslot_screen(slot, ox, oy)
            calib = self.bait_refill_calib or _refill.DEFAULT_CALIBRATION

            # GEBUNDENE Obergrenze + interruptible: die schwere Op (Inventar
            # oeffnen + Seiten scannen + draggen) bekommt ein hartes Zeitbudget
            # UND bricht bei F6/Stop sofort ab. Klare Start-/Ende-Zeile -> der Bot
            # haengt nie stumm. ``should_stop`` faengt den Stop auch zwischen den
            # Engine-Schritten (Page-Switch/Drag) ab.
            deadline = _stopsig.Deadline(
                self._BAIT_REFILL_BUDGET, signal=getattr(self, 'stop_signal', None))
            _flog(self.state, t('fishing.bait_refill_started'),
                  budget=int(self._BAIT_REFILL_BUDGET))

            # Das Inventar ist beim Angeln IMMER offen -> KEIN I-Druck (kein
            # Oeffnen/Schliessen), direkt aus dem offenen Inventar nachlegen.
            inp = _refill_backend or pydirectinput
            result = _refill.refill_from_inventory(
                _refill.BAIT_NAMES, target, inp=inp,
                wincap=self.wincap, db=self.bait_refill_db, calib=calib,
                sleep=self._refill_sleep, should_stop=self._refill_should_stop)

            # ZEIGER WEGFAHREN -- in JEDEM Ergebnisfall (auch nach 'error'/
            # 'stopped'; der Drag kann den Zeiger auch dann auf dem Slot
            # zurueckgelassen haben). Bleibt er auf dem Quickslot stehen, deckt
            # der Item-Tooltip des Clients die Chat-Zeile zu und der Bot liest ab
            # da den Tooltip statt des Chats -- Fischname UND Koeder-Rueckmeldung
            # fallen aus (Live-Report + Messung 2026-08-09, siehe
            # refill.CURSOR_PARK_XY).
            _refill.park_cursor(inp, ox, oy, sleep=self._refill_sleep)

            if result == 'dragged':
                _flog(self.state, t('fishing.bait_refill_done'),
                      secs='{:.1f}'.format(deadline.elapsed()))
            elif result == 'empty':
                _flog(self.state, t('fishing.bait_refill_none_left'))
                self.botting = False
                self._notify_bait_empty()
            elif result == 'stopped':
                # Per F6/Stop abgebrochen -- still (der Lauf endet ohnehin); nur
                # eine knappe Diagnose-Zeile, damit der Abbruch nachvollziehbar ist.
                _flog(self.state, t('fishing.bait_refill_stopped'))
            else:   # 'error' -> diesmal ohne Nachlegen weiter (kein Stop)
                _flog(self.state, t('fishing.bait_refill_failed'))

            # Sicherheits-Decke: hat die Op das harte Budget gerissen (z. B. ein
            # nie endender Drag), KLAR melden statt stumm weiterzulaufen.
            if deadline.expired() and result not in ('stopped',):
                _flog(self.state, t('fishing.bait_refill_timeout'),
                      budget=int(self._BAIT_REFILL_BUDGET))
        except Exception:
            # Niemals den Angel-Loop kippen.
            pass

    def _bait_diag(self, message, **fields):
        """Gedrosselte Diagnose-Zeile fuers Koeder-Nachlegen (alle
        ``_BAIT_DIAG_INTERVAL`` s hoechstens eine). Reines Logging -- wirft nie,
        aendert nichts am Verhalten. Nutzt denselben _flog-Kanal wie der Rest."""
        try:
            now = time()
            if (self._last_bait_diag > 0
                    and now - self._last_bait_diag < self._BAIT_DIAG_INTERVAL):
                return
            self._last_bait_diag = now
            _flog(self.state, message, **fields)
        except Exception:
            pass

    def _obstructed_diag(self, screenshot):
        """Meldet gedrosselt, dass die Chat-Lesezone gerade VERDECKT ist.

        Ein Item-Tooltip des Clients (Zeiger auf einem Quickslot) klappt nach
        oben ueber die Chat-Zeile; der Bot liest dann Tooltip-Text statt Chat.
        Seit dem Zeiger-Park nach dem Nachlegen sollte das nicht mehr vorkommen
        -- taucht die Zeile trotzdem auf, steht der Zeiger aus einem anderen
        Grund dort (z. B. der Nutzer hat ihn selbst hingelegt), und der Report
        laesst sich am Log ablesen statt zu raten. Reines Logging, wirft nie."""
        try:
            now = time()
            if (self._last_obstructed_log > 0
                    and now - self._last_obstructed_log < self._BAIT_DIAG_INTERVAL):
                return
            # Zeitstempel VOR der Pruefung setzen: sonst drosselt nur der
            # Treffer-Fall und im Normalfall (Zone frei) liefe die zweite
            # Binarisierung in JEDEM Minispiel-Frame mit. So ist es eine
            # PRUEF-Drossel -- eine Verdeckung wird hoechstens um ein Intervall
            # spaeter gemeldet, was fuer eine Diagnosezeile folgenlos ist.
            self._last_obstructed_log = now
            if _fc.chat_zone_obstructed(screenshot):
                _flog(self.state, t('fishing.chat_zone_obstructed'))
        except Exception:
            pass

    def _check_bait_feedback(self, screenshot):
        """Liest die Client-Antwort auf den letzten Koeder-Tastendruck.

        Drei Ausgaenge:
          * BESTAETIGT -- der Koeder haengt; nur zaehlen, Ablauf unveraendert.
          * ABGELEHNT  -- der Client sagt "waehrend du angelst": es haengt KEIN
            Koeder. Vor/waehrend des Wurfs (State <= 2) wird deshalb neu
            gekoedert statt ins Leere zu werfen; laeuft dagegen schon ein
            Minispiel (State 3), wird NUR protokolliert -- ein laufender Fang
            darf nie wegen einer Chat-Zeile abgebrochen werden.
          * keine Aussage -- nach ``_BAIT_FEEDBACK_WINDOW_S`` aufgeben und
            unveraendert weiterlaufen (der Sensor bremst den Loop nie aus).

        Wirft nie -- ein Lesefehler darf den Angel-Loop nicht kippen.
        """
        if self._bait_pending_since <= 0:
            return
        now = time()
        if now - self._bait_pending_since > self._BAIT_FEEDBACK_WINDOW_S:
            self._bait_pending_since = 0.0
            return
        try:
            feedback, sig = _fc.read_action_feedback(screenshot)
        except Exception:
            return

        # Die Chat-Zeile BLEIBT stehen. Ohne diese Sperre wuerde dieselbe
        # Ablehnung in jedem Frame -- und nach dem naechsten Koeder-Versuch
        # gleich nochmal -- gewertet: der Bot wartete endlos auf eine Antwort,
        # die laengst da war. Jede Zeile darf genau EINMAL zaehlen.
        if feedback == _fc.NONE:
            return
        if sig is not None and sig == self._bait_last_feedback_sig:
            return
        self._bait_last_feedback_sig = sig

        if feedback == _fc.BAITED:
            self._bait_pending_since = 0.0
            self._bait_ok += 1
            self._bait_blocked_streak = 0
            return
        if feedback != _fc.BLOCKED:
            return          # unbekannte Antwort -> unveraendert weiterlaufen

        self._bait_pending_since = 0.0
        self._bait_blocked += 1
        self._bait_blocked_streak += 1
        if self.state > 2:
            _flog(self.state, t('fishing.bait_blocked_late'))
            return
        # Neu koedern -- aber erst nach einer Wartezeit. timer_action in die
        # ZUKUNFT setzen heisst: der State-0-Zweig zieht erst nach
        # _BAIT_RETRY_WAIT_S + bait_time wieder los.
        self.state = 0
        self.timer_action = now + self._BAIT_RETRY_WAIT_S
        _flog(0, t('fishing.bait_blocked_retry'),
              wartezeit=self._BAIT_RETRY_WAIT_S)
        if self._bait_blocked_streak >= self._BAIT_BLOCKED_WARN_AT:
            _flog(0, t('fishing.bait_blocked_repeat'),
                  anzahl=self._bait_blocked_streak)

    def _log_bait_balance(self):
        """Gedrosselte Bilanz-Zeile (alle ``_BAIT_BALANCE_EVERY`` Wuerfe).

        Macht ohne Zutun des Nutzers sichtbar, ob die Koeder wirklich sitzen --
        genau die Zahl, die bisher gefehlt hat. Wirft nie."""
        try:
            if (self._BAIT_BALANCE_EVERY <= 0
                    or self._bait_casts % self._BAIT_BALANCE_EVERY != 0):
                return
            # 'abgelehnt' ist seit dem Wegfall der Abbruch-Pause die WICHTIGSTE
            # Zahl hier: sie sagt, wie oft der Client das sofortige Neu-Koedern
            # zurueckgewiesen hat -- also was das v1.6.5-Tempo real kostet.
            _flog(self.state, t('fishing.bait_balance'),
                  wuerfe=self._bait_casts, bestaetigt=self._bait_ok,
                  abgelehnt=self._bait_blocked)
        except Exception:
            pass

    def _notify_bait_empty(self):
        """Ruft den optionalen Popup-Hook (vom RunLoop gesetzt) genau dann, wenn
        wegen leeren Koeders gestoppt wird. None -> nur Log (Entkopplung). Wirft
        nie."""
        callback = self.on_bait_empty
        if callback is None:
            return
        try:
            callback()
        except Exception:
            pass

    def _do_mount_cancel(self, steps):
        """Fuehrt die PURE Mount-Sequenz (mount.mount_cancel_steps) als
        Tastendruecke aus: ('press', key) -> keyDown/keyUp, ('sleep', s) ->
        sleep. Reiner Thin-Executor; die Logik liegt in mount.py. Wirft nie."""
        try:
            for action, value in steps:
                if action == 'press':
                    _input.key(value)         # keyDown+keyUp atomar (ein Lease)
                elif action == 'sleep':
                    sleep(value)
        except Exception:
            pass

    def set_to_begin(self, values):

        # Zeitlimit bei JEDEM Start zuruecksetzen und NUR bei positiver
        # Minutenzahl aktivieren. Sonst (Haken an, Feld "0") waere
        # ``time()-initial > 0`` sofort wahr -> der Bot wuerde direkt stoppen;
        # und ein altes Limit aus einem frueheren Lauf darf nicht haengenbleiben.
        self.end_time_enable = False
        self.end_time = 0
        if values['-ENDTIMEP-']:
            try:
                self.end_time = int(values['-ENDTIME-']) * 60
            except Exception:
                self.end_time = 0
            self.end_time_enable = self.end_time > 0

        self.bait_time = values['-BAITTIME-']
        self.throw_time = values['-THROWTIME-']
        self.game_time = values['-STARTGAME-']

        # Golden-Tuna-Feld defensiv lesen -- ein kaputter/fehlender Wert darf das
        # Angeln NIE brechen (-> Default 3 = Koeder benutzen).
        try:
            action = int(values.get('-GOLDENTUNA-', 3))
        except (TypeError, ValueError):
            action = 3
        self.golden_tuna_action = action if action in (1, 2, 3) else 3

        # Mount-Animation-Cancel defensiv aus den frozen keys lesen (Default
        # AUS/'3' -> byte-stabil). Ein fehlender/kaputter Wert darf nichts
        # brechen.
        self.mount_enabled = bool(values.get('-MOUNT-', False))
        mkey = values.get('-MOUNTKEY-', '3')
        self.mount_key = str(mkey) if mkey else '3'

        # Angel-Whitelist defensiv lesen (Default AUS -> byte-stabil). Der
        # konkrete Fisch-Zustands-Dict (whitelist_states) wird separat vom
        # RunLoop auf die Instanz injiziert (wie bait_key/cast_key); ein
        # fehlender Schluessel laesst die Whitelist einfach aus.
        self.whitelist_enabled = bool(values.get('-WHITELIST-',
                                                  self.whitelist_enabled))
        self._whitelist_decided = False

        # Koeder-Nachlegen defensiv aus den frozen keys lesen (Default AUS ->
        # byte-stabil). Die konkrete Live-Infrastruktur (bait_refill_db/_calib,
        # inventory_hotkey, on_bait_empty) injiziert der RunLoop separat auf die
        # Instanz -- ein fehlender Schluessel laesst das Nachlegen einfach aus.
        self.bait_refill_enabled = bool(values.get('-BAITREFILL-',
                                                    self.bait_refill_enabled))
        # Drossel pro Lauf zuruecksetzen -> direkt beim ersten Baiten geprueft.
        self._last_bait_check = 0.0

        # FRUEH loggen -- noch VOR dem Fenster-Capture, damit der Start auch dann
        # in der Console steht, wenn das Spielfenster (noch) nicht gefunden wird
        # (sonst wuerde diese Zeile bei einem Capture-Fehler nie erreicht).
        _flog(0, t('fishing.started'), bait=self.bait_time,
              throw=self.throw_time, game=self.game_time,
              golden_action=self.golden_tuna_action,
              stop_after_min=(self.end_time // 60 if self.end_time_enable else 0))

        # Defensiv: konnten die Vorlagenbilder geladen werden? In der EXE waren sie
        # frueher None (nackter Pfad) -> Minispiel nie erkannt. Jetzt klar melden.
        if self.needle_img is None or self.needle_img_clock is None:
            _flog(0, t('fishing.needles_missing'),
                  fiss=(self.needle_img is None),
                  clock=(self.needle_img_clock is None))

        try:
            self.wincap = WindowCapture(constants.GAME_NAME)
        except Exception as exc:
            _flog(0, t('fishing.game_window_not_found'),
                  fenster=constants.GAME_NAME, detail=str(exc))
            raise
        self.state = 0
        self.initial_time = time()
        self.timer_action = time()
        # Selbstdiagnose pro Lauf zuruecksetzen.
        self._bite_seen_this_cycle = False
        self._casts_without_bite = 0
        # Koeder-Bilanz pro Lauf frisch zaehlen (sonst summierte ein zweiter
        # Start die Zahlen des ersten auf und die Bilanz waere wertlos).
        self._bait_pending_since = 0.0
        self._bait_ok = 0
        self._bait_blocked = 0
        self._bait_blocked_streak = 0
        self._bait_casts = 0
        self._bait_last_feedback_sig = None

        # Tasten (Koeder/Auswerfen) brauchen eine echte Haltezeit, sonst sieht
        # DirectInput sie nie. Ein vorheriger Inventar-Scan kann PAUSE auf 0,05
        # gesenkt haben (ok fuer Maus, zu kurz fuer die Tastatur) -> hier den
        # bewaehrten 0,1-Wert (= v1.1.0-Default) fuer den ganzen Angel-Lauf erzwingen.
        _input.set_pause(0.1)

        # DEBUG-Klick-Tracker mit der Live-Fenstergeometrie verdrahten (Quelle
        # fuer die OFFSET_STALE-Erkennung). Reines Diagnose-Logging -- wirft nie.
        self._arm_click_tracker()

        mouse_x = int(self.FISH_WINDOW_POSITION[0] + self.wincap.offset_x + 200)
        mouse_y = int(self.FISH_WINDOW_POSITION[1] + self.wincap.offset_y + 200)

        _input.click(mouse_x, mouse_y, button='right', tag='focus')

    def _arm_click_tracker(self):
        """Verdrahtet den DEBUG-Klick-Tracker mit der Live-Fenstergeometrie:
        Quelle fuer die OFFSET_STALE-Erkennung ist der gespeicherte Offset
        (``wincap.offset_x/y``) vs. das aktuelle ``GetWindowRect``. Reines
        Diagnose-Logging, streng defensiv -- wirft nie und veraendert nichts am
        Klick-Verhalten.
        """
        if click_tracker is None:
            return
        try:
            wincap = getattr(self, 'wincap', None)
            hwnd = getattr(wincap, 'hwnd', None)
            cropped_x = int(getattr(wincap, 'cropped_x', 0) or 0)
            cropped_y = int(getattr(wincap, 'cropped_y', 0) or 0)
            get_rect = None
            if hwnd:
                import win32gui
                get_rect = lambda: win32gui.GetWindowRect(hwnd)
            click_tracker.configure(get_rect=get_rect,
                                    cropped=(cropped_x, cropped_y))
        except Exception:
            pass

    # -- ANGEL-FIX: Welt-Klick am Minispiel-Ende verhindern ----------------
    def _minigame_recheck_gone(self):
        """True gdw. das Minispiel (Uhr) UNMITTELBAR vor dem Fischklick auf einem
        FRISCHEN Screenshot KLAR nicht mehr aktiv ist.

        Hintergrund: ``detected_end`` stammt vom Screenshot am Tick-ANFANG; der
        physische Klick faellt ~0,1-0,3 s spaeter (PAUSE + moveTo). Endet das
        Minispiel genau in diesem Fenster, traefe der Linksklick die Wasser-
        flaeche dahinter -> der Char laeuft ins Wasser. Darum hier ein zweiter,
        taufrischer Blick mit DERSELBEN Uhr-NCC-Logik + Schwelle (>0.9) wie
        ``detect_minigame``/``detected_end``.

        FAIL-SAFE ('im Zweifel klicken'): NUR ein eindeutig berechnetes
        'Uhr-Score <= 0.9' liefert True (Klick unterdruecken). Ausgeschalteter
        Schalter, fehlender/leerer Screenshot, nicht auswertbarer NCC (ok=False,
        z.B. fehlende Vorlage/Formabweichung) ODER jede Exception -> False (normal
        klicken). So kann der Re-Check einen legitimen Fang NIE faelschlich
        verhindern. Wirft nie.
        """
        # Schalter M2FB_MINIGAME_RECHECK: Default AN ('1'); '0'/off/false/no =>
        # alter Zustand (Re-Check aus -> immer klicken).
        try:
            val = os.environ.get('M2FB_MINIGAME_RECHECK', '').strip().lower()
        except Exception:
            val = ''
        if val in ('0', 'off', 'false', 'no'):
            return False
        # Frischen Screenshot holen -- scheitert das, im Zweifel klicken.
        try:
            screenshot = self.wincap.get_screenshot()
        except Exception:
            return False
        if screenshot is None:
            return False
        # Denselben Uhr-Crop bilden wie runHack (detect_end_img) und mit DERSELBEN
        # NCC-Logik/Schwelle bewerten. ok=False (Form-/Typ-/Vorlagen-Problem) ist
        # UNSICHER -> klicken; nur ein sauber berechneter Score <= 0.9 heisst 'weg'
        # (Spiegel zu detect_minigame: dort ist 'aktiv' == max_val > 0.9).
        try:
            x0 = self.FISH_WINDOW_POSITION[0]
            y0 = self.FISH_WINDOW_POSITION[1]
            x1 = x0 + self.FISH_WINDOW_SIZE[0]
            y1 = y0 + self.FISH_WINDOW_SIZE[1]
            crop = screenshot[y0:y1, x0:x1]
            ok, max_val, _ = _match_template_max(crop, self.needle_img_clock)
        except Exception:
            return False
        if not ok:
            return False
        return max_val <= 0.9

    def _click_diag(self, mouse_x, mouse_y):
        """Zusatzfelder fuer die Klick-Zeile im Debug-Log: WARUM dieser Punkt
        (Erkennungs-Pfad aus :meth:`detect`), wie sicher die Vorlage sass, wie
        schnell/weit das Ziel gegen den Bezugspunkt lag, wie alt dieser
        Bezugspunkt schon ist -- und wie weit/lange der zuletzt ZUGESTELLTE Klick
        entfernt liegt (macht das Echo-Muster direkt im Log sichtbar).

        grund-Werte: ``ruht`` (Fund exakt auf dem Bezugspunkt), ``vorhalt``
        (bewusst FISH_VELO_PREDICT px daneben geklickt), ``totbereich`` /
        ``erster-fund`` / ``kein-fisch`` / ``vorlage-fehlt`` (keine Klick-Pfade).

        Reine Diagnose -- wirft nie; im Fehlerfall fehlen nur die Felder.
        """
        out = {}
        try:
            info = getattr(self, '_last_detect_info', None) or {}
            out['grund'] = info.get('grund', '?')
            for key, fmt in (('conf', '{:.2f}'), ('velo', '{:.0f}'),
                             ('dist', '{:.1f}'), ('ref_alter', '{:.2f}')):
                val = info.get(key)
                if val is not None:
                    out[key] = fmt.format(val)
            last = self._last_click_pos
            if last is not None:
                dx = mouse_x - last[0]
                dy = mouse_y - last[1]
                out['abstand_vorher'] = '{:.1f}'.format((dx * dx + dy * dy) ** 0.5)
                out['t_vorher'] = '{:.2f}'.format(time() - self._last_click_time)
        except Exception:
            pass
        return out

    def _count_click(self, key):
        """Zaehlt die Klick-Entscheidungen der laufenden Runde (Bilanz-Zeile in
        :meth:`_on_cycle_end`). Wirft nie."""
        try:
            stats = getattr(self, '_click_stats', None)
            if not isinstance(stats, dict):
                stats = {}
                self._click_stats = stats
            stats[key] = stats.get(key, 0) + 1
        except Exception:
            pass

    def _is_echo_click(self, mouse_x, mouse_y):
        """True gdw. dieser Klick ein Nachzuegler auf die zuletzt geklickte Stelle
        ist: Abstand <= ``FISH_ECHO_RADIUS_PX`` UND hoechstens
        ``FISH_ECHO_WINDOW_S`` seit dem letzten zugestellten Klick.

        Schalter ``M2FB_ECHO_GUARD``: Default AN ('1'); '0'/off/false/no => alter
        Zustand (Sperre aus -> immer klicken).

        FAIL-SAFE: jede Unsicherheit (kein Vorgaenger, Fenster abgelaufen, defekte
        Werte, Exception) -> False = klicken. Die Sperre kann einen echten Fang
        damit nie verhindern, sondern hoechstens einen Klick um Frames verzoegern.
        Wirft nie.
        """
        try:
            val = os.environ.get('M2FB_ECHO_GUARD', '').strip().lower()
        except Exception:
            val = ''
        if val in ('0', 'off', 'false', 'no'):
            return False
        try:
            last = self._last_click_pos
            if last is None:
                return False
            if (time() - self._last_click_time) > self.FISH_ECHO_WINDOW_S:
                return False
            dx = mouse_x - last[0]
            dy = mouse_y - last[1]
            return (dx * dx + dy * dy) <= self.FISH_ECHO_RADIUS_PX ** 2
        except Exception:
            return False

    def _deliver_minigame_click(self, mouse_x, mouse_y):
        """Stellt den Minispiel-Fischklick zu -- ABER mit dem ANGEL-FIX-Re-Check
        (:meth:`_minigame_recheck_gone`) UNMITTELBAR davor: ist das Minispiel im
        frischen Frame KLAR weg, wird der Klick UNTERDRUECKT (gar nicht gesendet)
        und als ``SUPPRESSED: minigame-weg`` geloggt; sonst normal geklickt.

        Byte-identisch zum Altverhalten, wenn der Schalter aus ist ODER das
        Minispiel noch aktiv/unsicher ist (dann klickt es exakt wie zuvor).
        Rueckgabe: True = geklickt, False = unterdrueckt.
        """
        # Diagnose VOR dem Zustellen bilden -- danach ist der Bezugspunkt schon
        # ueberschrieben und der Abstand zum Vorgaenger waere 0.
        diag = self._click_diag(mouse_x, mouse_y)
        # ZUERST die billige Echo-Pruefung (kein Screenshot noetig): der Fisch haengt
        # dann schon am Haken, die Uhr laeuft aber weiter -> der Uhr-Re-Check unten
        # wuerde diesen Klick durchlassen.
        if self._is_echo_click(mouse_x, mouse_y):
            if click_tracker is not None:
                click_tracker.record_suppressed(mouse_x, mouse_y,
                                                tag='minigame',
                                                reason='echo-klick')
            _flog(3, 'Minispiel-Fischklick UNTERDRUECKT: Echo auf die zuletzt '
                     'geklickte Stelle (Nachzuegler nach dem Fang -> Welt-Klick '
                     'verhindert)', x=mouse_x, y=mouse_y, **diag)
            self._count_click('unterdrueckt-echo')
            return False
        if self._minigame_recheck_gone():
            # Klick UNTERDRUECKT: Uhr weg -> ein Klick fiele in die Welt.
            if click_tracker is not None:
                click_tracker.record_suppressed(mouse_x, mouse_y,
                                                tag='minigame',
                                                reason='minigame-weg')
            _flog(3, 'Minispiel-Fischklick UNTERDRUECKT: Uhr im frischen Frame '
                     'weg (Welt-Klick verhindert)', x=mouse_x, y=mouse_y, **diag)
            self._count_click('unterdrueckt-uhr-weg')
            return False
        _input.click(mouse_x, mouse_y, tag='minigame')
        self._last_click_pos = (mouse_x, mouse_y)
        self._last_click_time = time()
        _flog(3, t('fishing.fish_clicked'), x=mouse_x, y=mouse_y, **diag)
        self._count_click('geklickt-' + str(diag.get('grund', '?')))
        return True

    def runHack(self):
        screenshot = self.wincap.get_screenshot()

        # Einmal schneiden: roher Crop (fuer detect_end) + HSV-gefilterter Crop.
        x0 = self.FISH_WINDOW_POSITION[0]
        y0 = self.FISH_WINDOW_POSITION[1]
        x1 = x0 + self.FISH_WINDOW_SIZE[0]
        y1 = y0 + self.FISH_WINDOW_SIZE[1]
        detect_end_img = screenshot[y0:y1, x0:x1]
        crop_img = self.hsv_filter.apply_hsv_filter(detect_end_img)

        cv.putText(crop_img, 'FPS: ' + str(1/(time() - self.loop_time))[:2],
                (10, 200), cv.FONT_HERSHEY_SIMPLEX,  0.5, (0, 255, 0), 2)
        cv.putText(crop_img, 'State: ' + str(self.state) + ' ' + str(time() - self.timer_action)[:5],
                (10, 160), cv.FONT_HERSHEY_SIMPLEX,  0.5, (0, 255, 0), 2)
        self.loop_time = time()

        # DEBUG-Klick-Tracker: Tick-Referenzzeit + Zustand/Offset stempeln (Basis
        # fuer das Delta-t Screenshot->Klick jeder folgenden Aktion). Billig,
        # reines Logging -- wirft nie. detected_end folgt weiter unten via set_gate.
        if click_tracker is not None:
            click_tracker.mark_tick(
                state=self.state,
                offset_x=getattr(self.wincap, 'offset_x', None),
                offset_y=getattr(self.wincap, 'offset_y', None))

        # ANGEL-WHITELIST -- ENTKOPPELT vom Minispiel: ab dem Auswerfen wird JEDEN
        # Frame der kleine Chat-Streifen ausgewertet. Wiederverwendung des oben
        # ohnehin geholten ``screenshot`` (KEIN Extra-Capture) + winzige OCR auf
        # ~290x17px -> guenstig, also volle Loop-Frequenz statt Throttle = maximaler
        # Speed ohne Delay. So wird "am Haken"/Niete erkannt, SOBALD es im Chat
        # steht (oft vor dem Minispiel), und unerwuenscht sofort abgebrochen ->
        # diese Runde hier beenden. Erst ab State 2 (nach dem Auswurf); _apply_
        # whitelist prueft "aktiv" + "schon entschieden" selbst (aus = byte-stabil).
        if self.state >= 2 and self._apply_whitelist(screenshot):
            return crop_img

        daily = self.detect_daily_reward(screenshot)

        if daily:
            field = self.golden_tuna_action
            ox, oy = self.wincap.offset_x, self.wincap.offset_y
            mouse_x = int(ox + self.GOLDEN_TUNA_X)
            mouse_y = int(oy + self.GOLDEN_TUNA_Y[field])
            _input.click(mouse_x, mouse_y, tag='daily')
            # Bestaetigungs-Fenster SCHARF schalten statt blind zu klicken: es
            # kommt erst mit der Server-Antwort (der alte Sofort-Klick feuerte
            # vorher ins Leere -> Dialog blieb offen). _until = pro-Dialog-Fenster
            # (wird bei JEDEM gefundenen Dialog verlaengert), _hard = absolute
            # Obergrenze als Backstop gegen endlose Verlaengerung.
            now = time()
            # Harte Deadline NUR an der steigenden Flanke einer Episode setzen
            # (nicht jeden Frame neu) -- sonst haelt ein klebender daily-Zustand
            # (dauerhaft schwarze Ecke) den Backstop endlos am Leben. Absolut ab
            # dem ERSTEN daily-Frame der Episode; _until darauf gedeckelt.
            if now >= getattr(self, '_golden_confirm_hard', 0.0):
                self._golden_confirm_hard = now + self.GOLDEN_CONFIRM_MAX_S
            self._golden_confirm_until = min(now + self.GOLDEN_CONFIRM_WAIT_S,
                                             self._golden_confirm_hard)
            # Weltklick-Sperre an ECHTER Evidenz (Popup steht diesen Frame) + Grace.
            self._golden_suppress_until = now + self.GOLDEN_SUPPRESS_GRACE_S
            if now - getattr(self, '_last_daily_log', 0) > 3:
                self._last_daily_log = now
                _flog(self.state, t('fishing.golden_tuna_clicked'),
                      field=field, x=mouse_x, y=mouse_y)
        elif time() < getattr(self, '_golden_confirm_until', 0.0):
            # Auf den Bestaetigungs-Dialog warten und OK erst klicken, wenn er
            # WIRKLICH im Frame steht (Template der Knopf-Leiste). Der Dialog
            # wandert je nach Textlaenge -> geklickt wird die GEFUNDENE Mitte.
            # WICHTIG (User-Report 2026-07-22): der Server schickt teils MEHRERE
            # Dialoge nacheinander (Buff-/Ergebnis-Meldung), egal ob ein Buff
            # faellt -> nach jedem OK-Klick wird das Fenster VERLAENGERT (bis zur
            # harten Deadline), damit auch der 2./3. Dialog abgeraeumt wird statt
            # offen zu bleiben (offener Dialog = Bot klickt in die Welt = Char
            # laeuft vor). Cooldown verhindert 60 Klicks/s auf denselben Dialog.
            found, _score, point = self.detect_golden_confirm(screenshot)
            now = time()
            cooldown_ok = (now - getattr(self, '_last_confirm_click', 0.0)
                           > self.GOLDEN_CONFIRM_CLICK_COOLDOWN_S)
            if found:
                # Dialog steht diesen Frame -> Weltklick-Sperre (an ECHTER
                # Evidenz) auffrischen, unabhaengig vom Cooldown des OK-Klicks.
                self._golden_suppress_until = now + self.GOLDEN_SUPPRESS_GRACE_S
            if found and point is not None and cooldown_ok:
                ox, oy = self.wincap.offset_x, self.wincap.offset_y
                ok_x = int(ox + point[0])
                ok_y = int(oy + point[1])
                _input.click(ok_x, ok_y, tag='confirm')
                self._last_confirm_click = now
                # Fenster verlaengern -- aber nie ueber die harte Deadline hinaus.
                self._golden_confirm_until = min(
                    now + self.GOLDEN_CONFIRM_WAIT_S,
                    getattr(self, '_golden_confirm_hard', now))
                if now - getattr(self, '_last_confirm_log', 0) > 3:
                    self._last_confirm_log = now
                    _flog(self.state, t('fishing.golden_tuna_confirmed',
                                        x=ok_x, y=ok_y))

        # Verify total time

        if self.end_time_enable and time() - self.initial_time > self.end_time:
            _flog(self.state, t('fishing.stop_time_limit'),
                  minutes=self.end_time // 60)
            self.botting = False

        # KOEDER-RUECKMELDUNG: hat der Client den letzten Koeder-Tastendruck
        # angenommen oder abgelehnt? Ohne offenen Druck sofort wieder raus.
        # Muss VOR der State-Maschine laufen: lehnte der Client ab, stellt die
        # Pruefung auf State 0 zurueck, bevor hier ins Leere geworfen wird.
        self._check_bait_feedback(screenshot)

        # State to click put the bait in the rod

        if self.state == 0:

            # KOEDER-NACHLEGEN (opt-in, Default AUS -> no-op): vor dem Baiten den
            # Koeder-Quickslot pruefen und ggf. EINEN Koeder aus dem Inventar
            # nachlegen (gedrosselt; reuse des ohnehin geholten screenshot). Ist
            # kein Koeder mehr da, stoppt _maybe_refill_bait den Bot selbst.
            self._maybe_refill_bait(screenshot)

            if time() - self.timer_action > self._roll_deadline(self.bait_time):
                _input.key(self.bait_key)     # keyDown+keyUp atomar (ein Lease)
                self.state = 1
                self.timer_action = time()
                # Ab jetzt die Client-Antwort auf DIESEN Druck erwarten
                # (_check_bait_feedback wertet sie in den naechsten Frames aus).
                self._bait_pending_since = self.timer_action
                # Neuer Wurf -> Whitelist darf diesen Fang frisch bewerten.
                self._whitelist_decided = False
                self._whitelist_last_sig = None
                _flog(1, t('fishing.bait_set'))

        # State to throw the bait

        if self.state == 1:
            if time() - self.timer_action > self._roll_deadline(self.throw_time):
                _input.key(self.cast_key)     # keyDown+keyUp atomar (ein Lease)
                self.state = 2
                self.timer_action = time()
                self._bait_casts += 1
                _flog(2, t('fishing.cast_out'))
                self._log_bait_balance()

        # Delay to start the clicks

        if self.state == 2:
            if time() - self.timer_action > self._roll_deadline(self.game_time):
                self.state = 3
                self.timer_action = time()
                _flog(3, t('fishing.minigame_phase_start'))

        # Countdown to finish the state

        detected_end = self.detect_minigame(detect_end_img)

        # DEBUG-Klick-Tracker: Minispiel-Gate fuer den kommenden Fischklick
        # nachziehen (reines Logging, wirft nie).
        if click_tracker is not None:
            click_tracker.set_gate(detected_end)

        if self.state == 3:

            # Merken, ob in DIESER Angel-Runde ueberhaupt ein echtes Minispiel
            # (Uhr) erschien -- trennt "echte Runde beendet" von "kein Biss".
            if detected_end:
                self._bite_seen_this_cycle = True

            # (Whitelist-Auswertung laeuft jetzt ENTKOPPELT am Anfang von runHack,
            # jeden Frame ab State 2 -- nicht mehr hier ans Minispiel gekoppelt.)

            if time() - self.timer_action > 15:
                self.timer_action = time()
                self.state = 0
                _flog(0, t('fishing.minigame_timeout'))
                self._on_cycle_end()
            if time() - self.timer_action > 5 and detected_end is False:
                self.timer_action = time()
                self.state = 0
                # SMART: echtes Rundenende vs. "nie ein Minispiel gesehen".
                if self._bite_seen_this_cycle:
                    _flog(0, t('fishing.minigame_finished'))
                    # BESTAETIGTER Fang: Counter-Hook feuern (einmal) + optional
                    # die Fang-Animation per Mount-Toggle abbrechen. Beides streng
                    # defensiv -- darf den Angel-Loop nie kippen.
                    self._fire_on_catch()
                    if self.mount_enabled:
                        self._do_mount_cancel(mount.mount_cancel_steps(
                            self.mount_key))
                else:
                    _flog(0, t('fishing.no_bite'))
                self._on_cycle_end()

        # make the click

        # Waehrend ein Golden-Tuna-Modal (Popup ODER Bestaetigungsdialog) steht,
        # KEINE Minispiel-/Weltklicks: der Fischklick traefe sonst HINTER den
        # Dialog in die Welt -> ungewollte Vorwaertsbewegung (User-Report
        # 2026-07-22). Die Sperre haengt an TATSAECHLICHER Modal-Evidenz + kurzer
        # Grace (_golden_suppress_until), NICHT am generoesen Klick-Fenster --
        # sonst blockt ein spurioeser daily-False-Positive (schwarze Ecke) das
        # Angeln 10-25s. Das Confirm-Fenster (_golden_confirm_until) raeumt
        # parallel die Dialoge per OK-Klick ab.
        in_golden_confirm = time() < getattr(self, '_golden_suppress_until', 0.0)

        if (time() - self.timer_mouse) > 0.3 and self.state == 3 \
                and detected_end and not in_golden_confirm:
            
            # Detect the fish            

            square_pos = self.detect(crop_img)

            if square_pos:

                # Recalculate the mouse position with the fish position

                pos_x = square_pos[0]
                pos_y = square_pos[1]

                center_x = self.FISH_WINDOW_SIZE[0]/2
                center_y = self.FISH_WINDOW_SIZE[1]/2

                mouse_x = int(pos_x)
                mouse_y = int(pos_y)

                # Verify if the fish is in range

                d = self.FISH_RANGE**2 - ((center_x-mouse_x)**2 + (center_y-mouse_y)**2)

                # Make the click

                if (d > 0):
                    self.timer_mouse = time()

                    mouse_x = int(pos_x + self.FISH_WINDOW_POSITION[0] + self.wincap.offset_x)
                    mouse_y = int(pos_y + self.FISH_WINDOW_POSITION[1] + self.wincap.offset_y)

                    # ANGEL-FIX: UNMITTELBAR vor dem physischen Fischklick nochmal
                    # auf einem FRISCHEN Screenshot pruefen, ob das Minispiel noch
                    # aktiv ist. Ist die Uhr weg, wuerde der Linksklick die Welt
                    # dahinter treffen -> Char laeuft ins Wasser. Fail-safe: im
                    # Zweifel klicken (siehe _minigame_recheck_gone).
                    self._deliver_minigame_click(mouse_x, mouse_y)

        return crop_img
