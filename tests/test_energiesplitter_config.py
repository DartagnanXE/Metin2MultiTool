# -*- coding: utf-8 -*-
"""Tests fuer die reine Energiesplitter-Rechen-Logik (energiesplitter/calc.py)
und das Config-Schema (defaults/validate/clamp/enum).

Headless, reine stdlib + numpy-frei: calc.py ist reine Arithmetik; das
Config-Modul ist toolkit-frei importierbar.
"""

import unittest

from energiesplitter import calc
from interface import config


# ---------------------------------------------------------------------------
# energiesplitter/calc.py -- plan_hammer_yang
# ---------------------------------------------------------------------------
class TestPlanHammerYang(unittest.TestCase):
  def test_default_breakdown(self):
    plan = calc.plan_hammer_yang(200, 15000)
    self.assertEqual(plan['hammer_count'], 200)
    self.assertEqual(plan['price_per_item'], 15000)
    self.assertEqual(plan['hammer_yang'], 200 * 15000)
    self.assertEqual(plan['dagger_yang'], 200 * 15000)
    self.assertEqual(plan['total_yang'], 200 * 30000)

  def test_dagger_equals_hammer(self):
    plan = calc.plan_hammer_yang(7, 12345)
    self.assertEqual(plan['hammer_yang'], plan['dagger_yang'])
    self.assertEqual(plan['total_yang'],
                     plan['hammer_yang'] + plan['dagger_yang'])

  def test_zero_and_negative_clamped(self):
    for n in (0, -1, -999):
      plan = calc.plan_hammer_yang(n, 15000)
      self.assertEqual(plan['hammer_count'], 0)
      self.assertEqual(plan['total_yang'], 0)
    plan = calc.plan_hammer_yang(10, -5)
    self.assertEqual(plan['price_per_item'], 0)
    self.assertEqual(plan['total_yang'], 0)

  def test_garbage_never_raises(self):
    for bad in (None, 'x', [], {}, object(), 3.9):
      plan = calc.plan_hammer_yang(bad, bad)
      self.assertIsInstance(plan['total_yang'], int)
      self.assertGreaterEqual(plan['total_yang'], 0)

  def test_float_input_truncates_to_int(self):
    plan = calc.plan_hammer_yang(3.9, 15000.0)
    self.assertEqual(plan['hammer_count'], 3)
    self.assertEqual(plan['price_per_item'], 15000)

  def test_all_values_are_ints(self):
    plan = calc.plan_hammer_yang(50, 15000)
    for v in plan.values():
      self.assertIsInstance(v, int)


# ---------------------------------------------------------------------------
# energiesplitter/calc.py -- plan_stack_purchase
# ---------------------------------------------------------------------------
class TestPlanStackPurchase(unittest.TestCase):
  # Default-Stacks = echte Hammer-Shop-Groessen (Addendum A1: 1/50/200).
  def test_greedy_largest_first(self):
    # 200 bei genug Platz -> genau 1x 200er-Stack.
    self.assertEqual(calc.plan_stack_purchase(200, 99), [200])
    # 250 -> 200 + 50.
    self.assertEqual(calc.plan_stack_purchase(250, 99), [200, 50])

  def test_exact_target_with_singles(self):
    # 251 -> 200 + 50 + 1 (1er nur zum exakten Treffen).
    self.assertEqual(calc.plan_stack_purchase(251, 99), [200, 50, 1])

  def test_never_exceeds_target(self):
    for target in (1, 5, 11, 50, 99, 200, 201, 250, 251, 410, 999):
      stacks = calc.plan_stack_purchase(target, 999)
      self.assertLessEqual(sum(stacks), target)

  def test_free_slots_caps_stack_count(self):
    # Nur 2 freie Slots -> hoechstens 2 Stacks, auch wenn target mehr braeuchte.
    stacks = calc.plan_stack_purchase(411, 2)
    self.assertLessEqual(len(stacks), 2)
    self.assertEqual(stacks, [200, 200])

  def test_one_slot_one_stack(self):
    stacks = calc.plan_stack_purchase(1000, 1)
    self.assertEqual(len(stacks), 1)
    self.assertEqual(stacks, [200])

  def test_nonpositive_returns_empty(self):
    self.assertEqual(calc.plan_stack_purchase(0, 5), [])
    self.assertEqual(calc.plan_stack_purchase(-3, 5), [])
    self.assertEqual(calc.plan_stack_purchase(100, 0), [])
    self.assertEqual(calc.plan_stack_purchase(100, -1), [])

  def test_runtime_stack_sizes_honoured(self):
    # Addendum A1 (1/50/200) statt Bild-Default -- Caller liefert die Wahrheit.
    self.assertEqual(
        calc.plan_stack_purchase(250, 99, stack_sizes=(200, 50, 1)),
        [200, 50])
    self.assertEqual(
        calc.plan_stack_purchase(251, 99, stack_sizes=(200, 50, 1)),
        [200, 50, 1])

  def test_default_matches_addendum(self):
    # Der Default OHNE explizite Groessen muss 1/50/200 sein (kein 100/10 mehr).
    self.assertEqual(calc.plan_stack_purchase(200, 99), [200])
    self.assertEqual(calc.plan_stack_purchase(250, 99), [200, 50])
    self.assertEqual(calc.plan_stack_purchase(251, 99), [200, 50, 1])

  def test_small_free_space_uses_smaller_stacks(self):
    # Knapper Freiplatz: nur 1 Slot -> hoechstens 1 (groesster passender) Stack.
    self.assertEqual(calc.plan_stack_purchase(60, 1), [50])
    self.assertEqual(calc.plan_stack_purchase(49, 1), [1])
    # 2 Slots, Ziel 51 -> 50 + 1.
    self.assertEqual(calc.plan_stack_purchase(51, 2), [50, 1])

  def test_unsorted_and_dirty_sizes(self):
    # Unsortiert / mit Dubletten / mit Muell -> robust (absteigend, dedupliziert).
    self.assertEqual(
        calc.plan_stack_purchase(310, 99,
                                 stack_sizes=(10, 200, 100, 200, 0, -5, 'x')),
        [200, 100, 10])

  def test_empty_sizes_returns_empty(self):
    self.assertEqual(calc.plan_stack_purchase(100, 5, stack_sizes=()), [])
    self.assertEqual(calc.plan_stack_purchase(100, 5, stack_sizes=(0, -1)), [])

  def test_never_raises_on_garbage(self):
    for t_, f_ in ((None, None), ('x', 'y'), (object(), []), (5.5, 2.9)):
      out = calc.plan_stack_purchase(t_, f_)
      self.assertIsInstance(out, list)


# ---------------------------------------------------------------------------
# Config-Schema: defaults / validate / clamp / enum
# ---------------------------------------------------------------------------
class TestEnergiesplitterConfig(unittest.TestCase):
  def test_app_modes_include_es(self):
    self.assertIn('energiesplitter_hammer', config.APP_MODES)
    self.assertIn('energiesplitter_dagger', config.APP_MODES)

  def test_defaults_present(self):
    cfg = config.validate(config.DEFAULTS)
    es = cfg['energiesplitter']
    self.assertEqual(es['hammer']['hammer_count'], 200)
    self.assertEqual(es['hammer']['energie_freischalten'], True)
    self.assertEqual(es['hammer']['price_per_item'], 15000)
    self.assertEqual(es['hammer']['gold_floor'], 50000)
    self.assertEqual(es['hammer']['prefer_stack'], 'largest_fit')
    self.assertEqual(es['dagger']['process_mode'], 'one_to_one')
    self.assertEqual(es['shared']['speed_profile'], 'fast')
    self.assertEqual(es['shared']['dry_run'], True)
    # yang_check Default TRUE (sicher): live Yang-Gold-Wand aktiv.
    self.assertEqual(es['shared']['yang_check'], True)

  def test_yang_check_default_true_and_bool_coerced(self):
    # Default fehlt -> True; beliebiger Wert -> bool().
    cfg = config.validate({'energiesplitter': {'shared': {}}})
    self.assertIs(cfg['energiesplitter']['shared']['yang_check'], True)
    cfg2 = config.validate(
        {'energiesplitter': {'shared': {'yang_check': 0}}})
    self.assertIs(cfg2['energiesplitter']['shared']['yang_check'], False)
    cfg3 = config.validate(
        {'energiesplitter': {'shared': {'yang_check': 1}}})
    self.assertIs(cfg3['energiesplitter']['shared']['yang_check'], True)

  def test_modes_validate(self):
    for mode in ('energiesplitter_hammer', 'energiesplitter_dagger'):
      cfg = config.validate({'mode': mode})
      self.assertEqual(cfg['mode'], mode)

  def test_hammer_count_clamped(self):
    low = config.validate(
        {'energiesplitter': {'hammer': {'hammer_count': 0}}})
    high = config.validate(
        {'energiesplitter': {'hammer': {'hammer_count': 999999}}})
    self.assertEqual(low['energiesplitter']['hammer']['hammer_count'],
                     config.ES_HAMMER_MIN)
    self.assertEqual(high['energiesplitter']['hammer']['hammer_count'],
                     config.ES_HAMMER_MAX)

  def test_gold_floor_min_enforced(self):
    cfg = config.validate(
        {'energiesplitter': {'hammer': {'gold_floor': 0}}})
    self.assertEqual(cfg['energiesplitter']['hammer']['gold_floor'],
                     config.ES_GOLD_FLOOR_MIN)

  def test_pause_clamped(self):
    cfg = config.validate(
        {'energiesplitter': {'shared': {'mouse_pause': 99,
                                        'keyboard_pause': 0.0}}})
    s = cfg['energiesplitter']['shared']
    self.assertEqual(s['mouse_pause'], config.ES_PAUSE_MAX)
    self.assertEqual(s['keyboard_pause'], config.ES_PAUSE_MIN)

  def test_bad_enums_fall_back(self):
    cfg = config.validate({'energiesplitter': {
        'hammer': {'prefer_stack': 'nonsense'},
        'dagger': {'process_mode': 'nope'},
        'shared': {'speed_profile': 'turbo'}}})
    es = cfg['energiesplitter']
    self.assertEqual(es['hammer']['prefer_stack'], 'largest_fit')
    self.assertEqual(es['dagger']['process_mode'], 'one_to_one')
    self.assertEqual(es['shared']['speed_profile'], 'fast')

  def test_garbage_block_yields_defaults(self):
    for junk in (None, 42, 'x', [], {'hammer': 'bad'}):
      cfg = config.validate({'energiesplitter': junk})
      es = cfg['energiesplitter']
      self.assertIn('hammer', es)
      self.assertIn('dagger', es)
      self.assertIn('shared', es)
      self.assertIsInstance(es['hammer']['hammer_count'], int)

  def test_validate_does_not_mutate_input(self):
    src = {'energiesplitter': {'hammer': {'hammer_count': 50}}}
    before = repr(src)
    config.validate(src)
    self.assertEqual(repr(src), before)


if __name__ == '__main__':
  unittest.main()
