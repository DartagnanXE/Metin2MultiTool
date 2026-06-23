# -*- coding: utf-8 -*-
"""Tests fuer window_mark -- die Klick-zum-Erfassen-Logik (win32 injiziert).

Headless-testbar gemacht durch Injektion von ``user32``/``win32gui``-Fakes und
einem reinen Stepper (``ClickCapture.step``), den die GUI spaeter aus einer
``after()``-Schleife mit echten ``GetCursorPos``/``GetAsyncKeyState``-Werten
fuettert. Das echte Anklicken am Spielfenster bleibt LIVE-only.
"""

import window_mark as wm


class _FakeUser32:
    """WindowFromPoint(child) -> root via Mapping; GetAncestor liefert root."""
    def __init__(self, child_at_point, child_to_root):
        self._child_at_point = child_at_point  # dict (x,y)->child_hwnd
        self._child_to_root = child_to_root    # dict child->root
        self.calls = []

    def WindowFromPoint(self, pt):
        self.calls.append(('WindowFromPoint', (pt.x, pt.y)))
        return self._child_at_point.get((pt.x, pt.y), 0)

    def GetAncestor(self, hwnd, flag):
        self.calls.append(('GetAncestor', hwnd, flag))
        return self._child_to_root.get(hwnd, hwnd)


def _point(x, y):
    class _P:
        pass
    p = _P()
    p.x, p.y = x, y
    return p


class TestWindowFromPoint:
    def test_resolves_child_to_toplevel_root(self):
        u = _FakeUser32(child_at_point={(100, 200): 555},
                        child_to_root={555: 999})
        hwnd = wm.window_from_point((100, 200), user32=u, point_factory=_point)
        assert hwnd == 999

    def test_no_window_returns_none(self):
        u = _FakeUser32(child_at_point={}, child_to_root={})
        assert wm.window_from_point((0, 0), user32=u, point_factory=_point) is None


class _FakeWin32Gui:
    def __init__(self):
        self.flashed = []

    def FlashWindow(self, hwnd, b):
        self.flashed.append(hwnd)
        return True


class TestFlashWindow:
    def test_flashes_given_hwnd(self):
        g = _FakeWin32Gui()
        wm.flash_window(123, win32gui=g, count=2)
        assert g.flashed == [123, 123]

    def test_defensive_on_none(self):
        g = _FakeWin32Gui()
        wm.flash_window(None, win32gui=g)  # darf nicht werfen
        assert g.flashed == []


class TestClickCapture:
    def _make(self, point_to_root, valid):
        # resolve_fn(cursor_pos)->root hwnd|None ; valid_fn()->set
        return wm.ClickCapture(
            resolve_fn=lambda pos: point_to_root.get(pos),
            valid_hwnds_fn=lambda: set(valid))

    def test_starts_idle(self):
        cap = self._make({}, [])
        assert cap.state == wm.ClickCapture.IDLE

    def test_arm_sets_armed(self):
        cap = self._make({}, [1])
        cap.arm()
        assert cap.state == wm.ClickCapture.ARMED

    def test_idle_step_is_noop(self):
        cap = self._make({(5, 5): 1}, [1])
        # nicht armiert -> Klick ignoriert
        cap.step(left_down=True, cursor_pos=(5, 5))
        assert cap.state == wm.ClickCapture.IDLE

    def test_arming_click_does_not_self_trigger(self):
        # Der Knopf-Klick (Taste noch gedrueckt beim arm) darf NICHT erfassen.
        cap = self._make({(5, 5): 1}, [1])
        cap.arm()
        cap.step(left_down=True, cursor_pos=(5, 5))   # noch der Knopf-Klick
        assert cap.state == wm.ClickCapture.ARMED
        assert cap.captured_hwnd is None

    def test_rising_edge_on_game_window_captures(self):
        cap = self._make({(50, 60): 999}, [999])
        cap.arm()
        cap.step(left_down=False, cursor_pos=(0, 0))   # sauberes Loslassen
        cap.step(left_down=True, cursor_pos=(50, 60))  # echter Klick aufs Spiel
        assert cap.state == wm.ClickCapture.CAPTURED
        assert cap.captured_hwnd == 999

    def test_click_on_non_game_window_stays_armed(self):
        cap = self._make({(50, 60): 12}, [999])  # 12 ist KEIN Spielfenster
        cap.arm()
        cap.step(left_down=False, cursor_pos=(0, 0))
        cap.step(left_down=True, cursor_pos=(50, 60))
        assert cap.state == wm.ClickCapture.ARMED
        assert cap.captured_hwnd is None

    def test_then_correct_click_captures(self):
        cap = self._make({(1, 1): 12, (2, 2): 999}, [999])
        cap.arm()
        cap.step(left_down=False, cursor_pos=(0, 0))
        cap.step(left_down=True, cursor_pos=(1, 1))    # Fehlklick -> bleibt armed
        assert cap.state == wm.ClickCapture.ARMED
        cap.step(left_down=False, cursor_pos=(1, 1))   # loslassen
        cap.step(left_down=True, cursor_pos=(2, 2))    # richtiger Klick
        assert cap.state == wm.ClickCapture.CAPTURED
        assert cap.captured_hwnd == 999

    def test_cancel(self):
        cap = self._make({}, [1])
        cap.arm()
        cap.cancel()
        assert cap.state == wm.ClickCapture.CANCELLED
