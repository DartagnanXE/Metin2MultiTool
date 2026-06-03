# -*- coding: utf-8 -*-
"""LifecycleMixin -- extracted from interface/app (behaviour-preserving).

Mixin for :class:`interface.app.App`. Holds only methods (no
``__init__``, no class-level mutable state) so MRO is unaffected and every
``self`` reference resolves exactly as in the original module.
"""

from interface.app._common import *  # noqa: F401,F403


class LifecycleMixin:
    def _flush_stats(self):
        """Run the registered final-stats-save hook (if any). Never raises.

        Called on every exit path so accrued runtime/counters reach stats.json
        even when no catch/solve triggered the debounced save before exit."""
        try:
            hook = getattr(self, '_stats_save_hook', None)
            if callable(hook):
                hook()
        except Exception:
            pass

    def _on_close(self):
        self._flush_stats()
        try:
            cfgmod.save(self.controller.current_config())
        except Exception:
            pass
        try:
            if self._tray_icon is not None:
                self._tray_icon.stop()
        except Exception:
            pass
        try:
            self.log_panel.detach()
        except Exception:
            pass
        self.destroy()

    # -- UI-Synchronisierung ---------------------------------------------

    def _maybe_onboard(self):
        """Zeigt beim ersten Start den Onboarding-Dialog (Name + Transparenz-Hinweis).

        Nur wenn noch kein Name gewaehlt UND das Onboarding noch nie entschieden
        wurde. Streng defensiv -- ein Fehler hier darf den Start nie kippen."""
        try:
            from interface import onboarding
            if onboarding.needs_onboarding(self.controller.current_config()):
                onboarding.open_onboarding(self, on_done=self._on_onboarded)
        except Exception:
            pass

    def _on_onboarded(self, result):
        """Nach dem Onboarding: Widgets/Tab aktualisieren + ggf. Sender starten."""
        try:
            self._cfg = self.controller.current_config()
            # Sender-Zustand neu bewerten (Name koennte jetzt gesetzt sein) +
            # Ranking-Tab aktualisieren.
            self._start_telemetry()
            from interface import ranking_view
            ranking_view.refresh_leaderboard(self)
        except Exception:
            pass

    def _ensure_install_id(self):
        """Mintet + persistiert die zufaellige ``install_id`` EINMALIG, auf dem
        GUI-Thread, beim Start -- BEVOR der Telemetrie-Worker-Thread laeuft.

        Wurzelfix gegen "zwei FishLover"/Re-Onboarding: Frueher wurde die ID erst
        LAZY im ``_telemetry_state`` auf dem WORKER-Thread erzeugt und ihr Save
        ueber ``self.app.after()`` -- vom Nicht-GUI-Thread -- geplant (unzuver-
        laessig). Damit haftete die Identitaet nur am sauberen ``_on_close``. Hier
        liegt sie ab dem ersten Start synchron auf der Platte (``persist_now``)
        und der Worker liest sie nur noch. Idempotent (vorhandene ID bleibt).
        Streng defensiv -- ein Fehler darf den Start nie kippen."""
        try:
            from telemetry import hwid
            current = getattr(self, '_install_id', None)
            if not current:
                current = str(self.controller.current_config().get(
                    'telemetry', {}).get('install_id', '') or '')
            if not current:
                current = hwid.new_install_id()
                self.controller.update_config('telemetry', 'install_id', current)
                # Sofort auf Platte -> ueberlebt auch einen harten Exit gleich
                # nach dem ersten Start (sonst neue ID beim naechsten Start).
                self.controller.persist_now()
            self._install_id = current
        except Exception:
            pass

    def _telemetry_state(self):
        """Thread-sicherer Snapshot fuer den Telemetrie-Sender.

        Liefert genau die Felder, die telemetry.client.start_sender erwartet
        (enabled/username/submit_url/interval_s + fertiges payload). Liest NUR
        unveraenderliche Kopien (current_config + app._stats) -> sicher aus dem
        Daemon-Thread aufrufbar.

        Anonymes Modell: die Identitaet ist die ZUFAELLIGE install_id (einmalig
        erzeugt + in der Config persistiert); sie wird als (Draht-)``hwid`` ins
        Payload gereicht. ``enabled`` haengt NICHT mehr an einem Nutzer-Opt-out
        -- nur daran, dass install_id + submit_url existieren UND nicht blockiert
        wurde. Wirft nie."""
        try:
            cfg = self.controller.current_config()
            telemetry = cfg.get('telemetry', {})
            username = str(cfg.get('username', '') or '')
            from telemetry import hwid, payload
            from version import __version__
            import datetime as _dt
            stats = getattr(self, '_stats', None)
            install_id = getattr(self, '_install_id', None)
            if not install_id:
                install_id = str(telemetry.get('install_id', '') or '')
                if not install_id:
                    # Einmalig erzeugen + persistieren (immutabel, auto-saved).
                    install_id = hwid.ensure_install_id(
                        lambda: self.controller.current_config().get(
                            'telemetry', {}).get('install_id', ''),
                        lambda v: self.controller.update_config(
                            'telemetry', 'install_id', v))
                self._install_id = install_id
            built = payload.build_submit(
                username, install_id, stats, __version__, _dt.datetime.now())
            submit_url = str(telemetry.get('submit_url', '') or '')
            return {
                'enabled': bool(install_id) and bool(submit_url)
                           and not self._ranking_banned,
                'username': username,
                'hwid': install_id,
                'submit_url': submit_url,
                'interval_s': telemetry.get('interval_s', 120),
                'payload': built,
            }
        except Exception:
            return {'enabled': False, 'username': '', 'hwid': '',
                    'submit_url': '', 'interval_s': 120, 'payload': {}}

    def _start_telemetry(self):
        """Startet (oder ersetzt) den Telemetrie-Daemon-Sender. Gated durch den
        Snapshot -- laeuft leer, solange keine install_id/URL existiert oder die
        Installation blockiert ist. Streng defensiv; wirft nie.

        Tests / Dev-Tools duerfen NIE an den Live-Server senden: die Opt-out-Env
        ``M2FB_NO_TELEMETRY`` (gesetzt von tests/conftest.py + dem GUI-Smoke-
        Harness) verhindert, dass der Sender ueberhaupt startet. Produktion setzt
        sie nie."""
        import os
        if os.environ.get('M2FB_NO_TELEMETRY'):
            self._telemetry_thread = None
            return
        try:
            interval = int(self._cfg.get('telemetry', {}).get('interval_s', 120))
        except Exception:
            interval = 120
        try:
            from telemetry import client
            self._telemetry_thread = client.start_sender(
                self._telemetry_state, on_status=self._on_telemetry_status,
                interval=interval)
        except Exception:
            self._telemetry_thread = None

    def _on_telemetry_status(self, status):
        """Sender-Status-Callback (laeuft auf dem WORKER-Thread -> via after(0,
        ...) ins UI marshallen). 'banned' -> Ranking-Tab versteckt das Board +
        zeigt den Bann-Hinweis. Wirft nie."""
        try:
            if status == 'banned':
                self.after(0, self._handle_banned)
            elif status == 'started':
                self.after(0, lambda: log.event('-', t(
                    'telemetry.sender_started',
                    interval=self._cfg.get('telemetry', {}).get(
                        'interval_s', 120))))
            elif status == 'stopped':
                self.after(0, lambda: log.event('-',
                                                t('telemetry.sender_stopped')))
        except Exception:
            pass

    def _handle_banned(self):
        """GUI-Thread: Bann verarbeiten -- Flag setzen, Ranking-Tab umschalten."""
        try:
            self._ranking_banned = True
            log.event('-', t('telemetry.sender_banned'))
            from interface import ranking_view
            ranking_view.refresh_leaderboard(self)
        except Exception:
            pass

    # -- Status-/Detection-Note (unten rechts) ---------------------------
