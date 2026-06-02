# -*- coding: utf-8 -*-
"""Pure, stdlib-only tests for ``windowcapture.select_target_hwnd`` (CS4).

This is the "make the selection logic testable" requirement: the function that
decides WHICH window handle the bot operates is a pure function over an injected
window list + mode + chosen hwnd (no win32, no Tk), so it can be exhaustively
unit-tested headless. ``windowcapture`` imports ``win32gui`` at module top; on
the project's py.exe that is present. If it is somehow unavailable the module
skips (the pure helper itself needs no win32, but the import does).
"""

import unittest

try:
    import windowcapture as wc
    _IMPORT_OK = True
    _IMPORT_ERR = ''
except Exception as exc:  # pragma: no cover - depends on environment
    _IMPORT_OK = False
    _IMPORT_ERR = repr(exc)


@unittest.skipUnless(_IMPORT_OK,
                     'windowcapture not importable: ' + _IMPORT_ERR)
class TestSelectTargetHwnd(unittest.TestCase):
    def _windows(self, *hwnds):
        # Mirror enumerate_game_windows() entries (only 'hwnd' matters here).
        return [{'hwnd': h, 'w': 800, 'h': 600, 'x': 0, 'y': 0} for h in hwnds]

    def test_last_focused_returns_none(self):
        # Default mode -> None signals the legacy FindWindow / last-focused path,
        # regardless of the chosen hwnd or window list.
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), 'last_focused', 22))
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), 'last_focused', None))
        self.assertIsNone(
            wc.select_target_hwnd([], 'last_focused', 99))

    def test_specific_with_valid_chosen_returns_chosen(self):
        # 'specific' + the chosen hwnd still present -> push exactly that handle.
        self.assertEqual(
            wc.select_target_hwnd(self._windows(11, 22, 33), 'specific', 22), 22)

    def test_specific_with_chosen_gone_falls_back_none(self):
        # 'specific' but the chosen window vanished from the list -> safe None
        # fallback (never push a dead handle).
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 33), 'specific', 22))

    def test_specific_with_empty_list_is_none(self):
        self.assertIsNone(wc.select_target_hwnd([], 'specific', 22))
        self.assertIsNone(wc.select_target_hwnd(None, 'specific', 22))

    def test_specific_with_chosen_none_is_none(self):
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), 'specific', None))

    def test_unknown_mode_treated_as_last_focused(self):
        # Defensive: an unexpected mode value must not push a handle.
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), 'whatever', 22))

    def test_mode_constants_exist(self):
        self.assertEqual(wc.MODE_LAST_FOCUSED, 'last_focused')
        self.assertEqual(wc.MODE_SPECIFIC, 'specific')

    def test_specific_picks_chosen_among_malformed_entries(self):
        # The window list may carry dicts lacking 'hwnd' (defensive enumerate);
        # the chosen handle is still found when a well-formed entry holds it.
        windows = [{'w': 800}, {'no_hwnd': 1}, {'hwnd': 22}]
        self.assertEqual(wc.select_target_hwnd(windows, 'specific', 22), 22)

    def test_specific_chosen_absent_from_malformed_list_is_none(self):
        # None of the (malformed) entries expose the chosen handle -> safe None.
        windows = [{'w': 800}, {'no_hwnd': 1}]
        self.assertIsNone(wc.select_target_hwnd(windows, 'specific', 22))

    def test_specific_with_chosen_zero_is_none(self):
        # 0 is a falsy / invalid handle -> never pushed (legacy path).
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), 'specific', 0))

    def test_last_focused_ignores_malformed_list(self):
        # Default mode short-circuits to None before ever inspecting the list,
        # so even a wholly malformed list cannot make it raise or push a handle.
        self.assertIsNone(
            wc.select_target_hwnd([{'bad': 1}, 'garbage'], 'last_focused', 22))

    def test_empty_string_mode_treated_as_last_focused(self):
        self.assertIsNone(
            wc.select_target_hwnd(self._windows(11, 22), '', 22))


if __name__ == '__main__':
    unittest.main()
