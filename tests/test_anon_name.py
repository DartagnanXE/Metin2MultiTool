# -*- coding: utf-8 -*-
"""Pure tests for the deterministic anon-name generator (telemetry.anon_name).

The same install id + language always yields the same funny name; different ids
(almost surely) differ; the format is ``<Adj><Animal>#NNNN``; junk never raises;
EN != DE for the same id. A fixed VECTOR of (id -> expected EN, expected DE) is
pinned here; the SERVER test (server/tests/test_server_run1.py) asserts the SAME
EN vector against its own copy so the two import-isolated generators can never
silently drift. Stdlib unittest.
"""

import re
import unittest

from telemetry.anon_name import ADJECTIVES, ANIMALS, anon_name

# Shared correctness pin. The EN column is also asserted by the server test.
_VECTOR = {
    'install-aaaa': ('MightyBass#1350', 'MächtigerBarsch#1350'),
    'install-bbbb': ('LuckyCrab#0300', 'GlücklicherKrabbe#0300'),
    '0123456789abcdef0123456789abcdef': ('NimbleTrout#9239', 'FlinkerForelle#9239'),
    'zzz': ('NimblePerch#2426', 'FlinkerBarsch#2426'),
}

_FORMAT = re.compile(r'^[^#]+#\d{4}$')


class TestAnonName(unittest.TestCase):
    def test_deterministic_per_id_and_lang(self):
        self.assertEqual(anon_name('abc', 'en'), anon_name('abc', 'en'))
        self.assertEqual(anon_name('abc', 'de'), anon_name('abc', 'de'))

    def test_differs_across_ids(self):
        names = {anon_name('id-{}'.format(i), 'en') for i in range(50)}
        # Random-ish spread: not all collapse to one name.
        self.assertGreater(len(names), 1)

    def test_format_adj_animal_hash_four_digits(self):
        for lang in ('en', 'de'):
            name = anon_name('whatever', lang)
            self.assertRegex(name, _FORMAT)
            self.assertTrue(name.split('#')[1].isdigit())
            self.assertEqual(len(name.split('#')[1]), 4)

    def test_en_differs_from_de_for_same_id(self):
        self.assertNotEqual(anon_name('same-id', 'en'),
                            anon_name('same-id', 'de'))

    def test_unknown_lang_falls_back_to_en(self):
        self.assertEqual(anon_name('id', 'fr'), anon_name('id', 'en'))

    def test_never_raises_on_junk(self):
        for junk in (None, 12345, object(), b'bytes', 3.14):
            name = anon_name(junk, 'en')
            self.assertRegex(name, _FORMAT)

    def test_lists_same_length_per_language(self):
        # EN and DE must be the SAME length so the index space matches.
        self.assertEqual(len(ADJECTIVES['en']), len(ADJECTIVES['de']))
        self.assertEqual(len(ANIMALS['en']), len(ANIMALS['de']))

    def test_de_has_real_umlauts(self):
        joined = ''.join(ADJECTIVES['de'] + ANIMALS['de'])
        self.assertTrue(any(ch in joined for ch in 'äöüÄÖÜ'),
                        'DE word lists should use real umlauts')

    def test_shared_vector_en_and_de(self):
        for install_id, (en_name, de_name) in _VECTOR.items():
            self.assertEqual(anon_name(install_id, 'en'), en_name)
            self.assertEqual(anon_name(install_id, 'de'), de_name)


if __name__ == '__main__':
    unittest.main()
