# -*- coding: utf-8 -*-
"""The global bot-stop hotkey: key->VK mapping + its config slot.

The poll itself (GetAsyncKeyState in the tick) is a live win32 call; here we lock
the pure pieces -- the key-string -> virtual-key-code mapping and that
``controls.stop_hotkey`` defaults to F6 and validates like any hotkey.
"""

import unittest

import run_loop
from interface import config


class TestKeyToVk(unittest.TestCase):
    def test_function_keys(self):
        self.assertEqual(run_loop._key_to_vk('f6'), 117)     # VK_F6
        self.assertEqual(run_loop._key_to_vk('F1'), 112)     # VK_F1, case-insensitive
        self.assertEqual(run_loop._key_to_vk('f12'), 123)    # VK_F12

    def test_letters_and_digits(self):
        self.assertEqual(run_loop._key_to_vk('q'), ord('Q'))
        self.assertEqual(run_loop._key_to_vk('5'), ord('5'))

    def test_invalid_keys_are_none(self):
        for bad in ('', None, 'f0', 'f13', 'space', 'ctrl', 'abc', '!'):
            self.assertIsNone(run_loop._key_to_vk(bad))


class TestStopHotkeyConfig(unittest.TestCase):
    def test_default_is_f6(self):
        cfg = config.validate(config.DEFAULTS)
        self.assertEqual(cfg['controls']['stop_hotkey'], 'f6')

    def test_valid_key_kept_lowercased(self):
        cfg = config.validate({'controls': {'stop_hotkey': 'F8'}})
        self.assertEqual(cfg['controls']['stop_hotkey'], 'f8')

    def test_garbage_resets_to_default(self):
        cfg = config.validate({'controls': {'stop_hotkey': ''}})
        self.assertEqual(cfg['controls']['stop_hotkey'], 'f6')


if __name__ == '__main__':
    unittest.main()
