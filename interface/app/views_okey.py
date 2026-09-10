# -*- coding: utf-8 -*-
"""OkeyViewMixin -- der Reiter fuer das Okey-Kartenspiel.

Drei Dinge stehen darin, mehr braucht es nicht: wie viele Kartensets
nacheinander gespielt werden, wie stark der Loeser rechnen soll, und was
dabei herauskam.

Die Stufen-Tabelle darunter ist ausdruecklich gewuenscht -- sie soll die Wahl
begruendbar machen statt sie zu erraten. Die Zahlen darin sind gemessen (400
identische Kartenmischungen je Stufe) und liegen in :mod:`okey.stufen`, einem
Modul ohne einen einzigen Import. Das ist kein Zufall: der Reiter zeigt die
Tabelle, ohne dass beim Programmstart Strategie oder OpenCV geladen werden --
die schwere Maschinerie kommt erst im Arbeits-Thread dazu, wenn wirklich
gespielt wird. Der Reiter soll aufgehen, nicht laden.
"""

import threading

from interface.app._common import *  # noqa: F401,F403

#: Anzeige-Reihenfolge der Stufen -- die staerkste zuerst.
LEVEL_KEYS = (('beste', 'ui.okey_level_beste'),
              ('stark', 'ui.okey_level_stark'),
              ('schnell', 'ui.okey_level_schnell'),
              ('sofort', 'ui.okey_level_sofort'))


def _zeit(sekunden):
    """Zeitangabe fuer Laien: Millisekunden, wenn es sonst 0,0 hiesse."""
    if sekunden >= 1.0:
        return '%.1f s' % sekunden
    if sekunden >= 0.01:
        return '%.0f ms' % (sekunden * 1000)
    return '< 10 ms'


class OkeyViewMixin:
    def _build_okey_view(self, _parent):
        view = self._new_view('okey')
        self._view_header(view, t('ui.view_okey'), t('ui.okey_sub'))

        card = Section(view, t('ui.group_okey'))
        card.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        body = card.body
        body.grid_columnconfigure(0, weight=1)

        self._okey_btn = ctk.CTkButton(
            body, text=t('ui.okey_start_btn'), height=44, corner_radius=12,
            font=ctk.CTkFont(size=15, weight='bold'),
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            command=self._on_okey_start_stop)
        self._okey_btn.grid(row=0, column=0, sticky='ew', pady=(0, 2))
        InfoBadge(body, text=t('ui.okey_help')).grid(row=0, column=1,
                                                     sticky='ne', padx=(6, 0))

        opts = ctk.CTkFrame(body, fg_color='transparent')
        opts.grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))

        cfg = self.controller.current_config().get('okey', {})

        ctk.CTkLabel(opts, text=t('ui.okey_decks_label'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0,
                                                     padx=(0, 8), sticky='w')
        self._okey_decks_var = ctk.StringVar(value=str(cfg.get('decks', 1)))
        ctk.CTkEntry(opts, textvariable=self._okey_decks_var, width=60,
                     justify='center').grid(row=0, column=1, sticky='w')
        ctk.CTkLabel(opts, text=t('ui.okey_decks_note'), text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=2,
                                                     padx=(10, 0), sticky='w')

        ctk.CTkLabel(opts, text=t('ui.okey_solver_label'),
                     text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=12)).grid(row=1, column=0,
                                                     padx=(0, 8), pady=(6, 0),
                                                     sticky='w')
        gewaehlt = dict(LEVEL_KEYS).get(cfg.get('solver', 'beste'),
                                        'ui.okey_level_beste')
        self._okey_level_var = ctk.StringVar(value=t(gewaehlt))
        ctk.CTkOptionMenu(opts, variable=self._okey_level_var, width=160,
                          values=[t(k) for _v, k in LEVEL_KEYS],
                          command=lambda _v: self._okey_save()).grid(
            row=1, column=1, pady=(6, 0), sticky='w')
        ctk.CTkLabel(opts, text=t('ui.okey_solver_note'),
                     text_color=TEXT_FAINT, font=ctk.CTkFont(size=11),
                     wraplength=300, justify='left').grid(
            row=1, column=2, padx=(10, 0), pady=(6, 0), sticky='w')

        self._okey_status = ctk.CTkLabel(
            body, text=t('ui.okey_idle'), anchor='w', text_color=TEXT_FAINT,
            font=ctk.CTkFont(size=11), wraplength=440)
        self._okey_status.grid(row=2, column=0, columnspan=2, sticky='w',
                               pady=(8, 0))

        self._okey_stats = ctk.CTkLabel(
            body, text='', anchor='w', text_color=TEAL_BRIGHT,
            font=ctk.CTkFont(size=12, weight='bold'), wraplength=440)
        self._okey_stats.grid(row=3, column=0, columnspan=2, sticky='w',
                              pady=(2, 0))

        self._build_okey_table(view)

        try:
            if getattr(self, '_okey_running', False):
                self._okey_btn.configure(text=t('ui.okey_stop_btn'),
                                         fg_color=PANEL_LIGHT, text_color=TEXT)
            elif self.controller.running:
                self._okey_btn.configure(state='disabled')
        except Exception:
            pass

    # -- Die Stufen-Tabelle --------------------------------------------------

    def _build_okey_table(self, view):
        """Was die vier Stufen kosten und bringen -- als echte Tabelle."""
        from okey import stufen          # reine Daten, kein schwerer Import

        card = Section(view, t('ui.okey_table_title'))
        card.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        grid = card.body
        for spalte, gewicht in enumerate((0, 0, 0, 0, 0, 1)):
            grid.grid_columnconfigure(spalte, weight=gewicht)

        kopf = (t('ui.okey_col_level'), t('ui.okey_col_time'),
                t('ui.okey_col_game'), t('ui.okey_col_points'),
                t('ui.okey_col_gold'), t('ui.okey_col_how'))
        for spalte, text in enumerate(kopf):
            ctk.CTkLabel(grid, text=text, text_color=TEXT_MUTED, anchor='w',
                         font=ctk.CTkFont(size=11, weight='bold')).grid(
                row=0, column=spalte, sticky='w', padx=(0, 12), pady=(0, 4))

        namen = dict(LEVEL_KEYS)
        for zeile, daten in enumerate(stufen.tabelle(), start=1):
            schluessel = daten['stufe']
            werte = (t(namen[schluessel]),
                     _zeit(daten['s_je_zug']),
                     _zeit(daten['s_je_partie']),
                     '%.0f' % daten['punkte'],
                     '%.1f %%' % (100 * daten['gold']),
                     t('ui.okey_how_%s' % schluessel))
            for spalte, text in enumerate(werte):
                ctk.CTkLabel(
                    grid, text=text, anchor='w', justify='left',
                    text_color=TEAL_BRIGHT if zeile == 1 else TEXT,
                    wraplength=240 if spalte == 5 else 0,
                    font=ctk.CTkFont(size=11)).grid(
                    row=zeile, column=spalte, sticky='w', padx=(0, 12),
                    pady=1)

        ctk.CTkLabel(grid, text=t('ui.okey_table_note'), text_color=TEXT_FAINT,
                     font=ctk.CTkFont(size=10), wraplength=470,
                     justify='left', anchor='w').grid(
            row=len(LEVEL_KEYS) + 1, column=0, columnspan=6, sticky='w',
            pady=(6, 0))

    # -- Auswahl + Speichern -------------------------------------------------

    def _okey_level(self):
        label = self._okey_level_var.get()
        for wert, key in LEVEL_KEYS:
            if t(key) == label:
                return wert
        return 'beste'

    def _okey_decks(self):
        try:
            return max(0, min(999, int(self._okey_decks_var.get().strip()
                                       or '0')))
        except Exception:
            return 1

    def _okey_save(self):
        """Auswahl in die Konfiguration schreiben (ueberlebt den Neustart).

        ``update_config`` nimmt (Bereich, Schluessel, Wert) -- EIN Wert je
        Aufruf, kein Dict. Ein Dict wanderte hier zuerst hinein; der Aufruf
        waere im try/except still gescheitert und die Einstellung nach jedem
        Neustart wieder auf Anfang gestanden, ohne dass irgendetwas auffaellt.
        """
        try:
            self.controller.update_config('okey', 'decks', self._okey_decks())
            self.controller.update_config('okey', 'solver', self._okey_level())
        except Exception:
            pass

    # -- Start/Stop ----------------------------------------------------------

    def _on_okey_start_stop(self):
        if getattr(self, '_okey_running', False):
            self._okey_abort = True
            try:
                self._okey_btn.configure(state='disabled',
                                         text=t('ui.okey_stopping'))
            except Exception:
                pass
            return

        if self.controller.running:
            log.event('-', t('okey.blocked_running'))
            return
        present, _hwnd, _gw, _gh, _healthy = _probe_game()
        if not present:
            log.event('-', t('ui.start_aborted_no_window'))
            try:
                self._okey_status.configure(
                    text=t('ui.status_start_no_window'))
            except Exception:
                pass
            return

        self._okey_save()
        decks, level = self._okey_decks(), self._okey_level()
        self._okey_running = True
        self._okey_abort = False
        try:
            self._apply_preferred_hwnd()
        except Exception:
            pass
        cfg = self.controller.current_config()
        try:
            self._okey_btn.configure(text=t('ui.okey_stop_btn'),
                                     fg_color=PANEL_LIGHT, text_color=TEXT)
            self._okey_status.configure(text=t('ui.okey_running'))
        except Exception:
            pass

        def _on_game(ses, spiel):
            self.after(0, lambda: self._okey_progress(ses, spiel))

        def _worker():
            try:
                from interface import okey_runner
                ses = okey_runner.run_okey_session(
                    cfg, decks=decks, staerke=level, on_game_done=_on_game,
                    abort_fn=lambda: getattr(self, '_okey_abort', False))
                self.after(0, lambda s=ses: self._on_okey_done(s))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_okey_failed(e))

        threading.Thread(target=_worker, name='okey-session',
                         daemon=True).start()

    # -- Rueckmeldungen ------------------------------------------------------

    def _okey_progress(self, ses, spiel):
        try:
            # Leere Truhe = die Runde wurde nicht ausgezahlt (Abbruch oder
            # Fehler). Ohne diesen Fall stuende hier ein roher Schluesselname.
            truhe = spiel.truhe or 'none'
            self._okey_status.configure(text=t(
                'ui.okey_progress', n=ses.gespielt, points=spiel.punkte,
                chest=t('ui.okey_chest_%s' % truhe), status=spiel.status))
            self._okey_stats.configure(text=self._okey_stats_text(ses))
        except Exception:
            pass

    def _okey_stats_text(self, ses):
        n = max(1, ses.gespielt)
        return t('ui.okey_stats_line', n=ses.gespielt,
                 points=ses.punkte_gesamt, avg='%.0f' % (ses.punkte_gesamt / n),
                 gold=ses.truhen.get('gold', 0),
                 silver=ses.truhen.get('silber', 0),
                 bronze=ses.truhen.get('bronze', 0))

    def _okey_reset_button(self):
        self._okey_running = False
        self._okey_abort = False
        try:
            self._okey_btn.configure(state='normal',
                                     text=t('ui.okey_start_btn'),
                                     fg_color=TEAL, text_color=INK)
        except Exception:
            pass

    def _on_okey_done(self, ses):
        self._okey_reset_button()
        if ses.grund == 'fehler':
            text = t('ui.okey_status_error', step=ses.fehler_schritt)
        elif ses.grund == 'abbruch':
            text = t('ui.okey_status_aborted', n=ses.gespielt,
                     points=ses.punkte_gesamt)
        else:
            text = t('ui.okey_status_done', n=ses.gespielt,
                     points=ses.punkte_gesamt, reason=ses.grund)
        try:
            self._okey_status.configure(text=text)
            self._okey_stats.configure(text=self._okey_stats_text(ses))
        except Exception:
            pass

    def _on_okey_failed(self, exc):
        self._okey_reset_button()
        try:
            self._okey_status.configure(text=t('ui.status_start_failed'))
        except Exception:
            pass
        log.error(t('okey.worker_crashed'), exc=exc)
