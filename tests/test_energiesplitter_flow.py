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
                 'actions_done', 'gold_spent', '_planned_spent',
                 'consecutive_unverified'):
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
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: True)
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
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: True)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('item:hammer', missing)

  def test_uncalibrated_blocks(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: False,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: True)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('calibration:800x600', missing)

  def test_content_uncalibrated_blocks(self):
    # FIX 2: Fenster-Groesse OK, aber Inhalt liest NICHT plausibel -> rot.
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: False)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('content_calibration', missing)

  def test_content_check_missing_function_blocks(self):
    # Fehlt is_calibrated am Reader (alter Build) -> defensiv rot, kein Crash.
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1)  # KEIN is_calibrated
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('content_calibration', missing)

  def test_content_check_never_raises(self):
    # is_calibrated wirft -> defensiv rot, kein Crash.
    bot = _make_bot()
    def _boom(*a, **k):
      raise RuntimeError('frame kaputt')
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=_boom)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('content_calibration', missing)


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

  def test_yang_check_false_does_not_weaken_input_gate(self):
    # yang_check=FALSE entfernt NUR die live Yang-Wand -- der Eingabe-GATE
    # (_guarded: dry_run/armed/abort) bleibt UNVERAENDERT: kein Input im dry_run.
    _reset_input()
    bot = _make_bot()
    bot.yang_check = False
    bot.dry_run = True
    bot.botting = True
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(sum(_INPUT_CALLS.values()), 0, _INPUT_CALLS)
    self.assertFalse(bot._right_click(10, 10))
    self.assertFalse(bot._press_key('g'))
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


class TestYangCheckDisabled(unittest.TestCase):
  """yang_check=FALSE (RISIKO-Pfad): der LIVE-Yang-Gate entfaellt, ABER
  max_actions UND ein FESTER max_gold_spend-Deckel bleiben ZWINGEND wirksam und
  Erkennung-vor-Aktion bleibt UNVERAENDERT (Kauf/Drag nur bei GATE gruen)."""

  def _bot(self, gold, max_spend=10 ** 9, spent=0, price=15000, actions=0,
           planned_spent=0):
    bot = _make_bot()
    _arm(bot)
    bot.yang_check = False
    bot.gold_floor = 50000
    bot.max_gold_spend = max_spend
    bot.price_per_item = price
    bot.gold_spent = spent
    bot.actions_done = actions
    bot._planned_spent = planned_spent
    bot._read_gold = lambda: gold
    return bot

  # -- gold_floor-Wand AUS + unlesbares Yang blockiert NICHT --------------
  def test_unreadable_yang_does_not_stop(self):
    bot = self._bot(gold=None, max_spend=10 ** 9)
    bot.botting = True
    out = bot.gold_guard(15000)
    # Kein Stop, kein gold_unreadable -- Sentinel 0 (nicht-gatend) zurueck.
    self.assertEqual(out, 0)
    self.assertTrue(bot.botting)
    self.assertNotEqual(bot._stop_reason, 'gold_unreadable')

  def test_live_gold_floor_wall_off(self):
    # Gold knapp ueber 0, weit unter floor -> mit yang_check=TRUE wuerde
    # gold_floor stoppen; mit FALSE laeuft es weiter (Wand ist aus).
    bot = self._bot(gold=1000, max_spend=10 ** 9)
    bot.botting = True
    out = bot.gold_guard(15000)
    self.assertTrue(bot.botting)
    self.assertNotEqual(bot._stop_reason, 'gold_floor')
    self.assertEqual(out, 1000)  # lesbares Gold wird opportunistisch zurueckgegeben

  # -- FESTER max_gold_spend-Deckel bleibt ZWINGEND ----------------------
  def test_fixed_spend_cap_still_stops(self):
    # Deckel = _planned_spent + planned_cost. 45000 + 15000 = 60000 > 50000.
    bot = self._bot(gold=10 ** 9, max_spend=50000, planned_spent=45000)
    bot.botting = True
    out = bot.gold_guard(15000)
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')

  def test_fixed_spend_cap_uses_prediction_not_yang_delta(self):
    # Selbst bei UNLESBAREM Yang (kein Delta verfuegbar) greift der Deckel ueber
    # den geplanten Akkumulator -> OCR-unabhaengig wirksam.
    bot = self._bot(gold=None, max_spend=50000, planned_spent=45000)
    bot.botting = True
    out = bot.gold_guard(15000)
    self.assertIsNone(out)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')

  def test_under_cap_proceeds(self):
    bot = self._bot(gold=10 ** 9, max_spend=50000, planned_spent=15000)
    bot.botting = True
    out = bot.gold_guard(15000)   # 15000 + 15000 = 30000 <= 50000
    self.assertTrue(bot.botting)
    self.assertNotEqual(bot._stop_reason, 'max_gold_spend')

  def test_cap_counts_full_stack_cost_not_per_action(self):
    # KERN des Safety-Audit-Fix: ein Hammer-Stack-Kauf kostet stack*price, zaehlt
    # aber nur als EINE Aktion. Der Deckel MUSS die echten Stack-Kosten sehen,
    # nicht actions_done*price (das wuerde bei Stacks>1 grob unterzaehlen und der
    # Deckel waere keine echte zweite Wand).
    #   _planned_spent steht bereits bei 2.9 Mio (z.B. 1 Stack a 200*15000=3 Mio
    #   minus etwas), naechster 200er-Stack kostet 3 Mio -> Deckel 5 Mio -> Stop.
    bot = self._bot(gold=10 ** 9, max_spend=5_000_000, price=15000,
                    actions=1, planned_spent=2_900_000)
    bot.botting = True
    out = bot.gold_guard(200 * 15000)   # 2.9M + 3.0M = 5.9M > 5.0M
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')
    # Gegenprobe: die ALTE Prognose actions_done*price + planned_cost waere
    # 1*15000 + 3.0M = 3.015M <= 5.0M und haette FAELSCHLICH durchgelassen.
    self.assertLessEqual(bot.actions_done * bot.price_per_item + 200 * 15000,
                         bot.max_gold_spend)

  # -- max_actions bleibt wirksam ----------------------------------------
  def test_max_actions_still_effective(self):
    bot = self._bot(gold=10 ** 9)
    bot.max_actions = 2
    bot.actions_done = 2
    bot.botting = True
    self.assertTrue(bot._action_cap_hit())
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_actions')

  # -- Erkennung-vor-Aktion UNVERAENDERT ---------------------------------
  def test_guard_unchanged_dry_run_blocks_input(self):
    bot = self._bot(gold=10 ** 9)
    bot.dry_run = True            # nicht entsichert
    self.assertTrue(bot._guarded())   # yang_check aendert das GATE nicht

  def test_guard_unchanged_not_armed_blocks_input(self):
    bot = self._bot(gold=10 ** 9)
    bot.armed = False
    self.assertTrue(bot._guarded())

  # -- phase0_gate gruen OHNE Yang-Kalibrierung, aber MIT Grid/Templates --
  def test_phase0_green_without_yang_calibration(self):
    bot = _make_bot()
    bot.yang_check = False
    # assets_ready meldet NUR yang_digits fehlend -> mit yang_check=FALSE
    # gefiltert; Grid ist da (read_gold-Modul + _grid_present True).
    fake_detect = types.SimpleNamespace(
        assets_ready=lambda mode: (False, ['yang_digits']))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(
        read_gold=lambda b, r: 1,
        is_calibrated=lambda b, r=None: False,   # Yang liest NICHT plausibel
        _grid_present=lambda: True)              # ... aber das Grid ist da
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertTrue(armed, missing)
    self.assertEqual(missing, [])

  def test_phase0_still_needs_grid_when_yang_off(self):
    # yang_check=FALSE entfernt NUR die Yang-Lesbarkeit -- fehlt das Grid,
    # bleibt das Gate rot (keine sicheren Drag-/Slot-Ziele).
    bot = _make_bot()
    bot.yang_check = False
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: True,
                                      _grid_present=lambda: False)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('grid_calibration', missing)

  def test_phase0_yang_on_still_requires_content(self):
    # Gegenprobe: yang_check=TRUE (Default) -> die Yang-Inhalts-Verifikation
    # bleibt Pflicht; fehlende yang_digits + unlesbarer Inhalt halten rot.
    bot = _make_bot()
    bot.yang_check = True
    fake_detect = types.SimpleNamespace(
        assets_ready=lambda mode: (False, ['yang_digits']))
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True,
                                     gold_roi=lambda mode=None: (0, 0, 1, 1))
    fake_gold = types.SimpleNamespace(read_gold=lambda b, r: 1,
                                      is_calibrated=lambda b, r=None: False,
                                      _grid_present=lambda: True)
    with mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo), \
         mock.patch.object(esbot_mod, '_gold_reader', fake_gold):
      armed, missing = bot.phase0_gate()
    self.assertFalse(armed)
    self.assertIn('yang_digits', missing)
    self.assertIn('content_calibration', missing)


class TestRealSpendCapDrift(unittest.TestCase):
  """FIX 1: gold_spent wird per gelesenem Yang-Delta fortgeschrieben -- auch
  ohne Verifikation -- damit max_gold_spend die REAL kumulierte Abnahme deckelt."""

  def test_note_real_spend_adds_positive_delta(self):
    bot = _make_bot()
    bot.gold_spent = 0
    added = bot._note_real_spend(100000, 85000)
    self.assertEqual(added, 15000)
    self.assertEqual(bot.gold_spent, 15000)

  def test_note_real_spend_ignores_non_positive_and_none(self):
    bot = _make_bot()
    bot.gold_spent = 5000
    self.assertEqual(bot._note_real_spend(80000, 80000), 0)   # kein Delta
    self.assertEqual(bot._note_real_spend(80000, 90000), 0)   # negativ (Anstieg)
    self.assertEqual(bot._note_real_spend(80000, None), 0)    # unlesbar
    self.assertEqual(bot._note_real_spend(None, 80000), 0)
    self.assertEqual(bot.gold_spent, 5000)                    # unveraendert

  def test_unverified_hammer_buy_advances_cap(self):
    # Kauf real bezahlt (Gold sank um 150000) ABER nicht verifiziert
    # (Bag wuchs nicht) -> gold_spent MUSS dennoch um 150000 steigen, damit
    # der naechste gold_guard den Deckel korrekt anwendet.
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.hammer_count = 10
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.consecutive_unverified_stop = 99   # nicht am Unverified-Stop scheitern
    bot.botting = True
    golds = [500000, 350000]               # before, after: real -150000
    bot._read_gold = lambda: golds.pop(0)
    bot._plan_stacks = lambda target, free: [10]
    bot._locate_shop_item = lambda item: (100, 90)
    bot._bag_count_measurable = lambda: True
    bot._count_hammers = lambda: 0         # Bag wuchs NICHT -> unverifiziert
    bot.runHack()
    self.assertEqual(bot.gekauft, 0)       # NICHT als Kauf gezaehlt
    self.assertEqual(bot.gold_spent, 150000)  # aber realer Verbrauch verbucht

  def test_unverified_dagger_buy_advances_cap(self):
    _reset_input()
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_ONE_DOLCH
    bot.price_per_item = 15000
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.consecutive_unverified_stop = 99
    bot.botting = True
    golds = [200000, 185000]               # before, after: real -15000
    bot._read_gold = lambda: golds.pop(0)
    bot._locate_shop_item = lambda item: (300, 200)
    bot._inventory_signature = lambda: object()
    bot.verify_purchase = lambda gb, c: (False, 185000)   # bezahlt, unverifiziert
    bot.runHack()
    self.assertEqual(bot._dolche_gekauft, 0)
    self.assertEqual(bot.gold_spent, 15000)  # realer Verbrauch verbucht

  def test_cap_stops_after_unverified_drift(self):
    # Kern der Haertung: nach einem unverifizierten, real bezahlten Kauf
    # blockt der naechste gold_guard am Deckel -- der Cap driftet NICHT.
    bot = _make_bot()
    _arm(bot)
    bot.gold_floor = 0
    bot.max_gold_spend = 150000
    bot.gold_spent = 0
    # Simuliere den realen Verbrauch eines unverifizierten Kaufs:
    bot._note_real_spend(500000, 350000)   # +150000 -> Deckel ausgeschoepft
    self.assertEqual(bot.gold_spent, 150000)
    bot._read_gold = lambda: 350000
    bot.botting = True
    out = bot.gold_guard(15000)            # 150000 + 15000 > 150000 -> Stop
    self.assertIsNone(out)
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')


class TestPlannedSpendCapStack(unittest.TestCase):
  """Safety-Audit MEDIUM-Fix (yang_check=FALSE): der Deckel zaehlt die ECHTEN
  Stack-Kosten je Kauf (_planned_spent), nicht actions_done*price. Bei Stacks>1
  stoppt der Bot, NACHDEM die kumulierten Stack-Kosten den Deckel erreichen --
  nicht erst nach actions_done*price (das unterzaehlt systematisch)."""

  def test_planned_spent_accumulates_full_stack_cost(self):
    bot = _make_bot()
    bot._planned_spent = 0
    # Hammer-Stack 200 a 15000 = 3.0 Mio -- EIN Kauf, ECHTE Kosten.
    self.assertEqual(bot._note_planned_spend(200 * 15000), 3_000_000)
    self.assertEqual(bot._planned_spent, 3_000_000)
    # Zweiter Kauf addiert erneut die echten Kosten.
    bot._note_planned_spend(50 * 15000)
    self.assertEqual(bot._planned_spent, 3_750_000)

  def test_planned_spend_ignores_non_positive(self):
    bot = _make_bot()
    bot._planned_spent = 1000
    self.assertEqual(bot._note_planned_spend(0), 0)
    self.assertEqual(bot._note_planned_spend(-5), 0)
    self.assertEqual(bot._planned_spent, 1000)

  def test_reset_counters_zeroes_planned_spent(self):
    bot = _make_bot()
    bot._planned_spent = 99
    bot._reset_counters()
    self.assertEqual(bot._planned_spent, 0)

  def test_buy_step_stops_after_cumulative_stack_cost_hits_cap(self):
    # End-to-End ueber den ECHTEN Hammer-Buy-Step mit yang_check=FALSE:
    # Stack=50, price=15000 -> 750000 je Kauf. Deckel=1.6 Mio.
    # Kauf 1: 0 + 750000 <= 1.6M  -> OK   (-> _planned_spent=750000)
    # Kauf 2: 750000 + 750000 = 1.5M <= 1.6M -> OK (-> _planned_spent=1.5M)
    # Kauf 3: 1.5M + 750000 = 2.25M > 1.6M -> STOP (NACH 2 Kaeufen, nicht 100).
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.yang_check = False
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.hammer_count = 1000          # weit ueber dem, was der Deckel zulaesst
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 1_600_000
    bot.max_actions = 999            # NICHT der limitierende Backstop hier
    bot.price_per_item = 15000
    bot.botting = True
    # Yang lesbar UND sinkt real um die Stack-Kosten -> Kauf wird verifiziert
    # (gekauft steigt); der Deckel speist sich dennoch aus _planned_spent, nicht
    # aus dem Gold-Delta (yang_check=FALSE).
    gold = [10 ** 9]
    def _read():
      return gold[0]
    def _click(*a, **k):
      _INPUT_CALLS['right'] += 1
      gold[0] -= 50 * 15000   # echte Stack-Kosten fliessen ab
    bot._read_gold = _read
    bot._right_click = _click
    bot._plan_stacks = lambda target, free: [50]
    bot._locate_shop_item = lambda item: (100, 90)
    bot._bag_count_measurable = lambda: False   # Gold-Delta-Beleg traegt
    # Kauf-Schritt wiederholt fahren bis Stop.
    for _ in range(20):
      if not bot.botting:
        break
      bot._hammer_buy_step()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'max_gold_spend')
    # Genau 2 Kaeufe durften laufen (2*750000=1.5M <= Deckel; 3. haette ihn
    # gerissen). Der ALTE actions_done*price-Deckel haette 2*15000=30000 gesehen
    # und ~106 Kaeufe durchgelassen -- das war die Luecke.
    self.assertEqual(bot.gekauft, 100)        # 2 Stacks a 50
    self.assertEqual(bot._planned_spent, 1_500_000)
    self.assertEqual(_INPUT_CALLS['right'], 2)  # nur 2 reale Kaeufe ausgeloest


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

  def test_fallback_stack_sizes_match_addendum(self):
    # Ohne Live-Reader faellt der Bot auf die echten Hammer-Stacks (1/50/200)
    # zurueck -- nicht mehr das alte (200,100,10,1) Shop-Bild-Tupel.
    bot = _make_bot()
    with mock.patch.object(esbot_mod, '_detect', None):
      self.assertEqual(bot._read_shop_stack_sizes(), (200, 50, 1))


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


class TestHammerPerBuyRelocate(unittest.TestCase):
  """Pro Kauf wird der Shop-Hammer per Template neu lokalisiert; Re-Lokalisierung
  scharf vorgeschaltet, mit Rueckfall auf den verifizierten Slot."""

  def test_relocate_used_when_available(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (1, 1)
    bot.hammer_count = 10
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.botting = True
    golds = [500000, 500000 - 150000]
    bot._read_gold = lambda: golds.pop(0)
    bot._plan_stacks = lambda target, free: [10]
    seen = {}
    bot._locate_shop_item = lambda item: (seen.__setitem__('item', item) or (200, 50))
    bot.runHack()
    self.assertEqual(seen['item'], 'hammer')
    self.assertEqual(bot._hammer_slot, (200, 50))  # re-lokalisiert, nicht stale
    self.assertEqual(_INPUT_CALLS['right'], 1)
    self.assertEqual(bot.gekauft, 10)

  def test_relocate_miss_falls_back_to_cached(self):
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
    golds = [500000, 350000]
    bot._read_gold = lambda: golds.pop(0)
    bot._plan_stacks = lambda target, free: [10]
    bot._locate_shop_item = lambda item: None   # Re-Lokalisierung scheitert
    bot.runHack()
    self.assertEqual(_INPUT_CALLS['right'], 1)   # Rueckfall-Slot geklickt
    self.assertEqual(bot.gekauft, 10)

  def test_no_slot_at_all_stops_without_input(self):
    _reset_input()
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = None
    bot.hammer_count = 10
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.botting = True
    bot._read_gold = lambda: 500000
    bot._plan_stacks = lambda target, free: [10]
    bot._locate_shop_item = lambda item: None
    bot.runHack()
    self.assertFalse(bot.botting)
    self.assertEqual(bot._stop_reason, 'item_not_in_shop')
    self.assertEqual(_INPUT_CALLS['right'], 0)


class TestHammerBagGrowthGate(unittest.TestCase):
  """Bag-Stack-Beleg: erzwungen nur wenn messbar; sonst Gold-Delta traegt."""

  def _buy_bot(self):
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.hammer_count = 10
    bot.gekauft = 0
    bot.gold_floor = 0
    bot.max_gold_spend = 10 ** 9
    bot.botting = True
    bot._plan_stacks = lambda target, free: [10]
    bot._locate_shop_item = lambda item: (100, 90)
    return bot

  def test_not_measurable_skips_bag_check(self):
    _reset_input()
    bot = self._buy_bot()
    golds = [500000, 350000]
    bot._read_gold = lambda: golds.pop(0)
    bot._bag_count_measurable = lambda: False
    bot.runHack()
    self.assertEqual(bot.gekauft, 10)
    self.assertEqual(bot.state, EnergiesplitterBot.ST_CHECK_DONE)

  def test_measurable_requires_growth(self):
    _reset_input()
    bot = self._buy_bot()
    bot.consecutive_unverified_stop = 1
    golds = [500000, 350000]   # Gold sank korrekt ...
    bot._read_gold = lambda: golds.pop(0)
    bot._bag_count_measurable = lambda: True
    bot._count_hammers = lambda: 0   # ... aber Bag wuchs NICHT
    bot.runHack()
    self.assertEqual(bot.gekauft, 0)          # NICHT als Kauf gezaehlt
    self.assertNotEqual(bot.state, EnergiesplitterBot.ST_CHECK_DONE)


class TestDaggerVerifyByReRead(unittest.TestCase):
  """Neue Grundwahrheit: KEIN Dialog -> verify = Dolch-Slot leer UND Hammer
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


if __name__ == '__main__':
  unittest.main()
