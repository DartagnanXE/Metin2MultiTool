"""Live-Log-Panel: zeigt ``debuglog``-Events in Echtzeit im UI (Console-Ansicht).

Das frueher separate Debug-Tool lebt jetzt in derselben App (Umschalter
``Bot | Console``). Die Datei-Log-Senke (``puzzle_debug.log``) bleibt unberuehrt
-- dieses Panel registriert sich ZUSAETZLICH als UI-Senke via ``log.add_sink``.

Toolbar: **Copy** (Inhalt in die Zwischenablage), **Open log file** (oeffnet
``puzzle_debug.log``), **Clear** (leert nur die Anzeige, nicht die Datei).

Thread-Sicherheit: ``debuglog`` kann aus einem Worker-/Bot-Thread emittieren,
Tk-Widgets duerfen nur aus dem GUI-Thread angefasst werden. Die Senke schiebt
jede Zeile in eine ``queue.Queue``; das Fenster leert sie periodisch via
``after()`` (``pump``) ins Textfeld.
"""

import os
import queue

import customtkinter as ctk

from debuglog import log
from i18n import t
from interface.widgets import (LIVE_GREEN, PANEL, PANEL_HOVER, PANEL_LIGHT,
                               TEAL, TEXT, TEXT_MUTED)


# Obergrenze fuer im Textfeld gehaltene Zeilen (gegen unbegrenztes Wachstum).
MAX_LINES = 500
# Pro Pump-Durchlauf maximal so viele Zeilen ziehen (haelt das UI responsiv).
DRAIN_BATCH = 200
# Pfad der Datei-Log-Senke (siehe hack.py: log.configure(path=...)).
LOG_FILE = 'puzzle_debug.log'


class LogPanel(ctk.CTkFrame):
    """Karten-Panel mit Live-Indikator, Toolbar und scrollendem Log-Textfeld."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=PANEL, corner_radius=12, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._queue = queue.Queue()
        self._attached = False
        self._line_count = 0

        # -- Kopfzeile: Titel + Live-Indikator + Toolbar --
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)

        title_wrap = ctk.CTkFrame(header, fg_color='transparent')
        title_wrap.grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(
            title_wrap, text=t('console.live_log'), anchor='w',
            font=ctk.CTkFont(size=14, weight='bold'),
            text_color=TEAL).grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(title_wrap, text='  ●', text_color=LIVE_GREEN,
                     font=ctk.CTkFont(size=13)).grid(row=0, column=1)
        ctk.CTkLabel(title_wrap, text=t('console.live'), text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=12)).grid(row=0, column=2,
                                                     padx=(2, 0))

        toolbar = ctk.CTkFrame(header, fg_color='transparent')
        toolbar.grid(row=0, column=1, sticky='e')
        self._toolbtn(toolbar, t('console.copy'), self.copy_to_clipboard).grid(
            row=0, column=0, padx=3)
        self._toolbtn(toolbar, t('console.open_file'), self.open_log_file).grid(
            row=0, column=1, padx=3)
        self._toolbtn(toolbar, t('console.clear'), self.clear).grid(
            row=0, column=2, padx=3)

        self._textbox = ctk.CTkTextbox(
            self, fg_color=PANEL_LIGHT, text_color=TEXT, wrap='none',
            font=ctk.CTkFont(family='Consolas', size=11), corner_radius=8)
        self._textbox.grid(row=1, column=0, sticky='nsew', padx=10,
                           pady=(0, 12))
        self._textbox.configure(state='disabled')

    @staticmethod
    def _toolbtn(master, text, command):
        return ctk.CTkButton(
            master, text=text, width=78, height=26, corner_radius=7,
            fg_color=PANEL_LIGHT, hover_color=PANEL_HOVER, text_color=TEXT,
            font=ctk.CTkFont(size=12), command=command)

    # -- Senken-Anbindung -------------------------------------------------

    def attach(self):
        if not self._attached:
            log.add_sink(self._enqueue)
            self._attached = True

    def detach(self):
        if self._attached:
            log.remove_sink(self._enqueue)
            self._attached = False

    def _enqueue(self, line):
        """Senken-Callback (evtl. Worker-Thread) -> nur Queue fuellen."""
        try:
            self._queue.put_nowait(line)
        except Exception:
            pass

    # -- Periodisches Leeren der Queue (nur GUI-Thread) -------------------

    def pump(self):
        """Zieht angesammelte Zeilen aus der Queue ins Textfeld. Wirft nie."""
        lines = []
        try:
            for _ in range(DRAIN_BATCH):
                lines.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            return

        if not lines:
            return

        try:
            self._textbox.configure(state='normal')
            self._textbox.insert('end', '\n'.join(lines) + '\n')
            self._line_count += len(lines)
            self._trim()
            self._textbox.see('end')
            self._textbox.configure(state='disabled')
        except Exception:
            pass

    def _trim(self):
        if self._line_count <= MAX_LINES:
            return
        try:
            remove = self._line_count - MAX_LINES
            self._textbox.delete('1.0', '{}.0'.format(remove + 1))
            self._line_count = MAX_LINES
        except Exception:
            pass

    # -- Toolbar-Aktionen -------------------------------------------------

    def copy_to_clipboard(self):
        """Kopiert den sichtbaren Log-Inhalt in die Zwischenablage."""
        try:
            text = self._textbox.get('1.0', 'end').strip()
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def open_log_file(self):
        """Oeffnet ``puzzle_debug.log`` mit dem Standardprogramm (Windows)."""
        try:
            path = os.path.abspath(LOG_FILE)
            if os.path.exists(path):
                os.startfile(path)            # nur Windows; sonst -> except
        except Exception:
            pass

    def clear(self):
        """Leert das sichtbare Log (Datei-Log bleibt unberuehrt)."""
        try:
            self._textbox.configure(state='normal')
            self._textbox.delete('1.0', 'end')
            self._textbox.configure(state='disabled')
            self._line_count = 0
        except Exception:
            pass
