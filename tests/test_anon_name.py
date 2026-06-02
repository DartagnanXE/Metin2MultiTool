# -*- coding: utf-8 -*-
"""Pure tests for the deterministic anon-name generator (telemetry.anon_name).

Same install id -> same funny BASE name (one of 100, NO numeric suffix --
collision disambiguation is the server's job); different ids (almost surely)
differ; the name is language-neutral; junk never raises. A fixed VECTOR of
(id -> expected name) is pinned here; the SERVER test
(server/tests/test_server_run1.py) asserts the SAME vector against its own copy
so the two import-isolated generators can never silently drift. Stdlib unittest.
"""

import unittest

from telemetry.anon_name import NAMES, anon_name

# Shared correctness pin (also asserted by the server test, same values).
_VECTOR = {
    'install-aaaa': 'CritKitten',
    'install-bbbb': 'JinnoJester',
    '0123456789abcdef0123456789abcdef': 'SlipperyEel',
    'zzz': 'ChunjoChamp',
}


class TestAnonName(unittest.TestCase):
    def test_deterministic_per_id(self):
        self.assertEqual(anon_name('abc'), anon_name('abc'))

    def test_lang_is_ignored(self):
        # Names are language-neutral now: lang must NOT change the result.
        self.assertEqual(anon_name('id', 'de'), anon_name('id', 'en'))
        self.assertEqual(anon_name('id', 'fr'), anon_name('id', 'en'))

    def test_differs_across_ids(self):
        names = {anon_name('id-{}'.format(i)) for i in range(50)}
        self.assertGreater(len(names), 1)

    def test_name_is_a_bare_pool_entry(self):
        for seed in ('whatever', 'foo', 'bar', 'x', 'install-aaaa'):
            name = anon_name(seed)
            self.assertIn(name, NAMES)              # exactly a pool entry...
            self.assertNotIn('#', name)             # ...no '#NNNN' suffix
            self.assertFalse(name[-1].isdigit())    # ...no trailing digit

    def test_never_raises_on_junk(self):
        for junk in (None, 12345, object(), b'bytes', 3.14):
            self.assertIn(anon_name(junk), NAMES)

    def test_pool_is_100_unique(self):
        self.assertEqual(len(NAMES), 100)
        self.assertEqual(len(set(NAMES)), 100)

    def test_shared_vector(self):
        for install_id, expected in _VECTOR.items():
            self.assertEqual(anon_name(install_id), expected)


if __name__ == '__main__':
    unittest.main()
