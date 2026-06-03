# -*- coding: utf-8 -*-
"""Tests fuer die stabile config.json-Position (interface/config/paths.py) und
die Legacy-Migration in io.load.

Regression gegen den "zwei FishLover"/Re-Onboarding-Bug: der Pfad war ein nackter
CWD-relativer 'config.json', der bei der Portable-EXE nicht verlaesslich getroffen
wurde. Reine Standardbibliothek -> laeuft ueberall (auch headless/WSL)."""

import json
import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from interface.config import io, paths  # noqa: E402


class TestConfigPath(unittest.TestCase):
    def test_dev_not_frozen_is_cwd_filename(self):
        # Dev/Test: byte-stabil das bisherige Verhalten.
        self.assertEqual(paths.config_path(frozen=False), 'config.json')

    def test_frozen_writable_is_next_to_exe(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, 'Metin2FishBot.exe')
            self.assertEqual(
                paths.config_path(frozen=True, executable=exe),
                os.path.join(d, 'config.json'))

    def test_frozen_unwritable_exe_falls_back_to_appdata(self):
        with tempfile.TemporaryDirectory() as appd:
            # EXE in einem nicht existierenden Ordner -> dort nicht schreibbar.
            exe = os.path.join(os.sep, 'nonexistent_ro_dir_xyz123', 'app.exe')
            p = paths.config_path(frozen=True, executable=exe, appdata=appd)
            self.assertEqual(p, os.path.join(appd, paths.APP_DIR, 'config.json'))
            self.assertTrue(os.path.isdir(os.path.join(appd, paths.APP_DIR)))

    def test_never_raises_on_garbage(self):
        for kw in ({'frozen': True, 'executable': None},
                   {'frozen': True, 'executable': ''},
                   {'frozen': 'yes', 'executable': 123}):
            self.assertIsInstance(paths.config_path(**kw), str)

    def test_dir_writable_true_for_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(paths._dir_writable(d))

    def test_dir_writable_false_for_missing_or_empty(self):
        self.assertFalse(paths._dir_writable('/no/such/dir/xyz123'))
        self.assertFalse(paths._dir_writable(''))
        self.assertFalse(paths._dir_writable(None))


class TestLegacyMigration(unittest.TestCase):
    def test_implicit_default_migrates_legacy_cwd_config_when_frozen(self):
        # Frozen simuliert: Default-Pfad liegt anderswo + fehlt -> der implizite
        # load() zieht die alte CWD-config.json (Upgrader verliert nichts).
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            orig = io.DEFAULT_CONFIG_PATH
            try:
                os.chdir(d)
                with open('config.json', 'w', encoding='utf-8') as handle:
                    json.dump({'username': 'LegacyName'}, handle)
                io.DEFAULT_CONFIG_PATH = os.path.join(d, 'exe', 'config.json')
                cfg = io.load()           # implizit -> Migration aktiv
                self.assertEqual(cfg.get('username'), 'LegacyName')
            finally:
                io.DEFAULT_CONFIG_PATH = orig
                os.chdir(cwd)

    def test_explicit_missing_path_does_not_migrate(self):
        # Regression: ein EXPLIZITER fehlender Pfad darf NIE die CWD-config.json
        # aufsammeln (Tests laufen aus einem Repo MIT config.json).
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            try:
                os.chdir(d)
                with open('config.json', 'w', encoding='utf-8') as handle:
                    json.dump({'username': 'ShouldNotLeak'}, handle)
                cfg = io.load(os.path.join(d, 'explicit_missing.json'))
                self.assertEqual(cfg.get('username', ''), '')   # saubere Defaults
            finally:
                os.chdir(cwd)

    def test_explicit_existing_path_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            anchored = os.path.join(d, 'anchored.json')
            with open(anchored, 'w', encoding='utf-8') as handle:
                json.dump({'username': 'AnchoredName'}, handle)
            cfg = io.load(anchored)
            self.assertEqual(cfg.get('username'), 'AnchoredName')


if __name__ == '__main__':
    unittest.main(verbosity=2)
