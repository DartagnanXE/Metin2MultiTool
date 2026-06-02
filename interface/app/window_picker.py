# -*- coding: utf-8 -*-
"""WindowPickerMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403


class WindowPickerMixin:
    def _refresh_window_picker(self):
        """Aktualisiert die Liste sichtbarer METIN2-Fenster + die Picker-UI.

        <=1 Fenster: ``_chosen_hwnd`` loeschen, Picker-Knopf verstecken ->
        byte-identisch zu frueher (Single-Window). >1: Knopf zeigen. Die UI wird
        NUR bei geaenderter HWND-Signatur angefasst (kein Sekunden-Flackern)."""
        try:
            import constants
            import windowcapture
            windows = windowcapture.enumerate_game_windows(constants.GAME_NAME)
        except Exception:
            windows = []
        self._game_windows = windows
        sig = tuple(w['hwnd'] for w in windows)
        if sig == self._window_sig:
            return
        self._window_sig = sig
        # Gewaehltes Ziel verwerfen, wenn es nicht mehr existiert.
        if self._chosen_hwnd not in sig:
            self._chosen_hwnd = None
        multi = len(windows) > 1
        try:
            btn = getattr(self, 'pick_btn', None)
            if btn is not None:
                if multi:
                    btn.grid()
                else:
                    btn.grid_remove()
        except Exception:
            pass
        # CS4: der MODUS-Umschalter ('Zuletzt fokussiert' <-> 'Bestimmtes Fenster')
        # erscheint nur, wenn ueberhaupt eine Wahl besteht (>1 Fenster); sonst
        # versteckt (Single-Window = byte-identisch zu frueher). Gleiche
        # Signatur-Gating wie der Picker-Knopf (kein Flackern).
        try:
            mbtn = getattr(self, 'mode_btn', None)
            if mbtn is not None:
                if multi:
                    self._refresh_window_mode_label()
                    mbtn.grid()
                else:
                    mbtn.grid_remove()
        except Exception:
            pass

    def _open_window_picker(self):
        """Kleiner Auswahldialog (eigenes CTkToplevel) der gefundenen METIN2-
        Fenster -- je Fenster eine Zeile mit Groesse/Position. Auswahl setzt das
        Ziel-HWND (Item N). Strikt defensiv."""
        windows = list(self._game_windows)
        if len(windows) <= 1:
            return
        try:
            dlg = ctk.CTkToplevel(self)
            dlg.title(t('ui.pick_window_title'))
            dlg.configure(fg_color=BG)
            dlg.resizable(False, False)
            dlg.geometry('360x{}'.format(70 + 40 * len(windows)))
            try:
                dlg.transient(self)
            except Exception:
                pass
            dlg.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(dlg, text=t('ui.pick_window_title'), text_color=TEXT,
                         font=ctk.CTkFont(size=14, weight='bold')).grid(
                row=0, column=0, sticky='w', padx=16, pady=(14, 6))

            def _close():
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                try:
                    dlg.destroy()
                except Exception:
                    pass

            for i, win in enumerate(windows):
                n = i + 1
                row_text = t('ui.pick_window_row', n=n, w=win['w'], h=win['h'],
                             x=win['x'], y=win['y'])

                def _pick(w=win, num=n, dialog_close=_close):
                    dialog_close()
                    self._on_pick_window(w['hwnd'], num, w['w'], w['h'])

                ctk.CTkButton(
                    dlg, text=row_text, height=30, corner_radius=8,
                    fg_color=PANEL_LIGHT, hover_color=PANEL_HOVER,
                    text_color=TEXT, font=ctk.CTkFont(size=12),
                    command=_pick).grid(row=1 + i, column=0, sticky='ew',
                                        padx=16, pady=3)

            dlg.protocol('WM_DELETE_WINDOW', _close)
            try:
                dlg.after(60, dlg.grab_set)
                dlg.lift()
            except Exception:
                pass
        except Exception:
            pass

    def _on_pick_window(self, hwnd, n, w, h):
        """Speichert das gewaehlte Ziel-HWND (runtime-only) + loggt die Wahl.

        Eine explizite Wahl impliziert den Modus 'specific' (CS4): der Bot soll
        ab jetzt genau dieses Fenster bespielen, bis der Nutzer im Footer-Umschalter
        wieder auf 'Zuletzt fokussiert' zurueckschaltet."""
        self._chosen_hwnd = hwnd
        self._window_mode = 'specific'
        self._refresh_window_mode_label()
        log.event('-', t('ui.window_chosen', n=n, w=w, h=h))

    def _apply_preferred_hwnd(self):
        """Reicht das (modus-abhaengige) Ziel-HWND an WindowCapture durch.

        Honoriert den Fenster-MODUS (CS4) ueber die reine
        :func:`windowcapture.select_target_hwnd`-Logik:

          * 'last_focused' -> ``None`` -> ``set_preferred_hwnd(None)`` ->
            FindWindow-Pfad (byte-identisch zu frueher / zuletzt fokussiert).
          * 'specific'     -> das gewaehlte ``_chosen_hwnd``, NUR wenn es noch in
            der aktuellen Fensterliste (gueltig/sichtbar) ist; sonst sicherer
            Rueckfall auf ``None``.

        Strikt defensiv -- ein Fehler hier darf Start/Scan nie kippen."""
        try:
            import windowcapture
            mode = getattr(self, '_window_mode', 'last_focused')
            target = windowcapture.select_target_hwnd(
                getattr(self, '_game_windows', []), mode, self._chosen_hwnd)
            windowcapture.set_preferred_hwnd(target)
        except Exception:
            pass

    def _window_mode_label_text(self):
        """Aktueller MODUS-Text fuer den Footer-Umschalter (sprachabhaengig)."""
        if getattr(self, '_window_mode', 'last_focused') == 'specific':
            return t('ui.window_mode_specific')
        return t('ui.window_mode_last_focused')

    def _refresh_window_mode_label(self):
        """Frischt den Text des Footer-Modus-Umschalters auf (defensiv)."""
        try:
            mbtn = getattr(self, 'mode_btn', None)
            if mbtn is not None:
                mbtn.configure(text=self._window_mode_label_text())
        except Exception:
            pass

    def _on_toggle_window_mode(self):
        """Klick auf den Footer-Umschalter: kippt den Fenster-MODUS (CS4).

        'last_focused' <-> 'specific'. Frischt das Label auf, loggt die Aenderung
        und (falls gerade ein Lauf aktiv ist) wendet das bevorzugte HWND sofort
        neu an, damit der Wechsel mitten im Lauf greift. Strikt defensiv."""
        cur = getattr(self, '_window_mode', 'last_focused')
        self._window_mode = ('last_focused' if cur == 'specific' else 'specific')
        self._refresh_window_mode_label()
        try:
            log.event('-', t('ui.window_mode_changed',
                             mode=self._window_mode_label_text()))
        except Exception:
            pass
        try:
            if self.controller.running:
                self._apply_preferred_hwnd()
        except Exception:
            pass

    def _clear_preferred_hwnd(self):
        """Loescht die WindowCapture-Praeferenz (beim Stop). Strikt defensiv."""
        try:
            import windowcapture
            windowcapture.clear_preferred_hwnd()
        except Exception:
            pass

    # -- Auto-Update (dezentes, schliessbares Banner) --------------------
