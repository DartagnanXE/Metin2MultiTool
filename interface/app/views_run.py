# -*- coding: utf-8 -*-
"""FishingPuzzleConsoleViewsMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403


class FishingPuzzleConsoleViewsMixin:
    def _build_fishing_view(self, _parent):
        view = self._new_view('fishing')
        # Inhalt OBEN gruppiert: KEIN verteilender Zwischenraum -- alle Regler sitzen
        # kompakt am oberen Rand, der Rest-Leerraum sammelt sich ruhig UNTEN (row 2
        # bleibt leer -> kollabiert auf 0). Fenster bleibt fix auf der hoechsten View
        # (Settings) -- kein Springen beim Tab-Wechsel, keine Mittel-Luecke.
        self._view_header(view, t('ui.view_fishing'), t('ui.fishing_sub'),
                          badge=t('ui.badge_primary'))

        # Karte "Timing": die drei Delay-Slider mit ?-Hilfe.
        timing = Section(view, t('ui.delays_seconds'))
        timing.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        tbody = timing.body

        self.bait_slider = LabeledSlider(
            tbody, t('ui.wait_to_put_bait'),
            default=self._cfg['fishing']['bait_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'bait_time', v))
        self.bait_slider.grid(row=0, column=0, sticky='ew', pady=4)
        InfoBadge(tbody, text=t('ui.bait_delay_help')).grid(
            row=0, column=1, sticky='ne', padx=(4, 0))

        self.throw_slider = LabeledSlider(
            tbody, t('ui.wait_to_throw'),
            default=self._cfg['fishing']['throw_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'throw_time', v))
        self.throw_slider.grid(row=1, column=0, sticky='ew', pady=4)
        InfoBadge(tbody, text=t('ui.throw_delay_help')).grid(
            row=1, column=1, sticky='ne', padx=(4, 0))

        self.start_slider = LabeledSlider(
            tbody, t('ui.wait_to_start_game'),
            default=self._cfg['fishing']['start_game_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'start_game_time', v))
        self.start_slider.grid(row=2, column=0, sticky='ew', pady=4)
        InfoBadge(tbody, text=t('ui.start_delay_help')).grid(
            row=2, column=1, sticky='ne', padx=(4, 0))

        # Zeitlimit-Zeile: EIN Dreifach-Segment (Aus | Stoppen | Inventar-
        # Cleanup) + Minutenfeld. UMGEBAUT 2026-06-10: die alte Checkbox+
        # Segment-Kombi war eine Falle -- Segment auf Cleanup, Haekchen
        # vergessen -> KEIN Timer aktiv, der Bot stoppte irgendwann aus
        # anderem Grund und es sah aus wie ein Cleanup-Fehler (User-Report).
        # Jetzt traegt das Segment selbst den Aus-Zustand: genau EIN Schalter.
        stop_row = ctk.CTkFrame(view, fg_color='transparent')
        stop_row.grid(row=3, column=0, sticky='ew', pady=(2, 8))
        stop_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(stop_row, text=t('ui.timer_after_min'),
                     text_color=TEXT).grid(row=0, column=0, sticky='w')
        InfoBadge(stop_row, text=t('ui.timer_action_help')).grid(
            row=0, column=1, sticky='e', padx=(4, 4))
        self.stop_after_entry = ctk.CTkEntry(
            stop_row, width=64, justify='center')
        self.stop_after_entry.grid(row=0, column=2, sticky='e')
        self.stop_after_entry.insert(
            0, str(self._cfg['fishing']['stop_after_minutes']))
        self.stop_after_entry.bind('<KeyRelease>', self._on_stop_minutes)

        timer_action_pairs = [
            ('off', t('ui.timer_action_off')),
            ('stop', t('ui.timer_action_stop')),
            ('cleanup', t('ui.timer_action_cleanup')),
        ]
        self._timer_action_v2l = {v: l for v, l in timer_action_pairs}
        self._timer_action_l2v = {l: v for v, l in timer_action_pairs}
        fishing_cfg = self._cfg['fishing']
        current = ('off' if not fishing_cfg['stop_after_enabled']
                   else fishing_cfg.get('timer_action', 'stop'))
        self.timer_action_seg = SegmentedRow(
            stop_row, label='',
            values=[l for _v, l in timer_action_pairs],
            default=self._timer_action_v2l.get(
                current, t('ui.timer_action_off')),
            command=self._on_timer_action_change,
            info=None)
        self.timer_action_seg.grid(row=1, column=0, columnspan=3,
                                   sticky='ew', pady=(4, 0))

        # Golden-Tuna-Aktion: Labels '1'/'2'/'3' -> int-Werte (byte-stabil).
        # Golden-Tuna-Hilfe = VERIFIZIERTE Wiki-Fakten (keine erfundenen Zahlen);
        # ersetzt den alten knappen Hilfetext. Default bleibt 3 (Nutzer entscheidet).
        self.golden_tuna_seg = SegmentedRow(
            view, label=t('ui.golden_tuna_action'), values=['1', '2', '3'],
            default=str(self._cfg['fishing']['golden_tuna_action']),
            command=self._on_golden_tuna_change,
            info=t('ui.golden_tuna_verified'))
        self.golden_tuna_seg.grid(row=4, column=0, sticky='ew', pady=(0, 4))

        # Reittier/Mount-Animation-Cancel: direkt als Fishing-OPTION (Checkbox +
        # ?-Hilfe), Stil wie die Stop-after-Zeile. Die zugehoerige Reittier-TASTE
        # sitzt in den Settings unter "Angel-Tasten" (kein eigener Mount-Abschnitt).
        mount_row = ctk.CTkFrame(view, fg_color='transparent')
        mount_row.grid(row=5, column=0, sticky='ew', pady=(0, 4))
        mount_row.grid_columnconfigure(0, weight=1)
        self._mount_var = ctk.BooleanVar(
            value=self._cfg['fishing']['mount_enabled'])
        self.mount_chk = ctk.CTkCheckBox(
            mount_row, text=t('ui.mount_enabled'), variable=self._mount_var,
            text_color=TEXT, fg_color=TEAL, hover_color=TEAL_HOVER,
            command=self._on_mount_toggle)
        self.mount_chk.grid(row=0, column=0, sticky='w')
        InfoBadge(mount_row, text=t('ui.mount_help')).grid(
            row=0, column=1, sticky='e', padx=(4, 4))

        # Angel-Whitelist: an/aus direkt als Fishing-OPTION (Checkbox + ?-Hilfe),
        # Stil wie die Mount-/Stop-after-Zeile. Default AUS -> es wird alles
        # geangelt (byte-stabil). Die konkreten Fisch-Entscheidungen kommen aus
        # dem Inventar-Tab; dieser Schalter ist nur der Master-an/aus.
        whitelist_row = ctk.CTkFrame(view, fg_color='transparent')
        whitelist_row.grid(row=6, column=0, sticky='ew', pady=(0, 4))
        whitelist_row.grid_columnconfigure(0, weight=1)
        self._whitelist_var = ctk.BooleanVar(
            value=self._cfg['fishing']['whitelist_enabled'])
        self.whitelist_chk = ctk.CTkCheckBox(
            whitelist_row, text=t('ui.whitelist_enabled'),
            variable=self._whitelist_var, text_color=TEXT, fg_color=TEAL,
            hover_color=TEAL_HOVER, command=self._on_whitelist_toggle)
        self.whitelist_chk.grid(row=0, column=0, sticky='w')
        InfoBadge(whitelist_row, text=t('ui.whitelist_help')).grid(
            row=0, column=1, sticky='e', padx=(4, 4))

        # Koeder-Nachlegen: an/aus direkt als Fishing-OPTION (Checkbox + ?-Hilfe),
        # Stil wie die Whitelist-/Mount-Zeile. Default AUS -> der Bot prueft den
        # Koeder-Slot nie (byte-stabil). Erkennt der Bot den Koeder-Quickslot leer,
        # legt er einen Koeder aus dem Inventar nach; ist keiner mehr da, stoppt er.
        bait_refill_row = ctk.CTkFrame(view, fg_color='transparent')
        bait_refill_row.grid(row=7, column=0, sticky='ew', pady=(0, 4))
        bait_refill_row.grid_columnconfigure(0, weight=1)
        self._bait_refill_var = ctk.BooleanVar(
            value=self._cfg['fishing']['bait_refill_enabled'])
        self.bait_refill_chk = ctk.CTkCheckBox(
            bait_refill_row, text=t('ui.bait_refill_enabled'),
            variable=self._bait_refill_var, text_color=TEXT, fg_color=TEAL,
            hover_color=TEAL_HOVER, command=self._on_bait_refill_toggle)
        self.bait_refill_chk.grid(row=0, column=0, sticky='w')
        InfoBadge(bait_refill_row, text=t('ui.bait_refill_help')).grid(
            row=0, column=1, sticky='e', padx=(4, 4))

    def _build_puzzle_view(self, _parent):
        view = self._new_view('puzzle')
        # Inhalt OBEN gruppiert: KEIN verteilender Zwischenraum (row 3 bleibt leer ->
        # kollabiert auf 0). Detection + Solver sitzen kompakt oben, Rest-Leerraum
        # sammelt sich ruhig unten. Fenster bleibt fix (keine Mittel-Luecke).
        self._view_header(view, t('ui.view_puzzle'), t('ui.puzzle_sub'),
                          badge=t('ui.badge_secondary'))

        # Karte "Detection": Detection-Modus + Color-Sampling. Die Modus-Labels
        # ('Default'/'Auto'/'Manual'|'Manuell') sind sprachabhaengig -> ueber
        # value<->label-Dicts gefuehrt (interner Enum bleibt 'mark'). Manuell
        # oeffnet bei Auswahl weiterhin das interaktive Mark-Overlay.
        detect = Section(view, t('ui.board_detection'))
        detect.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        dbody = detect.body
        detection_pairs = _detection_pairs()
        self._detect_v2l = {value: label for value, label in detection_pairs}
        self._detect_l2v = {label: value for value, label in detection_pairs}
        self.detection_seg = SegmentedRow(
            dbody, label='',
            values=[label for _value, label in detection_pairs],
            default=self._detect_label_for(self._cfg['puzzle']['detection_mode']),
            command=self._on_detection_change,
            info=t('ui.detection_help'), info_image=REFERENCE_IMAGE,
            info_image_size=REFERENCE_IMAGE_SIZE)
        self.detection_seg.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        self.color_seg = SegmentedRow(
            dbody, label=t('ui.color_sampling'), values=['Single', 'Multi'],
            default=self._cfg['puzzle']['color_mode'].capitalize(),
            command=self._on_color_change, info=t('ui.color_sampling_help'))
        self.color_seg.grid(row=1, column=0, sticky='ew')

        # Karte "Solver": Puzzle-Methode. (Der frueher hier sitzende "Brettbereich
        # markieren"-Knopf entfaellt -- Manuell oeffnet das Overlay direkt; die
        # "kein markierter Bereich"-Statuszeile entfaellt ebenfalls.)
        solver = Section(view, t('ui.puzzle_method'))
        solver.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        sbody = solver.body
        solver_pairs = _solver_pairs()
        self._solver_v2l = {value: label for value, label in solver_pairs}
        self._solver_l2v = {label: value for value, label in solver_pairs}
        self.solver_seg = SegmentedRow(
            sbody, label='',
            values=[label for _value, label in solver_pairs],
            default=self._solver_label_for(self._cfg['puzzle']['solver_mode']),
            command=self._on_solver_change, info=t('ui.puzzle_method_help'))
        self.solver_seg.grid(row=0, column=0, sticky='ew')

        # "Force Deluxe"-Schalter DIREKT unter der Solver-Auswahl (V3-Reservat-
        # Strategie). Eigene ?-Hilfe mit dem ehrlichen Mathe-Trade-off; nur
        # wirksam bei 'KI optimiert' + vorhandener Deluxe-Box (sonst Standard-
        # Verhalten). Reicht den Toggle ueber _on_force_deluxe_toggle in die
        # Config; waehrend des Laufs gesperrt (sync_controls).
        sbody.grid_columnconfigure(0, weight=1)
        self._force_deluxe_var = ctk.BooleanVar(
            value=bool(self._cfg['puzzle'].get('force_deluxe', False)))
        self.force_deluxe_switch = self._switch_row(
            sbody, 1, t('ui.force_deluxe'), None, t('ui.force_deluxe_help'),
            self._force_deluxe_var, self._on_force_deluxe_toggle,
            return_switch=True)
        # (Box-Nachlegen-Schalter entfernt in v1.3: leere Boxen werden jetzt per
        # Spiel-Neustart ueber die Eventuebersicht behandelt, kein Inventar-Scan.)

    def _build_console_view(self, _parent):
        view = self._new_view('console')
        view.grid_rowconfigure(1, weight=1)
        self._view_header(view, t('ui.view_console'), t('ui.console_sub'))
        self.log_panel = LogPanel(view)
        self.log_panel.grid(row=1, column=0, sticky='nsew')
        # Winziger, BEWUSST unscheinbarer "Test Window"-Knopf unter dem Log:
        # spawnt das Fake-"METIN2"-Fenster, damit START auch ohne echtes Spiel
        # laeuft. Deutlich kleiner/schlichter als die echten Knoepfe (kein
        # Fill, kleine Schrift, gedaempfte Farben) -- reines Test-Hilfsmittel.
        # Zwei winzige Test-Knoepfe unten rechts nebeneinander: das Board-Fenster
        # (START-Trockenlauf) und -- CS5 -- das Inventar-Fenster (Scanner- +
        # Mehrfenster-Picker-Trockenlauf). Beide bewusst unscheinbar.
        test_row = ctk.CTkFrame(view, fg_color='transparent')
        test_row.grid(row=2, column=0, sticky='e', pady=(6, 0))
        self.inv_test_window_btn = ctk.CTkButton(
            test_row, text=t('ui.test_window_inventory'), height=22, width=108,
            corner_radius=6, fg_color='transparent', hover_color=PANEL_HOVER,
            text_color=TEXT_FAINT, border_width=1, border_color=PANEL_LIGHT,
            font=ctk.CTkFont(size=10), command=self._on_inventory_test_window)
        self.inv_test_window_btn.grid(row=0, column=0, sticky='e', padx=(0, 6))
        self.test_window_btn = ctk.CTkButton(
            test_row, text=t('ui.test_window'), height=22, width=92,
            corner_radius=6, fg_color='transparent', hover_color=PANEL_HOVER,
            text_color=TEXT_FAINT, border_width=1, border_color=PANEL_LIGHT,
            font=ctk.CTkFont(size=10), command=self._on_test_window)
        self.test_window_btn.grid(row=0, column=1, sticky='e')

    # -- Inventory (manueller Scan; Ausgabe geht in die Console) ----------
