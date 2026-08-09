# -*- coding: utf-8 -*-
"""Auto-refill: drag a bait into the quick-slot / a puzzle box onto the board.

This is the PURE brain + the input PRIMITIVE of the refill automation, kept free
of any live dependency (no ``pydirectinput``, no ``WindowCapture``) so it is unit
tested headlessly; the live loop injects the input API + the screenshot. The two
things that genuinely need the live window -- the exact quick-slot drop pixel and
the drag timing -- are isolated as the tunables ``QUICKSLOT_XY`` / ``DRAG_*``.

Game runs FIXED at 800x600, so every UI element sits at a constant client pixel;
the only per-run variable is the window's top-left on screen (``offset_x/y``,
exactly what fishingbot/puzzle already add to every click).

Quick-slot model (per the spec): exactly 8 slots, keys ``1 2 3 4`` (slots 1-4)
and ``F1 F2 F3 F4`` (slots 5-8) -- nothing else. The configured bait key both
selects the slot to drag INTO and is the key fishing presses to bait the rod.
"""

from inventory.constants import (DEFAULT_CALIBRATION, INPUT_SETTLE_S,
                                 MATCH_THRESHOLD)
from inventory.grid import lattice_from_calibration

try:  # pragma: no cover - numpy present in production
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

# The only 8 valid quick-slot keys (index 0 -> slot 1, ... index 7 -> slot 8).
QUICKSLOT_KEYS = ('1', '2', '3', '4', 'f1', 'f2', 'f3', 'f4')

# Drop-pixel CENTRE of each quick-slot in the 800x601 client (before the window
# offset). RE-MEASURED from a real live capture (live_capture.png, 800x601 CLIENT
# -- NOT the 802x632 reference): the quick-slot belt sits along the bottom edge,
# split by a central chevron divider into 1-4 (left) and 5-8 (right). The clean
# periodic slot borders on the empty right half land at x=455,487,519,551,583
# (pitch 32px), bracketing slots 5-8 at centres 471/503/535/567; the left half
# borders at 316/348/380/412/444 bracket slots 1-4 at 332/364/396/428. Row centre
# y~582 (icon interior spans y~568..596). The bait stack "47" sat in slot 2 here.
QUICKSLOT_XY = {
    1: (332, 582), 2: (364, 582), 3: (396, 582), 4: (428, 582),
    5: (471, 582), 6: (503, 582), 7: (535, 582), 8: (567, 582),
}

# Obergrenze der Match-Distanz fuer ein Item, das der Bot ANFASSEN darf (siehe
# find_first). Bewusst der "sicherer Treffer"-Wert des Matchers -- die
# grosszuegigere margin-primary-Ausnahme gilt nur fuer die Anzeige.
REFILL_MAX_DISTANCE = MATCH_THRESHOLD

# Item names eligible for each refill (recognised by the inventory engine).
BAIT_NAMES = ('Worm',)
BOX_NAMES = ('Fischpuzzlebox', 'Fischpuzzlebox_Deluxe')
# Getrennte Namen pro PUZZLE-Box-Slot: die STANDARD-Box darf NUR in den unteren
# Standard-Slot, die DELUXE-Box NUR in den oberen Deluxe-Slot -- nie vertauscht.
# (``find_first`` matcht ``s.name in want``, also findet ein 1-Tupel ausschliesslich
# genau diese Box -> nie das jeweils andere Item.)
BOX_STD_NAMES = ('Fischpuzzlebox',)
BOX_DELUXE_NAMES = ('Fischpuzzlebox_Deluxe',)


def box_refill_due(streak, *, min_streak, done, max_done):
    """Pure Entscheidung fuers Puzzle-Box-Nachlegen (headless testbar).

    ``True`` nur, wenn die Box als leer gilt (``streak`` leere getpiece IN FOLGE
    >= ``min_streak``) UND die Sicherheits-Obergrenze noch nicht erreicht ist
    (``done < max_done``). Streak-basiert statt Slot-OCR, weil das wiederholte
    Ausbleiben eines Steins das robusteste "Box leer"-Signal des Spiels ist.
    Defensiv: nicht-numerische Eingaben -> ``False`` (nie nachlegen im Zweifel)."""
    try:
        return int(streak) >= int(min_streak) and int(done) < int(max_done)
    except (TypeError, ValueError):
        return False

# Inventory pages in scan order, and the grid shape.
PAGE_ORDER = ('I', 'II', 'III', 'IV')

# Drag timing (seconds) -- tunable on the live window.
DRAG_STEPS = 12        # intermediate moves so the game registers the drag
DRAG_SETTLE = INPUT_SETTLE_S   # pause after press / before release (speed knob)


def quickslot_index(key):
    """1..8 for a valid quick-slot key (case-insensitive), else ``None``."""
    try:
        return QUICKSLOT_KEYS.index(str(key).strip().lower()) + 1
    except (ValueError, AttributeError):
        return None


def is_quickslot_key(key):
    """True iff ``key`` is one of the 8 allowed quick-slot keys."""
    return quickslot_index(key) is not None


def quickslot_screen(slot_1to8, offset_x=0, offset_y=0):
    """Screen ``(x, y)`` to drop an item INTO quick-slot ``slot_1to8`` (1..8)."""
    cx, cy = QUICKSLOT_XY[int(slot_1to8)]
    return (int(offset_x + cx), int(offset_y + cy))


def inventory_slot_screen(row, col, offset_x=0, offset_y=0,
                          calib=DEFAULT_CALIBRATION):
    """Screen ``(x, y)`` of the CENTRE of inventory slot ``(row, col)``.

    Page-independent (switching tabs does not move the grid); the caller opens
    the right page first. Derived from the calibration grid (origin + pitch) so
    it tracks the user's own calibration, + the window offset like every other
    click in the bot.
    """
    lat = lattice_from_calibration(calib)
    ox, oy = lat.origin
    px, py = lat.pitch
    x = ox + col * px + px // 2
    y = oy + row * py + py // 2
    return (int(offset_x + x), int(offset_y + y))


def find_first(inv, names, pages=PAGE_ORDER):
    """First slot holding one of ``names``, in PAGE order then row-major.

    Returns ``(page, row, col)`` or ``None``. This is the documented refill
    order: inventory pages I->IV, each slot 1..45 top-to-bottom. Works on any
    object exposing ``pages -> {page: [SlotResult]}``.

    STRENGER ALS DIE ANZEIGE: ein Slot, der nur ueber die margin-primary-
    Ausnahme als erkannt gilt (Distanz zwischen ``MATCH_THRESHOLD`` und
    ``MARGIN_PRIMARY_MAX_DIST``), wird hier NICHT angefasst. Real gemessen
    (2026-08-05): ein bronzenes Abzeichen lief mit Distanz 29,5 als 'Worm'.
    Solange der echte Koeder-Stapel existiert, gewinnt der zeilenweise -- ist er
    aufgebraucht, haette der Bot das Abzeichen in den Koeder-Slot gezogen und
    weiter ins Leere geworfen, statt ehrlich "kein Koeder mehr" zu melden.
    Fuer die reine ANZEIGE bleibt die Ausnahme unveraendert; streng ist nur,
    was der Bot tatsaechlich ANFASST -- dort ist ein Fehlgriff teuer.
    """
    want = set(names)
    page_map = getattr(inv, 'pages', {}) or {}
    for page in pages:
        slots = page_map.get(page) or ()
        for s in slots:
            if getattr(s, 'state', None) != 'item':
                continue
            if getattr(s, 'name', None) not in want:
                continue
            dist = getattr(s, 'distance', None)
            if dist is not None and dist > REFILL_MAX_DISTANCE:
                # Sichtbar verwerfen: sonst sieht der Nutzer nur "kein Koeder
                # gefunden" und raetselt, obwohl ein Kandidat da war.
                try:
                    from debuglog import log as _dbg
                    _dbg.event('refill', 'Kandidat verworfen (zu unsicher): '
                               'Seite {} R{}C{} {} Distanz {:.1f} > {:.1f}'
                               .format(page, getattr(s, 'row', '?'),
                                       getattr(s, 'col', '?'),
                                       getattr(s, 'name', '?'), float(dist),
                                       float(REFILL_MAX_DISTANCE)))
                except Exception:
                    pass
                continue
            return (page, int(s.row), int(s.col))
    return None


def summarize_inventory(inv, pages=PAGE_ORDER):
    """Kompakte Debug-Zusammenfassung des Scans: pro Seite die erkannten Item-
    Namen + die Zahl NICHT erkannter (belegter, aber un-klassifizierter) Slots.

    Genau das fehlte bei "keine Box gefunden": eine present-aber-``unknown``
    klassifizierte Box taucht in keiner Item-Liste auf, wohl aber als ``?N``
    (unbekannt) -- so ist sofort sichtbar, ob die Box GAR NICHT da ist oder nur
    nicht ERKANNT wird. Rein lesend, wirft nie."""
    page_map = getattr(inv, 'pages', {}) or {}
    parts = []
    for page in pages:
        slots = page_map.get(page) or ()
        names = []
        unknown = 0
        for s in slots:
            st = getattr(s, 'state', None)
            if st == 'item':
                names.append(str(getattr(s, 'name', '?')))
            elif st == 'unknown':
                unknown += 1
        seg = '%s:[%s]' % (page, ','.join(names) if names else '-')
        if unknown:
            seg += '+?%d' % unknown
        parts.append(seg)
    return ' '.join(parts)


def _looks_like_grid_mislock(inv, pages=PAGE_ORDER, min_unknown=10):
    """``True``, wenn der Scan auf KEINER Seite auch nur EIN Item erkannt hat,
    aber viele belegte-aber-unklassifizierte Slots sah.

    Das ist die Signatur eines verschobenen Rasters (``I:[-]+?45 II:[-]+?45
    ...``): bei einem echt leeren Beutel sind die Slots ``empty``, nicht
    ``unknown``, und bei einem korrekt gerasteten vollen Beutel wird praktisch
    immer mindestens ein Item erkannt. Rein lesend, wirft nie -> ``False`` im
    Zweifel (dann bleibt es beim bisherigen Verhalten).

    ABGRENZUNG zu :func:`interface.inventory_io._is_all_unknown` (aehnliche
    Signatur, ANDERE Deutung -- bitte NICHT zusammenlegen): jenes prueft eine
    QUOTE und wertet die Lage als "Inventar wurde zugeklappt", inklusive "gar
    keine Seiten gescannt" -> True. Beides waere hier falsch: der Refill hat das
    Inventar per Open-Probe schon als offen verifiziert, und ein leerer Scan darf
    keinen Zweit-Scan ausloesen. Darum absolute Untergrenze statt Quote und
    ``False`` bei leerem Scan. Liegt der Fall doch mal anders (Inventar schliesst
    mitten im Scan), kostet der Irrtum genau EINEN zusaetzlichen Scan -- das
    Ergebnis bleibt 'empty' wie bisher."""
    try:
        page_map = getattr(inv, 'pages', {}) or {}
        unknown = 0
        for page in pages:
            for s in page_map.get(page) or ():
                st = getattr(s, 'state', None)
                if st == 'item':
                    return False           # irgendwas wurde erkannt -> kein Mislock
                if st == 'unknown':
                    unknown += 1
        return unknown >= int(min_unknown)
    except Exception:
        return False


def plan_refill(inv, names):
    """Decide the next refill action from a scan.

    Returns ``('drag', page, row, col)`` for the first matching item, or
    ``('empty',)`` when none is left (the caller stops the bot + warns).
    """
    loc = find_first(inv, names)
    return ('drag', loc[0], loc[1], loc[2]) if loc is not None else ('empty',)


def drag(api, x1, y1, x2, y2, steps=DRAG_STEPS, settle=DRAG_SETTLE,
         sleep=None):
    """Press-hold-move-release drag from ``(x1,y1)`` to ``(x2,y2)``.

    ``api`` is any object with ``moveTo(x, y)``, ``mouseDown()``, ``mouseUp()``
    (pydirectinput in production, a recorder in tests). Intermediate moves make
    the game register the drag rather than a teleport. ``sleep`` defaults to
    ``time.sleep``; tests pass a no-op. Never raises -> a failed drag must not
    crash the bot loop (it releases the button in a finally).
    """
    if sleep is None:
        import time
        sleep = time.sleep
    try:
        api.moveTo(int(x1), int(y1))
        sleep(settle)
        api.mouseDown()
        sleep(settle)
        n = max(1, int(steps))
        for i in range(1, n + 1):
            x = x1 + (x2 - x1) * i // n
            y = y1 + (y2 - y1) * i // n
            api.moveTo(int(x), int(y))
            sleep(settle / n)
        sleep(settle)
    finally:
        try:
            api.mouseUp()
        except Exception:
            pass


def two_click_place(api, x1, y1, x2, y2, settle=DRAG_SETTLE, sleep=None):
    """Item per ZWEI-KLICK setzen statt Drag: Linksklick Quelle (aufnehmen) ->
    Pause -> Linksklick Ziel (setzen). User-Grundwahrheit: das Setzen ist kein
    Drag, sondern Aufnehmen+Setzen. NUR fuer UI-Slot->UI-Slot (Box -> Box-Slot der
    Puzzle-Oberflaeche) -- NICHT fuer Slot->Welt (dort bleibt :func:`drag` sicherer,
    weil ein Welt-Klick sonst die Figur laufen liesse). Kein haengender Mausknopf.
    Defensiv: wirft nie. (Die geteilte :func:`drag` bleibt fuer die Fisch-Koeder-
    Nachfuellung unveraendert.)"""
    if sleep is None:
        import time
        sleep = time.sleep

    def _click(x, y):
        try:
            if hasattr(api, 'click'):
                api.click(x=int(x), y=int(y))
            else:
                api.moveTo(int(x), int(y))
                api.mouseDown()
                api.mouseUp()
        except Exception:
            pass

    _click(x1, y1)        # Box aufnehmen
    sleep(settle)
    _click(x2, y2)        # auf den Box-Slot setzen


# Neutraler Ablage-Punkt fuer den ZEIGER nach dem Nachlegen (Client-Pixel im
# 800x601-Client, vor dem Fenster-Offset).
#
# WARUM (2026-08-09, am Live-Bild gemessen): Der Drag endet auf dem Quickslot
# (QUICKSLOT_XY, y=582) und der Zeiger BLEIBT dort stehen. Der Client blendet
# dann seinen Item-Tooltip ein -- und der klappt NACH OBEN auf, quer ueber die
# Chat-Zeile: Tooltip-Rahmen y[514,592] gegen die Chat-Lesezone y[579,596], also
# 14 der 18 Zeilen verdeckt, inklusive der kompletten Textzeile y[582,589]. Der
# Bot liest ab da den TOOLTIP statt des Chats (gemessen: 5 "Woerter" auf einem
# LEEREN Chat) -> Fischname und Koeder-Rueckmeldung fallen aus, die Whitelist
# greift nicht mehr. Jeder andere Runner parkt laengst (inventory_runner,
# inventory_campfire_runner, inventory_discard_runner) -- nur dieser Pfad nicht.
#
# Der Punkt ist ``inventory.hover.tab_park_point(DEFAULT_CALIBRATION)``, hier als
# Konstante festgehalten, damit refill.py abhaengigkeitsarm bleibt. Er liegt
# LINKS des Inventar-Panels und OBERHALB der Quickslot-Leiste, also im
# Weltbereich, wo der Client keine Tooltips zeigt -- und mit doppelter Reserve
# ausserhalb der Chat-Lesezone (x 585 > 405 UND y 372 << 548). Verankert durch
# test_bait_feedback.test_park_point_clear_of_chat_zone.
CURSOR_PARK_XY = (585, 372)


def park_cursor(api, offset_x=0, offset_y=0, xy=CURSOR_PARK_XY, sleep=None,
                settle=INPUT_SETTLE_S):
    """Zeiger auf den neutralen :data:`CURSOR_PARK_XY` fahren -- NUR ``moveTo``.

    Bewusst KEIN Klick: ein Linksklick in die Welt liesse die Figur loslaufen.
    Nach dem Verlassen des Slots blendet der Client den Tooltip sofort aus, das
    kurze ``settle`` gibt ihm einen Frame Zeit, bevor der naechste Screenshot
    gelesen wird. Defensiv: wirft nie -- ein misslungener Park darf weder den
    Nachlege-Vorgang noch den Angel-Loop kippen.
    """
    if sleep is None:
        import time
        sleep = time.sleep
    try:
        api.moveTo(int(offset_x) + int(xy[0]), int(offset_y) + int(xy[1]))
        sleep(settle)
    except Exception:
        pass


# Empty-slot probe tunables. An EMPTY slot is DARK *and* FLAT (uniform
# background) *and* free of bright "icon ink"; an OCCUPIED slot -- even a dark,
# thin reddish bait icon like the "47" worm stack -- carries BRIGHT pixels (icon
# highlights / white stack digits) AND high local contrast. All three empty
# signals must agree (AND), so a false EMPTY (-> wrong refill) needs an occupied
# slot that is at once dark, flat and ink-free -- effectively indistinguishable
# from empty; the AND stays conservative in the safe direction.
#
# Thresholds sit in the MIDDLE of the empty/occupied gap MEASURED across every
# real frame we have (live_capture.png worm slot + user keybind frame + FischOCR
# fishing frames), not hugged to one capture:
#   empty  slots : mean 9..10 | std 7..16 | bright 0..2
#   occupied     : mean 25..113 | std 46..97 | bright 38..308
# -> std gap 16->46 (mid ~31), bright gap 2->38, mean gap 10->25.
#
# WICHTIG (2026-07-22, Live-Report): Metin2 rendert seit einem Patch die TASTEN-
# ZIFFER ("2") auf JEDEN Quickslot -- auch auf den leeren. Dieses kleine Overlay
# hob am leeren Bait-Slot std von ~7 auf ~16 und bright von 0 auf 2 und riss so
# die alte, zu enge Schwelle (std<14, bright<4) -> der Bot las den leeren Slot
# als BELEGT und legte NIE nach. Die neuen Schwellen (std<30, bright<20) tolerieren
# das Ziffer-Overlay mit Marge und bleiben weit unter dem Occupied-Minimum (std 46,
# bright 38). Regressions-Frame: tests/fixtures/refill/quickslot_keybind_empty_slot2.png.
QUICKSLOT_PROBE_RADIUS = 11   # half-size of the sampled square (px)
QUICKSLOT_DARK_MEAN = 45      # slot mean grayscale must be below this to be empty
QUICKSLOT_FLAT_STD = 30       # ... and contrast (std) below this (flat bg + key-digit overlay)
QUICKSLOT_BRIGHT_VALUE = 70   # a pixel brighter than this counts as "icon ink"
QUICKSLOT_MAX_BRIGHT_PX = 20  # ... and fewer than this many bright px (tolerates the key digit)


def quickslot_is_empty(screenshot_bgr, slot_1to8, radius=QUICKSLOT_PROBE_RADIUS,
                       dark_mean=QUICKSLOT_DARK_MEAN, flat_std=QUICKSLOT_FLAT_STD,
                       bright_value=QUICKSLOT_BRIGHT_VALUE,
                       max_bright_px=QUICKSLOT_MAX_BRIGHT_PX):
    """True iff quick-slot ``slot_1to8`` is CONFIDENTLY EMPTY (no item icon).

    Samples a small patch at the slot's client pixel on the captured window
    (the screenshot IS the 800x601 client, so client == screenshot coords) and
    calls it empty ONLY when that patch is at once DARK (low mean), FLAT (low
    std) and free of bright "icon ink" pixels -- the fingerprint of the empty
    slot background. Any item, even a dark bait icon with a stack count, breaks
    at least one of those, so it reads as occupied. Channel-order agnostic
    (uses the per-pixel channel mean), so it works on BGR captures or RGB alike.

    Strictly conservative for the refill loop: returns ``False`` (assume
    OCCUPIED -> do NOT refill) whenever numpy/the image is unavailable, the
    patch is degenerate, or anything raises. In doubt we never refill.
    """
    stats = quickslot_probe_stats(screenshot_bgr, slot_1to8, radius=radius,
                                  bright_value=bright_value)
    if stats is None:
        return False
    mean, std, bright_px = stats
    is_dark = mean < float(dark_mean)
    is_flat = std < float(flat_std)
    return is_dark and is_flat and bright_px < int(max_bright_px)


def quickslot_probe_stats(screenshot_bgr, slot_1to8,
                          radius=QUICKSLOT_PROBE_RADIUS,
                          bright_value=QUICKSLOT_BRIGHT_VALUE):
    """``(mean, std, bright_px)`` des Slot-Patches -- oder ``None``, wenn nicht
    messbar (kein numpy/Bild, falsche Form, degenerierter Patch).

    Reines Diagnose-Fenster in EXAKT dieselben Pixel, die
    :func:`quickslot_is_empty` bewertet. Zweck: bei "Bot legt nicht nach, obwohl
    leer" die tatsaechlich am Slot-Pixel gemessenen Werte loggen -- so ist sofort
    sichtbar, ob (a) der Slot-Punkt fuer das Fenster des Nutzers falsch sitzt
    (mean/std passen nicht zum leeren Hintergrund) oder (b) die Schwellen nicht
    greifen. Wirft nie."""
    if _np is None or screenshot_bgr is None:
        return None
    try:
        cx, cy = QUICKSLOT_XY[int(slot_1to8)]
        arr = _np.asarray(screenshot_bgr)
        if arr.ndim != 3 or arr.shape[2] < 3:
            return None
        h, w = arr.shape[0], arr.shape[1]
        r = max(1, int(radius))
        y0, y1 = max(0, cy - r), min(h, cy + r)
        x0, x1 = max(0, cx - r), min(w, cx + r)
        if y1 <= y0 or x1 <= x0:
            return None
        patch = arr[y0:y1, x0:x1, :3].astype(_np.float32)
        gray = patch.mean(axis=2)
        return (float(gray.mean()), float(gray.std()),
                int((gray > float(bright_value)).sum()))
    except Exception:
        return None


def tab_click(inp, calib, offset_x, offset_y, page, tag='refill'):
    """Click an inventory page tab (I..IV) via the injected input api.

    Defensive (wie der ganze Refill-Pfad): ein fehlender Tab-Punkt oder ein
    Input-Fehler darf den Scan NIE abreissen -- still no-op statt Exception.

    ``tag`` (DEBUG-Klick-Tracker, Angel-Lauf): Tab-Klicks sind reine UI-Klicks
    (Inventar-Reiter) -- sie bewegen den Char NICHT. Im Multiclient laufen sie
    ueber ``CursorClient.click`` und wuerden ohne Tag als ``tag='other'``
    faelschlich als STRAY-CLICK erscheinen. Mit ``tag='refill'`` erkennt der
    Tracker sie als gegateten UI-Klick. Das rohe ``pydirectinput`` (Single-
    Client) kennt kein ``tag`` -> defensiver Fallback ohne das kwarg (Klick
    byte-identisch; dieser Pfad ist ohnehin nicht getrackt).
    """
    try:
        pt = ((calib or {}).get('tabs', {}) or {}).get(page)
        if not pt:
            return
        x = int(offset_x + pt[0])
        y = int(offset_y + pt[1])
        try:
            inp.click(x=x, y=y, button='left', tag=tag)
        except TypeError:
            # Backend ohne tag-kwarg (rohes pydirectinput) -> Alt-Aufruf. Die
            # TypeError entsteht beim Argument-Binding VOR der Klick-Ausfuehrung
            # -> kein Doppelklick.
            inp.click(x=x, y=y, button='left')
    except Exception:
        pass


def refill_from_inventory(item_names, target_xy, *, inp, wincap, db,
                          calib=DEFAULT_CALIBRATION, sleep=None,
                          should_stop=None):
    """Scan the (already open) inventory + drag the first matching item to
    ``target_xy``. Returns ``'dragged'`` / ``'empty'`` / ``'error'`` / ``'stopped'``.

    Reuses the headless scanner (tab-click page switch built from the
    calibration + window offset) + the tested find/coordinate/drag helpers.
    Strictly defensive -- a vision/input failure returns ``'error'`` and never
    raises into the bot loop.

    ``should_stop`` is an optional no-arg predicate (the live loop passes the
    global Stop-Signal). When it goes truthy the op aborts at the NEXT checkpoint
    -- between page switches, before the drag -- and returns ``'stopped'`` so a
    panic-stop (F6) is honoured within one page-switch nap instead of blocking
    the loop for the whole multi-page scan + drag. Off (``None``) -> unchanged.
    """
    if sleep is None:
        import time
        sleep = time.sleep
    stop = should_stop if callable(should_stop) else (lambda: False)

    def _napped(seconds):
        """Sleep ``seconds`` but bail the instant a stop is requested.

        Returns ``False`` if a stop interrupted the nap (caller aborts). The
        injected ``sleep`` is the interruptible Stop-Signal.wait in production
        (returns False on a stop) and a plain/​no-op sleep in tests; either way we
        re-check ``stop`` after it so the abort is honoured regardless.
        """
        result = sleep(seconds)
        if result is False:
            return False
        return not stop()

    try:
        if stop():
            return 'stopped'
        from inventory.scanner import scan_inventory
        # Vertrag (vgl. fishingbot.bait_refill_db / run_loop._bait_refill_db):
        # db=None -> Engine baut/nutzt den gebuendelten Default selbst. Der
        # serielle scan_inventory-Pfad ruft classify_slot -> db.best_slot_result
        # ungeschuetzt auf; mit db=None wuerde das jeden Slot mit AttributeError
        # abbrechen (vom aeusseren except als 'error' verschluckt -> Nachlegen
        # stumm tot). Hier EINMAL defensiv die Bundle-DB nachladen; klappt auch
        # das nicht (z. B. numpy/PIL fehlt), sauber 'error' melden.
        if db is None:
            try:
                from interface.inventory_io import _get_db
                db = _get_db()
            except Exception:
                return 'error'
        ox = int(getattr(wincap, 'offset_x', 0) or 0)
        oy = int(getattr(wincap, 'offset_y', 0) or 0)

        # Abbruch-Marke fuer den seriellen Page-Scan: ``_switch_page`` ist der
        # einzige Hook waehrend des Scans -- wird hier zwischen den Seiten
        # gesetzt, falls ein Stop kam, damit der Scan nach der aktuellen Seite
        # zuegig endet (statt alle 4 Seiten + Drag durchzuziehen).
        aborted = {'stop': False}

        def _switch_page(page):
            # MUSS die Tab navigieren: scan_inventory ruft switch_page_fn(page),
            # um auf Seite ``page`` zu wechseln, BEVOR es den Frame greift. Ohne
            # den Klick blieb dieselbe (Start-)Seite offen -> der Scanner sah I..IV
            # alle als Seite I, Items auf II/III/IV wurden nie gefunden -> der Bot
            # meldete faelschlich 'empty'. Erst klicken, dann die (interruptible)
            # Settle-Nap fuer den Stop-Check.
            tab_click(inp, calib, ox, oy, page)
            if not _napped(0.2):
                aborted['stop'] = True

        def _scan():
            return scan_inventory(
                capture_fn=wincap.get_screenshot,
                switch_page_fn=_switch_page,
                db=db, calib=calib)

        inv = _scan()
        if aborted['stop'] or stop():
            return 'stopped'
        loc = find_first(inv, item_names)

        # SELBSTHEILUNG bei einem Raster-Fehl-Lock: kein einziger Slot auf KEINER
        # Seite erkannt, obwohl belegte Slots gesehen wurden -- das ist kein
        # leerer Beutel, sondern ein verschobenes Raster (jeder Slot-Ausschnitt
        # trifft die Luecke zwischen zwei Zellen). Passiert real, wenn ein alter
        # Lock aus ``grid_lock.json`` nicht mehr passt. Einmalig den Session-Lock
        # verwerfen und neu scannen (dann laeuft der Kalt-Sweep). Kostet nur im
        # Fehlerfall; ein wirklich leerer Beutel hat auch keine unknown-Slots und
        # loest das hier nie aus.
        if loc is None and _looks_like_grid_mislock(inv):
            try:
                from inventory.grid import reset_align_cache
                reset_align_cache()
                from debuglog import log as _dbg
                _dbg.event('refill', 'Kein Slot erkannt, aber belegte Slots '
                                     'gesehen -> Raster-Lock verworfen, Scan '
                                     'wird wiederholt')
            except Exception:
                pass
            if not (aborted['stop'] or stop()):
                inv = _scan()
                loc = find_first(inv, item_names)
        if aborted['stop'] or stop():
            return 'stopped'

        if loc is None:
            # DIAGNOSE: was hat der Scan ueberhaupt gefunden? Eine present-aber-
            # 'unknown' klassifizierte Box (z.B. Stack-Zahl wirft das Template-
            # Matching) erscheint hier als '?N' -> sofort erkennbar, ob die Box
            # FEHLT oder nur nicht ERKANNT wird. Soft -- Logging darf nie kippen.
            try:
                from debuglog import log as _dbg
                _dbg.event('refill', 'Inventar-Scan: gesucht={} | gefunden: {}'.format(
                    list(item_names), summarize_inventory(inv)))
            except Exception:
                pass
            return 'empty'
        page, row, col = loc
        tab_click(inp, calib, ox, oy, page)
        if not _napped(0.25):
            return 'stopped'
        fx, fy = inventory_slot_screen(row, col, ox, oy, calib)
        # Den Drag selbst mit der interruptiblen Sleep ausstatten: bricht ein Stop
        # mitten in den Zwischen-Moves, gibt der finally-Block in ``drag`` die
        # Maustaste trotzdem frei (kein haengender Mausknopf).
        drag(inp, fx, fy, int(target_xy[0]), int(target_xy[1]), sleep=sleep)
        _napped(0.15)
        return 'dragged'
    except Exception:
        return 'error'


# ---------------------------------------------------------------------------
# DEDIZIERTER PUZZLE-BOX-FINDER (robust, client-kalibriert)
#
# Warum nicht der itemdb-Scan? Auf dem echten Client (Screenshot 2026-06-17)
# erkannte ``scan_inventory`` GAR NICHTS (alle Slots 'unknown'): (1) der Grid-
# Auto-Align lockt ~10px daneben (Default-Grid 633,244 ist korrekt -> Box-Zentrum
# 713,388 ✓), und (2) die Box traegt eine GROSSE Stueckzahl (57/104/200) in der
# UNTEREN Haelfte -> Voll-Icon-MAD 41 (> Schwelle). Loesung (Bild-validiert):
# am FESTEN Kalibrier-Grid abtasten + nur die OBERE Icon-Haelfte matchen
# (Stueckzahl ignoriert). Messwerte: Standard-Box topMAD~1.0, Deluxe-Box ~24.8,
# JEDER Nicht-Box-Slot >=39 -> Schwelle 28 trennt sauber.
# ---------------------------------------------------------------------------
BOX_MATCH_TOP_ROWS = 16   # nur die oberen 16 Zeilen matchen (untere = Stueckzahl)
BOX_MATCH_MAX_MAD = 28.0  # bild-validiert: Box <=24.8, alles andere >=39
BOX_MATCH_SHIFT = 3       # +-px Suchfenster (wie itemdb-Shift, gegen Sub-Pixel-Drift)

_BOX_TPL_CACHE = {}


def _box_template(name):
    """``(bgr_float32[32,32,3], top_mask_bool[32,32])`` fuer
    ``inventory_icons/<name>.png`` -- nur die obere Haelfte der Alpha-Maske aktiv
    (untere traegt die variable Stueckzahl). Gecacht; ``None`` bei Fehler/headless.
    BGR (cv2), passend zum BGR-Screenshot der WindowCapture."""
    if name in _BOX_TPL_CACHE:
        return _BOX_TPL_CACHE[name]
    result = None
    try:
        import os
        import cv2
        from respath import resource_path
        path = resource_path(os.path.join('inventory_icons', name + '.png'))
        bgra = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if bgra is not None and bgra.ndim == 3 and bgra.shape[2] >= 4 \
                and bgra.shape[0] >= BOX_MATCH_TOP_ROWS and _np is not None:
            bgr = bgra[:, :, :3].astype(_np.float32)
            mask = bgra[:, :, 3] > 32
            mask[BOX_MATCH_TOP_ROWS:, :] = False   # untere Haelfte (Zahl) ignorieren
            if mask.any():
                result = (bgr, mask)
    except Exception:
        result = None
    _BOX_TPL_CACHE[name] = result
    return result


def _box_slot_mad(frame, cx, cy, tpl_bgr, tpl_mask, shift=BOX_MATCH_SHIFT):
    """Kleinste maskierte MAD (obere Haelfte) eines ``tpl``-Icons um Slot-Zentrum
    ``(cx, cy)`` mit ``+-shift`` px Suchfenster. ``1e9`` wenn nicht auswertbar."""
    th, tw = tpl_bgr.shape[0], tpl_bgr.shape[1]
    h, w = frame.shape[0], frame.shape[1]
    best = 1e9
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            y0 = cy + dy - th // 2
            x0 = cx + dx - tw // 2
            if y0 < 0 or x0 < 0 or y0 + th > h or x0 + tw > w:
                continue
            patch = frame[y0:y0 + th, x0:x0 + tw, :3].astype(_np.float32)
            d = _np.abs(patch - tpl_bgr)[tpl_mask]
            if d.size:
                m = float(d.mean())
                if m < best:
                    best = m
    return best


def find_box_slot(capture_fn, switch_page_fn, box_names, calib=DEFAULT_CALIBRATION,
                  pages=PAGE_ORDER, should_stop=None):
    """ERSTE Box (eines der ``box_names``) im Inventar -- Seite ``pages`` in
    Reihenfolge, je Seite row-major -- per OBERE-HAELFTE-Template-Match am
    KALIBRIER-Grid (kein Auto-Align). Rueckgabe ``(page, row, col, name)`` oder
    ``None``. Streng defensiv: wirft nie."""
    if _np is None:
        return None
    tpls = [(n, _box_template(n)) for n in box_names]
    tpls = [(n, t) for n, t in tpls if t is not None]
    if not tpls:
        return None
    grid = (calib or {}).get('grid', {}) or {}
    cols = int(grid.get('cols', 5))
    rows = int(grid.get('rows', 9))
    try:
        lat = lattice_from_calibration(calib)
        ox0, oy0 = lat.origin
        px, py = lat.pitch
    except Exception:
        return None
    stop = should_stop if callable(should_stop) else (lambda: False)
    for page in pages:
        try:
            switch_page_fn(page)
        except Exception:
            pass
        if stop():
            return None
        try:
            frame = capture_fn()
        except Exception:
            frame = None
        if frame is None or getattr(frame, 'ndim', 0) != 3:
            continue
        for row in range(rows):
            for col in range(cols):
                cx = int(ox0 + col * px + px // 2)
                cy = int(oy0 + row * py + py // 2)
                for name, (tb, tm) in tpls:
                    if _box_slot_mad(frame, cx, cy, tb, tm) <= BOX_MATCH_MAX_MAD:
                        return (page, row, col, name)
    return None


INVENTORY_OPEN_MIN_DIFF = 15.0   # Slot-Zentren minus -Raender; offen gemessen ~38


def inventory_looks_open(frame, calib=DEFAULT_CALIBRATION):
    """TEMPLATE-FREI pruefen, ob das Inventar offen ist (ersetzt die auf manchen
    Clients unzuverlaessige Tab-Template-Probe).

    Die offene Tasche zeigt das 5x9-Slot-Raster: die Slot-RAND-Spalten (alle
    ``pitch`` px) sind deutlich DUNKLER als die Slot-ZENTRUM-Spalten (am echten
    Client gemessen: Differenz ~38). Die Spielwelt hat keine solche Periodik.
    Rueckgabe ``(is_open: bool, diff: float)`` -- ``diff`` fuers Debug/Kalibrieren.
    Streng defensiv: bei jedem Fehler ``(False, 0.0)``."""
    if _np is None or frame is None or getattr(frame, 'ndim', 0) != 3:
        return (False, 0.0)
    try:
        grid = (calib or {}).get('grid', {}) or {}
        cols = int(grid.get('cols', 5))
        rows = int(grid.get('rows', 9))
        lat = lattice_from_calibration(calib)
        ox0, oy0 = lat.origin
        px, py = lat.pitch
        gray = _np.asarray(frame)[:, :, :3].astype(_np.float32).mean(axis=2)
        h, w = gray.shape
        y0 = int(oy0)
        y1 = min(h, int(oy0 + rows * py))
        if y1 - y0 < py:
            return (False, 0.0)

        def _col_mean(x):
            x = int(x)
            if x < 0 or x >= w:
                return None
            return float(gray[y0:y1, x].mean())

        borders = [_col_mean(ox0 + c * px) for c in range(cols + 1)]
        centers = [_col_mean(ox0 + c * px + px // 2) for c in range(cols)]
        borders = [v for v in borders if v is not None]
        centers = [v for v in centers if v is not None]
        if not borders or not centers:
            return (False, 0.0)
        diff = float(_np.mean(centers) - _np.mean(borders))
        return (diff >= INVENTORY_OPEN_MIN_DIFF, diff)
    except Exception:
        return (False, 0.0)


def box_refill_from_inventory(box_names, target_xy, *, inp, wincap,
                              open_toggle_fn=None, calib=DEFAULT_CALIBRATION,
                              sleep=None, should_stop=None, max_open_tries=3):
    """ROBUSTES Box-Nachlegen ohne die kaputte Tab-Template-Probe.

    Ablauf: (1) template-frei pruefen ob das Inventar offen ist
    (``inventory_looks_open``); (2) ist es ZU, ``open_toggle_fn`` aufrufen
    (Fokus + Inventar-Hotkey -> Toggle) und erneut pruefen -- so wird das Inventar
    waehrend des Puzzles zuverlaessig geoeffnet, OHNE bei geschlossener Tasche
    blind Tabs ins Spiel zu klicken; (3) am festen Kalibrier-Grid + obere-Haelfte-
    Match die ERSTE Box finden (``find_box_slot``) und an ``target_xy`` ziehen.
    Rueckgabe ``'dragged'|'empty'|'error'|'stopped'``. Wirft nie."""
    if sleep is None:
        import time
        sleep = time.sleep
    stop = should_stop if callable(should_stop) else (lambda: False)

    def _napped(seconds):
        result = sleep(seconds)
        if result is False:
            return False
        return not stop()

    def _dbg(msg):
        try:
            from debuglog import log as _l
            _l.event('refill', msg)
        except Exception:
            pass

    try:
        if stop():
            return 'stopped'
        ox = int(getattr(wincap, 'offset_x', 0) or 0)
        oy = int(getattr(wincap, 'offset_y', 0) or 0)

        # (1)+(2) Inventar verifiziert oeffnen -- template-frei, mit Toggle-Retry.
        opened = False
        for attempt in range(max(1, int(max_open_tries))):
            if stop():
                return 'stopped'
            frame = None
            try:
                frame = wincap.get_screenshot()
            except Exception:
                frame = None
            is_open, diff = inventory_looks_open(frame, calib)
            _dbg('Inventar-Offen-Check: offen={} (Differenz={:.0f}, Schwelle={:.0f}), '
                 'Versuch {}'.format(is_open, diff, INVENTORY_OPEN_MIN_DIFF, attempt + 1))
            if is_open:
                opened = True
                break
            # zu -> Toggle (Fokus + Hotkey) und settle, dann erneut pruefen
            if open_toggle_fn is None:
                break
            try:
                open_toggle_fn()
            except Exception:
                pass
            if not _napped(0.5):
                return 'stopped'
        if not opened:
            _dbg('Inventar liess sich nicht verifiziert oeffnen -> kein Nachlegen')
            return 'empty'

        # (3) Box am festen Grid suchen (Inventar ist jetzt offen -> Tab-Klicks sicher).
        aborted = {'stop': False}

        def _switch_page(page):
            tab_click(inp, calib, ox, oy, page)
            if not _napped(0.2):
                aborted['stop'] = True

        loc = find_box_slot(wincap.get_screenshot, _switch_page, box_names,
                            calib=calib,
                            should_stop=lambda: aborted['stop'] or stop())
        if aborted['stop'] or stop():
            return 'stopped'
        if loc is None:
            _dbg('Box-Scan (obere-Haelfte-Match) gesucht={} -> keine Box gefunden'
                 .format(list(box_names)))
            return 'empty'
        page, row, col, name = loc
        _dbg('Box gefunden: {} auf Seite {} Slot (r{},c{})'.format(name, page, row, col))
        tab_click(inp, calib, ox, oy, page)
        if not _napped(0.25):
            return 'stopped'
        fx, fy = inventory_slot_screen(row, col, ox, oy, calib)
        # ZWEI-KLICK statt Drag (Box -> Box-Slot, beides UI): aufnehmen + setzen.
        two_click_place(inp, fx, fy, int(target_xy[0]), int(target_xy[1]), sleep=sleep)
        _napped(0.15)
        return 'dragged'
    except Exception:
        return 'error'
