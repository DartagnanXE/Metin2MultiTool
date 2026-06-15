"""EnergiesplitterBot -- Bot-Kern + Phase-0-GATE + State-Maschinen (Eigentuemer D).

EINE Klasse, ZWEI Aktionen (Modus-Schalter ``self.mode``):

* ``MODE_HAMMER``  -- Aktion 1: Haemmer am Alchemisten kaufen.
* ``MODE_DAGGER``  -- Aktion 2: Dolche am Waffenhaendler kaufen + 1:1 zu
  Energiesplittern verarbeiten (Drag Hammer -> Dolch-Slot).

Integration ueber den ``run_loop``-Bot-Tick (wie ``fishbot``/``puzzlebot``):
``set_to_begin(values)`` friert die Config ein und ruft den Phase-0-GATE,
``runHack()`` fuehrt GENAU EINEN blockierenden Tick aus und stoppt sich bei
jeder Stop-Bedingung selbst (``self.botting = False``).

PHASE-0-GATE (harter Blocker, §2 CONTRACT): solange ``self.dry_run`` ODER
``not self.armed``, ruft der Bot NIE ``rightClick``/``click``/``drag``/
``keyDown`` -- er liest, loggt und stoppt. ``armed`` setzt ALLEIN
``phase0_gate()`` = ``detect.assets_ready(mode).ready AND
geometry.is_calibrated(wincap)``. Zusaetzlich greifen die OCR-unabhaengigen
Backstops ``gold_floor``/``max_gold_spend``/``max_actions``/``price_per_item``/
``consecutive_unverified_stop`` in JEDER Kauf-/Verarbeitungs-Entscheidung.

Headless-Sicherheit: ``pydirectinput`` und die Schwester-Module von Agent A
(``detect``/``geometry``/``gold_reader``) werden WEICH importiert. Fehlt etwas,
landet es als ``missing``-Eintrag im GATE -- kein ImportError, kein Klick.
"""

import constants
from debuglog import log
from i18n import t

# -- weiche Imports (Build-Reihenfolge A/B/D parallel; headless-sicher) -------
# Fehlt ein Modul, bleibt der Bot importierbar; der Phase-0-GATE meldet die
# Luecke als 'missing' und blockt -- nie ein harter ImportError, nie ein Klick.

try:  # Eingabe-Treiber (Windows-only; in Tests gestubbt)
    import pydirectinput as _input
except Exception:  # pragma: no cover - nur ohne Windows-Treiber
    _input = None

try:  # Fenster-Capture (Windows-only; in Tests gestubbt)
    from windowcapture import WindowCapture as _WindowCapture
except Exception:  # pragma: no cover
    _WindowCapture = None

try:  # Vision/Asset-Pruefung (Agent A)
    from energiesplitter import detect as _detect
except Exception:
    _detect = None

try:  # Geometrie/Kalibrierung (Agent A)
    from energiesplitter import geometry as _geometry
except Exception:
    _geometry = None

try:  # Gold-Reader (Agent A)
    from energiesplitter import gold_reader as _gold_reader
except Exception:
    _gold_reader = None

try:  # Rechen-Logik (Agent B)
    from energiesplitter import calc as _calc
except Exception:
    _calc = None

# Drag-Primitiv WIEDERVERWENDEN (A2) -- nie neu bauen. mouseUp im finally.
try:
    from inventory_discard import drag as _discard_drag
except Exception:  # pragma: no cover
    _discard_drag = None


MODE_HAMMER = 'hammer'
MODE_DAGGER = 'dagger'


class EnergiesplitterBot:
  """Energiesplitter-Bot mit Modus-Schalter (siehe Modul-Docstring, CONTRACT §1)."""

  # -- State-Konstanten (Klassen-Attribute, int) --------------------------
  ST_INIT = 0
  ST_INVENTORY_BASE = 1
  ST_APPROACH_NPC = 2
  ST_SELECT_NPC = 3
  ST_OPEN_DIALOG = 4
  ST_UNLOCK_DECIDE = 5
  ST_OPEN_SHOP = 6
  ST_UNLOCK_STORY = 7
  ST_LOCATE_HAMMER = 8
  ST_BUY_LOOP = 9
  ST_CHECK_DONE = 10
  ST_LOCATE_DOLCH = 11
  ST_BUY_ONE_DOLCH = 12
  ST_PROCESS_DRAG = 13
  ST_VERIFY_PROCESS = 14
  ST_RESCAN = 15
  ST_STOP = 99

  # -- Modus-Konstanten ---------------------------------------------------
  MODE_HAMMER = MODE_HAMMER
  MODE_DAGGER = MODE_DAGGER

  # -- run_loop-/Lebenszyklus-Defaults (von run_loop ueberschrieben) ------
  botting = False
  mode = MODE_HAMMER
  state = ST_INIT
  wincap = None
  stop_signal = None

  # -- sichere Erststart-Defaults (CONTRACT §2) ---------------------------
  # dry_run=True bis Phase-0 + Nutzer-Bestaetigung; armed wird ALLEIN von
  # phase0_gate() gesetzt. So bleibt ein frisch konstruierter Bot harmlos.
  dry_run = True
  armed = False
  gold_floor = 50000
  max_actions = 2
  consecutive_unverified_stop = 3
  price_per_item = 15000

  def __init__(self):
    # Konstruktor haelt das Objekt headless-konstruierbar; die echte Config
    # friert set_to_begin ein. Defensive Defaults setzen, damit Read-Only-
    # Zugriffe vor set_to_begin nie crashen.
    self.mode = MODE_HAMMER
    self.state = self.ST_INIT
    self.wincap = None
    self.stop_signal = None
    self._stop_reason = None
    self._missing = []
    self._reset_config_defaults()
    self._reset_counters()

  # -- Config-Defaults (vor set_to_begin; werden dann eingefroren) --------
  def _reset_config_defaults(self):
    self.hammer_count = 200
    self.energie_freischalten = True
    self.price_per_item = 15000
    self.process_mode = 'one_to_one'
    self.batch_size = 50
    self.prefer_stack = 'largest_fit'
    self.mouse_pause = 0.05
    self.keyboard_pause = 0.10
    self.speed_profile = 'fast'
    self.jitter_pct = 0.15
    self.birdseye_on_miss = True
    self.birds_eye_key = 'g'
    self.gold_floor = 50000
    self.max_gold_spend = 0
    self.max_actions = 2
    self.consecutive_unverified_stop = 3
    self.dry_run = True
    self.armed = False

  def _reset_counters(self):
    self.gekauft = 0
    self.hammer_remaining = 0
    self.splitter_summe = 0
    self.actions_done = 0
    self.gold_spent = 0
    self.consecutive_unverified = 0
    self._gold_start = None
    self._gold_last = None
    self._dolche_gekauft = 0
    self._buy_retries = 0
    self._npc_tries = 0
    self._birdseye_used = False

  # -- abort_fn-Seam (wie Manage v1.1.6) ----------------------------------
  def abort_fn(self):
    """``True`` wenn das injizierte Stop-Signal gesetzt ist.

    Seam, nicht Polling: run_loop ruft ``stop_signal.add_callback`` -- dieser
    Lesepfad spiegelt nur das Flag. Defensiv: ohne Signal -> nie abbrechen.
    """
    sig = self.stop_signal
    if sig is None:
      return False
    try:
      return bool(sig.stopped)
    except Exception:  # pragma: no cover - defensiv
      return False

  # -- set_to_begin (idempotent; friert Config ein; ruft phase0_gate) -----
  def set_to_begin(self, values):
    """Friert ALLE Config-Attribute aus ``values`` ein, RESETtet State +
    Zaehler, leitet ``max_gold_spend``/``max_actions`` ab und ruft den
    Phase-0-GATE (setzt ``self.armed``). Erzeugt ``wincap``. KEIN Klick.

    Idempotent re-aufrufbar (run_loop setzt ``self.mode`` vor dem Aufruf).
    Fehlt das Spiel-Fenster, wird ``self._stop_reason`` gesetzt; das Laufflag
    bleibt run_loop-gesteuert (botting setzt der RunLoop).
    """
    self._reset_counters()
    self.state = self.ST_INIT
    self._stop_reason = None
    self._missing = []

    self._freeze_config(values or {})

    # max_gold_spend / max_actions ableiten (0 = auto), CONTRACT §1.3/§3.
    soll = max(0, int(self.hammer_count))
    if int(self.max_gold_spend) <= 0:
      self.max_gold_spend = soll * 2 * max(0, int(self.price_per_item))
    if int(self.max_actions) <= 0:
      self.max_actions = max(1, round(1.2 * soll))

    # wincap erzeugen -- Fenster fehlt -> Stop-Grund merken (kein Raise nach
    # aussen; run_loop steuert botting). WindowCapture wirft bei fehlendem HWND.
    self.wincap = None
    if _WindowCapture is not None:
      try:
        self.wincap = _WindowCapture(constants.GAME_NAME)
      except Exception:
        self.wincap = None
        self._stop_reason = 'no_window'

    self.phase0_gate()

  def _freeze_config(self, v):
    """Liest die -ES_*--Keys aus ``values`` (vom run_loop via
    apply_energiesplitter_config gelegt). Fehlt ein Key -> dokumentierter
    Default. Reine Wert-Uebernahme; Clamps macht validate.py (Eigentuemer C)."""
    def _get(key, default):
      val = v.get(key, default)
      return default if val is None else val

    self.hammer_count = int(_get('-ES_HAMMER_COUNT-', 200))
    self.energie_freischalten = bool(_get('-ES_FREISCHALTEN-', True))
    self.price_per_item = int(_get('-ES_PRICE-', 15000))
    self.process_mode = str(_get('-ES_PROCESS_MODE-', 'one_to_one'))
    self.batch_size = int(_get('-ES_BATCH-', 50))
    self.prefer_stack = str(_get('-ES_PREFER_STACK-', 'largest_fit'))
    self.mouse_pause = float(_get('-ES_MOUSE_PAUSE-', 0.05))
    self.keyboard_pause = float(_get('-ES_KB_PAUSE-', 0.10))
    self.speed_profile = str(_get('-ES_SPEED-', 'fast'))
    self.jitter_pct = float(_get('-ES_JITTER-', 0.15))
    self.birdseye_on_miss = bool(_get('-ES_BIRDSEYE-', True))
    self.birds_eye_key = 'g'
    self.gold_floor = int(_get('-ES_GOLD_FLOOR-', 50000))
    self.max_gold_spend = int(_get('-ES_MAX_SPEND-', 0))
    self.max_actions = int(_get('-ES_MAX_ACTIONS-', 0))
    self.consecutive_unverified_stop = int(_get('-ES_UNVERIF_STOP-', 3))
    self.dry_run = bool(_get('-ES_DRY_RUN-', True))

  # -- Phase-0-GATE (harter Blocker, CONTRACT §2) -------------------------
  def phase0_gate(self):
    """Setzt ``self.armed`` = (Assets bereit AND 800x600-kalibriert).

    Delegiert die reine Pruefung an Agent A (``detect.assets_ready`` +
    ``geometry.is_calibrated``). Fehlt ein Modul (Build-Reihenfolge) ODER
    fehlt das Fenster, bleibt ``armed=False`` und die Luecke landet in
    ``missing``. Liefert ``(armed, missing)`` und speichert ``self._missing``.
    """
    missing = []

    mode = self.mode if self.mode in (MODE_HAMMER, MODE_DAGGER) else MODE_HAMMER

    # 1) Assets (Templates / Item-Icons / Gold-Digits) -- via Agent A.
    if _detect is None or not hasattr(_detect, 'assets_ready'):
      missing.append('detect_module')
    else:
      try:
        ready, miss = _detect.assets_ready(mode)
        if not ready:
          missing.extend(list(miss or []))
      except Exception:
        missing.append('detect_error')

    # 2) Kalibrierung 800x600 -- via Agent A.
    if _geometry is None or not hasattr(_geometry, 'is_calibrated'):
      missing.append('geometry_module')
    elif self.wincap is None:
      missing.append('calibration:800x600')
    else:
      try:
        if not _geometry.is_calibrated(self.wincap):
          missing.append('calibration:800x600')
      except Exception:
        missing.append('calibration:800x600')

    # 3) Gold-Reader vorhanden (Read-only-Vorbedingung fuer jeden scharfen Lauf).
    if _gold_reader is None or not hasattr(_gold_reader, 'read_gold'):
      missing.append('gold_reader_module')

    self._missing = missing
    self.armed = (len(missing) == 0)
    return self.armed, missing

  # -- runHack: EIN blockierender Tick ------------------------------------
  def runHack(self):
    """Ein Tick: verzweigt nach ``self.mode``. Bei ``dry_run or not armed``
    nur Read-Only-Erkennung + Log + Selbst-Stop ("Phase-0 nicht bereit").
    Stoppt sich bei jeder Stop-Bedingung selbst (``self.botting=False``)."""
    if not self.botting:
      return

    # Abbruch-Seam (F6): hat Vorrang vor jeder teuren Aktion.
    if self.abort_fn():
      self._stop('aborted')
      return

    # Fenster fehlte schon beim set_to_begin -> sauberer Stop, kein Klick.
    if self._stop_reason == 'no_window' or self.wincap is None:
      self._log_section()
      log.event('-', t('energiesplitter.no_window'))
      self._stop('no_window')
      return

    # PHASE-0-GATE: blockt VOR jeder Maus-/Tasten-Aktion (CONTRACT §2/§7).
    if self.dry_run or not self.armed:
      self._log_section()
      log.event('-', t('energiesplitter.phase0_not_ready',
                       missing=', '.join(self._missing) or 'dry_run'))
      self._stop('phase0_not_ready')
      return

    if self.mode == MODE_HAMMER:
      self._tick_hammer()
    else:
      self._tick_dagger()

  # -- Selbst-Stop --------------------------------------------------------
  def _stop(self, reason):
    """Bilanz loggen, Cursor NICHT bewegen (kein Klick), botting=False."""
    self._stop_reason = reason
    try:
      log.event(self.state, t(
          'energiesplitter.done',
          hammers=self.gekauft, daggers=self._dolche_gekauft,
          splitters=self.splitter_summe,
          gold_before=self._fmt_gold(self._gold_start),
          gold_after=self._fmt_gold(self._gold_last),
          reason=reason))
    except Exception:  # pragma: no cover - Logging darf nie den Stop kippen
      pass
    self.state = self.ST_STOP
    self.botting = False

  @staticmethod
  def _fmt_gold(g):
    return '?' if g is None else g

  def _log_section(self):
    key = ('energiesplitter.section_hammer' if self.mode == MODE_HAMMER
           else 'energiesplitter.section_dagger')
    try:
      log.section(t(key))
    except Exception:  # pragma: no cover
      pass

  # -- Backstops (OCR-unabhaengig, IMMER aktiv) ---------------------------
  def _action_cap_hit(self):
    """``True`` + Stop, wenn die Aktions-Obergrenze erreicht ist."""
    if self.actions_done >= int(self.max_actions):
      log.event(self.state, t('energiesplitter.max_actions', n=self.max_actions))
      self._stop('max_actions')
      return True
    return False

  def gold_guard(self, planned_cost):
    """Pruefung VOR jedem Kauf (CONTRACT §2, R3). Liefert das gelesene Gold
    bei OK, sonst ``None`` UND stoppt selbst.

    Drei OCR-unabhaengige Backstops + ein OCR-Backstop:
      1. Gold unlesbar              -> Stop + Snapshot (nie blind kaufen).
      2. gelesen - Kosten < floor   -> Stop (Reserve schuetzen).
      3. gold_spent + Kosten > cap  -> Stop (absoluter Budget-Deckel).
    """
    gold = self._read_gold()
    if gold is None:
      self._snapshot('gold_unreadable')
      log.event(self.state, t('energiesplitter.gold_unreadable'))
      self._stop('gold_unreadable')
      return None
    if self._gold_start is None:
      self._gold_start = gold
    self._gold_last = gold

    if gold - int(planned_cost) < int(self.gold_floor):
      log.event(self.state, t('energiesplitter.gold_floor_hit', gold=gold))
      self._stop('gold_floor')
      return None

    if self.gold_spent + int(planned_cost) > int(self.max_gold_spend):
      log.event(self.state, t('energiesplitter.gold_floor_hit', gold=gold))
      self._stop('max_gold_spend')
      return None

    return gold

  def _note_unverified(self):
    """Zaehlt eine nicht-verifizierte Aktion; stoppt bei N in Folge."""
    self.consecutive_unverified += 1
    if self.consecutive_unverified >= int(self.consecutive_unverified_stop):
      log.event(self.state, t('energiesplitter.buy_unverified',
                              retries=self.consecutive_unverified))
      self._stop('consecutive_unverified')
      return True
    return False

  # -- Read-Only-Helfer (defensiv; nie Raise) -----------------------------
  def _shot(self):
    try:
      return self.wincap.get_screenshot()
    except Exception:  # pragma: no cover - defensiv
      return None

  def _read_gold(self):
    """Liest den Gold-Zaehler via Agent-A-Reader. Defensiv -> None heisst
    'unlesbar' (Caller stoppt). Read-only, kein Klick."""
    if _gold_reader is None or _geometry is None:
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    try:
      roi = _geometry.gold_roi(self.mode)
    except Exception:
      roi = None
    if roi is None:
      return None
    try:
      return _gold_reader.read_gold(bgr, roi)
    except Exception:  # pragma: no cover - defensiv
      return None

  def _snapshot(self, name):
    bgr = self._shot()
    try:
      log.snapshot('energiesplitter_' + name, bgr=bgr)
    except Exception:  # pragma: no cover
      pass

  # -- Maus/Tasten (NUR erreichbar, wenn GATE gruen; jeder Pfad re-prueft) -
  def _guarded(self):
    """``True`` solange KEINE teure Aktion erlaubt ist (Gate/abort)."""
    return self.dry_run or not self.armed or self.abort_fn() or _input is None

  def _to_screen(self, x, y):
    ox = getattr(self.wincap, 'offset_x', 0) or 0
    oy = getattr(self.wincap, 'offset_y', 0) or 0
    return int(x + ox), int(y + oy)

  def _right_click(self, x, y):
    if self._guarded():
      return False
    sx, sy = self._to_screen(x, y)
    try:
      _input.PAUSE = self.mouse_pause
      _input.click(x=sx, y=sy, button='right')
      return True
    except Exception:  # pragma: no cover - defensiv
      return False

  def _left_click(self, x, y):
    if self._guarded():
      return False
    sx, sy = self._to_screen(x, y)
    try:
      _input.PAUSE = self.mouse_pause
      _input.click(x=sx, y=sy)
      return True
    except Exception:  # pragma: no cover
      return False

  def _press_key(self, key):
    if self._guarded():
      return False
    try:
      _input.PAUSE = self.keyboard_pause
      _input.keyDown(key)
      _input.keyUp(key)
      return True
    except Exception:  # pragma: no cover
      return False

  def _drag(self, x1, y1, x2, y2):
    """Drag NUR via wiederverwendetem inventory_discard.drag (A2, mouseUp im
    finally). Vor dem Aufruf Gate-Re-Check; abort wird NICHT mitten im Drag
    geprueft (erst danach), damit kein Button haengen bleibt."""
    if self._guarded() or _discard_drag is None:
      return False
    sx1, sy1 = self._to_screen(x1, y1)
    sx2, sy2 = self._to_screen(x2, y2)
    try:
      _discard_drag(_input, sx1, sy1, sx2, sy2)
      return True
    except Exception:  # pragma: no cover - drag garantiert mouseUp im finally
      return False

  # -- gemeinsame Flow-Helfer (Detection von A) ---------------------------
  def approach_npc(self, npc_template_key):
    """Sucht den NPC-Namen (Gruen+NCC, Agent A). Trifft -> Punkt; sonst 1x
    Vogelperspektive-KEYPRESS, dann Stop. Liefert ``pt`` oder ``None``."""
    bgr = self._shot()
    if bgr is None or _detect is None:
      log.event(self.state, t('energiesplitter.npc_not_found', npc=npc_template_key))
      self._stop('npc_not_found')
      return None
    tpl = self._template(npc_template_key)
    ok, pt, _ncc = (False, None, 0.0)
    try:
      ok, pt, _ncc = _detect.find_npc_name(bgr, tpl)
    except Exception:  # pragma: no cover - defensiv
      ok, pt = False, None
    if ok and pt is not None:
      return pt
    # einmalige Vogelperspektive (KEYPRESS), dann Stop.
    if self.birdseye_on_miss and not self._birdseye_used:
      self._birdseye_used = True
      log.event(self.state, t('energiesplitter.toggled_birdseye', key=self.birds_eye_key))
      self._press_key(self.birds_eye_key)
      return None  # naechster Tick versucht erneut
    log.event(self.state, t('energiesplitter.npc_not_found', npc=npc_template_key))
    self._stop('npc_not_found')
    return None

  def _template(self, key):
    """Holt ein NCC-Template ueber Agent A (lazy). ``None`` -> Detektor
    behandelt es defensiv (kein Treffer)."""
    if _detect is None or not hasattr(_detect, 'load_template'):
      return None
    try:
      return _detect.load_template(key)
    except Exception:  # pragma: no cover
      return None

  def open_shop_via_dialog(self):
    """Klickt die Dialogzeile 'Laden oeffnen' (eindeutiger NCC-Match) und
    verifiziert ``shop_open``. Uneindeutig/Timeout -> Snapshot + Stop. Liefert
    ``True`` bei offenem Shop."""
    bgr = self._shot()
    if bgr is None or _detect is None:
      self._snapshot('shop_not_open')
      log.event(self.state, t('energiesplitter.shop_not_open'))
      self._stop('shop_not_open')
      return False
    tpl = self._template('laden_oeffnen')
    ok, pt, _ncc = (False, None, 0.0)
    try:
      ok, pt, _ncc = _detect.find_shop_item(bgr, tpl)
    except Exception:  # pragma: no cover
      ok, pt = False, None
    if not ok or pt is None:
      self._snapshot('shop_not_open')
      log.event(self.state, t('energiesplitter.shop_not_open'))
      self._stop('shop_not_open')
      return False
    self._left_click(pt[0], pt[1])
    after = self._shot()
    is_open = False
    try:
      is_open = bool(_detect.shop_open(after)) if after is not None else False
    except Exception:  # pragma: no cover
      is_open = False
    if not is_open:
      self._snapshot('shop_not_open')
      log.event(self.state, t('energiesplitter.shop_not_open'))
      self._stop('shop_not_open')
      return False
    return True

  def verify_purchase(self, gold_before, expected_cost):
    """Verifiziert einen Kauf OCR-gestuetzt: Gold sank um ~``expected_cost``
    (Abweichung >20%% -> nicht verifiziert). Liefert ``(ok, gold_after)``.
    Reine Lese-Pruefung -- kein Klick."""
    gold_after = self._read_gold()
    if gold_after is None:
      return False, None
    self._gold_last = gold_after
    delta = gold_before - gold_after
    if expected_cost <= 0:
      return delta > 0, gold_after
    rel = abs(delta - expected_cost) / float(expected_cost)
    return (delta > 0 and rel <= 0.20), gold_after

  def verify_process(self, before_bgr, after_bgr):
    """Verifiziert die 1:1-Verarbeitung: Splitter-Stack gewachsen (Agent A).
    Liefert den Zuwachs (>=0). Read-only."""
    if _detect is None or before_bgr is None or after_bgr is None:
      return 0
    try:
      return max(0, int(_detect.read_splitter_growth(before_bgr, after_bgr)))
    except Exception:  # pragma: no cover
      return 0

  # =======================================================================
  #  HAMMER-MODUS (Aktion 1 @ Alchemist)
  # =======================================================================
  def _tick_hammer(self):
    st = self.state
    if st == self.ST_INIT:
      self._log_section()
      log.event(st, t('energiesplitter.started', mode=self.mode))
      self.hammer_remaining = max(0, int(self.hammer_count))
      self.state = self.ST_INVENTORY_BASE
      return

    if st == self.ST_INVENTORY_BASE:
      # Item-Template Pflicht -- ohne Hammer-Icon kein messbarer Bestand.
      if not self._item_template_ready('hammer'):
        log.event(st, t('energiesplitter.item_template_missing', item='hammer'))
        self._stop('item_template_missing')
        return
      if not self._has_free_slot():
        log.event(st, t('energiesplitter.no_space'))
        self._stop('no_space')
        return
      self.state = self.ST_APPROACH_NPC
      return

    if st == self.ST_APPROACH_NPC:
      pt = self.approach_npc('npc_alchemist')
      if pt is None:
        return  # approach_npc hat ggf. schon gestoppt / Vogelperspektive
      self._npc_pt = pt
      self.state = self.ST_SELECT_NPC
      return

    if st == self.ST_SELECT_NPC:
      if not self._select_npc(self._npc_pt):
        return  # _select_npc stoppt selbst bei Miss
      self.state = self.ST_OPEN_DIALOG
      return

    if st == self.ST_OPEN_DIALOG:
      if not self._open_dialog(self._npc_pt):
        return
      self.state = self.ST_UNLOCK_DECIDE
      return

    if st == self.ST_UNLOCK_DECIDE:
      ds = self._dialog_state()
      if ds == 'locked' and self.energie_freischalten:
        self.state = self.ST_UNLOCK_STORY
      else:
        self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_UNLOCK_STORY:
      # Freischalt-Story: Weiter/Weiter/OK (NCC-Buttons). Negativliste NIE
      # klicken (Veredelung/Bonuswandel/extrahieren) -- Detection von A liefert
      # nur die freigegebenen Buttons; ist keiner da, weiter zum Shop.
      self._click_story_buttons()
      self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_OPEN_SHOP:
      if not self.open_shop_via_dialog():
        return
      self.state = self.ST_LOCATE_HAMMER
      return

    if st == self.ST_LOCATE_HAMMER:
      slot = self._locate_shop_item('hammer')
      if slot is None:
        log.event(st, t('energiesplitter.item_not_in_shop', item='hammer'))
        self._stop('item_not_in_shop')
        return
      self._hammer_slot = slot
      self.state = self.ST_BUY_LOOP
      return

    if st == self.ST_BUY_LOOP:
      self._hammer_buy_step()
      return

    if st == self.ST_CHECK_DONE:
      if self.gekauft >= int(self.hammer_count):
        self._stop('done')
      else:
        self.state = self.ST_BUY_LOOP
      return

    self._stop('unknown_state')

  def _hammer_buy_step(self):
    """Ein Kauf-Schritt: Stack greedy waehlen, gold_guard, Rechtsklick,
    verify_purchase. Alle Backstops vorgeschaltet."""
    if self._action_cap_hit():
      return
    remaining = int(self.hammer_count) - self.gekauft
    free = self._free_slot_count()
    stacks = self._plan_stacks(remaining, free)
    if not stacks:
      # Kein sicherer Kaufplan (kein Platz / Zielzahl erreicht).
      if remaining <= 0:
        self.state = self.ST_CHECK_DONE
      else:
        log.event(self.state, t('energiesplitter.no_space'))
        self._stop('no_space')
      return

    stack = stacks[0]
    cost = stack * int(self.price_per_item)
    gold_before = self.gold_guard(cost)
    if gold_before is None:
      return  # gold_guard hat gestoppt

    if self._guarded():
      # Sollte hier nie erreichbar sein (GATE in runHack) -- doppelter Riegel.
      self._stop('phase0_not_ready')
      return

    self._right_click(*self._hammer_slot)
    self.actions_done += 1

    ok, gold_after = self.verify_purchase(gold_before, cost)
    if ok:
      self.gekauft += stack
      self.gold_spent += (gold_before - (gold_after or gold_before))
      self.consecutive_unverified = 0
      self._buy_retries = 0
      log.event(self.state, t(
          'energiesplitter.bought', stack=stack, done=self.gekauft,
          soll=self.hammer_count, gold_before=gold_before,
          gold_after=self._fmt_gold(gold_after)))
      self.state = self.ST_CHECK_DONE
    else:
      # Doppelkauf-Schutz: NICHT sofort erneut rechtsklicken.
      self._buy_retries += 1
      if self._buy_retries > 2 or self._note_unverified():
        if self.botting:  # _note_unverified hat evtl. schon gestoppt
          log.event(self.state, t('energiesplitter.buy_unverified',
                                  retries=self._buy_retries))
          self._stop('buy_unverified')

  # =======================================================================
  #  DOLCH-MODUS (Aktion 2 @ Waffenhaendler) -- 1:1-Verarbeitung
  # =======================================================================
  def _tick_dagger(self):
    st = self.state
    if st == self.ST_INIT:
      self._log_section()
      log.event(st, t('energiesplitter.started', mode=self.mode))
      self.state = self.ST_INVENTORY_BASE
      return

    if st == self.ST_INVENTORY_BASE:
      if not self._item_template_ready('hammer'):
        log.event(st, t('energiesplitter.item_template_missing', item='hammer'))
        self._stop('item_template_missing')
        return
      if not self._item_template_ready('dolch'):
        log.event(st, t('energiesplitter.item_template_missing', item='dolch'))
        self._stop('item_template_missing')
        return
      self.hammer_remaining = self._count_hammers()
      if self.hammer_remaining <= 0:
        self._stop('done')
        return
      self.state = self.ST_APPROACH_NPC
      return

    if st == self.ST_APPROACH_NPC:
      pt = self.approach_npc('npc_waffenhaendler')
      if pt is None:
        return
      self._npc_pt = pt
      self.state = self.ST_SELECT_NPC
      return

    if st == self.ST_SELECT_NPC:
      if not self._select_npc(self._npc_pt):
        return
      self.state = self.ST_OPEN_DIALOG
      return

    if st == self.ST_OPEN_DIALOG:
      if not self._open_dialog(self._npc_pt):
        return
      self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_OPEN_SHOP:
      if not self.open_shop_via_dialog():
        return
      if not self._ensure_bag_open():
        return
      self.state = self.ST_LOCATE_DOLCH
      return

    if st == self.ST_LOCATE_DOLCH:
      slot = self._locate_shop_item('dolch')
      if slot is None:
        log.event(st, t('energiesplitter.item_not_in_shop', item='dolch'))
        self._stop('item_not_in_shop')
        return
      self._dolch_shop_slot = slot
      self.state = self.ST_BUY_ONE_DOLCH
      return

    if st == self.ST_BUY_ONE_DOLCH:
      self._dagger_buy_one()
      return

    if st == self.ST_PROCESS_DRAG:
      self._dagger_process_drag()
      return

    if st == self.ST_VERIFY_PROCESS:
      self._dagger_verify_process()
      return

    if st == self.ST_RESCAN:
      # Drift-Korrektur (glow-aware Re-Scan via A); Fortschritt am Splitter,
      # nicht am Hammer-Bestand. Read-only -> direkt weiter.
      if self.hammer_remaining > 0:
        self.state = self.ST_BUY_ONE_DOLCH
      else:
        self._stop('done')
      return

    self._stop('unknown_state')

  def _dagger_buy_one(self):
    """Kauft GENAU 1 Dolch (A1), bestimmt den realen Lande-Slot per Diff."""
    if self._action_cap_hit():
      return
    cost = int(self.price_per_item)
    gold_before = self.gold_guard(cost)
    if gold_before is None:
      return

    before = self._inventory_signature()
    self._right_click(*self._dolch_shop_slot)
    self.actions_done += 1

    ok, gold_after = self.verify_purchase(gold_before, cost)
    if not ok:
      self._buy_retries += 1
      if self._buy_retries > 2 or self._note_unverified():
        if self.botting:
          log.event(self.state, t('energiesplitter.buy_unverified',
                                  retries=self._buy_retries))
          self._stop('buy_unverified')
      return

    after = self._inventory_signature()
    land = self._diff_landing_slot(before, after)
    if land is None:
      # Kauf verifiziert (Gold sank), aber Lande-Slot unklar -> kein Drag.
      self._snapshot('dolch_slot_unknown')
      self._stop('process_unverified')
      return

    self._dolch_inv_slot = land
    self._dolche_gekauft += 1
    self.gold_spent += (gold_before - (gold_after or gold_before))
    self.consecutive_unverified = 0
    self._buy_retries = 0
    self.state = self.ST_PROCESS_DRAG

  def _dagger_process_drag(self):
    """Drag 1 Hammer -> verifizierter Dolch-Slot. NUR wenn Quelle=Hammer UND
    Ziel=Dolch (beide Template-positiv). Sonst Stop, KEIN Drag (R11)."""
    if self._action_cap_hit():
      return
    src = self._classified_hammer_slot()
    dst_ok = self._slot_is('dolch', self._dolch_inv_slot)
    if src is None or not dst_ok:
      log.event(self.state, t('energiesplitter.drag_unsafe'))
      self._stop('drag_unsafe')
      return

    self._before_proc = self._shot()
    sx, sy = self._slot_center(src)
    dx, dy = self._slot_center(self._dolch_inv_slot)
    self._drag(sx, sy, dx, dy)
    self.actions_done += 1
    self.state = self.ST_VERIFY_PROCESS

  def _dagger_verify_process(self):
    """Verifiziert: Splitter-Stack gewachsen. NUR dann dekrementieren (R5)."""
    after = self._shot()
    growth = self.verify_process(self._before_proc, after)
    if growth > 0:
      self.splitter_summe += growth
      self.hammer_remaining -= 1
      self.consecutive_unverified = 0
      log.event(self.state, t(
          'energiesplitter.processed', value=growth,
          sum=self.splitter_summe, rest=self.hammer_remaining))
      # Anti-Drift: kauft ohne zu verarbeiten? (R10/R5-Abbruch)
      if self._dolche_gekauft - self.splitter_summe > 2:
        log.event(self.state, t('energiesplitter.process_unverified'))
        self._stop('process_unverified')
        return
      self.state = self.ST_RESCAN
    else:
      if not self._note_unverified():
        log.event(self.state, t('energiesplitter.process_unverified'))
        self._stop('process_unverified')

  # -- NPC-Selektion / Dialog (gemeinsam) ---------------------------------
  def _select_npc(self, pt):
    """Rechtsklick auf NPC -> Selektions-Ring formbasiert bestaetigen (A).
    Kein Ring -> Stop (nie blind Linksklick). Liefert ``True`` bei Ring."""
    if pt is None:
      self._stop('select_failed')
      return False
    self._right_click(pt[0], pt[1])
    bgr = self._shot()
    ring = False
    if bgr is not None and _detect is not None:
      try:
        ring = bool(_detect.selection_ring_present(bgr, pt))
      except Exception:  # pragma: no cover
        ring = False
    if not ring:
      log.event(self.state, t('energiesplitter.select_failed'))
      self._stop('select_failed')
      return False
    return True

  def _open_dialog(self, pt):
    """Linksklick NPC -> warten bis ``dialog_state`` != None. Timeout ->
    Snapshot + Stop."""
    self._left_click(pt[0], pt[1])
    bgr = self._shot()
    ds = None
    if bgr is not None:
      ds = self._dialog_state_of(bgr)
    if ds is None:
      self._snapshot('dialog_timeout')
      log.event(self.state, t('energiesplitter.dialog_timeout'))
      self._stop('dialog_timeout')
      return False
    return True

  def _dialog_state(self):
    bgr = self._shot()
    return self._dialog_state_of(bgr) if bgr is not None else None

  def _dialog_state_of(self, bgr):
    if _detect is None or bgr is None:
      return None
    try:
      return _detect.dialog_state(bgr)
    except Exception:  # pragma: no cover
      return None

  def _click_story_buttons(self):
    """Klickt die freigegebenen Story-Buttons (Weiter/Weiter/OK) sofern A sie
    findet. Negativliste wird von A nie als klickbar geliefert."""
    for key in ('weiter', 'weiter', 'ok'):
      bgr = self._shot()
      if bgr is None or _detect is None:
        return
      tpl = self._template(key)
      try:
        ok, pt, _ncc = _detect.find_shop_item(bgr, tpl)
      except Exception:  # pragma: no cover
        ok, pt = False, None
      if ok and pt is not None:
        self._left_click(pt[0], pt[1])

  # -- Inventar/Shop-Lese-Bruecken (defensiv; Read-only) ------------------
  def _item_template_ready(self, item):
    if _detect is None or not hasattr(_detect, 'item_template_available'):
      return False
    try:
      return bool(_detect.item_template_available(item))
    except Exception:  # pragma: no cover
      return False

  def _has_free_slot(self):
    return self._free_slot_count() > 0

  def _free_slot_count(self):
    if _detect is None or not hasattr(_detect, 'free_slot_count'):
      return 0
    bgr = self._shot()
    if bgr is None:
      return 0
    try:
      return max(0, int(_detect.free_slot_count(bgr)))
    except Exception:  # pragma: no cover
      return 0

  def _count_hammers(self):
    if _detect is None or not hasattr(_detect, 'count_item'):
      return 0
    bgr = self._shot()
    if bgr is None:
      return 0
    try:
      return max(0, int(_detect.count_item(bgr, 'hammer')))
    except Exception:  # pragma: no cover
      return 0

  def _locate_shop_item(self, item):
    if _detect is None:
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    tpl = self._template(item)
    try:
      ok, pt, _ncc = _detect.find_shop_item(bgr, tpl)
    except Exception:  # pragma: no cover
      ok, pt = False, None
    return pt if ok else None

  def _plan_stacks(self, target, free_slots):
    """Greedy Stack-Plan ueber Agent B (LAUFZEIT-gelesene Stack-Groessen).
    Single-Modus -> nur 1er. Defensiv -> [] bei fehlendem calc/Read."""
    if target <= 0:
      return []
    sizes = self._read_shop_stack_sizes()
    if self.prefer_stack == 'singles':
      sizes = (1,)
    if _calc is None or not hasattr(_calc, 'plan_stack_purchase'):
      # Ohne Rechner: defensiv genau 1er-Stacks, sofern Platz.
      return [1] if free_slots > 0 else []
    try:
      return list(_calc.plan_stack_purchase(target, free_slots, sizes))
    except Exception:  # pragma: no cover
      return []

  def _read_shop_stack_sizes(self):
    """Gelesene Stack-Groessen aus dem Shop (A); Fallback Shop-Bild-Tupel."""
    if _detect is not None and hasattr(_detect, 'read_shop_stack_sizes'):
      try:
        sizes = _detect.read_shop_stack_sizes(self._shot())
        if sizes:
          return tuple(sizes)
      except Exception:  # pragma: no cover
        pass
    return (200, 100, 10, 1)

  def _ensure_bag_open(self):
    """Im Shop ist rechts oft 'Ausruestungsfenster' statt Tasche -> per
    panel_is_bag pruefen. Nicht-Bag -> Stop (kein blindes Drag-Ziel)."""
    if _detect is None or not hasattr(_detect, 'panel_is_bag'):
      return True  # Detektor liefert A; ohne ihn nicht blockieren (GATE deckt ab)
    bgr = self._shot()
    try:
      if bgr is not None and _detect.panel_is_bag(bgr):
        return True
    except Exception:  # pragma: no cover
      pass
    self._snapshot('bag_not_open')
    log.event(self.state, t('energiesplitter.shop_not_open'))
    self._stop('bag_not_open')
    return False

  def _inventory_signature(self):
    if _detect is None or not hasattr(_detect, 'inventory_signature'):
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    try:
      return _detect.inventory_signature(bgr)
    except Exception:  # pragma: no cover
      return None

  def _diff_landing_slot(self, before, after):
    if _detect is None or not hasattr(_detect, 'diff_landing_slot'):
      return None
    if before is None or after is None:
      return None
    try:
      return _detect.diff_landing_slot(before, after)
    except Exception:  # pragma: no cover
      return None

  def _classified_hammer_slot(self):
    """Liefert einen als HAMMER klassifizierten Quell-Slot (A), sonst None."""
    if _detect is None or not hasattr(_detect, 'find_inventory_item'):
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    try:
      ok, slot = _detect.find_inventory_item(bgr, 'hammer')
      return slot if ok else None
    except Exception:  # pragma: no cover
      return None

  def _slot_is(self, item, slot):
    if _detect is None or not hasattr(_detect, 'slot_is') or slot is None:
      return False
    bgr = self._shot()
    if bgr is None:
      return False
    try:
      return bool(_detect.slot_is(bgr, slot, item))
    except Exception:  # pragma: no cover
      return False

  def _slot_center(self, slot):
    if _geometry is not None and hasattr(_geometry, 'slot_center'):
      try:
        return _geometry.slot_center(slot)
      except Exception:  # pragma: no cover
        pass
    # Slot kann bereits ein (x, y)-Punkt sein.
    if isinstance(slot, (tuple, list)) and len(slot) == 2:
      return int(slot[0]), int(slot[1])
    return 0, 0
