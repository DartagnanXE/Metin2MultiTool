"""Tests fuer updater.py -- nur die NETZ-/PROZESS-FREIEN Pfade.

parse_release / check_for_update werden mit eingespeisten Daten getestet (kein
echter HTTP-Call); die Build-Modus-Erkennung per Monkeypatch von sys.frozen /
sys._MEIPASS; die .bat-Erzeugung als reiner String (kein Prozess startet).

Reine stdlib, headless -- updater importiert nur stdlib + version.
"""

import sys
import unittest

import updater


def _sample_release(tag='v1.0.4', with_asset=True):
    assets = []
    if with_asset:
        assets = [
            {'name': 'some-other-file.zip',
             'browser_download_url': 'https://example/other.zip', 'size': 10},
            {'name': updater.PORTABLE_ASSET_NAME,
             'browser_download_url':
                 'https://example/Metin2FishBot-Portable.exe',
             'size': 12_345_678},
        ]
    return {
        'tag_name': tag,
        'html_url': 'https://github.com/DartagnanXE/Metin2FishBot/releases/'
                    'tag/' + tag,
        'assets': assets,
    }


class TestParseRelease(unittest.TestCase):
    def test_picks_portable_asset(self):
        info = updater.parse_release(_sample_release())
        self.assertIsNotNone(info)
        self.assertEqual(info.tag, 'v1.0.4')
        self.assertEqual(info.version, '1.0.4')   # leading v stripped
        self.assertEqual(info.download_url,
                         'https://example/Metin2FishBot-Portable.exe')
        self.assertEqual(info.size, 12_345_678)
        self.assertIn('releases', info.page_url)

    def test_no_portable_asset_yields_none_url(self):
        info = updater.parse_release(_sample_release(with_asset=False))
        self.assertIsNotNone(info)
        self.assertIsNone(info.download_url)
        self.assertIsNone(info.size)

    def test_garbage_is_safe(self):
        self.assertIsNone(updater.parse_release(None))
        self.assertIsNone(updater.parse_release({}))
        self.assertIsNone(updater.parse_release({'tag_name': ''}))
        self.assertIsNone(updater.parse_release('not a dict'))


class TestCheckForUpdate(unittest.TestCase):
    def setUp(self):
        self._orig_fetch = updater.fetch_latest_release

    def tearDown(self):
        updater.fetch_latest_release = self._orig_fetch

    def test_newer_returns_info(self):
        updater.fetch_latest_release = lambda timeout=0: _sample_release(
            'v1.0.4')
        info = updater.check_for_update(current='1.0.3')
        self.assertIsNotNone(info)
        self.assertEqual(info.tag, 'v1.0.4')

    def test_same_returns_none(self):
        updater.fetch_latest_release = lambda timeout=0: _sample_release(
            'v1.0.3')
        self.assertIsNone(updater.check_for_update(current='1.0.3'))

    def test_older_returns_none(self):
        updater.fetch_latest_release = lambda timeout=0: _sample_release(
            'v1.0.2')
        self.assertIsNone(updater.check_for_update(current='1.0.3'))

    def test_fetch_failure_returns_none(self):
        updater.fetch_latest_release = lambda timeout=0: None
        self.assertIsNone(updater.check_for_update(current='1.0.3'))


class TestModeDetection(unittest.TestCase):
    def setUp(self):
        self._had_frozen = hasattr(sys, 'frozen')
        self._frozen = getattr(sys, 'frozen', None)
        self._had_meipass = hasattr(sys, '_MEIPASS')
        self._meipass = getattr(sys, '_MEIPASS', None)

    def tearDown(self):
        if self._had_frozen:
            sys.frozen = self._frozen
        elif hasattr(sys, 'frozen'):
            del sys.frozen
        if self._had_meipass:
            sys._MEIPASS = self._meipass
        elif hasattr(sys, '_MEIPASS'):
            del sys._MEIPASS

    def _set(self, frozen, meipass):
        if frozen:
            sys.frozen = True
        elif hasattr(sys, 'frozen'):
            del sys.frozen
        if meipass:
            sys._MEIPASS = r'C:\Temp\_MEI12345'
        elif hasattr(sys, '_MEIPASS'):
            del sys._MEIPASS

    def test_source(self):
        self._set(frozen=False, meipass=False)
        self.assertFalse(updater.is_frozen())
        self.assertFalse(updater.is_onefile())
        self.assertFalse(updater.is_onedir())
        self.assertFalse(updater.can_self_replace())

    def test_onefile(self):
        self._set(frozen=True, meipass=True)
        self.assertTrue(updater.is_frozen())
        self.assertTrue(updater.is_onefile())
        self.assertFalse(updater.is_onedir())
        self.assertTrue(updater.can_self_replace())

    def test_onedir(self):
        self._set(frozen=True, meipass=False)
        self.assertTrue(updater.is_frozen())
        self.assertFalse(updater.is_onefile())
        self.assertTrue(updater.is_onedir())
        self.assertFalse(updater.can_self_replace())


class TestBatGeneration(unittest.TestCase):
    def test_contains_values_and_labels(self):
        bat = updater.build_update_bat(
            pid=4321, target=r'C:\Apps\Metin2FishBot.exe',
            new=r'C:\Temp\Metin2FishBot-Portable-1.0.4.exe')
        self.assertIn('4321', bat)
        self.assertIn(r'C:\Apps\Metin2FishBot.exe', bat)
        self.assertIn(r'C:\Temp\Metin2FishBot-Portable-1.0.4.exe', bat)
        # die drei Schleifen-/Sprungmarken muessen vorhanden sein
        self.assertIn(':waitloop', bat)
        self.assertIn(':copyloop', bat)
        # cmd-Variablen muessen als EINFACHES % erhalten bleiben (kein %%)
        self.assertIn('%PID%', bat)
        self.assertIn('%TARGET%', bat)
        self.assertIn('%NEW%', bat)
        self.assertIn('%~f0', bat)
        self.assertNotIn('%%', bat)


class TestApplyGuards(unittest.TestCase):
    def test_apply_rejects_when_not_onefile(self):
        # Im Quellcode (kein _MEIPASS) darf apply_update_onefile nie ersetzen.
        had = hasattr(sys, '_MEIPASS')
        saved = getattr(sys, '_MEIPASS', None)
        if had:
            del sys._MEIPASS
        try:
            with self.assertRaises(updater.UpdateError):
                updater.apply_update_onefile(r'C:\Temp\whatever.exe')
        finally:
            if had:
                sys._MEIPASS = saved


if __name__ == '__main__':
    unittest.main()
