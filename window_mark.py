# -*- coding: utf-8 -*-
"""Klick-zum-Erfassen: ein Fenster eindeutig markieren, auch bei >4 offenen.

Die *ausgefeilte Technik* fuer die Multiclient-Einstellung: statt aus einer
Liste von ``hwnd@x,y`` zu raten, zeigt der Nutzer **physisch** auf das echte
Spielfenster. Wir loesen das Top-Level-Fenster unter dem Cursor auf
(``WindowFromPoint`` -> ``GetAncestor(GA_ROOT)``), pruefen ob es ein METIN2-
Fenster ist und bestaetigen per kurzem ``FlashWindow``.

Reiner ``user32``-Lesezugriff (WindowFromPoint/GetAncestor/GetCursorPos/
GetAsyncKeyState/FlashWindow) -- KEIN Prozess-Speicher, anti-cheat-neutral
(gleiche Doktrin wie :func:`windowcapture.focus_window`).

Testbarkeit: alle win32-Aufrufe sind injizierbar; :class:`ClickCapture` ist ein
reiner Stepper, den die GUI aus einer ``after()``-Schleife fuettert. Das echte
Anklicken bleibt LIVE-only.
"""

import ctypes

GA_ROOT = 2          # GetAncestor: oberstes Eltern-(Top-Level-)Fenster
VK_LBUTTON = 0x01    # linke Maustaste


# -- win32-Primitive (alle injizierbar) --------------------------------------

class _CPoint(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


def _real_user32():  # pragma: no cover - nur auf Windows
    return ctypes.windll.user32


def window_from_point(pt, *, user32=None, point_factory=None):
    """Top-Level-HWND unter Bildschirmpunkt ``pt=(x,y)`` (oder ``None``).

    Loest erst das Fenster unter dem Punkt auf und steigt dann via
    ``GetAncestor(GA_ROOT)`` zum Top-Level-Fenster hoch (ein Klick trifft sonst
    ein Kind-Control). Strikt defensiv -- wirft nie."""
    try:
        u = user32 or _real_user32()
        pf = point_factory or (lambda x, y: _CPoint(x, y))
        raw = u.WindowFromPoint(pf(int(pt[0]), int(pt[1])))
        if not raw:
            return None
        root = u.GetAncestor(raw, GA_ROOT)
        result = int(root or raw)
        return result or None
    except Exception:
        return None


def flash_window(hwnd, *, win32gui=None, count=3):
    """Fenster ``hwnd`` kurz blinken lassen (visuelle Bestaetigung).

    Defensiv: ``hwnd is None``/Fehler -> stiller no-op."""
    if not hwnd:
        return
    try:
        g = win32gui
        if g is None:  # pragma: no cover - nur auf Windows
            import win32gui as g
        for _ in range(max(1, int(count))):
            g.FlashWindow(hwnd, True)
    except Exception:
        pass


def cursor_pos(user32=None):  # pragma: no cover - LIVE-only (echter Cursor)
    """Aktuelle Cursor-Position ``(x, y)`` (oder ``None``)."""
    try:
        u = user32 or _real_user32()
        p = _CPoint()
        if u.GetCursorPos(ctypes.byref(p)):
            return (p.x, p.y)
    except Exception:
        pass
    return None


def left_button_down(user32=None):  # pragma: no cover - LIVE-only (echte Taste)
    """``True``, wenn die linke Maustaste gerade gedrueckt ist."""
    try:
        u = user32 or _real_user32()
        return bool(u.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False


# -- Klick-Erfassungs-Stepper (rein, testbar) --------------------------------

class ClickCapture:
    """Zustandsmaschine fuer „Knopf druecken -> Spielfenster anklicken".

    Die GUI ruft :meth:`arm`, dann periodisch (``after``) :meth:`step` mit dem
    aktuellen Tastenzustand + Cursor. Beim ersten *sauberen* Klick (Knopf-Klick
    muss erst losgelassen sein) auf ein gueltiges Spielfenster -> ``CAPTURED``.
    Klicks auf Fremdfenster/eigene UI werden ignoriert (bleibt ``ARMED``).

    Parameter
    ---------
    resolve_fn : callable(cursor_pos) -> hwnd|None
        Loest das Top-Level-Fenster unter dem Cursor (i.d.R. partial von
        :func:`window_from_point`).
    valid_hwnds_fn : callable() -> set[int]
        Aktuell gueltige METIN2-Fenster-HWNDs (z.B. aus
        ``enumerate_game_windows``).
    """

    IDLE = 'idle'
    ARMED = 'armed'
    CAPTURED = 'captured'
    CANCELLED = 'cancelled'

    def __init__(self, resolve_fn, valid_hwnds_fn):
        self._resolve = resolve_fn
        self._valid = valid_hwnds_fn
        self.state = self.IDLE
        self.captured_hwnd = None
        self._clean = False  # Knopf-Klick erst losgelassen?

    def arm(self):
        """Erfassung scharf schalten. Wartet auf sauberes Loslassen."""
        self.state = self.ARMED
        self.captured_hwnd = None
        self._clean = False

    def cancel(self):
        self.state = self.CANCELLED

    def step(self, left_down, cursor_pos):
        """Einen Poll-Schritt verarbeiten; liefert den neuen ``state``."""
        if self.state != self.ARMED:
            return self.state
        if not left_down:
            self._clean = True          # Knopf-Klick losgelassen -> bereit
            return self.state
        if not self._clean:
            return self.state           # noch der haltende Knopf-Klick
        # Steigende Flanke nach sauberem Loslassen = echter Ziel-Klick.
        hwnd = self._resolve(cursor_pos)
        if hwnd is not None and hwnd in self._valid():
            self.captured_hwnd = hwnd
            self.state = self.CAPTURED
        else:
            # Fehlklick (Fremdfenster/eigene UI): ignorieren, neue Flanke abwarten.
            self._clean = False
        return self.state
