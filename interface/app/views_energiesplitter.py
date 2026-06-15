# -*- coding: utf-8 -*-
"""EnergiesplitterViewMixin -- der Energiesplitter-Reiter (EINE Ansicht, ZWEI
Aktionen).

Aktion 1 ("Hammer kaufen") kauft am Alchemisten Haemmer; Aktion 2 ("Dolche
kaufen + verarbeiten") kauft am Waffenhaendler Dolche und verarbeitet sie 1:1
zu Energiesplittern. Beide laufen ueber den ``run_loop``-Bot-Tick (wie
``fishbot``/``puzzlebot``) -- KEIN eigener Worker-Thread (anders als ``seher``):
Der Start setzt ueber ``controller.set_mode(...)`` den aktiven Modus und ruft
``controller.on_start_stop()``; der RunLoop ruft danach pro Tick
``esbot.runHack()`` (Integration = Agent C).

Die Rechen-Logik (Yang-Aufschluesselung) lebt AUSSCHLIESSLICH in
``energiesplitter/calc.py`` -- diese View ruft sie nur auf und stellt das
Ergebnis dar. Solange Item-Icons/Templates fehlen ODER das Fenster nicht
800x600 ist, laeuft im Bot NUR die Erkennung (Phase-0-Gate, Agent D) -- die UI
weist im Hilfetext darauf hin.
"""

from interface.app._common import *  # noqa: F401,F403

from energiesplitter import calc

# Modus-Werte (Contract §0): EIN Reiter, zwei Start-Aktionen -> zwei APP_MODES.
ES_MODE_HAMMER = 'energiesplitter_hammer'
ES_MODE_DAGGER = 'energiesplitter_dagger'

# Enum-Auswahlen (value <-> Anzeige). Die Werte spiegeln das Config-Schema
# (Contract §3); die Labels sind kurze Klartext-Bezeichner (sprachneutral genug
# fuer ein Laien-Tool, ohne je-Sprache-Churn).
PREFER_STACK_LABELS = (('largest_fit', 'largest_fit'),
                       ('singles', 'singles'))
PROCESS_MODE_LABELS = (('one_to_one', '1:1'),
                       ('batch', 'batch'))
SPEED_PROFILE_LABELS = (('safe', 'safe'),
                        ('fast', 'fast'))


def _fmt_yang(value):
  """Formatiert einen Yang-Betrag mit Tausenderpunkten ('15.000')."""
  try:
    return '{:,}'.format(int(value)).replace(',', '.')
  except (TypeError, ValueError):
    return '0'


class EnergiesplitterViewMixin:
  def _build_energiesplitter_view(self, _parent):
    """Baut die Energiesplitter-Sicht (zwei Start-Knoepfe + Settings + Rechner)."""
    view = self._new_view('energiesplitter')
    self._view_header(view, t('ui.view_energiesplitter'),
                      t('ui.energiesplitter_sub'))

    card = Section(view, t('ui.group_energiesplitter'))
    card.grid(row=1, column=0, sticky='ew', pady=(0, 8))
    body = card.body
    body.grid_columnconfigure(0, weight=1)

    # -- Die zwei Start/Stop-Knoepfe (Aktion 1 / Aktion 2) ----------------
    btns = ctk.CTkFrame(body, fg_color='transparent')
    btns.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 2))
    btns.grid_columnconfigure(0, weight=1)
    btns.grid_columnconfigure(1, weight=1)

    self._es_hammer_btn = ctk.CTkButton(
        btns, text=t('ui.es_hammer_start_btn'), height=44, corner_radius=12,
        font=ctk.CTkFont(size=14, weight='bold'),
        fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
        command=lambda: self._on_es_start_stop('hammer'))
    self._es_hammer_btn.grid(row=0, column=0, sticky='ew', padx=(0, 4))

    self._es_dagger_btn = ctk.CTkButton(
        btns, text=t('ui.es_dagger_start_btn'), height=44, corner_radius=12,
        font=ctk.CTkFont(size=14, weight='bold'),
        fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
        command=lambda: self._on_es_start_stop('dagger'))
    self._es_dagger_btn.grid(row=0, column=1, sticky='ew', padx=(4, 0))

    InfoBadge(body, text=t('ui.es_help')).grid(
        row=0, column=2, sticky='ne', padx=(6, 0))

    # -- Hammer-Einstellungen (Aktion 1) ----------------------------------
    self._es_widgets = {}
    opts = ctk.CTkFrame(body, fg_color='transparent')
    opts.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(8, 0))
    opts.grid_columnconfigure(1, weight=1)
    r = 0

    # Anzahl Haemmer -- treibt den Live-Rechner.
    self._es_count_var = ctk.StringVar(value='200')
    r = self._es_row(opts, r, t('ui.es_count_label'),
                     self._es_entry('hammer', 'hammer_count',
                                    self._es_count_var, opts,
                                    on_change=self._es_update_calc))

    # Energie freischalten (Toggle).
    self._es_freischalten_var = ctk.BooleanVar(value=True)
    sw = ctk.CTkSwitch(
        opts, text=t('ui.es_freischalten_label'),
        variable=self._es_freischalten_var,
        command=lambda: self._es_set('hammer', 'energie_freischalten',
                                     bool(self._es_freischalten_var.get())))
    sw.grid(row=r, column=0, columnspan=2, sticky='w', pady=(6, 0))
    self._es_widgets['energie_freischalten'] = sw
    r += 1

    # Preis pro Stueck (Hammer) -- treibt ebenfalls den Rechner.
    self._es_price_var = ctk.StringVar(value='15000')
    r = self._es_row(opts, r, t('ui.es_price_label'),
                     self._es_entry('hammer', 'price_per_item',
                                    self._es_price_var, opts,
                                    on_change=self._es_update_calc))

    # Yang-Reserve (Hammer) -- Safety-Backstop.
    self._es_gold_floor_var = ctk.StringVar(value='50000')
    r = self._es_row(opts, r, t('ui.es_gold_floor_label'),
                     self._es_entry('hammer', 'gold_floor',
                                    self._es_gold_floor_var, opts))

    # max_gold_spend (0 = auto) -- Safety-Backstop.
    self._es_max_spend_var = ctk.StringVar(value='0')
    r = self._es_row(opts, r, t('ui.es_max_spend_label'),
                     self._es_entry('hammer', 'max_gold_spend',
                                    self._es_max_spend_var, opts))

    # prefer_stack (enum).
    self._es_prefer_stack_var = ctk.StringVar(value='largest_fit')
    r = self._es_row(opts, r, 'prefer_stack',
                     self._es_optionmenu('hammer', 'prefer_stack',
                                         self._es_prefer_stack_var,
                                         PREFER_STACK_LABELS, opts))

    # -- Dolch-Einstellungen (Aktion 2) -----------------------------------
    self._es_process_mode_var = ctk.StringVar(value='one_to_one')
    r = self._es_row(opts, r, 'process_mode',
                     self._es_optionmenu('dagger', 'process_mode',
                                         self._es_process_mode_var,
                                         PROCESS_MODE_LABELS, opts))

    self._es_batch_var = ctk.StringVar(value='50')
    r = self._es_row(opts, r, 'batch_size',
                     self._es_entry('dagger', 'batch_size',
                                    self._es_batch_var, opts))

    # -- Geteilte Einstellungen (shared) ----------------------------------
    self._es_speed_var = ctk.StringVar(value='fast')
    r = self._es_row(opts, r, 'speed_profile',
                     self._es_optionmenu('shared', 'speed_profile',
                                         self._es_speed_var,
                                         SPEED_PROFILE_LABELS, opts))

    self._es_mouse_pause_var = ctk.StringVar(value='0.05')
    r = self._es_row(opts, r, 'mouse_pause',
                     self._es_entry('shared', 'mouse_pause',
                                    self._es_mouse_pause_var, opts,
                                    is_float=True))

    self._es_kb_pause_var = ctk.StringVar(value='0.10')
    r = self._es_row(opts, r, 'keyboard_pause',
                     self._es_entry('shared', 'keyboard_pause',
                                    self._es_kb_pause_var, opts,
                                    is_float=True))

    self._es_max_actions_var = ctk.StringVar(value='0')
    r = self._es_row(opts, r, t('ui.es_max_actions_label'),
                     self._es_entry('shared', 'max_actions',
                                    self._es_max_actions_var, opts))

    self._es_unverif_var = ctk.StringVar(value='3')
    r = self._es_row(opts, r, 'consecutive_unverified_stop',
                     self._es_entry('shared', 'consecutive_unverified_stop',
                                    self._es_unverif_var, opts))

    self._es_jitter_var = ctk.StringVar(value='0.15')
    r = self._es_row(opts, r, 'jitter_pct',
                     self._es_entry('shared', 'jitter_pct',
                                    self._es_jitter_var, opts,
                                    is_float=True))

    self._es_birdseye_var = ctk.BooleanVar(value=True)
    bsw = ctk.CTkSwitch(
        opts, text='birdseye_on_miss',
        variable=self._es_birdseye_var,
        command=lambda: self._es_set('shared', 'birdseye_on_miss',
                                     bool(self._es_birdseye_var.get())))
    bsw.grid(row=r, column=0, columnspan=2, sticky='w', pady=(6, 0))
    self._es_widgets['birdseye_on_miss'] = bsw
    r += 1

    # Scharf / Live -- der BEWUSSTE arm-Schalter. Er ist die INVERSION von
    # ``dry_run``: Schalter AUS = Simulation (dry_run=True, sicher: nur
    # Erkennung), Schalter AN = scharfer Lauf, der ECHTES Yang ausgibt
    # (dry_run=False). Default AUS -> das erste echte Yang-Ausgeben ist eine
    # bewusste Tester-Aktion (erst nach Phase-0).
    self._es_scharf_var = ctk.BooleanVar(value=False)
    ssw = ctk.CTkSwitch(
        opts, text=t('ui.es_scharf_label'),
        variable=self._es_scharf_var,
        progress_color=DANGER,
        command=lambda: self._es_set('shared', 'dry_run',
                                     not bool(self._es_scharf_var.get())))
    ssw.grid(row=r, column=0, sticky='w', pady=(6, 0))
    InfoBadge(opts, text=t('ui.es_scharf_help')).grid(
        row=r, column=1, sticky='w', padx=(6, 0), pady=(6, 0))
    self._es_widgets['dry_run'] = ssw
    r += 1

    # -- Live-Yang-Rechner ------------------------------------------------
    calc_card = Section(view, t('ui.es_calc_title'))
    calc_card.grid(row=2, column=0, sticky='ew', pady=(0, 8))
    cbody = calc_card.body
    cbody.grid_columnconfigure(0, weight=1)
    self._es_calc_hammer = ctk.CTkLabel(
        cbody, text='', anchor='w', text_color=TEXT,
        font=ctk.CTkFont(size=12))
    self._es_calc_hammer.grid(row=0, column=0, sticky='w')
    self._es_calc_dagger = ctk.CTkLabel(
        cbody, text='', anchor='w', text_color=TEXT,
        font=ctk.CTkFont(size=12))
    self._es_calc_dagger.grid(row=1, column=0, sticky='w')
    self._es_calc_total = ctk.CTkLabel(
        cbody, text='', anchor='w', text_color=TEAL_BRIGHT,
        font=ctk.CTkFont(size=14, weight='bold'))
    self._es_calc_total.grid(row=2, column=0, sticky='w', pady=(2, 0))
    self._es_calc_gold = ctk.CTkLabel(
        cbody, text='', anchor='w', text_color=TEXT_FAINT,
        font=ctk.CTkFont(size=11), wraplength=440)
    self._es_calc_gold.grid(row=3, column=0, sticky='w', pady=(2, 0))

    # -- Status-Zeile -----------------------------------------------------
    self._es_status = ctk.CTkLabel(
        view, text=t('ui.es_idle'), anchor='w', text_color=TEXT_FAINT,
        font=ctk.CTkFont(size=11), wraplength=440)
    self._es_status.grid(row=3, column=0, sticky='w', pady=(2, 0))

    # Werte aus der Config in die Widgets spiegeln + Rechner befuellen.
    self._es_load_from_config()
    self._es_update_calc()
    self._es_sync_buttons()

  # -- Widget-Fabriken ----------------------------------------------------

  def _es_row(self, parent, row, label, widget):
    """Setzt eine Label/Widget-Zeile und liefert die naechste Zeilennummer."""
    ctk.CTkLabel(parent, text=label, text_color=TEXT_FAINT,
                 font=ctk.CTkFont(size=12)).grid(
        row=row, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
    widget.grid(row=row, column=1, sticky='w', pady=(6, 0))
    return row + 1

  def _es_entry(self, section, key, var, parent, on_change=None,
                is_float=False):
    """Erzeugt ein Zahlen-Eingabefeld, das beim Verlassen ``section.key`` setzt."""
    entry = ctk.CTkEntry(parent, textvariable=var, width=110,
                         justify='center')

    def _commit(_event=None):
      self._es_commit_number(section, key, var, is_float)
      if callable(on_change):
        on_change()

    entry.bind('<FocusOut>', _commit)
    entry.bind('<Return>', _commit)
    self._es_widgets[key] = entry
    return entry

  def _es_optionmenu(self, section, key, var, label_pairs, parent):
    """Erzeugt ein OptionMenu (Enum), das ``section.key`` auf den Wert setzt."""
    v2l = {value: label for value, label in label_pairs}
    l2v = {label: value for value, label in label_pairs}
    self._es_widgets.setdefault('_l2v', {})[key] = l2v
    self._es_widgets.setdefault('_v2l', {})[key] = v2l

    def _change(label):
      value = l2v.get(label, label_pairs[0][0])
      self._es_set(section, key, value)

    menu = ctk.CTkOptionMenu(parent, variable=var, width=140,
                             values=[label for _v, label in label_pairs],
                             command=_change)
    self._es_widgets[key] = menu
    return menu

  # -- Persistenz ---------------------------------------------------------

  def _es_sub(self, section):
    """Liefert eine Kopie des energiesplitter-Sub-Dicts (hammer/dagger/shared)."""
    try:
      cfg = self.controller.current_config()
      return dict(cfg.get('energiesplitter', {}).get(section, {}))
    except Exception:
      return {}

  def _es_set(self, section, key, value):
    """Schreibt EINEN Wert ins energiesplitter-Sub-Dict (immutabel + Auto-Save).

    Nutzt die bestehende ``update_config(section, key, dict)``-API: Wir lesen das
    aktuelle Sub-Dict, setzen den Schluessel und schreiben das ganze Sub-Dict
    unter ``energiesplitter.<section>`` zurueck (validate clampt es)."""
    try:
      sub = self._es_sub(section)
      sub[key] = value
      self._cfg = self.controller.update_config('energiesplitter', section,
                                                sub)
    except Exception:
      pass

  def _es_commit_number(self, section, key, var, is_float):
    """Liest das Eingabefeld, wandelt in int/float, schreibt + spiegelt zurueck."""
    raw = (var.get() or '').strip()
    try:
      value = float(raw) if is_float else int(float(raw))
    except (TypeError, ValueError):
      # Ungueltige Eingabe: aktuellen Config-Wert wieder anzeigen.
      cur = self._es_sub(section).get(key)
      if cur is not None:
        var.set(str(cur))
      return
    self._es_set(section, key, value)
    # Geklemmten Wert zurueckspiegeln (validate kann ihn korrigiert haben).
    clamped = self._es_sub(section).get(key, value)
    var.set(str(clamped))

  def _es_load_from_config(self):
    """Spiegelt die persistierten Config-Werte in die Widget-Variablen."""
    h = self._es_sub('hammer')
    d = self._es_sub('dagger')
    s = self._es_sub('shared')
    try:
      self._es_count_var.set(str(h.get('hammer_count', 200)))
      self._es_freischalten_var.set(bool(h.get('energie_freischalten', True)))
      self._es_price_var.set(str(h.get('price_per_item', 15000)))
      self._es_gold_floor_var.set(str(h.get('gold_floor', 50000)))
      self._es_max_spend_var.set(str(h.get('max_gold_spend', 0)))
      self._es_prefer_stack_var.set(str(h.get('prefer_stack', 'largest_fit')))
      self._es_process_mode_var.set(str(d.get('process_mode', 'one_to_one')))
      self._es_batch_var.set(str(d.get('batch_size', 50)))
      self._es_speed_var.set(str(s.get('speed_profile', 'fast')))
      self._es_mouse_pause_var.set(str(s.get('mouse_pause', 0.05)))
      self._es_kb_pause_var.set(str(s.get('keyboard_pause', 0.10)))
      self._es_max_actions_var.set(str(s.get('max_actions', 0)))
      self._es_unverif_var.set(str(s.get('consecutive_unverified_stop', 3)))
      self._es_jitter_var.set(str(s.get('jitter_pct', 0.15)))
      self._es_birdseye_var.set(bool(s.get('birdseye_on_miss', True)))
      # Scharf-Schalter = Inversion von dry_run (AN = scharf = dry_run False).
      self._es_scharf_var.set(not bool(s.get('dry_run', True)))
    except Exception:
      pass

  # -- Live-Rechner (ruft NUR energiesplitter/calc.py) --------------------

  def _es_update_calc(self):
    """Aktualisiert den Yang-Rechner aus Anzahl + Preis (Logik in calc.py)."""
    try:
      count = int(float((self._es_count_var.get() or '0').strip() or '0'))
    except (TypeError, ValueError):
      count = 0
    try:
      price = int(float((self._es_price_var.get() or '0').strip() or '0'))
    except (TypeError, ValueError):
      price = 15000
    plan = calc.plan_hammer_yang(count, price)
    try:
      self._es_calc_hammer.configure(text=t(
          'ui.es_calc_hammer', n=plan['hammer_count'],
          price=_fmt_yang(plan['price_per_item']),
          sum=_fmt_yang(plan['hammer_yang'])))
      self._es_calc_dagger.configure(text=t(
          'ui.es_calc_dagger', n=plan['hammer_count'],
          price=_fmt_yang(plan['price_per_item']),
          sum=_fmt_yang(plan['dagger_yang'])))
      self._es_calc_total.configure(text=t(
          'ui.es_calc_total', sum=_fmt_yang(plan['total_yang'])))
      gold_floor = int(self._es_sub('hammer').get('gold_floor', 50000))
      ok = self._es_gold_likely_ok(plan['total_yang'], gold_floor)
      self._es_calc_gold.configure(
          text=t('ui.es_calc_gold_ok') if ok else t('ui.es_calc_gold_low'))
    except Exception:
      pass

  def _es_gold_likely_ok(self, total_yang, gold_floor):
    """Heuristik fuer die Rechner-Anzeige (KEIN harter Guard -- der lebt im Bot).

    Liest das Gold NICHT (das macht der Bot live). Diese Anzeige ist rein
    informativ: Sie kann nicht garantieren, dass das Gold reicht -- der Bot
    stoppt zur Laufzeit sicher statt blind zu kaufen."""
    return True

  # -- Start/Stop (run_loop-Integration, KEIN eigener Worker-Thread) ------

  def _on_es_start_stop(self, which):
    """Start/Stop fuer Aktion 1 ('hammer') / Aktion 2 ('dagger').

    Laeuft bereits ein Bot -> Stop (in JEDER Ansicht stoppbar). Sonst: Fenster
    pruefen, Modus setzen, ueber den Controller starten. Der RunLoop (Agent C)
    uebernimmt den Tick + die Exklusivitaet (zweiter Start wird verweigert)."""
    if self.controller.running:
      # Ein Klick auf einen der Start-Knoepfe waehrend des Laufs = Stop-Wunsch.
      self.controller.on_start_stop()
      return

    present, _hwnd, _gw, _gh, _healthy = _probe_game()
    if not present:
      log.event('-', t('ui.start_aborted_no_window'))
      try:
        self._es_status.configure(text=t('ui.status_start_no_window'))
      except Exception:
        pass
      return

    mode = ES_MODE_HAMMER if which == 'hammer' else ES_MODE_DAGGER
    try:
      self._apply_preferred_hwnd()
    except Exception:
      pass
    # Pending-Edits vor dem Start committen (FocusOut feuert nicht garantiert).
    self._es_commit_all()
    self.controller.set_mode(mode)
    self._cfg = self.controller.current_config()
    try:
      self._es_status.configure(
          text=t('ui.es_running_hammer', done=0,
                 soll=self._es_sub('hammer').get('hammer_count', 0))
          if which == 'hammer'
          else t('ui.es_running_dagger', done=0, rest=0))
    except Exception:
      pass
    log.event('0', t('energiesplitter.started', mode=mode))
    self.controller.on_start_stop()
    self._es_sync_buttons()

  def _es_commit_all(self):
    """Committet alle Zahlen-Eingabefelder (vor dem Start, idempotent)."""
    self._es_commit_number('hammer', 'hammer_count', self._es_count_var, False)
    self._es_commit_number('hammer', 'price_per_item', self._es_price_var,
                           False)
    self._es_commit_number('hammer', 'gold_floor', self._es_gold_floor_var,
                           False)
    self._es_commit_number('hammer', 'max_gold_spend', self._es_max_spend_var,
                           False)
    self._es_commit_number('dagger', 'batch_size', self._es_batch_var, False)
    self._es_commit_number('shared', 'mouse_pause', self._es_mouse_pause_var,
                           True)
    self._es_commit_number('shared', 'keyboard_pause', self._es_kb_pause_var,
                           True)
    self._es_commit_number('shared', 'max_actions', self._es_max_actions_var,
                           False)
    self._es_commit_number('shared', 'consecutive_unverified_stop',
                           self._es_unverif_var, False)
    self._es_commit_number('shared', 'jitter_pct', self._es_jitter_var, True)

  def _es_sync_buttons(self):
    """Spiegelt den Laufzustand auf die beiden Start/Stop-Knoepfe.

    Laeuft der ES-Bot: der aktive Knopf wird zum 'Stoppen', der andere wird
    deaktiviert. Laeuft ein ANDERER Bot (fishing/puzzle): beide deaktiviert.
    Idle: beide als Start aktiv. Streng defensiv (Widgets evtl. noch nicht da)."""
    try:
      running = self.controller.running
      mode = self.controller.mode
    except Exception:
      running, mode = False, ''
    hammer_active = running and mode == ES_MODE_HAMMER
    dagger_active = running and mode == ES_MODE_DAGGER
    other_running = running and mode not in (ES_MODE_HAMMER, ES_MODE_DAGGER)

    def _btn(btn, start_text, active):
      if btn is None:
        return
      try:
        if active:
          btn.configure(text=t('ui.es_stop_btn'), fg_color=DANGER,
                        hover_color=DANGER_HOVER, text_color='#fff',
                        state='normal')
        elif running or other_running:
          # Ein anderer Lauf (oder die jeweils andere Aktion) blockiert.
          btn.configure(text=start_text, fg_color=PANEL_LIGHT,
                        hover_color=PANEL_LIGHT, text_color=TEXT_FAINT,
                        state='disabled')
        else:
          btn.configure(text=start_text, fg_color=TEAL,
                        hover_color=TEAL_HOVER, text_color=INK,
                        state='normal')
      except Exception:
        pass

    _btn(getattr(self, '_es_hammer_btn', None),
         t('ui.es_hammer_start_btn'), hammer_active)
    _btn(getattr(self, '_es_dagger_btn', None),
         t('ui.es_dagger_start_btn'), dagger_active)
