"""Zentrales Debug-/Diagnose-Logging fuer den Puzzle-Teil des Bots.

Bewusst NUR Python-Standardbibliothek (kein numpy/cv2/...), damit dieses Modul
ueberall importierbar und per ``unittest`` testbar bleibt und auch aus der
gepackten ``.exe`` heraus funktioniert.

Grundregel: Logging darf den Bot NIEMALS zum Absturz bringen. Jede oeffentliche
Methode kapselt ihre Arbeit in try/except und schluckt eigene Fehler still
(ein kaputter Logger darf nie den Angel-/Puzzle-Betrieb stoppen).

Benutzung ueberall::

    from debuglog import log
    log.event(state, 'Stein geholt', piece=4)
"""

import time
import traceback


class DebugLog:
    """Schreibt parallel auf Konsole und in eine Logdatei.

    Konfiguration ueber :meth:`configure`. Vor dem ersten ``configure`` gelten
    sichere Defaults (Konsole an, Datei aus), damit ein frueher Aufruf nie
    ins Leere laeuft.
    """

    _LEVELS = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40}

    def __init__(self):
        self._to_console = True
        self._to_file = False
        self._path = 'puzzle_debug.log'
        self._threshold = self._LEVELS['DEBUG']
        # Zusaetzliche UI-Senken (z.B. Live-Log-Panel). Jede Senke ist ein
        # Callable ``fn(line: str)``. Die Datei-/Konsolen-Senken bleiben davon
        # unberuehrt -- UI-Senken kommen REIN ADDITIV hinzu.
        self._sinks = []

    # -- Konfiguration ----------------------------------------------------

    def configure(self, to_console=True, to_file=True,
                  path='puzzle_debug.log', level='DEBUG'):
        """Stellt Senken und Mindest-Level ein. Wirft nie."""
        try:
            self._to_console = bool(to_console)
            self._to_file = bool(to_file)
            self._path = str(path) if path else 'puzzle_debug.log'
            self._threshold = self._LEVELS.get(str(level).upper(),
                                                self._LEVELS['DEBUG'])
            # Datei einmalig anlegen/leeren, damit jeder Lauf frisch startet.
            if self._to_file:
                with open(self._path, 'w', encoding='utf-8') as handle:
                    handle.write(self._stamp() + ' | INIT  | Logdatei gestartet\n')
        except Exception:
            # Konfiguration darf nie crashen -> auf sichere Defaults zurueck.
            self._to_console = True
            self._to_file = False

    # -- interne Helfer ---------------------------------------------------

    @staticmethod
    def _stamp():
        # time.strftime ist robust und vermeidet datetime-Now-Stolperfallen.
        return time.strftime('%Y-%m-%d %H:%M:%S')

    def _emit(self, line):
        """Schreibt eine fertige Zeile auf alle aktiven Senken. Wirft nie."""
        try:
            if self._to_console:
                print(line)
        except Exception:
            pass
        try:
            if self._to_file:
                with open(self._path, 'a', encoding='utf-8') as handle:
                    handle.write(line + '\n')
        except Exception:
            pass
        # UI-Senken zuletzt bedienen. Eine einzelne kaputte Senke darf weder die
        # anderen Senken noch den Bot stoppen -> jede Senke isoliert kapseln.
        # Snapshot-Kopie (list(...)): schuetzt vor Mutations-Race, falls eine
        # Senke waehrend des Emits add_sink/remove_sink aufruft (Thread-Variante).
        for sink in list(self._sinks):
            try:
                sink(line)
            except Exception:
                pass

    def _log(self, level_name, msg):
        try:
            if self._LEVELS.get(level_name, 0) < self._threshold:
                return
            self._emit('{} | {:5s} | {}'.format(
                self._stamp(), level_name, msg))
        except Exception:
            pass

    # -- einfache Level-Methoden -----------------------------------------

    def debug(self, msg):
        self._log('DEBUG', msg)

    def info(self, msg):
        self._log('INFO', msg)

    def warning(self, msg):
        self._log('WARNING', msg)

    def error(self, msg, exc=None):
        """Fehlerzeile; bei ``exc`` wird der vollstaendige Traceback angehaengt."""
        try:
            self._log('ERROR', msg)
            if exc is not None:
                tb = ''.join(traceback.format_exception(
                    type(exc), exc, exc.__traceback__))
                for tb_line in tb.rstrip().splitlines():
                    self._emit('{} | ERROR | {}'.format(self._stamp(), tb_line))
        except Exception:
            pass

    # -- strukturierte Zustandszeile -------------------------------------

    def event(self, state, message, **fields):
        """Strukturierte Zeile: ``zeit | STATE n | message | key=val ...``"""
        try:
            parts = ['{} | STATE {} | {}'.format(self._stamp(), state, message)]
            if fields:
                kv = ' '.join('{}={}'.format(k, fields[k])
                              for k in sorted(fields))
                parts.append(kv)
            self._emit(' | '.join(parts))
        except Exception:
            pass

    # -- mehrzeiliger Detail-Dump ----------------------------------------

    def snapshot(self, name, board=None, piece_type=None, bgr=None,
                 screen_xy=None, extra=None):
        """Mehrzeiliger Detail-Dump fuer die Debug-Konsole.

        Stellt das Board als huebsche Matrix dar und listet die uebrigen
        Diagnosewerte (Stein-Typ, gemessene BGR, Bildschirmkoordinate, extra).
        """
        try:
            lines = ['{} | SNAP  | === {} ==='.format(self._stamp(), name)]
            if piece_type is not None:
                lines.append('              piece_type = {}'.format(piece_type))
            if bgr is not None:
                lines.append('              bgr        = {}'.format(
                    self._fmt_bgr(bgr)))
            if screen_xy is not None:
                lines.append('              screen_xy  = {}'.format(
                    tuple(screen_xy)))
            if extra is not None:
                lines.append('              extra      = {}'.format(extra))
            if board is not None:
                lines.append('              board:')
                for row in self._board_rows(board):
                    lines.append('                ' + row)
            for line in lines:
                self._emit(line)
        except Exception:
            pass

    @staticmethod
    def _fmt_bgr(bgr):
        try:
            return '({}, {}, {})'.format(int(bgr[0]), int(bgr[1]), int(bgr[2]))
        except Exception:
            return str(bgr)

    @staticmethod
    def _board_rows(board):
        """Wandelt ein 2D-Board (Listen oder numpy) in huebsche Textzeilen.

        Defensiv: funktioniert mit verschachtelten Python-Listen genauso wie
        mit numpy-Arrays, ohne numpy zu importieren.
        """
        rows = []
        try:
            for row in board:
                cells = []
                for cell in row:
                    try:
                        cells.append(str(int(cell)))
                    except Exception:
                        cells.append(str(cell))
                rows.append(' '.join(cells))
        except Exception:
            rows.append(str(board))
        return rows

    # -- optische Trennung ------------------------------------------------

    def section(self, title):
        """Optische Trennlinie in Konsole und Datei."""
        try:
            bar = '=' * 60
            self._emit(bar)
            self._emit('=== {} '.format(title).ljust(60, '='))
            self._emit(bar)
        except Exception:
            pass

    # -- zusaetzliche UI-Senken (additiv) --------------------------------

    def add_sink(self, fn):
        """Registriert ein Callable ``fn(line: str)`` als zusaetzliche Senke.

        Jede emittierte Zeile wird (nach Konsole/Datei) auch an ``fn`` gereicht.
        Thread-/absturzsicher: Fehler in ``fn`` werden in :meth:`_emit`
        geschluckt -- eine kaputte UI-Senke stoppt nie den Bot. Doppelte
        Registrierungen werden ignoriert. Wirft nie.
        """
        try:
            if callable(fn) and fn not in self._sinks:
                self._sinks.append(fn)
        except Exception:
            pass

    def remove_sink(self, fn):
        """Entfernt eine zuvor registrierte Senke. Wirft nie."""
        try:
            if fn in self._sinks:
                self._sinks.remove(fn)
        except Exception:
            pass


# Singleton: ueberall via ``from debuglog import log`` importierbar.
log = DebugLog()


# -- modulweite Bequemlichkeits-Shims (absturzsicher) ----------------------
#
# Mehrere Module brauchten denselben "logge defensiv, wirf nie"-Wrapper und
# hatten ihn jeweils lokal kopiert. Hier EINMAL bereitgestellt -> ein einziger
# Aenderungspunkt, kein Drift. Die ``log``-Methoden schlucken zwar bereits ihre
# eigenen Fehler; das zusaetzliche try/except deckt zudem den (theoretischen)
# Fall ab, dass ``log`` selbst ersetzt/kaputt ist. Beide Helfer WERFEN NIE.

def log_event(state, message, **fields):
    """Strukturierte Event-Zeile (``log.event``), absturzsicher. Wirft nie."""
    try:
        log.event(state, message, **fields)
    except Exception:
        pass


def log_error(message, exc=None):
    """Fehlerzeile (``log.error``), absturzsicher. Wirft nie."""
    try:
        log.error(message, exc=exc)
    except Exception:
        pass
