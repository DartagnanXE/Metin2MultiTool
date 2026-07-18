# -*- coding: utf-8 -*-
"""Millisekunden-genauer Klick-Tracker fuer den Angelbot (Debug/Diagnose).

ZWECK: Der Nutzer soll einen "Char laeuft ins Wasser"-Vorfall reproduzierbar
MELDEN koennen. Dazu wird JEDER physische Maus-Klick millisekunden-genau + mit
vollem Kontext in die bestehende Debug-Logdatei (``debuglog``) geschrieben.
Er umschliesst die zwei physischen Klickpfade:

  * ``fishingbot._DirectBackend.click``   (Single-Client)
  * ``cursor_client.CursorClient.click``  (Multiclient, Lease-Burst)

Grundmechanik im Spiel: ein LINKS-Klick in die 3D-Welt laesst den Char DORTHIN
laufen; ein Rechtsklick bewegt nur die Kamera. Darum ist jeder LINKS-Klick der
Verdaechtige; passt er nicht zum sauber gegateten Minispiel-Muster, wird er als
``STRAY-CLICK`` prominent (eigene WARN-Zeile) markiert -- das ist der meldbare
Vorfall.

WICHTIG -- REINES LOGGING: dieses Modul veraendert KEINEN Klick, unterdrueckt
nichts und verschiebt nichts. Das Bot-Verhalten bleibt byte-identisch (ein Fix
folgt separat).

Nur Python-Standardbibliothek (+ das ebenfalls stdlib-only ``debuglog``), damit
das Modul ueberall (headless/CI/exe) importierbar und unit-testbar bleibt. Wie
``debuglog`` gilt: der Tracker darf den Bot NIEMALS zum Absturz bringen -> jede
oeffentliche Methode kapselt ihre Arbeit in try/except und schluckt eigene Fehler.
"""

import os
import time

try:
    from debuglog import log as _debuglog
except Exception:  # pragma: no cover - debuglog ist stdlib-only, sollte laden
    _debuglog = None


# -- Tuning-Defaults --------------------------------------------------------
# GetWindowRect hoechstens alle N ms wirklich abfragen (Drossel fuer den heissen
# Angel-Loop); dazwischen wird das letzte Ergebnis wiederverwendet.
DEFAULT_STALE_INTERVAL_MS = 500.0
# Delta-t (Screenshot-Tick -> Klick-Dispatch) groesser als das => Timing-Miss-
# Risiko beim Minispielklick (der physische Zeiger trifft evtl. schon die Welt).
DEFAULT_STRAY_DT_MS = 120.0
# Optische Hervorhebung der meldbaren Verdachtszeile.
_STRAY_MARKER = '!!! STRAY-CLICK !!!'
# Pfad-Labels, die ein sauber gegatetes UI-Ziel treffen (kein Weltpunkt-Verdacht
# per se): Daily-Reward-Dialog, dessen Bestaetigung, Refill-UI.
_GATED_UI_TAGS = ('daily', 'confirm', 'refill')


class ClickTracker:
    """Sammelt Ambient-Kontext pro Angel-Tick und protokolliert jeden Klick.

    Der Bot ruft pro Tick :meth:`mark_tick` (Zustand/Offset/Referenzzeit) und
    optional :meth:`set_gate` (detected_end); die Backends rufen :meth:`record`
    fuer JEDEN physischen Klick. ``record`` schreibt eine ms-genaue Zeile und
    entscheidet, ob es ein STRAY-Verdacht ist. Absturzsicher: wirft nie.
    """

    def __init__(self):
        self._enabled = self._env_default_enabled()
        self._stale_interval_ms = DEFAULT_STALE_INTERVAL_MS
        self._stray_dt_ms = self._env_float('M2FB_CLICK_TRACKER_DT_MS',
                                             DEFAULT_STRAY_DT_MS)
        self._get_rect = None      # callable()->(left,top,right,bottom) live
        self._cropped = (0, 0)     # (cropped_x, cropped_y) = (BORDER, TITLEBAR)
        # Ambient-Kontext pro Tick (vom Bot gesetzt):
        self._state = None
        self._offset = None        # gespeicherter (evtl. stale) (offset_x, offset_y)
        self._detected_end = None
        self._tick_perf_ms = None  # perf_counter*1000 zum Screenshot-Zeitpunkt
        # Drossel-Cache fuer den OFFSET_STALE-Check:
        self._last_rect_check_ms = None
        self._last_stale = None    # (is_stale, dx, dy) der letzten Messung

    # -- Env-Defaults -----------------------------------------------------
    @staticmethod
    def _env_default_enabled():
        # Default AN -- der Nutzer WILL ausfuehrliches Tracking. Nur ein
        # explizites Ausschalten via Env deaktiviert.
        val = os.environ.get('M2FB_CLICK_TRACKER', '').strip().lower()
        return val not in ('0', 'off', 'false', 'no')

    @staticmethod
    def _env_float(name, default):
        try:
            raw = os.environ.get(name)
            return float(raw) if raw not in (None, '') else float(default)
        except Exception:
            return float(default)

    # -- Konfiguration / Kontext (vom Bot) --------------------------------
    def configure(self, get_rect=None, cropped=None, enabled=None,
                  stale_interval_ms=None, stray_dt_ms=None):
        """Einmalige Verdrahtung: Live-Fensterrect-Quelle + Rahmen-Masse + Tuning.
        Wirft nie."""
        try:
            if get_rect is not None:
                self._get_rect = get_rect
            if cropped is not None:
                self._cropped = (int(cropped[0]), int(cropped[1]))
            if enabled is not None:
                self._enabled = bool(enabled)
            if stale_interval_ms is not None:
                self._stale_interval_ms = float(stale_interval_ms)
            if stray_dt_ms is not None:
                self._stray_dt_ms = float(stray_dt_ms)
        except Exception:
            pass

    def set_enabled(self, value):
        """Schalter (Default AN). Wirft nie."""
        try:
            self._enabled = bool(value)
        except Exception:
            pass

    def mark_tick(self, state=None, offset_x=None, offset_y=None,
                  detected_end=None):
        """Pro Angel-Tick aufrufen (direkt nach dem Screenshot). Stempelt die
        monotone Tick-Referenzzeit (Basis fuer Delta-t Screenshot->Klick) und den
        aktuellen Zustand/Offset. Billig -- wirft nie."""
        try:
            self._state = state
            if offset_x is not None and offset_y is not None:
                self._offset = (int(offset_x), int(offset_y))
            self._detected_end = detected_end
            self._tick_perf_ms = time.perf_counter() * 1000.0
        except Exception:
            pass

    def set_gate(self, detected_end):
        """detected_end feiner nachziehen (nach ``detect_minigame``). Wirft nie."""
        try:
            self._detected_end = detected_end
        except Exception:
            pass

    # -- Kern: einen physischen Klick protokollieren ----------------------
    def record(self, button, screen_x, screen_y, tag='other'):
        """Schreibt eine ms-genaue Klick-Zeile. REINES Logging, wirft nie.

        :param button: 'left' | 'right' (o.ae.).
        :param screen_x/screen_y: Ziel-BILDSCHIRM-Koordinate des Klicks.
        :param tag: Pfad-Label des Aufrufers
                    ('minigame'|'daily'|'confirm'|'focus'|'refill'|'other').
        """
        if not self._enabled:
            return
        try:
            now_ms = time.perf_counter() * 1000.0
            wall = self._wall_ms()
            button = 'left' if button is None else str(button)
            tag = str(tag or 'other')
            sx, sy = int(screen_x), int(screen_y)
            # Client-Koordinate = Screen - gespeicherter Offset (falls bekannt).
            client = None
            if self._offset is not None:
                client = (sx - self._offset[0], sy - self._offset[1])
            # Delta-t Screenshot-Tick -> Klick-Dispatch (monoton).
            dt_ms = (None if self._tick_perf_ms is None
                     else now_ms - self._tick_perf_ms)
            # OFFSET_STALE nur fuer LINKS-Klicks + gedrosselt (GetWindowRect).
            stale, dx, dy = self._check_offset_stale(button, now_ms)
            is_stray, reason = self._classify_stray(button, tag, dt_ms, stale)
            self._emit(now_ms, wall, button, tag, sx, sy, client, dt_ms,
                       stale, dx, dy, is_stray, reason)
        except Exception:
            pass

    # -- OFFSET_STALE: gespeicherter Offset vs. live Fensterposition ------
    def _check_offset_stale(self, button, now_ms):
        """Vergleicht den gespeicherten Offset mit der aus ``GetWindowRect`` live
        abgeleiteten Position. Delta != 0 => Fenster verschoben => Offset stale
        (deckt den ``resync_offsets``-nie-aufgerufen-Bug ab).

        PERFORMANCE: Rechtsklick (Kamera, bewegt den Char nie) ueberspringt den
        Check -> kein GetWindowRect. Ausserdem gedrosselt: hoechstens alle
        ``stale_interval_ms`` wird wirklich gemessen, sonst das letzte Ergebnis
        wiederverwendet -> der heisse Angel-Loop wird nicht ausgebremst.
        """
        if button != 'left' or self._get_rect is None or self._offset is None:
            return (False, 0, 0)
        if (self._last_rect_check_ms is not None
                and self._last_stale is not None
                and (now_ms - self._last_rect_check_ms) < self._stale_interval_ms):
            return self._last_stale
        try:
            rect = self._get_rect()
            live_off_x = int(rect[0]) + self._cropped[0]
            live_off_y = int(rect[1]) + self._cropped[1]
            dx = live_off_x - self._offset[0]
            dy = live_off_y - self._offset[1]
            result = (dx != 0 or dy != 0, dx, dy)
        except Exception:
            # GetWindowRect fehlgeschlagen (HWND zerstoert/Stub) -> nicht als
            # stale werten, aber niemals crashen.
            result = (False, 0, 0)
        self._last_rect_check_ms = now_ms
        self._last_stale = result
        return result

    # -- STRAY-Klassifikation --------------------------------------------
    def _classify_stray(self, button, tag, dt_ms, stale):
        """Entscheidet, ob dieser LINKS-Klick ein meldbarer Verdacht ist.

        Rueckgabe ``(is_stray, grund_oder_None)``.
        """
        # Rechtsklick = Kamera, bewegt den Char nie -> nie verdaechtig.
        if button != 'left':
            return (False, None)
        # Verschobenes Fenster/stale Offset -> Klick landet versetzt (Bug #4/#5).
        if stale:
            return (True, 'Fenster verschoben (OFFSET_STALE) -> Klick versetzt')
        if tag == 'minigame':
            # Der EINE sanktionierte Weltklick: sauber gegatet + zeitnah.
            if self._state != 3 or not self._detected_end:
                return (True, 'Minispielklick ohne sauberes Gate '
                              '(state=%r detected_end=%r)'
                              % (self._state, self._detected_end))
            if dt_ms is not None and dt_ms > self._stray_dt_ms:
                return (True, 'Minispielklick spaet zugestellt '
                              '(dt=%.0fms > %.0fms) -> Timing-Miss-Risiko'
                              % (dt_ms, self._stray_dt_ms))
            return (False, None)
        if tag in _GATED_UI_TAGS:
            # daily/confirm/refill: eigenes Detektions-Gate -> nicht per se stray.
            return (False, None)
        # Jeder andere LINKS-Klick (tag='other'/unbekannt) ist ein ungetaggter,
        # unerwarteter Pfad -> meldepflichtiger Verdachtsfall.
        return (True, 'ungetaggter Linksklick (unerwarteter Pfad, tag=%r)' % tag)

    # -- Ausgabe ----------------------------------------------------------
    def _emit(self, now_ms, wall, button, tag, sx, sy, client, dt_ms,
              stale, dx, dy, is_stray, reason):
        if _debuglog is None:
            return
        btn = {'left': 'LINKS', 'right': 'RECHTS'}.get(button, button.upper())
        client_str = ('%d,%d' % client) if client is not None else '?'
        dt_str = ('%.0f' % dt_ms) if dt_ms is not None else '?'
        state = self._state if self._state is not None else '-'
        stale_str = (' OFFSET_STALE=dx%d,dy%d' % (dx, dy)) if stale else ''
        try:
            if is_stray:
                # Prominente eigene WARN-Zeile -- hebt sich klar ab, greppbar.
                _debuglog.warning(
                    '%s | STATE %s | btn=%s tag=%s screen=%d,%d client=%s '
                    'dt_ms=%s t_ms=%.1f detected_end=%s%s | GRUND: %s | wall=%s'
                    % (_STRAY_MARKER, state, btn, tag, sx, sy, client_str,
                       dt_str, now_ms, self._detected_end, stale_str,
                       reason, wall))
            else:
                # Normale Klick-Zeile (immer, auch unter erhoehtem Level: event()
                # umgeht die Schwelle) -- gut lesbar/kopierbar.
                fields = {
                    'btn': btn,
                    'tag': tag,
                    'screen': '%d,%d' % (sx, sy),
                    'client': client_str,
                    'dt_ms': dt_str,
                    't_ms': '%.1f' % now_ms,
                    'detected_end': self._detected_end,
                    'wall': wall,
                }
                if stale_str:
                    fields['OFFSET_STALE'] = 'dx%d,dy%d' % (dx, dy)
                _debuglog.event(state, 'KLICK', **fields)
        except Exception:
            pass

    @staticmethod
    def _wall_ms():
        """Wanduhr-Zeitstempel mit Millisekunden: ``HH:MM:SS.mmm``."""
        now = time.time()
        ms = int((now - int(now)) * 1000)
        return time.strftime('%H:%M:%S', time.localtime(now)) + '.%03d' % ms


# -- Modul-Singleton + absturzsichere Shims (wie debuglog.log) --------------
tracker = ClickTracker()


def configure(**kwargs):
    """Modul-Shim fuer :meth:`ClickTracker.configure`. Wirft nie."""
    try:
        tracker.configure(**kwargs)
    except Exception:
        pass


def mark_tick(state=None, offset_x=None, offset_y=None, detected_end=None):
    """Modul-Shim fuer :meth:`ClickTracker.mark_tick`. Wirft nie."""
    try:
        tracker.mark_tick(state=state, offset_x=offset_x, offset_y=offset_y,
                          detected_end=detected_end)
    except Exception:
        pass


def set_gate(detected_end):
    """Modul-Shim fuer :meth:`ClickTracker.set_gate`. Wirft nie."""
    try:
        tracker.set_gate(detected_end)
    except Exception:
        pass


def record_click(button, screen_x, screen_y, tag='other'):
    """Modul-Shim fuer :meth:`ClickTracker.record`. Wirft nie."""
    try:
        tracker.record(button, screen_x, screen_y, tag=tag)
    except Exception:
        pass


def set_enabled(value):
    """Modul-Shim fuer :meth:`ClickTracker.set_enabled`. Wirft nie."""
    try:
        tracker.set_enabled(value)
    except Exception:
        pass
