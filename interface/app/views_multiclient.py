# -*- coding: utf-8 -*-
"""MulticlientViewMixin -- der Multiclient-Reiter (1-4 Clients, je Client ein
markiertes Spielfenster).

Der Nutzer waehlt 1-4 Clients; je Zeile einen Modus (Fischen/Puzzle/Seher/
Energiesplitter) und markiert das zugehoerige Spielfenster per **Klick aufs
echte Fenster** (``window_mark.ClickCapture`` -> ``WindowFromPoint`` -> Top-Level).
Das loest die Zuordnung eindeutig, auch wenn mehr als 4 Fenster offen sind.

Die reine Logik (Slots, Validierung, Specs) liegt in :mod:`multiclient_settings`,
die Markier-Primitive in :mod:`window_mark` -- beide headless-getestet. Diese
Datei ist die duenne CTk-Schicht (LIVE-only: Darstellung, echte Klick-Erfassung,
realer Worker-Start sind nur am Windows-Spiel verifizierbar). Strikt defensiv:
ein Fehler hier darf die App nie kippen.
"""

import threading

from interface.app._common import *  # noqa: F401,F403

import multiclient_settings as mcfg
import window_mark

# Reihenfolge + i18n-Keys der waehlbaren Modi (deckt sich mit launcher.VALID_MODES).
MC_MODE_KEYS = (('fischen', 'ui.mc_mode_fischen'),
                ('puzzle', 'ui.mc_mode_puzzle'),
                ('seher', 'ui.mc_mode_seher'),
                ('energiesplitter', 'ui.mc_mode_energiesplitter'))

_MARK_POLL_MS = 30  # Poll-Takt der Klick-Erfassung


class MulticlientViewMixin:
    def _build_multiclient_view(self, _parent):
        """Baut den Multiclient-Reiter (Anzahl + Client-Zeilen + Start/Stop)."""
        view = self._new_view('multiclient')
        self._view_header(view, t('ui.view_multiclient'), t('ui.mc_sub'))

        # Laufzeitzustand (nur diese View).
        self._mc_slots = [mcfg.ClientSlot()]
        self._mc_count = 1
        self._mc_running = False
        self._mc_capture = None       # aktive ClickCapture-Instanz
        self._mc_capture_idx = None   # welcher Slot wird gerade markiert

        card = Section(view, t('ui.group_multiclient'))
        card.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        body = card.body
        body.grid_columnconfigure(0, weight=1)

        # Anzahl-Auswahl 1-4.
        countrow = ctk.CTkFrame(body, fg_color='transparent')
        countrow.grid(row=0, column=0, sticky='w', pady=(0, 6))
        ctk.CTkLabel(countrow, text=t('ui.mc_count_label'), text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=(0, 8))
        self._mc_count_seg = Segmented(
            countrow, values=['1', '2', '3', '4'], default='1',
            command=self._mc_on_count)
        self._mc_count_seg.grid(row=0, column=1, sticky='w')

        # Container fuer die Client-Zeilen (wird bei Anzahl-Wechsel neu gebaut).
        self._mc_rows = ctk.CTkFrame(body, fg_color='transparent')
        self._mc_rows.grid(row=1, column=0, sticky='ew', pady=(2, 0))
        self._mc_rows.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(body, text=t('ui.mc_hint'), text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=11), wraplength=460,
                     justify='left').grid(row=2, column=0, sticky='w', pady=(8, 0))

        # Start/Stop-Leiste.
        btnrow = ctk.CTkFrame(body, fg_color='transparent')
        btnrow.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        btnrow.grid_columnconfigure(0, weight=1)
        self._mc_start_btn = ctk.CTkButton(
            btnrow, text=t('ui.mc_start_all'), height=40, corner_radius=12,
            font=ctk.CTkFont(size=14, weight='bold'),
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            command=self._mc_start_all)
        self._mc_start_btn.grid(row=0, column=0, sticky='ew')

        self._mc_status = ctk.CTkLabel(
            body, text='', anchor='w', text_color=TEXT_FAINT,
            font=ctk.CTkFont(size=11), wraplength=460, justify='left')
        self._mc_status.grid(row=4, column=0, sticky='w', pady=(6, 0))

        self._mc_load_from_config()

    # -- Config <-> View ---------------------------------------------------

    def _mc_load_from_config(self):
        """Slots + Anzahl aus der Config spiegeln und Zeilen aufbauen."""
        try:
            cfg = self.controller.current_config()
        except Exception:
            cfg = {}
        self._mc_slots = mcfg.slots_from_config(cfg)
        self._mc_count = mcfg.count_from_config(cfg)
        # Slot-Liste auf die Anzahl bringen (auffuellen/kuerzen).
        self._mc_slots = mcfg.set_count(self._mc_slots, self._mc_count)
        try:
            self._mc_count_seg.set(str(self._mc_count))
        except Exception:
            pass
        self._mc_rebuild_rows()

    def _mc_persist(self):
        """Aktuelle Slots/Anzahl in config['multiclient'] schreiben (Auto-Save)."""
        try:
            data = mcfg.config_from_slots(self._mc_slots, self._mc_count)
            self.controller.update_config('multiclient', 'count', data['count'])
            self.controller.update_config('multiclient', 'clients', data['clients'])
        except Exception:
            pass

    def _mc_on_count(self, value):
        """Anzahl-Segment geklickt: Slots anpassen, persistieren, neu bauen."""
        self._mc_count = mcfg.clamp_count(value)
        self._mc_slots = mcfg.set_count(self._mc_slots, self._mc_count)
        self._mc_persist()
        self._mc_rebuild_rows()

    # -- Client-Zeilen -----------------------------------------------------

    def _mc_rebuild_rows(self):
        """Baut die Zeilen fuer die aktiven Slots neu auf (defensiv)."""
        try:
            for child in list(self._mc_rows.winfo_children()):
                child.destroy()
        except Exception:
            pass
        self._mc_mark_btns = {}
        self._mc_status_lbls = {}
        for i in range(self._mc_count):
            slot = self._mc_slots[i] if i < len(self._mc_slots) else mcfg.ClientSlot()
            self._mc_build_row(i, slot)

    def _mc_build_row(self, i, slot):
        row = ctk.CTkFrame(self._mc_rows, fg_color=PANEL_LIGHT, corner_radius=10)
        row.grid(row=i, column=0, sticky='ew', pady=3)
        row.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(row, text=t('ui.mc_client_label', n=i + 1), text_color=TEXT,
                     font=ctk.CTkFont(size=12, weight='bold'), width=72).grid(
            row=0, column=0, padx=(10, 6), pady=8, sticky='w')

        # Modus-Dropdown.
        labels = [t(k) for _v, k in MC_MODE_KEYS]
        cur_label = t(dict(MC_MODE_KEYS).get(slot.mode, MC_MODE_KEYS[0][1]))
        var = ctk.StringVar(value=cur_label)
        ctk.CTkOptionMenu(
            row, variable=var, values=labels, width=150,
            command=lambda lbl, idx=i: self._mc_on_mode(idx, lbl)).grid(
            row=0, column=1, padx=(0, 8), sticky='w')

        # "Fenster markieren".
        mark = ctk.CTkButton(
            row, text=t('ui.mc_mark_btn'), width=140, height=30, corner_radius=8,
            fg_color=PANEL_HOVER, hover_color=TEAL_SOFT, text_color=TEXT,
            command=lambda idx=i: self._mc_begin_mark(idx))
        mark.grid(row=0, column=2, padx=(0, 6), sticky='w')
        self._mc_mark_btns[i] = mark

        # "Blinken" (Bestaetigung sichtbar machen).
        ctk.CTkButton(
            row, text=t('ui.mc_flash_btn'), width=64, height=30, corner_radius=8,
            fg_color='transparent', hover_color=PANEL_HOVER, text_color=TEXT_FAINT,
            command=lambda idx=i: self._mc_flash(idx)).grid(
            row=0, column=3, padx=(0, 8), sticky='w')

        # Status.
        lbl = ctk.CTkLabel(row, text='', anchor='w', text_color=TEXT_FAINT,
                           font=ctk.CTkFont(size=11))
        lbl.grid(row=0, column=4, padx=(0, 10), sticky='w')
        self._mc_status_lbls[i] = lbl
        self._mc_refresh_row(i)

    def _mc_refresh_row(self, i):
        """Status-Label eines Slots auffrischen (markiert/unmarkiert)."""
        try:
            slot = self._mc_slots[i]
            lbl = self._mc_status_lbls.get(i)
            if lbl is None:
                return
            if slot.hwnd is None:
                lbl.configure(text=t('ui.mc_status_unmarked'), text_color=TEXT_FAINT)
            else:
                lbl.configure(text=t('ui.mc_status_marked', hwnd=slot.hwnd),
                              text_color=TEAL_BRIGHT)
        except Exception:
            pass

    def _mc_on_mode(self, i, label):
        mode = next((v for v, k in MC_MODE_KEYS if t(k) == label), mcfg.DEFAULT_MODE)
        self._mc_slots = mcfg.set_mode(self._mc_slots, i, mode)
        self._mc_persist()

    # -- Markieren (Klick-zum-Erfassen) ------------------------------------

    def _mc_game_hwnds(self):
        """Aktuelle METIN2-Fenster-HWNDs als Set (fuer die Erfassungs-Validierung)."""
        try:
            import constants
            import windowcapture
            return {w['hwnd'] for w in
                    windowcapture.enumerate_game_windows(constants.GAME_NAME)}
        except Exception:
            return set()

    def _mc_begin_mark(self, i):
        """Klick-Erfassung fuer Slot ``i`` scharf schalten + Poll-Schleife starten.

        Erneuter Klick auf denselben Knopf (oder Esc) bricht eine laufende
        Erfassung ab."""
        if self._mc_capture is not None:
            # Re-Klick = Abbruch (egal welcher Slot); sonst ignorieren.
            self._mc_finish_mark(None)
            return
        if not self._mc_game_hwnds():
            self._mc_set_status(t('ui.mc_no_windows'))
            return
        self._mc_capture_idx = i
        self._mc_capture = window_mark.ClickCapture(
            resolve_fn=lambda pos: window_mark.window_from_point(pos),
            valid_hwnds_fn=self._mc_game_hwnds)
        self._mc_capture.arm()
        btn = self._mc_mark_btns.get(i)
        if btn is not None:
            try:
                btn.configure(text=t('ui.mc_mark_active'), state='normal')
            except Exception:
                pass
        # Esc bricht die Erfassung ab (wie im Hinweistext versprochen).
        try:
            self._mc_esc_bind = self.bind('<Escape>',
                                          lambda _e: self._mc_finish_mark(None),
                                          add='+')
        except Exception:
            self._mc_esc_bind = None
        self._mc_set_status(t('ui.mc_mark_active'))
        self._mc_poll_mark()

    def _mc_poll_mark(self):
        """Ein Poll-Schritt der aktiven Klick-Erfassung (LIVE-only Eingaben)."""
        cap = self._mc_capture
        if cap is None:
            return
        try:
            state = cap.step(window_mark.left_button_down(),
                             window_mark.cursor_pos())
        except Exception:
            state = cap.CANCELLED
        if state == cap.CAPTURED:
            self._mc_finish_mark(cap.captured_hwnd)
        elif state == cap.CANCELLED:
            self._mc_finish_mark(None)
        else:
            try:
                self.after(_MARK_POLL_MS, self._mc_poll_mark)
            except Exception:
                self._mc_finish_mark(None)

    def _mc_finish_mark(self, hwnd):
        """Erfassung abschliessen: HWND zuweisen (oder abbrechen), UI zuruecksetzen."""
        if self._mc_capture is None:
            return  # bereits abgeschlossen (Esc + Klick koennten doppelt feuern)
        i = self._mc_capture_idx
        self._mc_capture = None
        self._mc_capture_idx = None
        try:
            if getattr(self, '_mc_esc_bind', None):
                self.unbind('<Escape>', self._mc_esc_bind)
            self._mc_esc_bind = None
        except Exception:
            pass
        btn = self._mc_mark_btns.get(i) if i is not None else None
        if btn is not None:
            try:
                btn.configure(text=t('ui.mc_mark_btn'), state='normal')
            except Exception:
                pass
        if hwnd is not None and i is not None:
            self._mc_slots = mcfg.assign_hwnd(self._mc_slots, i, hwnd)
            self._mc_persist()
            window_mark.flash_window(hwnd)
            try:
                log.event('-', t('ui.mc_marked_log', n=i + 1, hwnd=hwnd))
            except Exception:
                pass
            # Auch andere Zeilen auffrischen (Duplikat koennte geloescht worden sein).
            for j in range(self._mc_count):
                self._mc_refresh_row(j)
            self._mc_set_status('')
        else:
            self._mc_set_status('')

    def _mc_flash(self, i):
        try:
            slot = self._mc_slots[i]
            if slot.hwnd is not None:
                window_mark.flash_window(slot.hwnd)
        except Exception:
            pass

    # -- Start / Stop ------------------------------------------------------

    def _mc_set_status(self, text):
        try:
            self._mc_status.configure(text=text)
        except Exception:
            pass

    def _mc_start_all(self):
        """Validieren, Specs ableiten und die Worker starten (LIVE-only Spawn)."""
        if self._mc_running:
            self._mc_stop_all()
            return
        if not mcfg.is_ready(self._mc_slots, self._mc_count):
            self._mc_set_status(t('ui.mc_not_ready'))
            return
        specs = mcfg.specs_from_slots(self._mc_slots, self._mc_count)
        if not specs:
            self._mc_set_status(t('ui.mc_not_ready'))
            return
        self._mc_running = True
        try:
            self._mc_start_btn.configure(text=t('ui.mc_stop_all'),
                                         fg_color=DANGER, hover_color=DANGER_HOVER)
        except Exception:
            pass
        self._mc_set_status(t('ui.mc_running', n=len(specs)))
        self._mc_thread = threading.Thread(
            target=self._mc_run_specs, args=(specs,), daemon=True)
        self._mc_thread.start()

    def _mc_run_specs(self, specs):
        """Hintergrund-Thread: laeuft bis Stop. Reiner Launcher-Aufruf (Defaults)."""
        try:
            import launcher
            launcher.run(specs, should_run=lambda: self._mc_running)
        except Exception as exc:  # pragma: no cover - LIVE-only
            try:
                log.event('-', 'Multiclient-Start fehlgeschlagen: {}'.format(exc))
            except Exception:
                pass
        finally:
            self._mc_running = False
            try:
                self.after(0, self._mc_on_run_ended)
            except Exception:
                pass

    def _mc_on_run_ended(self):
        try:
            self._mc_start_btn.configure(text=t('ui.mc_start_all'),
                                         fg_color=TEAL, hover_color=TEAL_HOVER)
        except Exception:
            pass
        self._mc_set_status(t('ui.mc_stopped'))

    def _mc_stop_all(self):
        """Signalisiert dem Launcher-Thread das Ende (should_run -> False)."""
        self._mc_running = False
        self._mc_set_status(t('ui.mc_stopped'))
