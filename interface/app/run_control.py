# -*- coding: utf-8 -*-
"""RunControlMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403


class RunControlMixin:
    def _on_start_stop(self):
        self.controller.on_start_stop()

    def _on_stop_minutes(self, _event=None):
        raw = self.stop_after_entry.get().strip()
        try:
            minutes = int(raw) if raw else 0
        except ValueError:
            minutes = 0
        self._cfg = self.controller.update_config(
            'fishing', 'stop_after_minutes', minutes)

    def _on_timer_action_change(self, label):
        """Zeitlimit-Wahl (EIN Dreifach-Segment): Aus | Stoppen | Cleanup.

        Schreibt BEIDE Config-Felder konsistent: 'off' -> Timer aus
        (stop_after_enabled=False, timer_action unangetastet); 'stop'/'cleanup'
        -> Timer an + die Aktion. So kann der alte Fallzustand "Aktion gewaehlt,
        aber Timer aus" gar nicht mehr entstehen."""
        value = getattr(self, '_timer_action_l2v', {}).get(label, 'off')
        if value == 'off':
            self._cfg = self.controller.update_config(
                'fishing', 'stop_after_enabled', False)
        else:
            self.controller.update_config(
                'fishing', 'stop_after_enabled', True)
            self._cfg = self.controller.update_config(
                'fishing', 'timer_action', value)

    def _on_golden_tuna_change(self, label):
        try:
            action = int(label)
        except (TypeError, ValueError):
            action = 3
        self._cfg = self.controller.update_config(
            'fishing', 'golden_tuna_action', action)

    def _on_color_change(self, label):
        self._cfg = self.controller.update_config(
            'puzzle', 'color_mode', label.lower())

    def _on_solver_change(self, label):
        value = self._solver_l2v.get(label, cfgmod.SOLVER_MODES[0])
        self._cfg = self.controller.update_config('puzzle', 'solver_mode', value)

    def _on_force_deluxe_toggle(self):
        """Schreibt den Force-Deluxe-Schalter (V3-Reservat) in die Config.

        Reines bool. Nur wirksam bei 'KI optimiert' + vorhandener Deluxe-Box
        (der PuzzleBot prueft das zur Laufzeit selbst); der Schalter persistiert
        die Wahl unabhaengig davon."""
        self._cfg = self.controller.update_config(
            'puzzle', 'force_deluxe', bool(self._force_deluxe_var.get()))

    def sync_controls(self):
        """Spiegelt den Laufzustand ins UI (Hero, Rail-Punkte, Sperren).

        Waehrend des Laufs: Fishing-/Puzzle-Einstellungen gesperrt, Hero rot
        ('Stop - <Modus>'), Lauf-Punkt auf dem aktiven Modus + Console. Settings
        (App-Praeferenzen) bleiben IMMER aktiv. Wird von set_running,
        _rebuild_ui, __init__ und jedem Tick (sync_button) gerufen.
        """
        running = self.controller.running
        mode = self.controller.mode

        # Lauf-Start fuer den Timer stempeln (false->true-Flanke).
        if running and not self._was_running:
            self._run_started_at = time.time()
        self._was_running = running

        # Hero-Text/Farbe.
        if running:
            key = ('ui.hero_stop_puzzle' if mode == 'puzzle'
                   else 'ui.hero_stop_fishing')
            try:
                sk = str(self.controller.current_config()
                         .get('controls', {}).get('stop_hotkey', 'f6')).upper()
            except Exception:
                sk = 'F6'
            # STOP ist in JEDER Ansicht bedienbar (laufender Bot muss immer
            # anhaltbar sein).
            self.hero_btn.configure(
                text='■  ' + t(key) + '   [' + sk + ']', fg_color=DANGER,
                hover_color=DANGER_HOVER, text_color='#fff', state='normal')
        else:
            # START nur in Fishing/Puzzle: dort ist eindeutig, WAS gestartet
            # wird (der Ansichtswechsel setzt den XOR-Modus). In Inventar/
            # Rangliste/Roadmap/Console/Einstellungen ist der Knopf ausgegraut
            # -- das Programm wuesste sonst nicht, welcher Modus gemeint ist.
            startable = getattr(self, '_active_view',
                                'fishing') in ('fishing', 'puzzle')
            if startable:
                self.hero_btn.configure(text='▶  ' + t('ui.hero_start'),
                                        fg_color=TEAL, hover_color=TEAL_HOVER,
                                        text_color=INK, state='normal')
            else:
                self.hero_btn.configure(text='▶  ' + t('ui.hero_start'),
                                        fg_color=PANEL_LIGHT,
                                        hover_color=PANEL_LIGHT,
                                        text_color=TEXT_FAINT,
                                        state='disabled')

        # Rail-Lauf-Punkte.
        self._update_running_dots(running, mode)

        # Fishing-/Puzzle-Steuerungen waehrend des Laufs sperren.
        for slider in (self.bait_slider, self.throw_slider, self.start_slider):
            slider.set_enabled(not running)
        for seg in (self.golden_tuna_seg, self.detection_seg,
                    self.color_seg, self.solver_seg, self.timer_action_seg):
            seg.set_enabled(not running)
        state = 'normal' if not running else 'disabled'
        self.stop_after_entry.configure(state=state)
        # Force-Deluxe-Schalter waehrend des Laufs sperren (wie die Segmente).
        try:
            self.force_deluxe_switch.configure(state=state)
        except Exception:
            pass
        # Reset-Knopf (Settings, Item K) nur im Leerlauf -- belt-and-suspenders
        # zum Idle-Guard in _on_reset_settings.
        try:
            self.reset_btn.configure(state=state)
        except Exception:
            pass
        # Inventar-Scan-Knopf nur im Leerlauf -- belt-and-suspenders zum
        # Idle-Guard in _on_scan_inventory (ein Scan kaempfte sonst mit dem
        # Angel-Loop um den Cursor -> Fehlklicks). Waehrend eines laufenden Scans
        # bleibt er ohnehin via _inv_scanning gesperrt; das hier respektiert das,
        # indem es im Leerlauf nur reaktiviert, wenn KEIN Scan laeuft.
        try:
            if running:
                self._inv_scan_btn.configure(state='disabled')
            elif not self._inv_scanning:
                self._inv_scan_btn.configure(state='normal')
        except Exception:
            pass
        # Settings-Schalter bleiben aktiv (kein Konflikt mit dem Lauf).

        # Energiesplitter-Knoepfe an den ECHTEN Laufzustand koppeln. KRITISCH:
        # ohne diesen Aufruf blieb der Knopf nach einem Selbst-Stopp des Bots
        # (GATE rot / Fehler / fertig) rot auf "Stoppen" stehen, obwohl
        # controller.running bereits False ist -> ein Klick darauf landete im
        # START-Zweig und startete NEU (Nutzer-Report: "laeuft dauerhaft, kann
        # man nicht stoppen"). sync_controls laeuft bei jeder Zustandsaenderung
        # und in jedem Tick (sync_button) -> der Knopf spiegelt jetzt immer den
        # wahren Zustand. Defensiv: vor dem Bau der View existiert die Methode/
        # die Knoepfe evtl. noch nicht -> getattr/try, nie den Sync kippen.
        try:
            sync = getattr(self, '_es_sync_buttons', None)
            if callable(sync):
                sync()
        except Exception:
            pass

    def sync_button(self):
        self.sync_controls()

    # -- Live-Lauf-Timer --------------------------------------------------

    def _tick_timer(self):
        """Aktualisiert die Timer-Anzeige 1x/Sekunde (immer aktiv, guenstig).

        Laeuft der Bot: Countdown der Restzeit (bei Zeitlimit) bzw. Hochzaehlen
        der Laufzeit. Im Leerlauf: Vorschau (Limit-Wert oder 00:00:00). Die
        Anzeige liest DIESELBE Config wie der Bot -- der echte Stop kommt aus
        hack._tick; diese Anzeige ist rein darstellend."""
        try:
            running = self.controller.running
            fishing = self._cfg['fishing']
            limit_on = (fishing['stop_after_enabled']
                        and fishing['stop_after_minutes'] > 0)
            # Inventar-Cleanup aktiv (Zeitlimit-Aktion 'cleanup', Bot gestoppt):
            # der Top-Timer zeigt den NEUSTART-Countdown, damit klar ist, was
            # gerade passiert. Laufen Grillen/Wegwerfen ueber 00:00 hinaus,
            # bleibt die Anzeige bei 00:00 stehen (Neustart folgt direkt danach;
            # der Tooltip erklaert das).
            if getattr(self, '_inv_cleanup_active', False) and not running:
                left = max(0, getattr(self, '_inv_cleanup_restart_at', 0)
                           - time.time())
                self.timer_val.configure(text=_mmss(left))
                self.timer_lbl.configure(text=t('ui.timer_cleanup'))
                self._timer_tip(t('ui.timer_tip_cleanup'))
            elif running:
                elapsed = time.time() - self._run_started_at
                if limit_on:
                    left = max(0, fishing['stop_after_minutes'] * 60 - elapsed)
                    self.timer_val.configure(text=_mmss(left))
                    self.timer_lbl.configure(text=t('ui.timer_left'))
                    self._timer_tip(t('ui.timer_tip_running',
                                      elapsed=_hms(elapsed), left=_mmss(left)))
                else:
                    self.timer_val.configure(text=_hms(elapsed))
                    self.timer_lbl.configure(text=t('ui.timer_elapsed'))
                    self._timer_tip(t('ui.timer_tip_countup',
                                      elapsed=_hms(elapsed)))
            else:
                if limit_on:
                    self.timer_val.configure(
                        text=_mmss(fishing['stop_after_minutes'] * 60))
                    self.timer_lbl.configure(text=t('ui.timer_limit'))
                    self._timer_tip(t('ui.timer_tip_limit',
                                      min=fishing['stop_after_minutes']))
                else:
                    self.timer_val.configure(text='00:00:00')
                    self.timer_lbl.configure(text=t('ui.timer_idle'))
                    self._timer_tip(t('ui.timer_tip_idle'))
        except Exception:
            pass
        try:
            self.after(1000, self._tick_timer)
        except Exception:
            pass

    def _timer_tip(self, text):
        """Setzt den Hover-Text des Timer-Tooltips (ohne Neuaufbau)."""
        try:
            if self._timer_tooltip is not None:
                self._timer_tooltip._text = text
        except Exception:
            pass

    # -- Onboarding + Telemetrie (Run 1) ---------------------------------
