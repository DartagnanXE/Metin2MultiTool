"""Belegt, dass das Energiesplitter-Modul an den Schluessel-Punkten LUECKENLOS
strukturiert loggt (ABSICHT / WAHRNEHMUNG / FEHLER-STOPP / ZUSTAND).

Stub-Muster identisch zu ``tests/test_energiesplitter_flow.py``: die Windows-only
Treiber + Agent-A-Module sind gestubbt, der Bot laeuft gegen den ECHTEN Code.
Die Logs werden ueber eine zusaetzliche ``log.add_sink``-Senke aufgefangen (das
EINE Singleton ``debuglog.log``, das alle Module via ``from debuglog import log``
teilen) -- so beweisen die Tests, dass eine erwartete Log-Zeile real emittiert
wurde, ohne den Logger zu mocken.

Grundregel-Check inklusive: das Logging darf NIE werfen und NIE das Verhalten
aendern (eine kaputte Senke stoppt den Bot nicht).
"""

import os
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
  sys.path.insert(0, _REPO_ROOT)


def _install_stubs():
  pdi = types.ModuleType('pydirectinput')
  pdi.PAUSE = 0
  pdi.click = lambda *a, **k: None
  pdi.moveTo = lambda *a, **k: None
  pdi.press = lambda *a, **k: None
  pdi.keyDown = lambda *a, **k: None
  pdi.keyUp = lambda *a, **k: None
  pdi.mouseDown = lambda *a, **k: None
  pdi.mouseUp = lambda *a, **k: None
  sys.modules['pydirectinput'] = pdi
  for name in ('win32gui', 'win32ui', 'win32con', 'win32api'):
    sys.modules.setdefault(name, types.ModuleType(name))


_install_stubs()

import energiesplitter.bot as esbot_mod              # noqa: E402
from energiesplitter.bot import (                     # noqa: E402
    EnergiesplitterBot, MODE_HAMMER, MODE_DAGGER)
from debuglog import log                              # noqa: E402


class _FakeWincap:
  offset_x = 0
  offset_y = 0

  def __init__(self, *a, **k):
    self._shot = object()

  def get_screenshot(self):
    return self._shot


def _values(**over):
  base = {
      '-ES_STACK_COUNT-': 1, '-ES_FREISCHALTEN-': False,
      '-ES_DAGGERS_PER_ROUND-': 1, '-ES_MAX_ACTIONS-': 0,
      '-ES_UNVERIF_STOP-': 3, '-ES_DRY_RUN-': True,
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
  bot.armed = True
  bot.dry_run = False


class _Capture:
  """Faengt alle emittierten Log-Zeilen ueber eine additive Senke."""

  def __init__(self):
    self.lines = []

  def __enter__(self):
    log.add_sink(self._sink)
    return self

  def __exit__(self, *exc):
    log.remove_sink(self._sink)
    return False

  def _sink(self, line):
    self.lines.append(line)

  def has(self, needle):
    return any(needle in ln for ln in self.lines)

  def matching(self, needle):
    return [ln for ln in self.lines if needle in ln]


class TestConfigSectionLogged(unittest.TestCase):
  def test_config_state_logged_on_section(self):
    bot = _make_bot()
    with _Capture() as cap:
      bot._log_section()
    self.assertTrue(cap.has('Konfiguration'), cap.lines)
    self.assertTrue(cap.has('stack_count=1'), cap.lines)
    self.assertTrue(cap.has('daggers_per_round='), cap.lines)
    # Simulation-Kennzeichnung im Config-Log.
    self.assertTrue(cap.has('SIMULATION') or cap.has('betrieb='), cap.lines)

  def test_gate_red_lists_missing(self):
    # Phase-0 ohne Assets -> GATE rot, fehlende Artefakte in der Config-Sektion.
    bot = _make_bot()
    self.assertFalse(bot.armed)
    with _Capture() as cap:
      bot._log_section()
    self.assertTrue(cap.has('GATE rot'), cap.lines)


class TestGatePerceptionLogged(unittest.TestCase):
  def test_phase0_logs_red_with_missing_list(self):
    bot = _make_bot()
    with _Capture() as cap:
      bot.phase0_gate()
    self.assertTrue(cap.has('Phase-0-GATE: rot'), cap.lines)
    self.assertTrue(cap.has('fehlend='), cap.lines)

  def test_phase0_logs_green(self):
    bot = _make_bot()
    fake_detect = types.SimpleNamespace(assets_ready=lambda mode: (True, []),
                                        grid_present=lambda: True)
    fake_geo = types.SimpleNamespace(is_calibrated=lambda w: True)
    with _Capture() as cap, \
         mock.patch.object(esbot_mod, '_detect', fake_detect), \
         mock.patch.object(esbot_mod, '_geometry', fake_geo):
      bot.phase0_gate()
    self.assertTrue(cap.has('Phase-0-GATE: gruen'), cap.lines)


class TestGateStopLogged(unittest.TestCase):
  def test_dry_run_stop_logs_phase0_not_ready(self):
    bot = _make_bot()
    bot.botting = True
    with _Capture() as cap:
      bot.runHack()
    self.assertFalse(bot.botting)
    self.assertTrue(cap.has('Phase-0') or cap.has('GATE rot'), cap.lines)


class TestHammerVerifyLogged(unittest.TestCase):
  def test_hammer_purchase_verification_logged(self):
    bot = _make_bot()
    _arm(bot)
    bot._bag_count_measurable = lambda: True
    bot._count_hammers = lambda: 1
    with _Capture() as cap:
      bot.verify_hammer_purchase(0)
    self.assertTrue(cap.has('WAHRNEHMUNG: Hammer-Kauf-Verifikation (Re-Read)'),
                    cap.lines)


class TestSimIntentLogged(unittest.TestCase):
  """Im Simulations-Modus (dry_run/nicht scharf) wird die VOLLE Absicht als
  '[SIM] wuerde ...' geloggt -- ohne dass etwas gekauft wird."""

  def test_sim_hammer_buy_intent_logged(self):
    bot = _make_bot(mode=MODE_HAMMER)
    # armed, aber NICHT scharf -> Simulation.
    bot.armed = True
    bot.dry_run = True
    bot.state = EnergiesplitterBot.ST_BUY_LOOP
    bot._hammer_slot = (100, 90)
    bot.stack_count = 3
    bot.gekauft = 0
    bot.botting = True
    bot._free_slot_count = lambda: 5
    bot._locate_shop_item = lambda item: (100, 90)
    with _Capture() as cap:
      bot._hammer_buy_step()
    self.assertTrue(cap.has('[SIM] wuerde'), cap.lines)
    self.assertTrue(cap.has('200er-Hammer-Stack kaufen'), cap.lines)

  def test_sim_dagger_drag_intent_logged(self):
    bot = _make_bot(mode=MODE_DAGGER)
    bot.armed = True
    bot.dry_run = True
    bot.state = EnergiesplitterBot.ST_PROCESS_DRAG
    bot.botting = True
    bot._dolch_inv_slot = (5, 5)
    bot._classified_hammer_slot = lambda: (1, 1)
    bot._slot_is = lambda item, slot: True
    bot._count_hammers = lambda: 4
    bot._shot = lambda: object()
    bot._slot_center = lambda s: (int(s[0]), int(s[1]))
    with _Capture() as cap:
      bot._dagger_process_drag()
    self.assertTrue(cap.has('WAHRNEHMUNG: Slot-Klassifikation vor Drag'), cap.lines)
    self.assertTrue(cap.has('[SIM] wuerde'), cap.lines)
    self.assertTrue(cap.has('Hammer-Stack auf Dolch-Slot ziehen'), cap.lines)


class TestPerceptionLogged(unittest.TestCase):
  def test_drag_unsafe_logs_reason(self):
    bot = _make_bot(mode=MODE_DAGGER)
    _arm(bot)
    bot.state = EnergiesplitterBot.ST_PROCESS_DRAG
    bot.botting = True
    bot._dolch_inv_slot = (5, 5)
    bot._classified_hammer_slot = lambda: None   # Quelle nicht Hammer
    bot._slot_is = lambda item, slot: True
    with _Capture() as cap:
      bot._dagger_process_drag()
    self.assertEqual(bot._stop_reason, 'drag_unsafe')
    self.assertTrue(cap.has('WAHRNEHMUNG: Slot-Klassifikation vor Drag'), cap.lines)
    self.assertTrue(cap.has('FEHLER: Drag unsicher'), cap.lines)


class TestLoggingNeverThrowsNeverChangesBehavior(unittest.TestCase):
  def test_broken_sink_does_not_stop_bot(self):
    # Eine werfende Senke darf den Bot NICHT kippen (Verhalten unveraendert).
    def _boom(_line):
      raise RuntimeError('kaputte Senke')
    bot = _make_bot()
    bot.botting = True
    log.add_sink(_boom)
    try:
      bot.runHack()   # darf nicht durchschlagen
    finally:
      log.remove_sink(_boom)
    self.assertFalse(bot.botting)   # sauberer Selbst-Stop, kein Crash

  def test_tick_exception_is_logged_and_reraised(self):
    # Logging schluckt den Fehler NICHT (das waere Verhaltensaenderung).
    bot = _make_bot(mode=MODE_HAMMER)
    _arm(bot)
    bot.botting = True
    def _boom():
      raise RuntimeError('tick kaputt')
    bot._tick_hammer = _boom
    with _Capture() as cap:
      with self.assertRaises(RuntimeError):
        bot.runHack()
    self.assertTrue(cap.has('FEHLER: unerwartete Ausnahme im Tick'), cap.lines)


if __name__ == '__main__':
  unittest.main()
