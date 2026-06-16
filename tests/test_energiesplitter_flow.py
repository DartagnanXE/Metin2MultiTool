"""Headless-Tests fuer den EnergiesplitterBot-Kern (Eigentuemer D), Umbau 2026-06-16.

Spiegelt das Stub-Muster aus ``tests/test_puzzle_hardening.py``: die Windows-
only Treiber (``pydirectinput``/``win32*``) UND die Schwester-Module von Agent A
(``detect``/``geometry``) werden VOR dem Bot-Import gestubbt, damit die reine
State-Machine-/Gate-/Safety-Logik gegen den ECHTEN Bot-Code laeuft.

YANG spielt KEINE Rolle mehr (kein Preis, kein Kontostand, kein gold_guard).

Schwerpunkt (CONTRACT §2/§7):
  * Phase-0-GATE blockt ohne Assets -> KEINE Maus-/Tasten-Aktion (mock-assert);
    armed = assets_ready + 800x600 + grid_present (OHNE Yang).
  * Aktion 1: ``stack_count`` mal 200er-Stack kaufen -> Auto-Stop.
  * Aktion 2: Dolche sequenziell verarbeiten (Drag pro Dolch).
  * Safety-Stops feuern: max_actions, consecutive_unverified.
  * Modus-Auswahl (hammer/dagger) verzweigt korrekt.
  * Kein rightClick/click/drag/keyDown solange dry_run or not armed.
  * Erkennung-vor-Aktion intakt (drag_unsafe, Slot-Klassifikation).
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
      '-ES_STACK_COUNT-': 1, '-ES_FREISCHALTEN-': False,
      '-ES_DAGGERS_PER_ROUND-': 1,
      '-ES_MOUSE_PAUSE-': 0.05, '-ES_KB_PAUSE-': 0.10,
      '-ES_SPEED-': 'fast', '-ES_JITTER-': 0.15,
      '-ES_BIRDSEYE-': True,
      '-ES_MAX_ACTIONS-': 0, '-ES_UNVERIF_STOP-': 3, '-ES_DRY_RUN-': True,
  }
  base.update(over)
  return base


def _make_bot(mode=MODE_HAMMER, values=None, with_window=True):
  bot = EnergiesplitterBot()
  bot.mode = mode
  cap = _FakeWincap if with_window else None
  with mock.patch.object(esbot_mod, '_WindowCapture', cap):
    bot.set_to_begin(values if values is not None else _values())
  return bot


def _arm(bot):
  """Schaltet den Bot kuenstlich scharf (Phase-0 erfuellt + dry_run aus),
  um die scharfen Pfade zu testen. In Produktion macht das phase0_gate()."""
  bot.armed = True
  bot.dry_run = False


def _fake_modules(grid=True):
  """Fakes fuer detect/geometry, mit denen das GATE gruen werden kann."""
  fake_detect = types.SimpleNamespace(
      assets_ready=lambda mode: (True, []),
      grid_present=lambda: grid)
  fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
  return fake_detect, fake_geo


class TestSetToBeginFreeze(unittest.TestCase):
  def test_resets_state_and_counters(self):
    bot = _make_bot()
    self.assertEqual(bot.state, EnergiesplitterBot.ST_INIT)
    for attr in ('gekauft', 'hammer_remaining', 'splitter_summe',
                 'actions_done', 'consecutive_unverified'):
      self.assertEqual(getattr(bot, attr), 0)

  def test_max_actions_auto_derived(self):
    bot = _make_bot(values=_values(**{'-ES_STACK_COUNT-': 100,
                                      '-ES_MAX_ACTIONS-': 0}))
    self.assertEqual(bot.max_actions, max(50, round(3 * 100)))

  def test_explicit_cap_kept(self):
    bot = _make_bot(values=_values(**{'-ES_MAX_ACTIONS-': 7}))
    self.assertEqual(bot.max_actions, 7)

  def test_freezes_new_keys(self):
    bot = _make_bot(values=_values(**{'-ES_STACK_COUNT-': 3,
                                      '-ES_DAGGERS_PER_ROUND-': 4}))
    self.assertEqual(bot.stack_count, 3)
    self.assertEqual(bot.daggers_per_round, 4)

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
    fake_detect, fake_geo = _fake_modules()
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertTrue(armed, missing)
    self.assertEqual(missing, [])

  def test_assets_missing_listed(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(
        assets_ready=lambda mode: (False, ['item:hammer', 'npc:alchemist']),
        grid_present=lambda: True)
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('item:hammer', missing)

  def test_uncalibrated_blocks(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []),
                                        grid_present=lambda: True)
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: False)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('calibration:800x600', missing)

  def test_grid_missing_blocks(self):
    # Fenster + Assets OK, aber Inventar-Raster nicht aufloesbar -> rot.
    bot = _make_bot()
    fake_detect, fake_geo = _fake_modules(grid=False)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('grid_calibration', missing)

  def test_grid_check_never_raises(self):
    bot = _make_bot()
    def _boom():
      raise RuntimeError('grid kaputt')
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []),
                                        grid_present=_boom)
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('grid_calibration', missing)

  def test_gate_has_no_yang_path(self):
    # Es gibt KEINE Yang-/gold_reader-Vorbedingung mehr -> mit den drei realen
    # Saeulen (assets+800x600+grid) wird das Gate gruen, ohne irgendein Yang-Stub.
    bot = _make_bot()
    fake_detect, fake_geo = _fake_modules()
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      armed, missing = bot.phase0_gate()
    self.assertTrue(armed, missing)


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
    bot = _make_bot(mode=MODE_HAMMER, values=_values(**{'-ES_STACK_COUNT-': 3}))
    _arm(bot)
    bot.botting = True
    bot.runHack()  # INIT -> INVENTORY_BASE
    self.assertEqual(bot.state, EnergiesplitterBot.ST_INVENTORY_BASE)
    self.assertEqual(bot.hammer_remaining, bot.stack_count)

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


class TestHammerBuyXStacks(unittest.TestCase):
  """Aktion 1: stack_count mal einen 200er-Stack kaufen -> Auto-Stop."""

  def _buy_bot(self, stack_count=3):
    bot = _make_bot(mode=MODE_HAMMER,
                    values=_values(**{'-ES_STACK_COUNT-': stack_count}))
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.botting = True
    bot._free_slot_count = lambda: 10
    bot._locate_shop_item = lambda item: (100, 90)
    bot._bag_count_measurable = lambda: False  # Re-Read traegt nicht -> True
    return bot

  def test_three_stacks_three_buys_then_stop(self):
    _reset_input()
    bot = self._buy_bot(stack_count=3)
    # Jeder Buy-Step kauft genau 1 Stack (Re-Read verifiziert via not-messbar).
    for _ in range(20):
      if not bot.botting:
        break
      bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'done')
    self.assertEqual(bot.gekauft, 3)
    self.assertEqual(_INPUT_CALLS['right'], 3)

  def test_check_done_stops_at_target(self):
    bot = self._buy_bot(stack_count=2)
    bot.gekauft = 2
    bot.state = EnergiesplitterBot.ST_CHECK_DONE
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'done')

  def test_measurable_requires_growth(self):
    # Bag messbar -> Kauf nur verifiziert, wenn der Hammer-Bestand wuchs.
    _reset_input()
    bot = self._buy_bot(stack_count=1)
    bot.consecutive_unverified_stop = 1
    bot._bag_count_measurable = lambda: True
    bot._count_hammers = lambda: 0   # waechst NIE -> unverifiziert
    bot.runHack()
    self.assertEqual(bot.gekauft, 0)
    self.assertNotEqual(bot.state, EnergiesplitterBot.ST_CHECK_DONE)

  def test_relocate_used_each_buy(self):
    _reset_input()
    bot = self._buy_bot(stack_count=1)
    seen = {}
    bot._locate_shop_item = lambda item: (seen.__setitem__('item', item)
                                          or (200, 50))
    bot.runHack()
    self.assertEqual(seen['item'], 'hammer')
    self.assertEqual(bot._hammer_slot, (200, 50))
    self.assertEqual(_INPUT_CALLS['right'], 1)
    self.assertEqual(bot.gekauft, 1)

  def test_relocate_miss_falls_back_to_cached(self):
    _reset_input()
    bot = self._buy_bot(stack_count=1)
    bot._hammer_slot = (100, 90)
    bot._locate_shop_item = lambda item: None  # Re-Lokalisierung scheitert
    bot.runHack()
    self.assertEqual(_INPUT_CALLS['right'], 1)
    self.assertEqual(bot.gekauft, 1)

  def test_no_slot_at_all_stops_without_input(self):
    _reset_input()
    bot = self._buy_bot(stack_count=1)
    bot._hammer_slot = None
    bot._locate_shop_item = lambda item: None
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'item_not_in_shop')
    self.assertEqual(_INPUT_CALLS['right'], 0)

  def test_max_actions_still_caps_buys(self):
    # max_actions greift weiter (OCR-unabhaengiger Backstop).
    _reset_input()
    bot = self._buy_bot(stack_count=100)
    bot.max_actions = 2
    bot.actions_done = 2
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_actions')
    self.assertEqual(_INPUT_CALLS['right'], 0)


class TestArmedPurchaseDoesInput(unittest.TestCase):
  """Gegenprobe: bei echtem GATE-gruen + verifiziertem Kauf wird der
  Rechtsklick tatsaechlich ausgeloest (Gate sperrt NICHT faelschlich)."""

  def test_verified_hammer_buy(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER,
                    values=_values(**{'-ES_STACK_COUNT-': 1}))
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.botting = True
    bot._free_slot_count = lambda: 5
    bot._locate_shop_item = lambda item: (100, 90)
    bot._bag_count_measurable = lambda: False
    bot.runHack()
    self.assertEqual(_INPUT_CALLS['right'], 1)
    self.assertEqual(bot.gekauft, 1)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_CHECK_DONE)


class TestScharfSwitch(unittest.TestCase):
  """Bewusster 'scharf'-Schalter = Umkehrung von dry_run (EINE Wahrheit)."""

  def test_default_not_scharf(self):
    bot = _make_bot()
    self.assertTrue(bot.dry_run)
    self.assertFalse(bot.scharf)

  def test_scharf_setter_clears_dry_run(self):
    bot = _make_bot()
    bot.scharf = True
    self.assertFalse(bot.dry_run)
    self.assertTrue(bot.scharf)

  def test_not_scharf_blocks_all_input(self):
    _reset_input()
    bot = _make_bot()
    bot.armed = True
    bot.scharf = False        # = dry_run True
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)


class TestDaggerSequential(unittest.TestCase):
  """Aktion 2: Dolche werden EINZELN NACHEINANDER verarbeitet (1 Drag je Dolch)."""

  def test_buy_one_queues_landing_slot(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER,
                    values=_values(**{'-ES_DAGGERS_PER_ROUND-': 1}))
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_ONE_DOLCH
    bot.botting = True
    bot.hammer_remaining = 5
    bot._round_to_buy = 1
    bot._dagger_queue = []
    bot._locate_shop_item = lambda item: (300, 200)
    bot._inventory_signature = lambda: object()
    bot._diff_landing_slot = lambda a, b: (7, 7)
    bot.runHack()
    self.assertEqual(bot._dolche_gekauft, 1)
    # Nach dem (einzigen) Kauf der Runde -> Verarbeitung begonnen (erster Dolch).
    self.assertEqual(bot.state, EnergiesplitterBot.ST_PROCESS_DRAG)
    self.assertEqual(bot._dolch_inv_slot, (7, 7))
    self.assertEqual(_INPUT_CALLS['right'], 1)

  def test_two_per_round_buys_two_before_processing(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER,
                    values=_values(**{'-ES_DAGGERS_PER_ROUND-': 2}))
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_ONE_DOLCH
    bot.botting = True
    bot.hammer_remaining = 5
    bot._round_to_buy = 2
    bot._dagger_queue = []
    slots = [(7, 7), (8, 8)]
    bot._locate_shop_item = lambda item: (300, 200)
    bot._inventory_signature = lambda: object()
    bot._diff_landing_slot = lambda a, b: slots.pop(0)
    bot.runHack()   # kauft Dolch 1 (round_to_buy 2->1), bleibt im BUY-State
    self.assertEqual(bot.state, EnergiesplitterBot.ST_BUY_ONE_DOLCH)
    self.assertEqual(bot._round_to_buy, 1)
    bot.runHack()   # kauft Dolch 2 (round_to_buy 1->0) -> Verarbeitung beginnt
    self.assertEqual(bot.state, EnergiesplitterBot.ST_PROCESS_DRAG)
    self.assertEqual(bot._dolche_gekauft, 2)
    self.assertEqual(len(bot._dagger_queue), 1)  # 1 verarbeitet, 1 wartet
    self.assertEqual(_INPUT_CALLS['right'], 2)

  def test_drag_records_hammer_count_before(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_PROCESS_DRAG
    bot.botting = True
    bot._dolch_inv_slot = (5, 5)
    bot._classified_hammer_slot = lambda: (1, 1)
    bot._slot_is = lambda item, slot: True
    bot._count_hammers = lambda: 4
    bot._shot = lambda: object()
    bot.runHack()
    self.assertEqual(bot._hammer_count_before_proc, 4)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_VERIFY_PROCESS)

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

  def test_verified_process_continues_queue(self):
    # Verifiziert -> dekrementiert, naechster Dolch der Runde wird verarbeitet.
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.hammer_remaining = 3
    bot.splitter_summe = 0
    bot._dolche_gekauft = 2
    bot._dagger_queue = [(9, 9)]   # noch ein Dolch wartet
    bot._before_proc = object()
    bot.state = EnergiesplitterBot.ST_VERIFY_PROCESS
    bot.botting = True
    bot._shot = lambda: object()
    bot.verify_process = lambda a, b: 1
    bot.runHack()
    self.assertEqual(bot.splitter_summe, 1)
    self.assertEqual(bot.hammer_remaining, 2)
    self.assertEqual(bot._dolch_inv_slot, (9, 9))
    self.assertEqual(bot.state, EnergiesplitterBot.ST_PROCESS_DRAG)

  def test_verified_process_empty_queue_rescans(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.hammer_remaining = 3
    bot.splitter_summe = 0
    bot._dolche_gekauft = 1
    bot._dagger_queue = []          # Runde fertig
    bot._before_proc = object()
    bot.state = EnergiesplitterBot.ST_VERIFY_PROCESS
    bot.botting = True
    bot._shot = lambda: object()
    bot.verify_process = lambda a, b: 1
    bot.runHack()
    self.assertEqual(bot.state, EnergiesplitterBot.ST_RESCAN)

  def test_no_growth_no_decrement_then_stop(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.hammer_remaining = 3
    bot.splitter_summe = 0
    bot.consecutive_unverified_stop = 1
    bot._before_proc = object()
    bot.state = EnergiesplitterBot.ST_VERIFY_PROCESS
    bot.botting = True
    bot._shot = lambda: object()
    bot.verify_process = lambda a, b: 0   # KEIN Beleg
    bot.runHack()
    self.assertEqual(bot.hammer_remaining, 3)
    self.assertFalse(bot.botting)

  def test_rescan_stops_when_no_hammers(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_RESCAN
    bot.botting = True
    bot._count_hammers = lambda: 0
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'done')

  def test_rescan_next_round_when_hammers_left(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_RESCAN
    bot.botting = True
    bot._count_hammers = lambda: 5
    bot.runHack()
    self.assertEqual(bot.state, EnergiesplitterBot.ST_LOCATE_DOLCH)

  def test_inventory_base_no_hammers_stops(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_INVENTORY_BASE
    bot.botting = True
    bot._item_template_ready = lambda item: True
    bot._count_hammers = lambda: 0
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'done')


class TestDaggerVerifyByReRead(unittest.TestCase):
  """Grundwahrheit: KEIN Dialog -> verify = Dolch-Slot leer UND Hammer
  dekrementiert (Re-Read), NICHT Splitter-Aussehen."""

  def test_slot_empty_and_hammer_drop_verifies(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot._dolch_inv_slot = (5, 5)
    bot._hammer_count_before_proc = 3
    fake_detect = types.SimpleNamespace()
    with mock.patch.object(esbot_mod, '_detect', fake_detect):
      bot._slot_is_empty = lambda slot, bgr=None: True
      bot._bag_count_measurable = lambda: True
      bot._count_hammers = lambda: 2   # 3 -> 2 = -1
      out = bot.verify_process(object(), object())
    self.assertEqual(out, 1)

  def test_slot_not_empty_fails(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot._dolch_inv_slot = (5, 5)
    bot._hammer_count_before_proc = 3
    fake_detect = types.SimpleNamespace()
    with mock.patch.object(esbot_mod, '_detect', fake_detect):
      bot._slot_is_empty = lambda slot, bgr=None: False   # Dolch noch da
      bot._bag_count_measurable = lambda: True
      bot._count_hammers = lambda: 2
      out = bot.verify_process(object(), object())
    self.assertEqual(out, 0)

  def test_hammer_not_dropped_fails_when_measurable(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot._dolch_inv_slot = (5, 5)
    bot._hammer_count_before_proc = 3
    fake_detect = types.SimpleNamespace()
    with mock.patch.object(esbot_mod, '_detect', fake_detect):
      bot._slot_is_empty = lambda slot, bgr=None: True
      bot._bag_count_measurable = lambda: True
      bot._count_hammers = lambda: 3   # NICHT gesunken
      out = bot.verify_process(object(), object())
    self.assertEqual(out, 0)


class TestEnsureInventoryOpen(unittest.TestCase):
    """Der Energiesplitter muss -- wie das Angel-Inventar -- die Tasche-Offen-
    Erkennung nutzen (open_probe) statt blind zu scannen. Sonst las er bei
    geschlossener Tasche 0 freie Plaetze (-> falscher no_space)."""

    def test_open_when_probe_true_proceeds(self):
        bot = _make_bot(mode=MODE_HAMMER)
        _arm(bot)
        fake = types.SimpleNamespace(
            ensure_inventory_open=lambda **kw: True)
        with mock.patch.object(esbot_mod, '_open_probe', fake), \
             mock.patch.object(esbot_mod, '_INV_CALIB', {'tabs': {}}):
            self.assertTrue(bot._ensure_inventory_open())
        self.assertNotEqual(bot._stop_reason, 'inventory_not_open')

    def test_closed_unopenable_stops(self):
        bot = _make_bot(mode=MODE_HAMMER)
        _arm(bot)
        bot.botting = True
        fake = types.SimpleNamespace(
            ensure_inventory_open=lambda **kw: False)
        with mock.patch.object(esbot_mod, '_open_probe', fake), \
             mock.patch.object(esbot_mod, '_INV_CALIB', {'tabs': {}}):
            self.assertFalse(bot._ensure_inventory_open())
        self.assertEqual(bot._stop_reason, 'inventory_not_open')
        self.assertFalse(bot.botting)

    def test_probe_unavailable_does_not_block(self):
        # headless / kein Inventar-Paket -> nicht blockieren (GATE deckt ab).
        bot = _make_bot(mode=MODE_HAMMER)
        _arm(bot)
        with mock.patch.object(esbot_mod, '_open_probe', None):
            self.assertTrue(bot._ensure_inventory_open())

    def test_presses_configured_hotkey_when_closed(self):
        # Bei geschlossener Tasche wird die konfigurierte Toggle-Taste gedrueckt.
        _reset_input()
        bot = _make_bot(mode=MODE_HAMMER)
        _arm(bot)
        bot.inventory_hotkey = 'i'
        # Fake-Probe: ruft press_fn EINMAL (simuliert 'war zu, jetzt offen').
        def _ensure(**kw):
            kw['press_fn']()
            return True
        fake = types.SimpleNamespace(ensure_inventory_open=_ensure)
        with mock.patch.object(esbot_mod, '_open_probe', fake), \
             mock.patch.object(esbot_mod, '_INV_CALIB', {'tabs': {}}):
            bot._ensure_inventory_open()
        self.assertEqual(_INPUT_CALLS['keyDown'], 1)   # genau eine Taste


class TestWindowFocus(unittest.TestCase):
  """Tasten brauchen FOKUS -- der Bot muss das Spiel-Fenster in den Vordergrund
  holen (sonst landet z.B. die Vogelperspektive 'g' im Bot-Fenster). Genau das
  fehlte -> NPC-Suche drehte sich endlos, weil 'g' nie im Spiel ankam."""

  def test_press_key_focuses_game_first(self):
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.wincap.hwnd = 1234
    calls = []
    with mock.patch.object(esbot_mod, '_focus_window',
                           lambda h: calls.append(h) or True):
      ok = bot._press_key('g')
    self.assertTrue(ok)
    self.assertEqual(calls, [1234])      # vor dem Tastendruck fokussiert

  def test_simulation_does_not_focus_or_press(self):
    # Im Simulationsmodus (dry_run) ist _press_key ein No-op -> kein Fokus-Klau.
    bot = _make_bot(mode=MODE_HAMMER)
    bot.armed = True
    bot.dry_run = True
    bot.wincap.hwnd = 1234
    calls = []
    with mock.patch.object(esbot_mod, '_focus_window',
                           lambda h: calls.append(h) or True):
      ok = bot._press_key('g')
    self.assertFalse(ok)
    self.assertEqual(calls, [])

  def test_run_focuses_game_once_at_start(self):
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.wincap.hwnd = 4321
    bot.botting = True
    bot.state = EnergiesplitterBot.ST_INIT
    calls = []
    with mock.patch.object(esbot_mod, '_focus_window',
                           lambda h: calls.append(h) or True):
      bot.runHack()                      # erster scharfer Tick (ST_INIT)
    self.assertTrue(bot._did_focus)
    self.assertEqual(calls, [4321])      # genau einmal in den Vordergrund


class TestApproachNpcBirdseyeRetry(unittest.TestCase):
  """NPC nicht erkannt -> Vogelperspektive umschalten, Kamera Zeit geben und
  MEHRFACH erneut suchen, bevor sauber gestoppt wird. Inkl. Regression fuer den
  t()-Crash ('multiple values for argument key')."""

  def _miss_detect(self, hits_on=None, counter=None):
    # find_npc_name: Treffer ab dem ``hits_on``-ten Aufruf (None = nie).
    def _find(bgr, tpl):
      counter['n'] += 1
      if hits_on is not None and counter['n'] >= hits_on:
        return (True, (50, 60), 0.95)
      return (False, None, 0.0)
    return types.SimpleNamespace(find_npc_name=_find)

  def test_miss_toggles_birdseye_n_times_then_stops_cleanly(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.NPC_SETTLE_S = 0          # keine Wartezeit im Test
    bot._template = lambda k: object()
    counter = {'n': 0}
    with mock.patch.object(esbot_mod, '_detect',
                           self._miss_detect(hits_on=None, counter=counter)):
      results = [bot.approach_npc('npc_alchemist')
                 for _ in range(EnergiesplitterBot.NPC_MAX_TRIES + 2)]
    # KEIN Treffer -> immer None; Vogelperspektive genau NPC_MAX_TRIES mal
    # gedrueckt (keyDown), danach sauberer Stop -- und KEINE Exception (t-Bug).
    self.assertTrue(all(r is None for r in results))
    self.assertEqual(_INPUT_CALLS['keyDown'], EnergiesplitterBot.NPC_MAX_TRIES)
    self.assertEqual(bot._stop_reason, 'npc_not_found')

  def test_found_after_retries_returns_point_no_stop(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.NPC_SETTLE_S = 0
    bot.botting = True
    bot._template = lambda k: object()
    counter = {'n': 0}
    pt = None
    with mock.patch.object(esbot_mod, '_detect',
                           self._miss_detect(hits_on=3, counter=counter)):
      for _ in range(EnergiesplitterBot.NPC_MAX_TRIES + 1):
        pt = bot.approach_npc('npc_alchemist')
        if pt is not None:
          break
    self.assertEqual(pt, (50, 60))
    self.assertNotEqual(bot._stop_reason, 'npc_not_found')
    self.assertTrue(bot.botting)            # nicht gestoppt
    self.assertEqual(bot._npc_tries, 0)     # nach Treffer zurueckgesetzt

  def test_birdseye_disabled_stops_immediately(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.birdseye_on_miss = False
    bot._template = lambda k: object()
    counter = {'n': 0}
    with mock.patch.object(esbot_mod, '_detect',
                           self._miss_detect(hits_on=None, counter=counter)):
      out = bot.approach_npc('npc_alchemist')
    self.assertIsNone(out)
    self.assertEqual(_INPUT_CALLS['keyDown'], 0)   # keine Vogelperspektive
    self.assertEqual(bot._stop_reason, 'npc_not_found')


if __name__ == '__main__':
  unittest.main()
