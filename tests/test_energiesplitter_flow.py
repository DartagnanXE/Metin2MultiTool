"""Headless-Tests fuer den EnergiesplitterBot-Kern (Eigentuemer D).

Spiegelt das Stub-Muster aus ``tests/test_puzzle_hardening.py``: die Windows-
only Treiber (``pydirectinput``/``win32*``) UND die Schwester-Module von Agent A
(``detect``/``geometry``/``gold_reader``) werden VOR dem Bot-Import gestubbt,
damit die reine State-Machine-/Gate-/Safety-Logik gegen den ECHTEN Bot-Code
laeuft.

Schwerpunkt (CONTRACT §2/§7):
  * Phase-0-GATE blockt ohne Assets -> KEINE Maus-/Tasten-Aktion (mock-assert).
  * Safety-Stops feuern: gold_floor, max_gold_spend, max_actions, gold-unlesbar,
    consecutive_unverified.
  * Stack-greedy-Plan korrekt (ueber die calc-Bruecke).
  * Modus-Auswahl (hammer/dagger) verzweigt korrekt.
  * Kein rightClick/click/drag/keyDown solange dry_run or not armed.
"""

import os
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
  sys.path.insert(0, _REPO_ROOT)


# -- Eingabe-/Capture-Stubs (zaehlen die Aufrufe) ---------------------------
_INPUT_CALLS = {'click': 0, 'right': 0, 'keyDown': 0, 'keyUp': 0,
                'mouseDown': 0, 'mouseUp': 0, 'moveTo': 0}


def _reset_input():
  for k in _INPUT_CALLS:
    _INPUT_CALLS[k] = 0


def _install_stubs():
  pdi = types.ModuleType('pydirectinput')
  pdi.PAUSE = 0

  def _click(*a, **k):
    if k.get('button') == 'right':
      _INPUT_CALLS['right'] += 1
    else:
      _INPUT_CALLS['click'] += 1

  pdi.click = _click
  pdi.moveTo = lambda *a, **k: _INPUT_CALLS.__setitem__('moveTo', _INPUT_CALLS['moveTo'] + 1)
  pdi.press = lambda *a, **k: None
  pdi.keyDown = lambda *a, **k: _INPUT_CALLS.__setitem__('keyDown', _INPUT_CALLS['keyDown'] + 1)
  pdi.keyUp = lambda *a, **k: _INPUT_CALLS.__setitem__('keyUp', _INPUT_CALLS['keyUp'] + 1)
  pdi.mouseDown = lambda *a, **k: _INPUT_CALLS.__setitem__('mouseDown', _INPUT_CALLS['mouseDown'] + 1)
  pdi.mouseUp = lambda *a, **k: _INPUT_CALLS.__setitem__('mouseUp', _INPUT_CALLS['mouseUp'] + 1)
  sys.modules['pydirectinput'] = pdi
  for name in ('win32gui', 'win32ui', 'win32con', 'win32api'):
    sys.modules.setdefault(name, types.ModuleType(name))


_install_stubs()

import energiesplitter.bot as esbot_mod          # noqa: E402
from energiesplitter.bot import (                 # noqa: E402
    EnergiesplitterBot, MODE_HAMMER, MODE_DAGGER)


# -- Fakes fuer Fenster + Agent-A-Detektoren --------------------------------
class _FakeWincap:
  offset_x = 0
  offset_y = 0

  def __init__(self, *a, **k):
    self._shot = object()  # opaker Marker; Detektoren sind gestubbt

  def get_screenshot(self):
    return self._shot


def _values(**over):
  base = {
      '-ES_HAMMER_COUNT-': 200, '-ES_FREISCHALTEN-': False,
      '-ES_PRICE-': 15000, '-ES_PROCESS_MODE-': 'one_to_one',
      '-ES_BATCH-': 50, '-ES_PREFER_STACK-': 'largest_fit',
      '-ES_MOUSE_PAUSE-': 0.05, '-ES_KB_PAUSE-': 0.10,
      '-ES_SPEED-': 'fast', '-ES_JITTER-': 0.15,
      '-ES_BIRDSEYE-': True, '-ES_GOLD_FLOOR-': 50000,
      '-ES_MAX_SPEND-': 0, '-ES_MAX_ACTIONS-': 0,
      '-ES_UNVERIF_STOP-': 3, '-ES_DRY_RUN-': True,
  }
  base.update(over)
  return base


def _make_bot(mode=MODE_HAMMER, values=None, with_window=True):
  bot = EnergiesplitterBot()
  bot.mode = mode
  if with_window:
    with mock.patch.object(esbot_mod, '_WindowCapture', _FakeWincap):
      bot.set_to_begin(values if values is not None else _values())
  else:
    with mock.patch.object(esbot_mod, '_WindowCapture', None):
      bot.set_to_begin(values if values is not None else _values())
  return bot


def _arm(bot):
  """Schaltet den Bot kuenstlich scharf (Phase-0 erfuellt + dry_run aus),
  um die scharfen Pfade zu testen. In Produktion macht das phase0_gate()."""
  bot.armed = True
  bot.dry_run = False


class TestSetToBeginFreeze(unittest.TestCase):
  def test_resets_state_and_counters(self):
    bot = _make_bot()
    self.assertEqual(bot.state, EnergiesplitterBot.ST_INIT)
    for attr in ('gekauft', 'hammer_remaining', 'splitter_summe',
                 'actions_done', 'gold_spent', 'consecutive_unverified'):
      self.assertEqual(getattr(bot, attr), 0)

  def test_max_gold_spend_auto_derived(self):
    bot = _make_bot(values=_values(**{'-ES_HAMMER_COUNT-': 10,
                                      '-ES_PRICE-': 15000,
                                      '-ES_MAX_SPEND-': 0}))
    self.assertEqual(bot.max_gold_spend, 10 * 2 * 15000)

  def test_max_actions_auto_derived(self):
    bot = _make_bot(values=_values(**{'-ES_HAMMER_COUNT-': 100,
                                      '-ES_MAX_ACTIONS-': 0}))
    self.assertEqual(bot.max_actions, round(1.2 * 100))

  def test_explicit_caps_kept(self):
    bot = _make_bot(values=_values(**{'-ES_MAX_SPEND-': 12345,
                                      '-ES_MAX_ACTIONS-': 7}))
    self.assertEqual(bot.max_gold_spend, 12345)
    self.assertEqual(bot.max_actions, 7)

  def test_idempotent(self):
    bot = _make_bot()
    bot.gekauft = 50
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    with mock.patch.object(esbot_mod, '_WindowCapture', _FakeWincap):
      bot.set_to_begin(_values())
    self.assertEqual(bot.gekauft, 0)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_INIT)


class TestPhase0Gate(unittest.TestCase):
  def test_missing_modules_block(self):
    bot = _make_bot()
    armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertTrue(missing)

  def test_all_present_arms(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(
        assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertTrue(armed, missing)
    self.assertEqual(missing, [])

  def test_assets_missing_listed(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(
        assets_ready=lambda mode: (False, ['item:hammer', 'gold_digits']))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('item:hammer', missing)

  def test_uncalibrated_blocks(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: False)
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('calibration:800x600', missing)


class TestGateBlocksAllInput(unittest.TestCase):
  """KEIN rightClick/click/drag/keyDown solange dry_run or not armed."""

  def test_dry_run_tick_no_input(self):
    _reset_input()
    bot = _make_bot()
    bot.botting = True
    self.assertTrue(bot.dry_run or not bot.armed)
    bot.runHack()
    self.assertFalse(bot.botting)  # Selbst-Stop
    self.assertEqual(bot.state, EnergiesplitterBot.ST_STOP)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)

  def test_dagger_dry_run_no_input(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER)
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)

  def test_armed_but_dry_run_still_blocks(self):
    _reset_input()
    bot = _make_bot()
    bot.armed = True       # Assets da ...
    bot.dry_run = True     # ... aber noch nicht entsichert
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)

  def test_guarded_helpers_no_op_when_blocked(self):
    _reset_input()
    bot = _make_bot()
    # dry_run=True -> jede Eingabe muss No-Op sein.
    self.assertFalse(bot._right_click(10, 10))
    self.assertFalse(bot._left_click(10, 10))
    self.assertFalse(bot._press_key('g'))
    self.assertFalse(bot._drag(1, 1, 2, 2))
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)


class TestNoWindowStop(unittest.TestCase):
  def test_no_window_stops_without_input(self):
    _reset_input()
    bot = _make_bot(with_window=False)
    bot.armed = True
    bot.dry_run = False
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'no_window')
    self.assertEqual(sum(_INPUT_CALLS.values()), 0)


class TestAbort(unittest.TestCase):
  def test_abort_fn_reads_signal(self):
    bot = _make_bot()
    self.assertFalse(bot.abort_fn())
    bot.stop_signal = types.SimpleNamespace(stopped=True)
    self.assertTrue(bot.abort_fn())

  def test_abort_stops_before_input(self):
    _reset_input()
    bot = _make_bot()
    _arm(bot)
    bot.stop_signal = types.SimpleNamespace(stopped=True)
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0)


class TestGoldGuard(unittest.TestCase):
  def _armed_bot(self, gold, floor=50000, max_spend=10 ** 9, spent=0):
    bot = _make_bot()
    _arm(bot)
    bot.gold_floor = floor
    bot.max_gold_spend = max_spend
    bot.gold_spent = spent
    bot._read_gold = lambda: gold
    return bot

  def test_gold_unreadable_stops(self):
    bot = self._armed_bot(gold=None)
    bot.botting = True
    with mock.patch.object(bot, '_snapshot'):
      out = bot.gold_guard(15000)
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'gold_unreadable')

  def test_gold_floor_hit_stops(self):
    bot = self._armed_bot(gold=60000, floor=50000)
    bot.botting = True
    out = bot.gold_guard(15000)   # 60000-15000 = 45000 < 50000 floor
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'gold_floor')

  def test_max_gold_spend_cap_stops(self):
    bot = self._armed_bot(gold=10 ** 9, floor=0, max_spend=20000, spent=10000)
    bot.botting = True
    out = bot.gold_guard(15000)   # 10000+15000 = 25000 > 20000 cap
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')

  def test_gold_ok_returns_value(self):
    bot = self._armed_bot(gold=500000, floor=50000, max_spend=10 ** 9)
    bot.botting = True
    out = bot.gold_guard(15000)
    self.assertEqual(out, 500000)
    self.assertTrue(bot.botting)


class TestActionCap(unittest.TestCase):
  def test_max_actions_stops(self):
    bot = _make_bot()
    _arm(bot)
    bot.max_actions = 2
    bot.actions_done = 2
    bot.botting = True
    self.assertTrue(bot._action_cap_hit())
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_actions')

  def test_below_cap_continues(self):
    bot = _make_bot()
    _arm(bot)
    bot.max_actions = 5
    bot.actions_done = 2
    bot.botting = True
    self.assertFalse(bot._action_cap_hit())
    self.assertTrue(bot.botting)


class TestConsecutiveUnverified(unittest.TestCase):
  def test_stops_after_n(self):
    bot = _make_bot()
    _arm(bot)
    bot.consecutive_unverified_stop = 3
    bot.consecutive_unverified = 0
    bot.botting = True
    self.assertFalse(bot._note_unverified())  # 1
    self.assertFalse(bot._note_unverified())  # 2
    self.assertTrue(bot._note_unverified())   # 3 -> Stop
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'consecutive_unverified')


class TestStackPlan(unittest.TestCase):
  """Stack-greedy-Plan ueber die calc-Bruecke (Agent B)."""

  def test_largest_fit_uses_calc(self):
    bot = _make_bot()
    _arm(bot)
    bot.prefer_stack = 'largest_fit'
    captured = {}

    def fake_plan(target, free, sizes):
      captured['args'] = (target, free, sizes)
      return [200, 100, 10]

    fake_calc = types.SimpleNamespace(plan_stack_purchase=fake_plan)
    bot._read_shop_stack_sizes = lambda: (200, 100, 10, 1)
    with mock.patch.object(esbot_mod, '_calc', fake_calc):
      plan = bot._plan_stacks(310, free_slots=5)
    self.assertEqual(plan, [200, 100, 10])
    self.assertEqual(captured['args'], (310, 5, (200, 100, 10, 1)))

  def test_singles_mode_forces_ones(self):
    bot = _make_bot()
    _arm(bot)
    bot.prefer_stack = 'singles'
    seen = {}

    def fake_plan(target, free, sizes):
      seen['sizes'] = sizes
      return [1]

    fake_calc = types.SimpleNamespace(plan_stack_purchase=fake_plan)
    with mock.patch.object(esbot_mod, '_calc', fake_calc):
      bot._plan_stacks(5, free_slots=5)
    self.assertEqual(seen['sizes'], (1,))

  def test_no_calc_defensive_singles(self):
    bot = _make_bot()
    _arm(bot)
    with mock.patch.object(esbot_mod, '_calc', None):
      self.assertEqual(bot._plan_stacks(5, free_slots=1), [1])
      self.assertEqual(bot._plan_stacks(5, free_slots=0), [])

  def test_target_zero_empty(self):
    bot = _make_bot()
    self.assertEqual(bot._plan_stacks(0, free_slots=5), [])


class TestModeBranch(unittest.TestCase):
  """runHack verzweigt nach self.mode (armed -> echter Tick-Pfad)."""

  def test_hammer_branch_called(self):
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.botting = True
    with mock.patch.object(bot, '_tick_hammer') as h, \
         mock.patch.object(bot, '_tick_dagger') as d:
      bot.runHack()
    self.assertTrue(h.called)
    self.assertFalse(d.called)

  def test_dagger_branch_called(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.botting = True
    with mock.patch.object(bot, '_tick_hammer') as h, \
         mock.patch.object(bot, '_tick_dagger') as d:
      bot.runHack()
    self.assertTrue(d.called)
    self.assertFalse(h.called)


class TestHammerStateFlow(unittest.TestCase):
  """Erste Hammer-Schritte: INIT -> INVENTORY_BASE -> Stop bei fehlendem
  Item-Template bzw. keinem Platz -- jeweils OHNE Maus-Aktion."""

  def test_init_transitions_to_inventory(self):
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.botting = True
    bot.runHack()  # INIT -> INVENTORY_BASE
    self.assertEqual(bot.state, EnergiesplitterBot.ST_INVENTORY_BASE)
    self.assertEqual(bot.hammer_remaining, bot.hammer_count)

  def test_item_template_missing_stops(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_INVENTORY_BASE
    bot.botting = True
    bot._item_template_ready = lambda item: False
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'item_template_missing')
    self.assertEqual(sum(_INPUT_CALLS.values()), 0)

  def test_no_space_stops(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_INVENTORY_BASE
    bot.botting = True
    bot._item_template_ready = lambda item: True
    bot._free_slot_count = lambda: 0
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'no_space')
    self.assertEqual(sum(_INPUT_CALLS.values()), 0)


class TestDaggerProcessVerification(unittest.TestCase):
  """1:1-Verarbeitung: dekrementiert NUR nach positiver Verifikation (R5)."""

  def test_decrement_only_on_growth(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.hammer_remaining = 3
    bot.splitter_summe = 0
    bot._dolche_gekauft = 1
    bot._before_proc = object()
    bot.state = EnergiesplitterBot.ST_VERIFY_PROCESS
    bot.botting = True
    bot._shot = lambda: object()
    bot.verify_process = lambda a, b: 7   # Splitter gewachsen
    bot.runHack()
    self.assertEqual(bot.splitter_summe, 7)
    self.assertEqual(bot.hammer_remaining, 2)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_RESCAN)

  def test_no_growth_no_decrement_then_stop(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.hammer_remaining = 3
    bot.splitter_summe = 0
    bot.consecutive_unverified_stop = 1   # sofortiger Stop bei 1. Fehlschlag
    bot._before_proc = object()
    bot.state = EnergiesplitterBot.ST_VERIFY_PROCESS
    bot.botting = True
    bot._shot = lambda: object()
    bot.verify_process = lambda a, b: 0   # KEIN Wachstum
    bot.runHack()
    self.assertEqual(bot.hammer_remaining, 3)   # NICHT dekrementiert
    self.assertFalse(bot.botting)

  def test_drag_unsafe_stops_without_drag(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_PROCESS_DRAG
    bot.botting = True
    bot._dolch_inv_slot = (5, 5)
    bot._classified_hammer_slot = lambda: None   # Quelle NICHT als Hammer erkannt
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'drag_unsafe')
    self.assertEqual(_INPUT_CALLS['mouseDown'], 0)
    self.assertEqual(_INPUT_CALLS['moveTo'], 0)


class TestArmedPurchaseDoesInput(unittest.TestCase):
  """Gegenprobe: bei echtem GATE-gruen + verifiziertem Kauf wird der
  Rechtsklick tatsaechlich ausgeloest (Gate sperrt NICHT faelschlich)."""

  def test_verified_hammer_buy(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.hammer_count = 10
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.botting = True
    golds = [500000, 500000 - 150000]   # before, after (10*15000)
    bot._read_gold = lambda: golds.pop(0)
    bot._plan_stacks = lambda target, free: [10]
    bot.runHack()
    self.assertEqual(_INPUT_CALLS['right'], 1)
    self.assertEqual(bot.gekauft, 10)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_CHECK_DONE)


if __name__ == '__main__':
  unittest.main()
