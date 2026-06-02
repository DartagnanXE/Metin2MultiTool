# -*- coding: utf-8 -*-
"""Pure tests for interface.inventory_manage (no Tk).

Locks the item ORDER (fish first, rest grouped by kind, tools excluded), the
click STATE cycle, the bundled item set, the localised (DE Metin2) names, and the
Pillow image variants / stack-count overlay / legend image. The Tk grid + the
placeholder apply are covered by the GUI smoke.
"""

import unittest

import i18n
from interface import inventory_manage as im


class TestCycleState(unittest.TestCase):
    def test_cycles_keep_remove_campfire(self):
        self.assertEqual(im.cycle_state(im.KEEP), im.REMOVE)
        self.assertEqual(im.cycle_state(im.REMOVE), im.CAMPFIRE)
        self.assertEqual(im.cycle_state(im.CAMPFIRE), im.KEEP)

    def test_wraps_and_survives_junk(self):
        self.assertEqual(im.cycle_state(2), 0)
        self.assertEqual(im.cycle_state('x'), im.KEEP)


class TestItemOrder(unittest.TestCase):
    def test_fish_first_then_rest_tools_excluded(self):
        names = ['Worm', 'Zander', 'Carp', 'Gold_Key', 'Eel', 'Bleach',
                 'Lagerfeuer']
        # Worm + Lagerfeuer (tools) are dropped; fish A->Z, then rest by kind.
        self.assertEqual(im.item_order(names),
                         ['Carp', 'Eel', 'Zander', 'Bleach', 'Gold_Key'])

    def test_rest_grouped_by_kind(self):
        # dyes (Bleach/Hair_Dye) -> keys -> rings, alphabetical within a group.
        names = ['Gold_Ring', 'Gold_Key', 'Red_Hair_Dye', 'Silver_Key']
        self.assertEqual(im.item_order(names),
                         ['Red_Hair_Dye', 'Gold_Key', 'Silver_Key', 'Gold_Ring'])

    def test_tools_never_returned(self):
        self.assertNotIn('Worm', im.item_order(['Worm', 'Carp']))
        self.assertNotIn('Lagerfeuer', im.item_order(['Lagerfeuer', 'Carp']))


class TestAvailableItems(unittest.TestCase):
    def test_excludes_tools_fish_first(self):
        items = im.available_items()
        self.assertEqual(len(items), 41)             # 43 icons - Worm - Lagerfeuer
        self.assertNotIn('Worm', items)
        self.assertNotIn('Lagerfeuer', items)
        last_fish = max(i for i, n in enumerate(items) if n in im.FISH)
        first_rest = min(i for i, n in enumerate(items) if n not in im.FISH)
        self.assertLess(last_fish, first_rest)

    def test_known_members(self):
        items = set(im.available_items())
        for name in ('Carp', 'Catfish', 'Gold_Key', 'Red_Hair_Dye'):
            self.assertIn(name, items)


class TestLocalizedName(unittest.TestCase):
    def test_de_uses_official_metin2_names(self):
        old = i18n.get_lang()
        try:
            i18n.set_lang('de')
            self.assertEqual(im.localized_name('Catfish'), 'Wels')
            self.assertEqual(im.localized_name('Red_King_Crab'), 'Königskrabbe')
            self.assertEqual(im.localized_name('Black_Hair_Dye'),
                             'Schwarzes Haarfärbemittel')
            self.assertEqual(im.localized_name('Kelpie_Key'),
                             'Wassernixenschlüssel')
            i18n.set_lang('en')
            self.assertEqual(im.localized_name('Catfish'), 'Catfish')
        finally:
            i18n.set_lang(old)

    def test_unknown_falls_back_to_pretty(self):
        self.assertEqual(im.localized_name('Foo_Bar'), 'Foo Bar')


class TestVariants(unittest.TestCase):
    def test_three_distinct_rgba_variants(self):
        keep, remove, fire = im.variants('Carp', 34)
        if keep is None:
            self.skipTest('Pillow / icon unavailable')
        for v in (keep, remove, fire):
            self.assertEqual(v.size, (34, 34))
            self.assertEqual(v.mode, 'RGBA')
        self.assertNotEqual(keep.tobytes(), remove.tobytes())
        self.assertNotEqual(keep.tobytes(), fire.tobytes())
        self.assertNotEqual(remove.tobytes(), fire.tobytes())

    def test_unknown_icon_is_none_triple(self):
        self.assertEqual(im.variants('NotAnItem_xyz', 34), (None, None, None))


class TestCountOverlay(unittest.TestCase):
    def test_positive_count_draws_number_zero_is_unchanged(self):
        base = im.load_icon('Carp', 34)
        if base is None:
            self.skipTest('Pillow / icon unavailable')
        with5 = im.apply_count(base, 5, 34)
        self.assertEqual(with5.size, (34, 34))
        self.assertNotEqual(base.tobytes(), with5.tobytes())   # number drawn
        with0 = im.apply_count(base, 0, 34)
        self.assertEqual(base.tobytes(), with0.tobytes())      # nothing at 0


class TestLegendImage(unittest.TestCase):
    def test_builds_rgba_three_cells_wide(self):
        img = im.legend_image(px=40, lang='de')
        if img is None:
            self.skipTest('Pillow / icon unavailable')
        self.assertEqual(img.mode, 'RGBA')
        self.assertGreater(img.size[0], 3 * 40)    # 3 labelled cells


if __name__ == '__main__':
    unittest.main()
