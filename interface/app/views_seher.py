# -*- coding: utf-8 -*-
"""SeherViewMixin -- der Seherwettstreit-Autoplayer-Reiter.

Dauerschleifen-Autoplayer: startet Spiele selbst (Strg+E -> Eventuebersicht
-> Seherwettstreit -> Start -> Ja), spielt sie, holt die Belohnung ab und
laeuft bis Stop / X Durchlaeufe / Vorrat leer -- optional gefolgt von
Charakterwechsel oder Client-Beenden. Laeuft NUR, wenn der Bot idle ist.
Alles Detaillierte landet in der Debug-Console (log.event) und im
JSONL-Protokoll (%APPDATA%/Metin2FishBot/seherwettstreit_results.jsonl).
"""

import threading

from interface.app._common import *  # noqa: F401,F403

ORDER_KEYS = (('desc', 'ui.seher_order_desc'),
              ('asc', 'ui.seher_order_asc'),
              ('random', 'ui.seher_order_random'))

AFTER_KEYS = (('stop', 'ui.seher_after_stop'),
              ('char', 'ui.seher_after_char'),
              ('client', 'ui.seher_after_client'))


class SeherViewMixin:
    def _build_seher_view(self, _parent):
        """Baut die Seherwettstreit-Sicht (Start-Knopf + Optionen + Status)."""
        view = self._new_view('seher')
        self._view_header(view, t('ui.view_seher'), t('ui.seher_sub'))

        card = Section(view, t('ui.group_seher'))
        card.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        body = card.body
        body.grid_columnconfigure(0, weight=1)

        self._seher_btn = ctk.CTkButton(
            body, text=t('ui.seher_start_btn'), height=44, corner_radius=12,
            font=ctk.CTkFont(size=15, weight='bold'),
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            command=self._on_seher_start_stop)
        self._seher_btn.grid(row=0, column=0, sticky='ew', pady=(0, 2))
        InfoBadge(body, text=t('ui.seher_help')).grid(
            row=0, column=1, sticky='ne', padx=(6, 0))

        # Optionen: Reihenfolge / Durchlaeufe / Endaktion.
        opts = ctk.CTkFrame(body, fg_color='transparent')
        opts.grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))

        ctk.CTkLabel(opts, text=t('ui.seher_order_label'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0,
                                                     padx=(0, 8), sticky='w')
        self._seher_order_var = ctk.StringVar(
            value=t(dict(ORDER_KEYS)['desc']))
        ctk.CTkOptionMenu(opts, variable=self._seher_order_var, width=160,
                          values=[t(k) for _v, k in ORDER_KEYS]).grid(
            row=0, column=1, sticky='w')
        ctk.CTkLabel(opts, text=t('ui.seher_order_note'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=11)).grid(
            row=0, column=2, padx=(10, 0), sticky='w')

        ctk.CTkLabel(opts, text=t('ui.seher_games_label'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=1, column=0,
                                                     padx=(0, 8), pady=(6, 0),
                                                     sticky='w')
        self._seher_games_var = ctk.StringVar(value='0')
        ctk.CTkEntry(opts, textvariable=self._seher_games_var, width=60,
                     justify='center').grid(row=1, column=1, pady=(6, 0),
                                            sticky='w')
        ctk.CTkLabel(opts, text=t('ui.seher_games_note'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=11)).grid(
            row=1, column=2, padx=(10, 0), pady=(6, 0), sticky='w')

        ctk.CTkLabel(opts, text=t('ui.seher_after_label'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0,
                                                     padx=(0, 8), pady=(6, 0),
                                                     sticky='w')
        self._seher_after_var = ctk.StringVar(
            value=t(dict(AFTER_KEYS)['stop']))
        ctk.CTkOptionMenu(opts, variable=self._seher_after_var, width=160,
                          values=[t(k) for _v, k in AFTER_KEYS]).grid(
            row=2, column=1, pady=(6, 0), sticky='w')
        ctk.CTkLabel(opts, text=t('ui.seher_after_note'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=11)).grid(
            row=2, column=2, padx=(10, 0), pady=(6, 0), sticky='w')

        self._seher_status = ctk.CTkLabel(
            body, text=t('ui.seher_idle'), anchor='w',
            text_color=TEXT_FAINT, font=ctk.CTkFont(size=11), wraplength=440)
        self._seher_status.grid(row=2, column=0, columnspan=2, sticky='w',
                                pady=(8, 0))

        # Sichtbarer Zug-Timer (4-s-Kadenz) -- vom Worker via after() gefuettert.
        self._seher_timer = ctk.CTkLabel(
            body, text='', anchor='w', text_color=TEAL_BRIGHT,
            font=ctk.CTkFont(size=16, weight='bold'))
        self._seher_timer.grid(row=3, column=0, columnspan=2, sticky='w',
                               pady=(2, 0))

        # Laeuft gerade eine Session und das UI wird neu gebaut
        # (Sprachwechsel): Zustand kosmetisch spiegeln.
        try:
            if getattr(self, '_seher_running', False):
                self._seher_btn.configure(text=t('ui.seher_stop_btn'),
                                          fg_color=PANEL_LIGHT,
                                          text_color=TEXT)
            elif self.controller.running:
                self._seher_btn.configure(state='disabled')
        except Exception:
            pass

    # -- Auswahl-Helfer -------------------------------------------------------

    def _seher_pick(self, keys, var, default):
        label = var.get()
        for value, key in keys:
            if t(key) == label:
                return value
        return default

    def _seher_max_games(self):
        try:
            return max(0, int(self._seher_games_var.get().strip() or '0'))
        except Exception:
            return 0

    # -- Start/Stop ---------------------------------------------------------

    def _on_seher_start_stop(self):
        if getattr(self, '_seher_running', False):
            self._seher_abort = True
            try:
                self._seher_btn.configure(state='disabled',
                                          text=t('ui.seher_stopping'))
            except Exception:
                pass
            return

        if self.controller.running:
            log.event('-', t('seher.blocked_running'))
            return
        present, _hwnd, _gw, _gh, _healthy = _probe_game()
        if not present:
            log.event('-', t('ui.start_aborted_no_window'))
            try:
                self._seher_status.configure(
                    text=t('ui.status_start_no_window'))
            except Exception:
                pass
            return

        self._seher_running = True
        self._seher_abort = False
        order = self._seher_pick(ORDER_KEYS, self._seher_order_var, 'desc')
        after = self._seher_pick(AFTER_KEYS, self._seher_after_var, 'stop')
        max_games = self._seher_max_games()
        try:
            self._apply_preferred_hwnd()
        except Exception:
            pass
        cfg = self.controller.current_config()
        try:
            self._seher_btn.configure(text=t('ui.seher_stop_btn'),
                                      fg_color=PANEL_LIGHT, text_color=TEXT)
            self._seher_status.configure(text=t('ui.seher_running'))
        except Exception:
            pass
        log.event('0', t('seher.started', order=order))

        def _on_game(ses, res):
            # Aus dem Worker-Thread -> UI-Update via after().
            self.after(0, lambda: self._seher_progress(ses, res))

        def _on_tick(phase, remaining):
            self.after(0, lambda: self._seher_tick(phase, remaining))

        def _worker():
            try:
                from interface import seher_runner as sr
                ses = sr.run_seher_session(
                    cfg, order=order, max_games=max_games,
                    after_action=after, on_game_done=_on_game,
                    on_tick=_on_tick,
                    abort_fn=lambda: getattr(self, '_seher_abort', False))
                self.after(0, lambda s=ses: self._on_seher_done(s))
            except Exception as exc:  # defensiv: nie den Thread crashen
                self.after(0, lambda e=exc: self._on_seher_failed(e))

        threading.Thread(target=_worker, name='seher-session',
                         daemon=True).start()

    def _seher_tick(self, phase, remaining):
        try:
            if phase == 'zug' and remaining and remaining > 0.05:
                self._seher_timer.configure(
                    text=t('ui.seher_timer_move', s='{:.1f}'.format(remaining)))
            elif phase == 'auswertung':
                self._seher_timer.configure(text=t('ui.seher_timer_eval'))
            else:
                self._seher_timer.configure(text='')
        except Exception:
            pass

    def _seher_progress(self, ses, res):
        try:
            self._seher_status.configure(text=t(
                'ui.seher_progress', n=ses.games_played,
                coins=ses.total_coins, p=res.points_me, g=res.points_opp))
        except Exception:
            pass

    def _on_seher_done(self, ses):
        self._seher_running = False
        self._seher_abort = False
        try:
            self._seher_timer.configure(text='')
        except Exception:
            pass
        try:
            self._seher_btn.configure(state='normal',
                                      text=t('ui.seher_start_btn'),
                                      fg_color=TEAL, text_color=INK)
        except Exception:
            pass
        if ses.stopped_reason == 'fehler':
            txt = t('ui.seher_status_error', err=ses.error_step)
        elif ses.stopped_reason == 'abort':
            txt = t('ui.seher_status_aborted_n', n=ses.games_played,
                    coins=ses.total_coins)
        else:
            txt = t('ui.seher_status_session_done', n=ses.games_played,
                    coins=ses.total_coins, reason=ses.stopped_reason)
        try:
            self._seher_status.configure(text=txt)
        except Exception:
            pass

    def _on_seher_failed(self, exc):
        self._seher_running = False
        self._seher_abort = False
        try:
            self._seher_timer.configure(text='')
        except Exception:
            pass
        try:
            self._seher_btn.configure(state='normal',
                                      text=t('ui.seher_start_btn'),
                                      fg_color=TEAL, text_color=INK)
            self._seher_status.configure(text=t('ui.status_start_failed'))
        except Exception:
            pass
        log.error(t('seher.worker_crashed'), exc=exc)
