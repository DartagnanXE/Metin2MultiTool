"""EnergiesplitterBot -- Bot-Kern + Phase-0-GATE + State-Maschinen (Eigentuemer D).

EINE Klasse, ZWEI Aktionen (Modus-Schalter ``self.mode``):

* ``MODE_HAMMER``  -- Aktion 1: ``stack_count`` (X) mal einen **200er-Hammer-
  Stack** am Alchemisten kaufen (template-verifiziert, Re-Read-belegt), dann
  Auto-Stop.
* ``MODE_DAGGER``  -- Aktion 2: Schleife bis keine Haemmer mehr im Inventar:
  ``daggers_per_round`` Dolche kaufen, dann EINZELN NACHEINANDER verarbeiten
  (je 1 Drag eines Hammer-STACKS auf einen Dolch verbraucht 1 Hammer + 1 Dolch).

Integration ueber den ``run_loop``-Bot-Tick (wie ``fishbot``/``puzzlebot``):
``set_to_begin(values)`` friert die Config ein und ruft den Phase-0-GATE,
``runHack()`` fuehrt GENAU EINEN blockierenden Tick aus und stoppt sich bei
jeder Stop-Bedingung selbst (``self.botting = False``).

PHASE-0-GATE (harter Blocker, §2 CONTRACT): solange ``self.dry_run`` ODER
``not self.armed``, ruft der Bot NIE ``rightClick``/``click``/``drag``/
``keyDown`` -- er liest, loggt und stoppt. ``armed`` setzt ALLEIN
``phase0_gate()`` = ``detect.assets_ready(mode).ready AND
geometry.is_calibrated(wincap) AND detect.grid_present()`` (Templates + Shop-
Anker bereit, Fenster-Groesse 800x600 UND aufloesbares Inventar-Raster). YANG
spielt seit dem Umbau 2026-06-16 KEINE Rolle mehr -- kein Preis, kein Kontostand,
keine Ausgabe-Verfolgung. Als OCR-unabhaengige Backstops bleiben ``max_actions``
(``_action_cap_hit``) und ``consecutive_unverified_stop`` in JEDER Kauf-/
Verarbeitungs-Entscheidung wirksam, plus die Erkennung-vor-Aktion (Kauf/Drag nur
auf template-verifizierte Ziele).

Headless-Sicherheit: ``pydirectinput`` und die Schwester-Module von Agent A
(``detect``/``geometry``) werden WEICH importiert. Fehlt etwas, landet es als
``missing``-Eintrag im GATE -- kein ImportError, kein Klick.
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

# Drag-Primitiv WIEDERVERWENDEN (A2) -- nie neu bauen. mouseUp im finally.
try:
    from inventory_discard import drag as _discard_drag
except Exception:  # pragma: no cover
    _discard_drag = None


MODE_HAMMER = 'hammer'
MODE_DAGGER = 'dagger'

# State-Maschinen + Bruecken als Mixins (NACH den weichen Globals importiert,
# damit deren Lauf-Lesen von ``_detect``/``_geometry`` ueber dieses Modul greift
# -- inkl. Test-Patching ``mock.patch.object(esbot_mod, ...)``).
from energiesplitter.bridges import BridgesMixin
from energiesplitter.flow_hammer import HammerFlowMixin
from energiesplitter.flow_dagger import DaggerFlowMixin


class EnergiesplitterBot(HammerFlowMixin, DaggerFlowMixin, BridgesMixin):
  """Energiesplitter-Bot mit Modus-Schalter (siehe Modul-Docstring, CONTRACT §1).

  Die zwei State-Maschinen (Hammer/Dolch) und die Detect-/Geometry-Bruecken sind
  in :mod:`energiesplitter.flow_hammer` / :mod:`energiesplitter.flow_dagger` /
  :mod:`energiesplitter.bridges` als Mixins ausgelagert -- die oeffentliche API
  (Attribute/Methoden) bleibt unveraendert auf DIESER Klasse."""

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
  max_actions = 2
  consecutive_unverified_stop = 3

  # Fixe Mechanik-Konstante: ein Hammer-Kauf ist IMMER ein 200er-Stack.
  HAMMER_STACK_SIZE = 200

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
    self.stack_count = 1
    self.energie_freischalten = True
    self.daggers_per_round = 1
    self.mouse_pause = 0.05
    self.keyboard_pause = 0.10
    self.speed_profile = 'fast'
    self.jitter_pct = 0.15
    self.birdseye_on_miss = True
    self.birds_eye_key = 'g'
    self.max_actions = 2
    self.consecutive_unverified_stop = 3
    self.dry_run = True
    self.armed = False

  def _reset_counters(self):
    # gekauft = bisher gekaufte 200er-Stacks (Aktion 1).
    self.gekauft = 0
    self.hammer_remaining = 0
    self.splitter_summe = 0
    self.actions_done = 0
    self.consecutive_unverified = 0
    self._dolche_gekauft = 0
    self._buy_retries = 0
    self._npc_tries = 0
    self._birdseye_used = False
    # Dolch-Verarbeitung: Warteschlange der gekauften, noch nicht verarbeiteten
    # Dolch-Slots der aktuellen Runde (EINZELN nacheinander abgearbeitet).
    self._dagger_queue = []
    self._round_to_buy = 0

  # -- 'scharf'-Schalter (bewusste Tester-Aktion, CONTRACT §2/§7) ----------
  # KANONISCHER Name fuer den bewussten Live-/scharf-Schalter. Default NICHT
  # scharf = Simulation/dry: alles erkennen + loggen, KEINE Maus. ``scharf`` ist
  # exakt die Umkehrung von ``dry_run`` (EINE Wahrheit, kein zweiter Riegel, der
  # auseinanderlaufen koennte): das erste echte Yang-Ausgeben verlangt ``dry_run
  # = False`` (UI-Entsicherung) UND ``armed`` (Phase-0-GATE) UND alle Backstops.
  @property
  def scharf(self):
    """``True`` nur, wenn der Bot bewusst entsichert ist (``not dry_run``)."""
    return not bool(self.dry_run)

  @scharf.setter
  def scharf(self, value):
    self.dry_run = not bool(value)

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
    Zaehler, leitet ``max_actions`` ab und ruft den Phase-0-GATE (setzt
    ``self.armed``). Erzeugt ``wincap``. KEIN Klick.

    Idempotent re-aufrufbar (run_loop setzt ``self.mode`` vor dem Aufruf).
    Fehlt das Spiel-Fenster, wird ``self._stop_reason`` gesetzt; das Laufflag
    bleibt run_loop-gesteuert (botting setzt der RunLoop).
    """
    self._reset_counters()
    self.state = self.ST_INIT
    self._stop_reason = None
    self._missing = []

    self._freeze_config(values or {})

    # max_actions ableiten (0 = auto): die Aktions-Obergrenze ist der einzige
    # verbliebene Auto-Backstop. Aktion 1 braucht ~stack_count Kaeufe; Aktion 2
    # haengt am Inventar-Bestand (open-ended) -> grosszuegiger Auto-Default.
    soll = max(1, int(self.stack_count))
    if int(self.max_actions) <= 0:
      self.max_actions = max(50, round(3 * soll))

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

    self.stack_count = int(_get('-ES_STACK_COUNT-', 1))
    self.energie_freischalten = bool(_get('-ES_FREISCHALTEN-', True))
    self.daggers_per_round = int(_get('-ES_DAGGERS_PER_ROUND-', 1))
    self.mouse_pause = float(_get('-ES_MOUSE_PAUSE-', 0.05))
    self.keyboard_pause = float(_get('-ES_KB_PAUSE-', 0.10))
    self.speed_profile = str(_get('-ES_SPEED-', 'fast'))
    self.jitter_pct = float(_get('-ES_JITTER-', 0.15))
    self.birdseye_on_miss = bool(_get('-ES_BIRDSEYE-', True))
    self.birds_eye_key = 'g'
    self.max_actions = int(_get('-ES_MAX_ACTIONS-', 0))
    self.consecutive_unverified_stop = int(_get('-ES_UNVERIF_STOP-', 3))
    self.dry_run = bool(_get('-ES_DRY_RUN-', True))

  # -- Phase-0-GATE (harter Blocker, CONTRACT §2) -------------------------
  def phase0_gate(self):
    """Setzt ``self.armed`` = (Assets bereit AND 800x600-kalibriert AND
    Inventar-Raster aufloesbar). YANG spielt KEINE Rolle mehr.

    Delegiert die reine Pruefung an Agent A:
      1. ``detect.assets_ready(mode)`` -- Item-/NPC-Templates + Shop-Anker bereit.
      2. ``geometry.is_calibrated(wincap)`` -- Fenster ~800x600.
      3. ``detect.grid_present()`` -- Inventar-Raster (Slot 1 -> Pixel) aufloesbar
         (sichere Drag-/Slot-Ziele).
    Fehlt ein Modul (Build-Reihenfolge) ODER das Fenster ODER das Raster, bleibt
    ``armed=False`` und die Luecke landet in ``missing`` (sicher = rot). Liefert
    ``(armed, missing)`` und speichert ``self._missing``.

    Erkennung-vor-Aktion bleibt unveraendert (Kauf/Drag weiter nur auf Template-
    verifizierte Ziele); die OCR-unabhaengigen Backstops sind ``max_actions`` +
    ``consecutive_unverified_stop``.
    """
    missing = []

    mode = self.mode if self.mode in (MODE_HAMMER, MODE_DAGGER) else MODE_HAMMER

    # 1) Assets (Item-/NPC-Templates / Shop-Anker) -- via Agent A.
    if _detect is None or not hasattr(_detect, 'assets_ready'):
      missing.append('detect_module')
    else:
      try:
        _ready, miss = _detect.assets_ready(mode)
        if miss:
          missing.extend(list(miss))
      except Exception:
        missing.append('detect_error')

    # 2) Kalibrierung 800x600 -- via Agent A (IMMER gefordert, beide Modi).
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

    # 3) Inventar-Raster aufloesbar (sichere Drag-/Slot-Ziele).
    if not self._grid_calibrated():
      missing.append('grid_calibration')

    self._missing = missing
    self.armed = (len(missing) == 0)
    # GATE-Entscheidung strukturiert protokollieren (Wahrnehmung/Fehler): bei rot
    # die EXAKTE Liste der fehlenden Assets/Kalibrierungen -- der Tester sieht
    # sofort, WORAN es haengt. Absturzsicher.
    try:
      if self.armed:
        log.event(self.state, 'Phase-0-GATE: gruen (scharf erlaubt)', modus=mode)
      else:
        log.event(self.state, 'Phase-0-GATE: rot (kein Kauf/Drag)',
                  modus=mode, fehlend=', '.join(missing))
    except Exception:  # pragma: no cover - Logging darf das Gate nie kippen
      pass
    return self.armed, missing

  def _grid_calibrated(self):
    """``True``, wenn das Inventar-Raster aufloesbar ist (Slot 1 -> Pixel).

    Nutzt ``detect.grid_present`` (reiner Kalibrier-Check ueber
    ``calibration.slot_center``) -- garantiert sichere Drag-/Slot-Ziele.
    Defensiv ``False`` bei fehlendem Modul. Read-only, wirft nie."""
    if _detect is None or not hasattr(_detect, 'grid_present'):
      return False
    try:
      return bool(_detect.grid_present())
    except Exception:  # pragma: no cover - defensiv
      return False

  # -- runHack: EIN blockierender Tick ------------------------------------
  def runHack(self):
    """Ein Tick: verzweigt nach ``self.mode``. Bei ``dry_run or not armed``
    nur Read-Only-Erkennung + Log + Selbst-Stop ("Phase-0 nicht bereit").
    Stoppt sich bei jeder Stop-Bedingung selbst (``self.botting=False``)."""
    if not self.botting:
      return

    # Abbruch-Seam (F6): hat Vorrang vor jeder teuren Aktion.
    if self.abort_fn():
      try:
        log.event(self.state, 'Abbruch-Signal (F6) erkannt -- stoppe vor jeder Aktion')
      except Exception:  # pragma: no cover
        pass
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

    try:
      log.event(self.state, 'ZUSTAND: Tick', modus=self.mode,
                actions_done=self.actions_done, gekauft=self.gekauft,
                rest=self.hammer_remaining)
    except Exception:  # pragma: no cover
      pass
    # Verhalten UNVERAENDERT: ein unerwarteter Tick-Fehler wird protokolliert
    # (mit Traceback fuer den Tester) und dann RE-RAISED -- das Logging darf den
    # Fehler nicht verschlucken (das waere eine Verhaltensaenderung).
    try:
      if self.mode == MODE_HAMMER:
        self._tick_hammer()
      else:
        self._tick_dagger()
    except Exception as exc:
      try:
        log.error('FEHLER: unerwartete Ausnahme im Tick (Modus {}, State {})'.format(
            self.mode, self.state), exc=exc)
      except Exception:  # pragma: no cover - Logging selbst darf nie werfen
        pass
      raise

  # -- Selbst-Stop --------------------------------------------------------
  def _stop(self, reason):
    """Bilanz loggen, Cursor NICHT bewegen (kein Klick), botting=False."""
    self._stop_reason = reason
    try:
      log.event(self.state, t(
          'energiesplitter.done',
          hammers=self.gekauft, daggers=self._dolche_gekauft,
          splitters=self.splitter_summe, reason=reason))
    except Exception:  # pragma: no cover - Logging darf nie den Stop kippen
      pass
    self.state = self.ST_STOP
    self.botting = False

  def _log_section(self):
    key = ('energiesplitter.section_hammer' if self.mode == MODE_HAMMER
           else 'energiesplitter.section_dagger')
    try:
      log.section(t(key))
    except Exception:  # pragma: no cover
      pass
    # Volle aktive Konfiguration + Kalibrier-/Asset-Status EINMAL pro Lauf-Start
    # protokollieren (Zustand/Fortschritt D): der Tester sieht sofort, womit der
    # Bot startet -- Modus, Mengen, alle Safety-Backstops, scharf vs Simulation
    # UND ob der Phase-0-GATE gruen ist (sonst die fehlenden Artefakte). Reines
    # Logging, absturzsicher.
    self._log_config_state()

  def _log_config_state(self):
    """Loggt die eingefrorene Konfiguration + GATE-/Asset-Status. Wirft nie."""
    try:
      log.event(self.state, 'Konfiguration',
                modus=self.mode,
                betrieb=('SCHARF' if self.scharf else 'SIMULATION'),
                dry_run=self.dry_run,
                armed=self.armed,
                stack_count=self.stack_count,
                daggers_per_round=self.daggers_per_round,
                max_actions=self.max_actions,
                unverif_stop=self.consecutive_unverified_stop,
                freischalten=self.energie_freischalten)
    except Exception:  # pragma: no cover - Logging darf nie den Lauf kippen
      pass
    try:
      if self.armed and not self._missing:
        log.event(self.state, 'GATE gruen -- alle Assets/Kalibrierung bereit')
      else:
        log.event(self.state, 'GATE rot -- es wird NICHT gekauft/gedraggt',
                  fehlend=(', '.join(self._missing) or 'dry_run'))
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
    try:
      log.event(self.state, 'ABSICHT: NPC ansprechen', npc=npc_template_key)
    except Exception:  # pragma: no cover
      pass
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
    try:
      log.event(self.state, 'WAHRNEHMUNG: NPC-Suche', npc=npc_template_key,
                gefunden=bool(ok and pt is not None),
                ncc=round(float(_ncc), 3), pos=(tuple(pt) if pt is not None else None))
    except Exception:  # pragma: no cover
      pass
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
    try:
      log.event(self.state, "WAHRNEHMUNG: Dialogzeile 'Laden oeffnen'",
                gefunden=bool(ok and pt is not None), ncc=round(float(_ncc), 3),
                pos=(tuple(pt) if pt is not None else None))
    except Exception:  # pragma: no cover
      pass
    if not ok or pt is None:
      self._snapshot('shop_not_open')
      log.event(self.state, t('energiesplitter.shop_not_open'))
      self._stop('shop_not_open')
      return False
    try:
      log.event(self.state, "ABSICHT: 'Laden oeffnen' anklicken", ziel=tuple(pt))
    except Exception:  # pragma: no cover
      pass
    self._left_click(pt[0], pt[1])
    after = self._shot()
    is_open = False
    try:
      is_open = bool(_detect.shop_open(after)) if after is not None else False
    except Exception:  # pragma: no cover
      is_open = False
    try:
      log.event(self.state, 'WAHRNEHMUNG: Shop offen?', offen=is_open)
    except Exception:  # pragma: no cover
      pass
    if not is_open:
      self._snapshot('shop_not_open')
      log.event(self.state, t('energiesplitter.shop_not_open'))
      self._stop('shop_not_open')
      return False
    return True

  def verify_hammer_purchase(self, bag_before):
    """Verifiziert einen Hammer-Stack-Kauf per Re-Read: der Hammer-Bestand im
    Beutel ist nach dem Kauf gewachsen. YANG wird NICHT gelesen.

    ``bag_before`` = gemessener Hammer-Bestand VOR dem Kauf (oder ``None``, wenn
    nicht messbar). Liefert ``True``, wenn der Bestand nachweislich gewachsen ist
    (``_verify_bag_growth`` erwartet >= 1 Slot Zuwachs durch den 200er-Stack);
    ist der Bag-Stack NICHT messbar (Phase-0-Stub), gilt der Kauf als belegt
    (``True``) -- der GATE haelt scharfe Laeufe ohne Live-Asset ohnehin zurueck.
    Reine Lese-Pruefung -- kein Klick. Wirft nie."""
    ok = bool(self._verify_bag_growth(bag_before, 1))
    try:
      log.event(self.state, 'WAHRNEHMUNG: Hammer-Kauf-Verifikation (Re-Read)',
                bag_vorher=bag_before, bag_messbar=self._bag_count_measurable(),
                verifiziert=bool(ok))
    except Exception:  # pragma: no cover
      pass
    return ok

  def verify_process(self, before_bgr, after_bgr):
    """Verifiziert die 1:1-Verarbeitung NACH der neuen Grundwahrheit (User
    2026-06-15): es gibt **KEIN Bestaetigungsfenster** -- der Erfolg wird NICHT
    am Splitter-Aussehen festgemacht (das ist unbeobachtbar), sondern an zwei
    re-gelesenen Inventar-Tatsachen:

      1. der gerade gefuellte **Dolch-Slot ist jetzt LEER** (Dolch verbraucht), UND
      2. der **Hammer-Bestand ist um genau 1 gesunken** (Hammer verbraucht).

    Liefert ``1`` bei verifizierter Verarbeitung, sonst ``0`` (der Caller
    dekrementiert NUR bei ``> 0`` -- R5). Read-only, kein Klick, wirft nie.

    Rueckwaerts-kompatibel: ist eine ``read_splitter_growth``-Messung verfuegbar
    und positiv (Live-Asset P0.5 spaeter), zaehlt auch das als Beleg.
    """
    if _detect is None:
      return 0
    after = after_bgr if after_bgr is not None else self._shot()

    # (1) Ziel-Dolch-Slot jetzt leer? (Dolch verbraucht.)
    slot = getattr(self, '_dolch_inv_slot', None)
    slot_emptied = self._slot_is_empty(slot, after) if slot is not None else False

    # (2) Hammer-Bestand um 1 gesunken? (Hammer verbraucht.) NUR erzwungen,
    # wenn der Bag-Stack real messbar ist (sonst traegt der Dolch-Slot-Beleg
    # allein -- der GATE haelt scharfe Laeufe ohne Live-Assets ohnehin zurueck).
    before_n = getattr(self, '_hammer_count_before_proc', None)
    if self._bag_count_measurable() and before_n is not None:
      now_n = self._count_hammers()
      hammer_dropped = (now_n is not None and now_n == before_n - 1)
    else:
      hammer_dropped = True  # nicht messbar -> kein blockierender Zusatz-Riegel

    try:
      log.event(self.state, 'WAHRNEHMUNG: Verarbeitungs-Verifikation (Re-Read)',
                dolch_slot_leer=bool(slot_emptied),
                hammer_dekrementiert=bool(hammer_dropped),
                bag_messbar=self._bag_count_measurable(),
                hammer_vorher=before_n)
    except Exception:  # pragma: no cover
      pass
    if slot_emptied and hammer_dropped:
      return 1

    # Optionaler Zusatz-Beleg (P0.5): echter Splitter-Zuwachs, falls messbar.
    try:
      if before_bgr is not None and after is not None:
        growth = int(_detect.read_splitter_growth(before_bgr, after))
        if growth > 0 and (slot_emptied or hammer_dropped):
          try:
            log.event(self.state, 'WAHRNEHMUNG: Splitter-Zuwachs als Zusatz-Beleg',
                      zuwachs=growth)
          except Exception:  # pragma: no cover
            pass
          return 1
    except Exception:  # pragma: no cover
      pass
    return 0

  # -- NPC-Selektion / Dialog (gemeinsam) ---------------------------------
  def _select_npc(self, pt):
    """Rechtsklick auf NPC -> Selektions-Ring formbasiert bestaetigen (A).
    Kein Ring -> Stop (nie blind Linksklick). Liefert ``True`` bei Ring."""
    if pt is None:
      self._stop('select_failed')
      return False
    try:
      log.event(self.state, 'ABSICHT: NPC rechtsklicken (anvisieren)', ziel=tuple(pt))
    except Exception:  # pragma: no cover
      pass
    self._right_click(pt[0], pt[1])
    bgr = self._shot()
    ring = False
    if bgr is not None and _detect is not None:
      try:
        ring = bool(_detect.selection_ring_present(bgr, pt))
      except Exception:  # pragma: no cover
        ring = False
    try:
      log.event(self.state, 'WAHRNEHMUNG: Selektions-Ring', ring=bool(ring),
                bei=tuple(pt))
    except Exception:  # pragma: no cover
      pass
    if not ring:
      log.event(self.state, t('energiesplitter.select_failed'))
      self._stop('select_failed')
      return False
    return True

  def _open_dialog(self, pt):
    """Linksklick NPC -> warten bis ``dialog_state`` != None. Timeout ->
    Snapshot + Stop."""
    try:
      log.event(self.state, 'ABSICHT: NPC linksklicken (Dialog oeffnen)', ziel=tuple(pt))
    except Exception:  # pragma: no cover
      pass
    self._left_click(pt[0], pt[1])
    bgr = self._shot()
    ds = None
    if bgr is not None:
      ds = self._dialog_state_of(bgr)
    try:
      log.event(self.state, 'WAHRNEHMUNG: Dialog-Zustand', zustand=ds,
                energie_freischalt_option=(ds == 'locked'))
    except Exception:  # pragma: no cover
      pass
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
      try:
        log.event(self.state, 'WAHRNEHMUNG: Story-Button', button=key,
                  gefunden=bool(ok and pt is not None),
                  pos=(tuple(pt) if pt is not None else None))
      except Exception:  # pragma: no cover
        pass
      if ok and pt is not None:
        try:
          log.event(self.state, 'ABSICHT: Story-Button klicken', button=key,
                    ziel=tuple(pt))
        except Exception:  # pragma: no cover
          pass
        self._left_click(pt[0], pt[1])
