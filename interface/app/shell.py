# -*- coding: utf-8 -*-
"""ShellMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403


class ShellMixin:
    def _rebuild_ui(self):
        """Baut die Shell in der aktuellen Sprache neu (Sprachwechsel).

        Der Laufzustand bleibt erhalten (steckt im BotController, nicht in den
        Widgets); die Log-Senke wird sauber ab- und wieder angehaengt. Footer
        (row 2) und Update-Banner (row 1) liegen auf eigenen Zeilen und werden
        NICHT zerstoert -- nur ihre Texte/Farben werden aufgefrischt (inkl. des
        nun im Footer wohnenden EN|DE-Umschalters via ``_refresh_lang_toggle``).
        """
        try:
            self.log_panel.detach()
        except Exception:
            pass
        widget = getattr(self, 'content', None)
        if widget is not None:
            try:
                widget.destroy()
            except Exception:
                pass
        self._build_content()
        self._show_view(self._active_view)
        self._apply_config_to_widgets()
        self._apply_window_prefs()
        self.sync_controls()
        if self._cfg['log']['show_in_ui']:
            self.log_panel.attach()
        # Footer ueberlebt den Neuaufbau -> den EN|DE-Umschalter neu einfaerben,
        # damit die aktive Sprache (teal) nach dem Wechsel stimmt.
        try:
            self._refresh_lang_toggle()
        except Exception:
            pass
        # CS4: der Footer-Modus-Umschalter ueberlebt den Neuaufbau ebenfalls ->
        # seinen (sprachabhaengigen) Text neu setzen, damit ein Sprachwechsel ihn
        # sofort uebersetzt (sonst erst beim naechsten 1s-Poll via Picker-Refresh).
        try:
            self._refresh_window_mode_label()
        except Exception:
            pass
        # Update-Banner liegt auf einer eigenen Grid-Zeile -> NICHT zerstoert;
        # nur seine Texte neu setzen.
        if (getattr(self, '_update_info', None) is not None
                and getattr(self, '_update_banner', None) is not None):
            try:
                self._refresh_update_banner_text()
                self._update_btn.configure(text=t('ui.update_now'))
            except Exception:
                pass
        try:
            self.update_idletasks()
        except Exception:
            pass

    # -- Shell: Rail + Body ----------------------------------------------

    def _build_content(self):
        """Shell (row 0): Icon-Rail (col 0) + Body (col 1).

        ``self.content`` bleibt der Name (``_rebuild_ui`` zerstoert ihn).
        """
        self.content = ctk.CTkFrame(self, fg_color='transparent')
        self.content.grid(row=0, column=0, sticky='nsew')
        self.content.grid_columnconfigure(1, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._build_rail(self.content)
        self._build_body(self.content)

    def _build_rail(self, parent):
        """Schmale Icon-Rail: Fishing/Puzzle/Ranking/Roadmap/Console oben, dann
        ein SICHTBARER Trenner, danach Inventory (separat, weil temporaer bis
        kalibriert), und unten angepinnt Settings."""
        rail = ctk.CTkFrame(parent, width=60, corner_radius=0, fg_color=RAIL_BG)
        rail.grid(row=0, column=0, sticky='ns')
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        # Top-Gruppe Fishing/Puzzle/Inventory/Ranking/Roadmap/Console (rows 0-5);
        # Inventory sitzt direkt unter Puzzle (regulaere Sektion). Die Spacer-Zeile
        # (row 7) waechst und drueckt das unten angepinnte Settings (row 8) nach
        # unten.
        rail.grid_rowconfigure(7, weight=1)

        self._rail_items = {}
        self._rail_dots = {}
        rows = {'fishing': 0, 'puzzle': 1, 'inventory': 2, 'seher': 3,
                'ranking': 4, 'roadmap': 5, 'console': 6,
                'settings': 8}
        tip_keys = {'fishing': 'ui.view_fishing', 'puzzle': 'ui.view_puzzle',
                    'console': 'ui.view_console',
                    'inventory': 'ui.view_inventory',
                    'seher': 'ui.view_seher',
                    'ranking': 'ui.view_ranking',
                    'roadmap': 'ui.view_roadmap',
                    'settings': 'ui.view_settings'}

        for view in RAIL_ORDER:
            btn = ctk.CTkButton(
                rail, text=RAIL_GLYPHS[view], width=42, height=42,
                corner_radius=12, font=ctk.CTkFont(size=18),
                fg_color='transparent', text_color=TEXT_FAINT,
                hover_color=RAIL_HOVER,
                command=lambda v=view: self._show_view(v))
            pad_top = 12 if rows[view] == 0 else 3
            pad_bottom = 10 if view == 'settings' else 3
            btn.grid(row=rows[view], column=0, pady=(pad_top, pad_bottom))
            self._rail_items[view] = btn
            try:
                Tooltip(btn, text=t(tip_keys[view]))
            except Exception:
                pass
            # Kleiner Lauf-Punkt, oben rechts auf dem Button (anfangs versteckt).
            dot = ctk.CTkLabel(btn, text='●', text_color=TEAL_BRIGHT,
                               fg_color='transparent',
                               font=ctk.CTkFont(size=9))
            self._rail_dots[view] = dot

    def _set_rail_active(self, view):
        """Hebt das aktive Rail-Item hervor (teal-Fill), die anderen neutral."""
        for name, btn in self._rail_items.items():
            try:
                if name == view:
                    btn.configure(fg_color=TEAL_SOFT, text_color=TEAL_BRIGHT)
                else:
                    btn.configure(fg_color='transparent',
                                  text_color=TEXT_FAINT)
            except Exception:
                pass

    def _update_running_dots(self, running, mode):
        """Zeigt den Lauf-Punkt auf dem aktiven Modus + Console, sonst versteckt."""
        show = {mode, 'console'} if running else set()
        for name, dot in self._rail_dots.items():
            try:
                if name in show:
                    dot.place(relx=0.72, y=4)
                else:
                    dot.place_forget()
            except Exception:
                pass

    def _build_body(self, parent):
        """Body (col 1): Command-Strip oben, getauschte Ansicht darunter."""
        body = ctk.CTkFrame(parent, fg_color='transparent')
        body.grid(row=0, column=1, sticky='nsew')
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self._build_command_strip(body)

        self.panel_wrap = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=0)
        self.panel_wrap.grid(row=1, column=0, sticky='nsew')
        self.panel_wrap.grid_columnconfigure(0, weight=1)
        self.panel_wrap.grid_rowconfigure(0, weight=1)

        self._views = {}
        self._build_fishing_view(self.panel_wrap)
        self._build_puzzle_view(self.panel_wrap)
        self._build_console_view(self.panel_wrap)
        self._build_inventory_view(self.panel_wrap)
        self._build_seher_view(self.panel_wrap)
        self._build_energiesplitter_view(self.panel_wrap)
        self._build_ranking_view(self.panel_wrap)
        self._build_roadmap_view(self.panel_wrap)
        self._build_settings_view(self.panel_wrap)

    # -- Command-Strip (Timer + START/STOP-Hero) -------------------------

    def _build_command_strip(self, parent):
        """Oberer Streifen: Lauf-Timer (links) + grosser START/STOP-Hero."""
        strip = ctk.CTkFrame(parent, fg_color=STRIP_BG, corner_radius=0)
        strip.grid(row=0, column=0, sticky='ew')
        strip.grid_columnconfigure(1, weight=1)

        # col 0 -- Timer-Block (Wert + Label).
        timer = ctk.CTkFrame(strip, fg_color='transparent', width=70)
        timer.grid(row=0, column=0, sticky='w', padx=(12, 6), pady=11)
        self.timer_val = ctk.CTkLabel(
            timer, text='00:00:00', text_color=TEXT,
            font=ctk.CTkFont(family='Consolas', size=14, weight='bold'))
        self.timer_val.grid(row=0, column=0)
        self.timer_lbl = ctk.CTkLabel(
            timer, text=t('ui.timer_idle'), text_color=TEXT_FAINT,
            font=ctk.CTkFont(size=9, weight='bold'))
        self.timer_lbl.grid(row=1, column=0)
        try:
            self._timer_tooltip = Tooltip(timer, text=t('ui.timer_tip_idle'))
        except Exception:
            self._timer_tooltip = None

        # col 1 -- Hero (gross, teal -> rot beim Laufen).
        self.hero_btn = ctk.CTkButton(
            strip, height=48, corner_radius=14,
            font=ctk.CTkFont(size=17, weight='bold'),
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            text='▶  ' + t('ui.hero_start'),
            command=self._on_start_stop)
        self.hero_btn.grid(row=0, column=1, sticky='ew', padx=(6, 12), pady=11)

    # -- Ansichts-Kopf + die 4 Ansichten ---------------------------------
