# -*- coding: utf-8 -*-
"""EN/DE parity for the translation table (:mod:`i18n_data`).

``i18n.t`` falls back EN -> key, so a MISSING or empty German string silently
degrades to English. This test makes the parity guarantee explicit:

  * every entry carries BOTH 'en' and 'de', non-empty;
  * the ``{placeholder}`` field names match between EN and DE (so neither
    language raises / leaks a raw brace at format time).

Pure stdlib -> always runnable headless.
"""

import string
import unittest

from i18n_data import TRANSLATIONS


def _placeholders(text):
    """Set of named ``{field}`` placeholders in a format string (ignore text)."""
    names = set()
    for _literal, field, _spec, _conv in string.Formatter().parse(text):
        if field:
            names.add(field)
    return names


class TestI18nParity(unittest.TestCase):
    def test_every_entry_has_both_languages(self):
        for key, entry in TRANSLATIONS.items():
            self.assertIsInstance(entry, dict, key)
            self.assertIn('en', entry, key)
            self.assertIn('de', entry, key)
            self.assertTrue(str(entry['en']).strip(),
                            'empty en for {!r}'.format(key))
            self.assertTrue(str(entry['de']).strip(),
                            'empty de for {!r}'.format(key))

    def test_placeholders_match_between_languages(self):
        for key, entry in TRANSLATIONS.items():
            en_fields = _placeholders(entry['en'])
            de_fields = _placeholders(entry['de'])
            self.assertEqual(
                en_fields, de_fields,
                'placeholder mismatch for {!r}: en={} de={}'.format(
                    key, sorted(en_fields), sorted(de_fields)))


# Keys the six change-sets reference directly. ``i18n.t`` falls back to the raw
# KEY when an entry is missing entirely, so the parity test above (which only
# iterates EXISTING entries) cannot catch a deleted key. This pins the
# change-set-critical strings so a refactor that drops one fails loudly.
_REQUIRED_KEYS = (
    # CS1 ranking / leaderboard
    'ui.leaderboard_rank', 'ui.leaderboard_player', 'ui.leaderboard_catches',
    'ui.leaderboard_your_rank', 'ui.leaderboard_empty',
    'ui.leaderboard_fetch_failed', 'ui.leaderboard_loading',
    'ui.leaderboard_refresh', 'ui.ranking_banned', 'ui.ranking_telemetry_off',
    'ui.stats_puzzles',
    # Anonymous model: transparency notices + reworded onboarding keys
    'ui.ranking_transparency', 'ui.onboarding_transparency',
    'ui.onboarding_intro', 'ui.onboarding_username_hint',
    'ui.ranking_username_sub',
    # CS3 inventory scan abort
    'inventory.scan_no_window', 'inventory.scan_not_open',
    'inventory.scan_started',
    # CS4 window picker + mode toggle
    'ui.pick_window_btn', 'ui.pick_window_title', 'ui.pick_window_row',
    'ui.window_chosen', 'ui.window_mode_last_focused', 'ui.window_mode_specific',
    'ui.window_mode_changed', 'ui.window_mode_toggle_tip',
    # CS5 fake test windows
    'ui.test_window_inventory_opened', 'ui.test_window_opened',
    'ui.test_window_failed',
    # CS6 footer / language toggle / detection note
    'ui.language_changed', 'ui.detect_searching', 'ui.window_title',
    # Fishing whitelist toggle (label + ?-help) in the Fishing view
    'ui.whitelist_enabled', 'ui.whitelist_help',
    # Fishing bait-refill toggle (label + ?-help) + runtime log lines
    'ui.bait_refill_enabled', 'ui.bait_refill_help',
    'fishing.bait_refill_empty_slot', 'fishing.bait_refill_done',
    'fishing.bait_refill_none_left', 'fishing.bait_refill_failed',
)


class TestRequiredKeysPresent(unittest.TestCase):
    def test_change_set_keys_exist_with_both_languages(self):
        for key in _REQUIRED_KEYS:
            self.assertIn(key, TRANSLATIONS,
                          'change-set key {!r} missing from table'.format(key))
            entry = TRANSLATIONS[key]
            self.assertTrue(str(entry.get('en', '')).strip(), key)
            self.assertTrue(str(entry.get('de', '')).strip(), key)


if __name__ == '__main__':
    unittest.main()
