# -*- coding: utf-8 -*-
"""Reine Entscheidungs-Logik der Angel-Whitelist (:mod:`fishing_whitelist`).

Prueft :func:`fishing_whitelist.decide` gegen alle Kombinationen aus
HookResult-Art (Fisch/Item/Niete/nichts/unsicher) und Inventar-Zustand
(KEEP/REMOVE/CAMPFIRE). Reines ``stdlib`` -> laeuft headless mit ``python3`` UND
unter ``py.exe -m pytest``.

Vertrag (Spec):
  * REMOVE-Fang -> ABORT
  * KEEP/CAMPFIRE-Fang -> KEEP_FISHING
  * NIETE -> ABORT
  * NONE / unsicher / UNKNOWN / unbekannter Name -> KEEP_FISHING
  * enabled=False -> IMMER KEEP_FISHING (byte-stabil)
  * wirft NIE (auch bei Muell-Eingaben).
"""

import unittest

import fishing_chat as fc
import fishing_whitelist as wl


def _r(kind=fc.FISH, name='Lachs', confident=True):
    return fc.HookResult(kind=kind, name=name, confident=confident)


class TestDecideCore(unittest.TestCase):
    def test_remove_fish_aborts(self):
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {'Lachs': wl.REMOVE}, enabled=True),
            wl.ABORT)

    def test_keep_fish_fishes_on(self):
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {'Lachs': wl.KEEP}, enabled=True),
            wl.KEEP_FISHING)

    def test_campfire_fish_fishes_on(self):
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {'Lachs': wl.CAMPFIRE}, enabled=True),
            wl.KEEP_FISHING)

    def test_remove_item_aborts(self):
        self.assertEqual(
            wl.decide(_r(kind=fc.ITEM, name='Rotes Haarfärbemittel'),
                      {'Rotes Haarfärbemittel': wl.REMOVE}, enabled=True),
            wl.ABORT)

    def test_niete_aborts(self):
        self.assertEqual(
            wl.decide(_r(kind=fc.NIETE, name=None, confident=False),
                      {}, enabled=True),
            wl.ABORT)

    def test_none_keeps_fishing(self):
        self.assertEqual(
            wl.decide(_r(kind=fc.NONE, name=None, confident=False),
                      {}, enabled=True),
            wl.KEEP_FISHING)


class TestDecideDefensive(unittest.TestCase):
    def test_unknown_name_never_aborts(self):
        # Sicherer Biss, aber Name unsicher (UNKNOWN/confident=False) -> nie ab.
        self.assertEqual(
            wl.decide(fc.HookResult(kind=fc.FISH, name=fc.UNKNOWN,
                                    confident=False),
                      {'Lachs': wl.REMOVE}, enabled=True),
            wl.KEEP_FISHING)

    def test_confident_but_name_not_in_map_is_keep(self):
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {'Zander': wl.REMOVE}, enabled=True),
            wl.KEEP_FISHING)

    def test_empty_states_keeps_everything(self):
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {}, enabled=True), wl.KEEP_FISHING)
        self.assertEqual(
            wl.decide(_r(name='Lachs'), None, enabled=True), wl.KEEP_FISHING)

    def test_disabled_is_always_keep(self):
        # Selbst ein REMOVE-Fang wird bei ausgeschalteter Whitelist geangelt.
        self.assertEqual(
            wl.decide(_r(name='Lachs'), {'Lachs': wl.REMOVE}, enabled=False),
            wl.KEEP_FISHING)
        # NIETE ebenso (aus = byte-stabil, nichts greift).
        self.assertEqual(
            wl.decide(_r(kind=fc.NIETE, name=None), {}, enabled=False),
            wl.KEEP_FISHING)

    def test_none_result_keeps_fishing(self):
        self.assertEqual(wl.decide(None, {}, enabled=True), wl.KEEP_FISHING)

    def test_garbage_inputs_never_raise(self):
        for bad in (object(), 123, 'x', {'kind': 'fish'}):
            res = wl.decide(bad, {'Lachs': wl.REMOVE}, enabled=True)
            self.assertIn(res, (wl.ABORT, wl.KEEP_FISHING))

    def test_garbage_states_never_raise(self):
        res = wl.decide(_r(name='Lachs'), states=42, enabled=True)
        self.assertEqual(res, wl.KEEP_FISHING)


class TestShouldAbortShim(unittest.TestCase):
    def test_should_abort_matches_decide(self):
        self.assertTrue(
            wl.should_abort(_r(name='Lachs'), {'Lachs': wl.REMOVE}, enabled=True))
        self.assertFalse(
            wl.should_abort(_r(name='Lachs'), {'Lachs': wl.KEEP}, enabled=True))


class TestStateConstantsMatchInventory(unittest.TestCase):
    """The mirrored state constants must equal the inventory source of truth."""

    def test_constants_equal_inventory_manage(self):
        try:
            from interface import inventory_manage as im
        except Exception:
            self.skipTest('interface package not importable headless')
        self.assertEqual((wl.KEEP, wl.REMOVE, wl.CAMPFIRE),
                         (im.KEEP, im.REMOVE, im.CAMPFIRE))


if __name__ == '__main__':
    unittest.main(verbosity=2)
