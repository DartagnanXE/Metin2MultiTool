"""Regressions-Test gegen ein fehlendes ``energiesplitter/__init__.py``.

Der echte Defekt: ohne Paket-Init fing ``interface/app/__init__.py`` den
``ImportError`` STILL ab -> die View baute nie, der Bot war nie verdrahtet, und
nichts wurde rot. Dieser Test importiert AUSSCHLIESSLICH ueber das PAKET
(``from energiesplitter import ...``) -- nicht ueber das Submodul ``.bot`` --,
sodass ein fehlendes ``__init__.py`` (oder ein kaputter Export) sofort rot wird.

Stub-Muster wie ``tests/test_puzzle_hardening.py``: die Windows-only Treiber
werden VOR dem Import gestubbt, damit der Import headless gegen den ECHTEN Code
laeuft (cv2/numpy bleiben echt; bot.py importiert sie ohnehin weich).
"""

import os
import sys
import types
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _install_stubs():
    pdi = types.ModuleType('pydirectinput')
    pdi.PAUSE = 0
    for fn in ('click', 'moveTo', 'press', 'keyDown', 'keyUp',
               'mouseDown', 'mouseUp'):
        setattr(pdi, fn, lambda *a, **k: None)
    sys.modules['pydirectinput'] = pdi
    for name in ('win32gui', 'win32ui', 'win32con', 'win32api'):
        sys.modules.setdefault(name, types.ModuleType(name))


_install_stubs()


class TestPackageImport(unittest.TestCase):
    def test_import_bot_via_package(self):
        # PAKET-Import (nicht .bot) -- faellt rot ohne __init__.py.
        from energiesplitter import EnergiesplitterBot
        bot = EnergiesplitterBot()
        self.assertEqual(bot.state, EnergiesplitterBot.ST_INIT)

    def test_import_mode_constants_via_package(self):
        from energiesplitter import MODE_HAMMER, MODE_DAGGER
        self.assertEqual(MODE_HAMMER, 'hammer')
        self.assertEqual(MODE_DAGGER, 'dagger')

    def test_package_all_exports(self):
        import energiesplitter as es
        for name in ('EnergiesplitterBot', 'MODE_HAMMER', 'MODE_DAGGER'):
            self.assertIn(name, es.__all__)
            self.assertTrue(hasattr(es, name))


if __name__ == '__main__':
    unittest.main()
