# -*- coding: utf-8 -*-
"""UpdateBannerMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403

# Periodische Update-Pruefung: alle 30 Minuten erneut gegen GitHub pruefen und
# den Status aktualisieren, falls eine neue Version erscheint (nicht nur beim
# Start). 30 min = 1_800_000 ms.
UPDATE_RECHECK_MS = 30 * 60 * 1000


class UpdateBannerMixin:
    def _kick_off_update_check(self):
        """Startet die Hintergrund-Versionspruefung beim Start UND plant die
        wiederkehrende 30-Minuten-Pruefung. Wirft NIE; ohne Netz oder bei
        Fehlern passiert einfach nichts (kein Banner)."""
        self._start_one_update_check()
        try:
            self.after(UPDATE_RECHECK_MS, self._periodic_update_check)
        except Exception:
            pass

    def _start_one_update_check(self):
        """Eine einzelne Hintergrundpruefung anstossen. ``updater`` LAZY
        importiert, damit headless-Tests nie das Netz-/Updater-Modul brauchen."""
        try:
            import updater
            from version import __version__
            updater.start_background_check(self._on_update_available,
                                           __version__)
        except Exception:
            pass

    def _periodic_update_check(self):
        """Wiederkehrende 30-Minuten-Pruefung: erneut pruefen + sich selbst neu
        planen. Findet sie eine neue Version, aktualisiert ``_on_update_available``
        den Status (Banner/Versionsanzeige). Wirft nie."""
        self._start_one_update_check()
        try:
            self.after(UPDATE_RECHECK_MS, self._periodic_update_check)
        except Exception:
            pass

    def _on_update_available(self, info):
        """Callback aus dem WORKER-Thread -> SOFORT auf den GUI-Thread bouncen
        (Tk ist nicht thread-sicher; Widget-Aufbau muss im GUI-Thread laufen)."""
        try:
            self.after(0, lambda: self._show_update_banner(info))
        except Exception:
            pass

    def _show_update_banner(self, info):
        """Zeigt das dezente, schliessbare Update-Banner (GUI-Thread).

        Idempotent ueber die 30-Minuten-Wiederholpruefungen: die Versionsanzeige
        unten links spiegelt IMMER die neueste gefundene Version, das Banner
        ploppt aber nur EINMAL pro Version auf (kein 30-Min-Generve) und NIE fuer
        eine vom Nutzer weggeklickte Version (eine NEUERE ploppt wieder)."""
        try:
            tag = getattr(info, 'tag', None)
            self._update_info = info
            self._highlight_version_update(info)   # Status immer aktualisieren
            if tag == getattr(self, '_update_surfaced_tag', None):
                return                              # diese Version schon gezeigt
            if tag == getattr(self, '_update_dismissed_tag', None):
                return                              # weggeklickt -> nicht neu nerven
            self._update_surfaced_tag = tag
            if self._update_banner is None:
                self._build_update_banner()
            self._refresh_update_banner_text()
            self._update_btn.configure(state='normal', text=t('ui.update_now'))
            self._update_banner.grid()           # sichtbar machen
            try:
                log.event('-', t('ui.update_found_log', version=tag or ''))
            except Exception:
                pass
        except Exception:
            pass

    def _build_update_banner(self):
        """Baut das Banner als EIGENE Grid-Zeile (row 1) -- nicht in der Shell
        (``content``), damit ein Sprachwechsel-Neuaufbau es nicht zerstoert."""
        bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bar.grid(row=1, column=0, sticky='ew')
        bar.grid_columnconfigure(0, weight=1)
        self._update_label = ctk.CTkLabel(
            bar, text='', anchor='w', text_color=TEXT,
            font=ctk.CTkFont(size=12, weight='bold'))
        self._update_label.grid(row=0, column=0, sticky='w', padx=(14, 8),
                                pady=8)
        self._update_btn = ctk.CTkButton(
            bar, text=t('ui.update_now'), height=28, width=150,
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=INK,
            corner_radius=8, command=self._on_update_click)
        self._update_btn.grid(row=0, column=1, sticky='e', padx=4, pady=8)
        self._update_dismiss = ctk.CTkButton(
            bar, text='✕', width=28, height=28, fg_color='transparent',
            hover_color=PANEL_HOVER, text_color=TEXT_MUTED,
            command=self._on_update_dismiss)
        self._update_dismiss.grid(row=0, column=2, sticky='e', padx=(0, 10),
                                  pady=8)
        self._update_banner = bar

    def _refresh_update_banner_text(self):
        info = getattr(self, '_update_info', None)
        version = getattr(info, 'tag', '') if info else ''
        try:
            self._update_label.configure(
                text=t('ui.update_available', version=version))
        except Exception:
            pass

    def _on_update_dismiss(self):
        """Blendet das Banner aus (nur ausblenden, Info bleibt) -- die Abweisung
        haelt die Sitzung. Merkt sich die weggeklickte Version, damit die
        30-Minuten-Wiederholpruefung dieselbe Version nicht erneut aufpoppt
        (eine NEUERE Version poppt sehr wohl wieder)."""
        try:
            self._update_dismissed_tag = getattr(
                getattr(self, '_update_info', None), 'tag', None)
            if self._update_banner is not None:
                self._update_banner.grid_remove()
        except Exception:
            pass

    def _on_update_click(self):
        """Verzweigt: onefile -> Download + Selbstersetzung; sonst (onedir/
        Quellcode) -> Releases-Seite oeffnen (onedir-Stub NICHT ueberschreiben)."""
        import updater
        info = getattr(self, '_update_info', None)
        if info is None:
            return
        if not updater.can_self_replace():
            updater.open_releases_page(
                getattr(info, 'page_url', updater.RELEASES_PAGE))
            self._set_update_banner_msg(t('ui.update_open_page'))
            log.event('-', t('ui.update_manual_required'))
            return
        if getattr(info, 'download_url', None) is None:
            # Onefile, aber kein Portable-Asset im Release -> nur Seite oeffnen.
            updater.open_releases_page(
                getattr(info, 'page_url', updater.RELEASES_PAGE))
            self._set_update_banner_msg(t('ui.update_no_asset'))
            return
        self._start_update_download(info)

    def _start_update_download(self, info):
        """Laedt das Portable-Asset in einem EIGENEN Daemon-Thread (die GUI darf
        waehrend des MB-Downloads nie einfrieren); Fortschritt/Ende werden via
        ``after`` zurueck auf den GUI-Thread gespiegelt."""
        import updater
        try:
            self._update_btn.configure(state='disabled')
        except Exception:
            pass
        self._set_update_banner_msg(t('ui.update_downloading', pct=0))

        def _progress(done, total):
            if total:
                text = t('ui.update_downloading',
                         pct=int(done * 100 / total))
            else:
                text = t('ui.update_downloading_unknown')
            try:
                self.after(0, lambda: self._set_update_banner_msg(text))
            except Exception:
                pass

        def _worker():
            try:
                path = updater.download_asset(info, progress=_progress)
                self.after(0, lambda: self._finish_update(path))
            except Exception as exc:
                # exc am Lambda-Erzeugungszeitpunkt binden (e=exc): Python 3 loescht
                # ``exc`` am Ende des except-Blocks; das via after(0,...) verzoegerte
                # Lambda liefe sonst erst im naechsten Tick und wuerfe NameError ->
                # _update_failed liefe nie, der Update-Knopf bliebe deaktiviert.
                self.after(0, lambda e=exc: self._update_failed(e))

        threading.Thread(target=_worker, name='update-download',
                         daemon=True).start()

    def _finish_update(self, downloaded_path):
        """Schreibt+startet den Selbstersetzungs-.bat und beendet die App hart,
        damit die .exe entsperrt ist und ueberschrieben + neu gestartet werden
        kann."""
        import updater
        try:
            self._set_update_banner_msg(t('ui.update_installing'))
            updater.apply_update_onefile(downloaded_path)
            log.section(t('ui.update_restarting'))
            try:
                cfgmod.save(self.controller.current_config())
            except Exception:
                pass
            try:
                self.log_panel.detach()
            except Exception:
                pass
            self.after(200, self._hard_exit_for_update)
        except Exception as exc:
            self._update_failed(exc)

    def _hard_exit_for_update(self):
        """Garantiert raus: ``os._exit`` haelt keine Tk-/Thread-/after-Reste,
        sodass die .exe-Sperre faellt und der .bat sie kopieren kann.

        Vor dem harten Exit die Statistik final sichern (os._exit umgeht sonst
        jeden Cleanup -> sonst ginge die seit dem letzten Fang/Loesen akkumulierte
        Laufzeit beim Auto-Update verloren)."""
        self._flush_stats()
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _update_failed(self, exc):
        log.error(t('ui.update_failed_log'), exc=exc)
        self._set_update_banner_msg(t('ui.update_failed'))
        try:
            self._update_btn.configure(state='normal')
        except Exception:
            pass

    def _set_update_banner_msg(self, text):
        try:
            self._update_label.configure(text=text)
        except Exception:
            pass

    # -- Inventar-Scan (Hintergrund-Thread, UI nie blockieren) -----------

    def _highlight_version_update(self, info):
        """Laesst die Versionsanzeige unten links dezent teal aufleuchten, sobald
        eine neuere Version vorliegt (Klick -> Update, via _on_version_click)."""
        try:
            tag = getattr(info, 'tag', '') or 'update'
            self._version_label.configure(
                text='▲ ' + self._version_base + ' → ' + tag,
                text_color=TEAL)
        except Exception:
            pass
