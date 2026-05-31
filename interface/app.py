"""Single-Window-UI fuer den Metin2 Fishing Bot (CustomTkinter, Teal/Dark).

V1.0-Aufbau:
  * EIN Fenster mit Ansichts-Umschalter oben: **Bot | Console** (kein separates
    Debug-Tool mehr -- die Live-Konsole lebt in derselben App).
  * Bot-Ansicht: grosser START/STOP-Button, Segmented ``Fishing | Puzzle``
    (exklusiv, waehrend Lauf gesperrt), SETTINGS (3 Delay-Slider 0.1-20s, Stop-
    after, Board Detection inkl. Mark-Kalibrierung + ``?``-Hilfe mit Referenzbild,
    Color Sampling, Puzzle-Methode).
  * Console-Ansicht: Live-Log gross + Toolbar (Kopieren / Logdatei oeffnen /
    Leeren).
  * Eigenes Fenster-/Taskleisten-Icon (musketier.ico), Sofort-Render, Status-
    zeile, Auto-Speichern der Einstellungen.

Die Auswahl-Schalter nutzen das robuste :class:`~interface.widgets.Segmented`
(echte Buttons) -- nie wieder leere graue Balken.

Die Bot-Steuerung haengt in :class:`BotController`; das Modul kennt die Bots nur
als injizierte Instanzen und liest/schreibt Optionen ueber :mod:`interface.config`.

UI-Strings ENGLISCH, Kommentare deutsch (Spec).
"""

import copy
import os

import customtkinter as ctk

from debuglog import log
from i18n import get_lang, set_lang, t
from interface import config as cfgmod
from interface.log_panel import LogPanel
from interface.widgets import (BG, DANGER, DANGER_HOVER, INK, LIVE_GREEN, PANEL,
                               PANEL_HOVER, PANEL_LIGHT, TEAL, TEAL_DARK,
                               TEAL_HOVER, TEXT, TEXT_MUTED, LabeledSlider,
                               Section, Segmented, SegmentedRow)
from respath import resource_path

ICON_FILE = 'musketier.ico'
REFERENCE_IMAGE = 'images/calibration_reference.png'

# Puzzle-Methode: config-Werte ('standard'/'trained') <-> Uebersetzungs-Keys.
# Die ANZEIGE-Labels sind sprachabhaengig -> werden LIVE pro Aufbau via
# _solver_pairs() uebersetzt (KEINE eingefrorene Modul-Konstante -- sonst wuerde
# ein Sprachwechsel die Labels nicht aktualisieren).
SOLVER_MODE_KEYS = (('standard', 'ui.solver_label_default'),
                    ('trained', 'ui.solver_label_trained'))


def _solver_pairs():
    """Aktuelle (value, label)-Paare der Puzzle-Methode (live uebersetzt)."""
    return tuple((value, t(key)) for value, key in SOLVER_MODE_KEYS)


def _game_window_present():
    """True, wenn das Spiel-Fenster (``constants.GAME_NAME``) da + sichtbar ist.

    GENAU der Check, den auch der Bot zum Finden nutzt (``FindWindow``) -- so
    bedeutet 'gruen' wirklich 'der Bot findet Metin2'. Rein passiver Win32-Read
    von Fenster-Metadaten -- KEIN Prozessspeicher (kein Anti-Cheat-Trigger).
    Wirft nie (headless / fehlendes win32 -> False)."""
    try:
        import constants
        import win32gui
        hwnd = win32gui.FindWindow(None, constants.GAME_NAME)
        return bool(hwnd) and bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


class BotController:
    """Haelt Laufzustand, Modus und die beiden Bot-Instanzen.

    Schnittstelle, gegen die ``hack.py`` verdrahtet: ``mode``/``running`` lesen,
    ``fishbot``/``puzzlebot`` ansprechen, ``collect_values()`` /
    ``current_config()`` fuer die Optionen. Die UI ruft ``on_start_stop`` beim
    Button-Klick. Einstellungen werden bei jeder Aenderung (entprellt)
    gespeichert.
    """

    def __init__(self, app, fishbot, puzzlebot, cfg):
        self.app = app
        self.fishbot = fishbot
        self.puzzlebot = puzzlebot
        self._cfg = cfgmod.validate(cfg)
        self.mode = self._cfg['mode']
        self.running = False
        self.on_start = None
        self.on_stop = None
        self._save_job = None

    # -- Konfigurationszugriff -------------------------------------------

    def current_config(self):
        return cfgmod.validate(self._cfg)

    def update_config(self, section, key, value):
        """Setzt einen Wert (immutabel), loggt ihn und plant ein Auto-Speichern."""
        new_cfg = copy.deepcopy(self._cfg)
        new_cfg.setdefault(section, {})[key] = value
        self._cfg = cfgmod.validate(new_cfg)
        log.event('-', t('ui.setting_changed', section=section, key=key,
                         value=value))
        self._schedule_save()
        return self._cfg

    def set_mode(self, mode):
        if mode in cfgmod.APP_MODES and not self.running:
            self.mode = mode
            new_cfg = copy.deepcopy(self._cfg)
            new_cfg['mode'] = mode
            self._cfg = cfgmod.validate(new_cfg)
            log.event('-', t('ui.mode_switched', mode=mode))
            self._schedule_save()

    def collect_values(self):
        return cfgmod.to_values(self._cfg)

    def set_language(self, lang):
        """Speichert die gewaehlte UI-Sprache ('en'/'de') in der Config."""
        new_cfg = copy.deepcopy(self._cfg)
        new_cfg['language'] = lang
        self._cfg = cfgmod.validate(new_cfg)
        self._schedule_save()

    # -- Auto-Speichern (entprellt) --------------------------------------

    def _schedule_save(self):
        """Plant ein Speichern in ~0.7s; weitere Aenderungen verschieben es.

        Schuetzt vor Datenverlust bei Absturz (statt nur beim Schliessen). Der
        Aufruf laeuft im GUI-Thread (after); faellt auf Sofort-Speichern zurueck,
        falls kein Scheduler verfuegbar ist.
        """
        try:
            if self._save_job is not None:
                self.app.after_cancel(self._save_job)
            self._save_job = self.app.after(700, self._do_save)
        except Exception:
            self._do_save()

    def _do_save(self):
        self._save_job = None
        try:
            cfgmod.save(self._cfg)
            log.event('-', t('ui.settings_saved'))
            self.app.flash_saved()
        except Exception:
            pass

    # -- Start/Stop -------------------------------------------------------

    def on_start_stop(self):
        try:
            if self.running:
                log.section(t('ui.stop_pressed_manual'))
                self.set_running(False)
                if callable(self.on_stop):
                    self.on_stop()
            else:
                log.section(t('ui.start_pressed', mode=self.mode))
                if callable(self.on_start):
                    self.on_start()
                else:
                    self._fallback_start()
                self.set_running(True)
        except Exception as exc:
            log.error(t('ui.start_stop_toggle_failed'), exc=exc)
            self.set_running(False)

    def _fallback_start(self):
        values = self.collect_values()
        if self.mode == 'fishing':
            self.fishbot.set_to_begin(values)
            self.fishbot.botting = True
            self.puzzlebot.botting = False
        else:
            self.puzzlebot.set_to_begin(values)
            self.puzzlebot.botting = True
            self.fishbot.botting = False

    def set_running(self, running):
        self.running = bool(running)
        if not self.running:
            self.fishbot.botting = False
            self.puzzlebot.botting = False
        self.app.sync_controls()


class App(ctk.CTk):
    """Das Single-Window: Topbar (Logo + Status + Bot|Console) + Inhalt."""

    def __init__(self, cfg=None, fishbot=None, puzzlebot=None):
        super().__init__()

        self._cfg = cfgmod.validate(cfg if cfg is not None else cfgmod.DEFAULTS)

        if fishbot is None or puzzlebot is None:
            from fishingbot import FishingBot
            from puzzle import PuzzleBot
            fishbot = fishbot or FishingBot()
            puzzlebot = puzzlebot or PuzzleBot()

        self.controller = BotController(self, fishbot, puzzlebot, self._cfg)

        # Gespeicherte Sprache anwenden, BEVOR das UI (mit t()) gebaut wird.
        set_lang(self._cfg['language'])

        ctk.set_appearance_mode('dark')
        ctk.set_widget_scaling(0.9)   # alles ~10% kompakter -> passt auf eine Seite
        self.title(t('ui.window_title'))
        self.geometry('580x800')
        self.minsize(480, 540)            # klein erlaubt -- Inhalt scrollt
        self.configure(fg_color=BG)
        self._saved_job = None
        self._game_present = False
        self._set_window_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)   # Inhaltsbereich waechst

        self._active_view = 'bot'
        self._build_topbar()
        self._build_content()
        self._show_view('bot')

        self._apply_config_to_widgets()
        self.sync_controls()

        if self._cfg['log']['show_in_ui']:
            self.log_panel.attach()

        self.protocol('WM_DELETE_WINDOW', self._on_close)
        # Sofort-Render erzwingen: sonst bleibt das Fenster auf manchen Setups
        # blass/leer, bis ein Event es neu zeichnet (V0-Symptom).
        self.after(60, self._force_render)
        # Spiel-Erkennung starten (Status gruen, sobald Metin2 gefunden).
        self.after(250, self._poll_game)
        # Lauf-Indikator pulsieren lassen (klares "es laeuft"-Zeichen).
        self._pulse_on = False
        self.after(600, self._pulse)

    # -- Fenster-Icon / Render -------------------------------------------

    def _set_window_icon(self):
        """Setzt das Musketier-Icon als Fenster-/Taskleisten-Icon.

        CustomTkinter ueberschreibt das Icon ~200ms nach dem Start mit seinem
        eigenen -> wir setzen es danach erneut (bekannter CTk-Workaround).
        """
        ico = resource_path(ICON_FILE)
        if not os.path.exists(ico):
            return
        try:
            self.iconbitmap(ico)
        except Exception:
            pass
        self.after(300, lambda: self._reapply_icon(ico))

    def _reapply_icon(self, ico):
        try:
            self.iconbitmap(ico)
        except Exception:
            pass

    def _force_render(self):
        try:
            self.update_idletasks()
            self.update()
            self.lift()
        except Exception:
            pass

    # -- Topbar (Titel + Status + Ansicht-Umschalter) --------------------

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bar.grid(row=0, column=0, sticky='ew')
        bar.grid_columnconfigure(1, weight=1)
        self.topbar = bar

        inner = ctk.CTkFrame(bar, fg_color='transparent')
        inner.grid(row=0, column=0, sticky='ew', padx=16, pady=10)
        inner.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(inner, fg_color='transparent')
        titles.grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(titles, text=t('ui.window_title'), anchor='w',
                     font=ctk.CTkFont(size=20, weight='bold'),
                     text_color=TEXT).grid(row=0, column=0, sticky='w')
        self.status_label = ctk.CTkLabel(
            titles, text=t('ui.status_ready'), anchor='w', text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12))
        self.status_label.grid(row=1, column=0, sticky='w')

        right = ctk.CTkFrame(inner, fg_color='transparent')
        right.grid(row=0, column=1, sticky='e')
        # Kleiner, dezenter EN/DE-Umschalter OBEN -- bewusst KEIN ebenbuertiger
        # Button zu Bot|Console, sondern klickbare Mini-Labels.
        self._build_lang_toggle(right).grid(row=0, column=0, sticky='e',
                                            pady=(0, 5))
        self.view_seg = Segmented(
            right, values=[t('ui.view_bot'), t('ui.view_console')],
            default=t('ui.view_bot'),
            command=self._on_view_change, height=30)
        self.view_seg.grid(row=1, column=0, sticky='e')

    def _build_lang_toggle(self, parent):
        """Kleiner, dezenter EN/DE-Umschalter: klickbare Mini-Labels (aktiv teal,
        inaktiv grau) -- KEIN ebenbuertiger Button zu Bot|Console."""
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        self._lang_labels = {}
        for col, lang in ((0, 'en'), (2, 'de')):
            lbl = ctk.CTkLabel(frame, text=lang.upper(), width=18,
                               font=ctk.CTkFont(size=11, weight='bold'),
                               cursor='hand2')
            lbl.grid(row=0, column=col)
            lbl.bind('<Button-1>',
                     lambda _e, lng=lang: self._on_lang_change(lng))
            self._lang_labels[lang] = lbl
        ctk.CTkLabel(frame, text='|', text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=10)).grid(row=0, column=1, padx=1)
        self._refresh_lang_toggle()
        return frame

    def _refresh_lang_toggle(self):
        cur = get_lang()
        for lang, lbl in getattr(self, '_lang_labels', {}).items():
            lbl.configure(text_color=(TEAL if lang == cur else TEXT_MUTED))

    def _on_lang_change(self, lang):
        """Schaltet die Sprache um, speichert sie und rendert das UI neu."""
        if lang == get_lang():
            return
        set_lang(lang)
        self.controller.set_language(lang)
        log.event('-', t('ui.language_changed', lang=lang))
        # Erst NACH dem Callback neu bauen (nicht das klickende Widget zerstoeren).
        self.after(10, self._rebuild_ui)

    def _rebuild_ui(self):
        """Baut Topbar + Inhalt in der aktuellen Sprache neu (nach Sprachwechsel).

        Der Laufzustand bleibt erhalten (steckt im BotController, nicht in den
        Widgets); die Log-Senke wird sauber ab- und wieder angehaengt.
        """
        try:
            self.log_panel.detach()
        except Exception:
            pass
        for widget in (getattr(self, 'topbar', None),
                       getattr(self, 'content', None)):
            if widget is not None:
                try:
                    widget.destroy()
                except Exception:
                    pass
        self._build_topbar()
        self._build_content()
        self._show_view(self._active_view)
        self._apply_config_to_widgets()
        self.sync_controls()
        if self._cfg['log']['show_in_ui']:
            self.log_panel.attach()
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _on_view_change(self, label):
        self._show_view('console' if label == t('ui.view_console') else 'bot')

    def _show_view(self, view):
        self._active_view = view
        if view == 'console':
            self.bot_view.grid_remove()
            self.console_view.grid()
        else:
            self.console_view.grid_remove()
            self.bot_view.grid()
        try:
            self.view_seg.set(t('ui.view_console') if view == 'console'
                              else t('ui.view_bot'))
        except Exception:
            pass

    # -- Inhaltsbereich (Bot- und Console-Ansicht uebereinander) ---------

    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color='transparent')
        self.content.grid(row=1, column=0, sticky='nsew')
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Bot-Ansicht scrollbar -> Inhalt wird NIE abgeschnitten, egal wie klein
        # das Fenster gezogen wird (loest 'nicht alles sichtbar').
        self.bot_view = ctk.CTkScrollableFrame(self.content,
                                               fg_color='transparent')
        self.bot_view.grid(row=0, column=0, sticky='nsew')
        self.bot_view.grid_columnconfigure(0, weight=1)
        self._build_bot_view(self.bot_view)

        self.console_view = ctk.CTkFrame(self.content, fg_color='transparent')
        self.console_view.grid(row=0, column=0, sticky='nsew')
        self.console_view.grid_columnconfigure(0, weight=1)
        self.console_view.grid_rowconfigure(0, weight=1)
        self._build_console_view(self.console_view)
        self.console_view.grid_remove()   # startet ausgeblendet

    def _build_bot_view(self, parent):
        # Mode + grosser START/STOP.
        wrap = ctk.CTkFrame(parent, fg_color='transparent')
        wrap.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 4))
        wrap.grid_columnconfigure(0, weight=1)

        self.mode_seg = SegmentedRow(
            wrap, label=t('ui.mode'), values=[t('ui.mode_fishing'),
                                              t('ui.mode_puzzle')],
            default=self._label_for_mode(self._cfg['mode']),
            command=self._on_mode_change)
        self.mode_seg.grid(row=0, column=0, sticky='ew')

        self.start_btn = ctk.CTkButton(
            wrap, text=t('ui.start'), height=44,
            font=ctk.CTkFont(size=16, weight='bold'),
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            corner_radius=12, command=self._on_start_stop)
        self.start_btn.grid(row=1, column=0, sticky='ew', pady=(6, 0))

        # Settings.
        section = Section(parent, t('ui.settings'))
        section.grid(row=1, column=0, sticky='ew', padx=16, pady=(6, 8))
        body = section.body

        ctk.CTkLabel(body, text=t('ui.delays_seconds'), anchor='w',
                     text_color=TEXT_MUTED).grid(
            row=0, column=0, sticky='w', pady=(0, 2))

        self.bait_slider = LabeledSlider(
            body, t('ui.wait_to_put_bait'),
            default=self._cfg['fishing']['bait_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'bait_time', v))
        self.bait_slider.grid(row=1, column=0, sticky='ew', pady=2)

        self.throw_slider = LabeledSlider(
            body, t('ui.wait_to_throw'),
            default=self._cfg['fishing']['throw_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'throw_time', v))
        self.throw_slider.grid(row=2, column=0, sticky='ew', pady=2)

        self.start_slider = LabeledSlider(
            body, t('ui.wait_to_start_game'),
            default=self._cfg['fishing']['start_game_time'],
            command=lambda v: self.controller.update_config(
                'fishing', 'start_game_time', v))
        self.start_slider.grid(row=3, column=0, sticky='ew', pady=2)

        stop_row = ctk.CTkFrame(body, fg_color='transparent')
        stop_row.grid(row=4, column=0, sticky='ew', pady=(8, 4))
        stop_row.grid_columnconfigure(0, weight=1)

        self.stop_after_var = ctk.BooleanVar(
            value=self._cfg['fishing']['stop_after_enabled'])
        self.stop_after_chk = ctk.CTkCheckBox(
            stop_row, text=t('ui.stop_after_time_min'), variable=self.stop_after_var,
            text_color=TEXT, fg_color=TEAL, hover_color=TEAL_HOVER,
            command=self._on_stop_after_toggle)
        self.stop_after_chk.grid(row=0, column=0, sticky='w')

        self.stop_after_entry = ctk.CTkEntry(
            stop_row, width=70, justify='center')
        self.stop_after_entry.grid(row=0, column=1, sticky='e')
        self.stop_after_entry.insert(
            0, str(self._cfg['fishing']['stop_after_minutes']))
        self.stop_after_entry.bind('<KeyRelease>', self._on_stop_minutes)

        # Board Detection + ``?``-Hilfe (mit Referenzbild) + Mark-Button.
        self.detection_seg = SegmentedRow(
            body, label=t('ui.board_detection'),
            values=['Default', 'Auto', 'Mark'],
            default=self._cfg['puzzle']['detection_mode'].capitalize(),
            command=self._on_detection_change,
            info=t('ui.detection_help'), info_image=REFERENCE_IMAGE)
        self.detection_seg.grid(row=5, column=0, sticky='ew', pady=(8, 2))

        self.mark_btn = ctk.CTkButton(
            body, text=t('ui.mark_board_region'), height=34,
            fg_color=PANEL_LIGHT, hover_color=PANEL_HOVER, text_color=TEAL,
            border_width=1, border_color=TEAL_DARK, corner_radius=8,
            command=self._on_mark)
        self.mark_btn.grid(row=6, column=0, sticky='ew', pady=(2, 4))

        self.mark_status = ctk.CTkLabel(
            body, text=self._mark_status_text(), anchor='w',
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11))
        self.mark_status.grid(row=7, column=0, sticky='w', pady=(0, 4))

        self.color_seg = SegmentedRow(
            body, label=t('ui.color_sampling'), values=['Single', 'Multi'],
            default=self._cfg['puzzle']['color_mode'].capitalize(),
            command=self._on_color_change,
            info=t('ui.color_sampling_help'))
        self.color_seg.grid(row=8, column=0, sticky='ew', pady=(8, 4))

        # Puzzle-Methode: Labels live uebersetzen + Label<->Wert-Maps frisch bauen.
        solver_pairs = _solver_pairs()
        self._solver_v2l = {value: label for value, label in solver_pairs}
        self._solver_l2v = {label: value for value, label in solver_pairs}
        self.solver_seg = SegmentedRow(
            body, label=t('ui.puzzle_method'),
            values=[label for _value, label in solver_pairs],
            default=self._solver_label_for(self._cfg['puzzle']['solver_mode']),
            command=self._on_solver_change,
            info=t('ui.puzzle_method_help'))
        self.solver_seg.grid(row=9, column=0, sticky='ew', pady=(8, 4))

        hint = ctk.CTkLabel(
            body, text=t('ui.resolution_hint'), anchor='w', text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11))
        hint.grid(row=10, column=0, sticky='w', pady=(8, 0))

    def _build_console_view(self, parent):
        self.log_panel = LogPanel(parent)
        self.log_panel.grid(row=0, column=0, sticky='nsew', padx=16,
                            pady=(8, 16))

    # -- Event-Handler ----------------------------------------------------

    def _on_start_stop(self):
        self.controller.on_start_stop()

    def _on_mode_change(self, label):
        mode = 'fishing' if label == t('ui.mode_fishing') else 'puzzle'
        self.controller.set_mode(mode)
        self._cfg = self.controller.current_config()

    def _on_stop_after_toggle(self):
        self._cfg = self.controller.update_config(
            'fishing', 'stop_after_enabled', bool(self.stop_after_var.get()))

    def _on_stop_minutes(self, _event=None):
        raw = self.stop_after_entry.get().strip()
        try:
            minutes = int(raw) if raw else 0
        except ValueError:
            minutes = 0
        self._cfg = self.controller.update_config(
            'fishing', 'stop_after_minutes', minutes)

    def _on_detection_change(self, label):
        self._cfg = self.controller.update_config(
            'puzzle', 'detection_mode', label.lower())

    def _on_color_change(self, label):
        self._cfg = self.controller.update_config(
            'puzzle', 'color_mode', label.lower())

    def _on_solver_change(self, label):
        value = self._solver_l2v.get(label, cfgmod.SOLVER_MODES[0])
        self._cfg = self.controller.update_config('puzzle', 'solver_mode', value)

    def _on_mark(self):
        """Oeffnet das Mark-Overlay (Modul B) und speichert die Kalibrierung."""
        try:
            from overlay_mark import pick_offset_interactive
        except Exception as exc:
            log.error(t('ui.mark_overlay_unavailable_log'), exc=exc)
            self.mark_status.configure(
                text=t('ui.mark_overlay_unavailable'))
            return
        try:
            result = pick_offset_interactive()
        except Exception as exc:
            log.error(t('ui.mark_overlay_failed'), exc=exc)
            result = None
        if result is not None:
            self._persist_mark_result(result)
            self._cfg = self.controller.update_config(
                'puzzle', 'detection_mode', 'mark')
            self.detection_seg.set('Mark')
        self.mark_status.configure(text=self._mark_status_text())

    def _persist_mark_result(self, result):
        offset = result.get('offset')
        if offset is not None:
            self._cfg = self.controller.update_config(
                'puzzle', 'mark_offset', [int(offset[0]), int(offset[1])])

        size = result.get('size')
        mark_size = None
        if size is not None:
            try:
                mark_size = [int(size[0]), int(size[1])]
            except (TypeError, ValueError, IndexError):
                mark_size = None
        self._cfg = self.controller.update_config(
            'puzzle', 'mark_size', mark_size)

        key_points = result.get('key_points') or {}
        mark_keypoints = {}
        try:
            for name, point in key_points.items():
                mark_keypoints[name] = [int(point[0]), int(point[1])]
        except (TypeError, ValueError, IndexError, AttributeError):
            mark_keypoints = {}
        self._cfg = self.controller.update_config(
            'puzzle', 'mark_keypoints', mark_keypoints)

    def _on_close(self):
        try:
            cfgmod.save(self.controller.current_config())
        except Exception:
            pass
        try:
            self.log_panel.detach()
        except Exception:
            pass
        self.destroy()

    # -- UI-Synchronisierung ---------------------------------------------

    def sync_controls(self):
        """Spiegelt den Laufzustand ins UI (Button, Status, Sperren).

        Waehrend des Laufs: Modus + Einstellungen gesperrt, Button rot ('STOP'),
        Status gruen. Der Ansicht-Umschalter (Bot|Console) bleibt IMMER aktiv,
        damit man auch waehrend des Laufs in die Konsole schauen kann.
        """
        running = self.controller.running
        if running:
            self.start_btn.configure(text=t('ui.stop'), fg_color=DANGER,
                                     hover_color=DANGER_HOVER,
                                     text_color='#2b0a0a')
            mode = (t('ui.mode_fishing') if self.controller.mode == 'fishing'
                    else t('ui.mode_puzzle'))
            self.status_label.configure(text=t('ui.status_running', mode=mode),
                                        text_color=LIVE_GREEN)
        else:
            self.start_btn.configure(text=t('ui.start'), fg_color=TEAL,
                                     hover_color=TEAL_HOVER, text_color=INK)
            text, color = self._idle_status()
            self.status_label.configure(text=text, text_color=color)

        self.mode_seg.set_enabled(not running)
        for slider in (self.bait_slider, self.throw_slider, self.start_slider):
            slider.set_enabled(not running)
        for seg in (self.detection_seg, self.color_seg, self.solver_seg):
            seg.set_enabled(not running)
        state = 'normal' if not running else 'disabled'
        self.stop_after_chk.configure(state=state)
        self.stop_after_entry.configure(state=state)
        self.mark_btn.configure(state=state)

    def sync_button(self):
        self.sync_controls()

    def flash_saved(self):
        """Zeigt kurz „saved ✓" in der Statuszeile (nur im Ruhezustand)."""
        if self.controller.running:
            return
        try:
            self.status_label.configure(text=t('ui.status_saved'), text_color=TEAL)
            if self._saved_job is not None:
                self.after_cancel(self._saved_job)
            self._saved_job = self.after(1200, self._restore_status)
        except Exception:
            pass

    def _restore_status(self):
        self._saved_job = None
        if not self.controller.running:
            text, color = self._idle_status()
            try:
                self.status_label.configure(text=text, text_color=color)
            except Exception:
                pass

    def _idle_status(self):
        """Statuszeile im Ruhezustand: gruen wenn Metin2 erkannt, sonst grau."""
        if getattr(self, '_game_present', False):
            return t('ui.status_metin2_detected'), LIVE_GREEN
        return t('ui.status_waiting_metin2'), TEXT_MUTED

    def _poll_game(self):
        """Prueft ~1x/s passiv, ob das Metin2-Fenster da ist, und spiegelt das in
        die Statuszeile (nur im Ruhezustand; 'Running'/'saved ✓' haben Vorrang).
        Rein lesender Win32-Check -- kein Anti-Cheat-Trigger."""
        self._game_present = _game_window_present()
        if not self.controller.running and self._saved_job is None:
            text, color = self._idle_status()
            try:
                self.status_label.configure(text=text, text_color=color)
            except Exception:
                pass
        try:
            self.after(1000, self._poll_game)
        except Exception:
            pass

    def notify_stop(self, reason):
        """Meldet prominent, DASS + WARUM der Bot sich selbst gestoppt hat.

        Steht ~4 s in der Statuszeile (rot bei Fehler, sonst amber), danach
        zurueck auf den Ruhestatus. Wird vom Tick gerufen, wenn ein Bot sich
        selbst beendet (Zeitlimit, Fehler, Region-/Truhen-Problem)."""
        try:
            color = (DANGER if reason == t('run.reason_error_see_console')
                     else '#f59e0b')
            self.status_label.configure(text=t('ui.status_stopped', reason=reason),
                                        text_color=color)
            if self._saved_job is not None:
                self.after_cancel(self._saved_job)
            self._saved_job = self.after(4000, self._restore_status)
        except Exception:
            pass

    def _pulse(self):
        """Blinkt den Status-Punkt, solange der Bot laeuft -- klares Lauf-Zeichen."""
        try:
            if self.controller.running:
                self._pulse_on = not self._pulse_on
                dot = '●' if self._pulse_on else '○'
                mode = (t('ui.mode_fishing') if self.controller.mode == 'fishing'
                        else t('ui.mode_puzzle'))
                self.status_label.configure(
                    text=t('ui.status_running_pulse', dot=dot, mode=mode),
                    text_color=LIVE_GREEN)
        except Exception:
            pass
        try:
            self.after(600, self._pulse)
        except Exception:
            pass

    def _apply_config_to_widgets(self):
        fishing = self._cfg['fishing']
        self.bait_slider.set(fishing['bait_time'])
        self.throw_slider.set(fishing['throw_time'])
        self.start_slider.set(fishing['start_game_time'])
        self.stop_after_var.set(fishing['stop_after_enabled'])
        self.stop_after_entry.delete(0, 'end')
        self.stop_after_entry.insert(0, str(fishing['stop_after_minutes']))

        puzzle = self._cfg['puzzle']
        self.detection_seg.set(puzzle['detection_mode'].capitalize())
        self.color_seg.set(puzzle['color_mode'].capitalize())
        self.solver_seg.set(self._solver_label_for(puzzle['solver_mode']))
        self.mode_seg.set(self._label_for_mode(self._cfg['mode']))

    # -- kleine Helfer ----------------------------------------------------

    @staticmethod
    def _label_for_mode(mode):
        return t('ui.mode_puzzle') if mode == 'puzzle' else t('ui.mode_fishing')

    def _solver_label_for(self, solver_mode):
        return self._solver_v2l.get(
            solver_mode, self._solver_v2l[cfgmod.SOLVER_MODES[0]])

    def _mark_status_text(self):
        offset = self.controller.current_config()['puzzle']['mark_offset']
        if offset is None:
            return t('ui.mark_status_none')
        return t('ui.mark_status_offset', x=offset[0], y=offset[1])
