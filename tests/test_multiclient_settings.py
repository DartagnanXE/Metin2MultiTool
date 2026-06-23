# -*- coding: utf-8 -*-
"""Tests fuer multiclient_settings -- reine Logik (headless, kein win32/GUI).

Deckt das ab, was OHNE echtes Spiel/Anzeige verifizierbar ist: Slot-Modell,
count-Clamp 1-4, (De)Serialisierung, immutable Updates, Dedup, Validierung und
die Ableitung der Launcher-Specs. GUI/Klick-Erfassung sind LIVE-only und hier
bewusst NICHT abgedeckt.
"""

import multiclient_settings as mc


class TestClampCount:
    def test_in_range_passthrough(self):
        assert mc.clamp_count(1) == 1
        assert mc.clamp_count(2) == 2
        assert mc.clamp_count(4) == 4

    def test_below_min_and_above_max(self):
        assert mc.clamp_count(0) == mc.MIN_CLIENTS
        assert mc.clamp_count(-5) == mc.MIN_CLIENTS
        assert mc.clamp_count(9) == mc.MAX_CLIENTS

    def test_non_int_defensive(self):
        assert mc.clamp_count(None) == mc.MIN_CLIENTS
        assert mc.clamp_count('zwei') == mc.MIN_CLIENTS
        assert mc.clamp_count(2.0) == 2  # numerisch akzeptiert


class TestNormalizeMode:
    def test_valid_passthrough(self):
        for m in mc.MODES:
            assert mc.normalize_mode(m) == m

    def test_invalid_to_default(self):
        assert mc.normalize_mode('quatsch') == mc.DEFAULT_MODE
        assert mc.normalize_mode(None) == mc.DEFAULT_MODE
        assert mc.normalize_mode('energiesplitter_hammer') == mc.DEFAULT_MODE


class TestSlotModel:
    def test_default_slot(self):
        s = mc.ClientSlot()
        assert s.mode == mc.DEFAULT_MODE
        assert s.hwnd is None

    def test_frozen_immutable(self):
        s = mc.ClientSlot(mode='puzzle', hwnd=42)
        import dataclasses
        try:
            s.mode = 'seher'  # type: ignore[misc]
            assert False, 'ClientSlot muss frozen sein'
        except dataclasses.FrozenInstanceError:
            pass


class TestSetCount:
    def test_grow_pads_with_defaults(self):
        slots = [mc.ClientSlot(mode='puzzle', hwnd=10)]
        out = mc.set_count(slots, 3)
        assert len(out) == 3
        assert out[0] == mc.ClientSlot(mode='puzzle', hwnd=10)
        assert out[1] == mc.ClientSlot()
        assert out[2] == mc.ClientSlot()

    def test_shrink_keeps_prefix(self):
        slots = [mc.ClientSlot(hwnd=1), mc.ClientSlot(hwnd=2), mc.ClientSlot(hwnd=3)]
        out = mc.set_count(slots, 1)
        assert len(out) == 1
        assert out[0].hwnd == 1

    def test_clamps_and_is_immutable(self):
        slots = [mc.ClientSlot(hwnd=1)]
        out = mc.set_count(slots, 99)
        assert len(out) == mc.MAX_CLIENTS
        assert slots == [mc.ClientSlot(hwnd=1)]  # Original unveraendert


class TestSetModeAndAssign:
    def test_set_mode_immutable(self):
        slots = [mc.ClientSlot(), mc.ClientSlot()]
        out = mc.set_mode(slots, 1, 'seher')
        assert out[1].mode == 'seher'
        assert slots[1].mode == mc.DEFAULT_MODE  # Original unveraendert

    def test_set_mode_invalid_index_noop(self):
        slots = [mc.ClientSlot()]
        assert mc.set_mode(slots, 5, 'puzzle') == slots

    def test_assign_hwnd_sets_target(self):
        slots = [mc.ClientSlot(), mc.ClientSlot()]
        out = mc.assign_hwnd(slots, 0, 12345)
        assert out[0].hwnd == 12345

    def test_assign_hwnd_clears_duplicate_elsewhere(self):
        # ein Fenster = ein Client: wird hwnd anderswo schon genutzt -> dort loeschen
        slots = [mc.ClientSlot(hwnd=999), mc.ClientSlot()]
        out = mc.assign_hwnd(slots, 1, 999)
        assert out[1].hwnd == 999
        assert out[0].hwnd is None

    def test_assign_hwnd_preserves_mode(self):
        slots = [mc.ClientSlot(mode='puzzle')]
        out = mc.assign_hwnd(slots, 0, 7)
        assert out[0].mode == 'puzzle'


class TestSerialization:
    def test_roundtrip(self):
        slots = [mc.ClientSlot(mode='puzzle', hwnd=11),
                 mc.ClientSlot(mode='seher', hwnd=None)]
        cfg = mc.config_from_slots(slots, count=2, auto_restart=True)
        assert cfg['count'] == 2
        assert cfg['auto_restart'] is True
        assert cfg['clients'][0] == {'mode': 'puzzle', 'hwnd': 11}
        assert cfg['clients'][1] == {'mode': 'seher', 'hwnd': None}
        back = mc.slots_from_config({'multiclient': cfg})
        assert back == slots

    def test_from_missing_config_gives_one_default_slot(self):
        slots = mc.slots_from_config({})
        assert slots == [mc.ClientSlot()]

    def test_from_config_clamps_count_and_modes(self):
        cfg = {'multiclient': {'count': 99, 'clients': [
            {'mode': 'bloedsinn', 'hwnd': 5},
            {'mode': 'puzzle', 'hwnd': 6}]}}
        slots = mc.slots_from_config(cfg)
        assert slots[0].mode == mc.DEFAULT_MODE  # invalider Modus -> default
        assert slots[0].hwnd == 5
        assert slots[1].mode == 'puzzle'

    def test_count_from_config(self):
        cfg = {'multiclient': {'count': 3, 'clients': []}}
        assert mc.count_from_config(cfg) == 3
        assert mc.count_from_config({}) == mc.MIN_CLIENTS


class TestValidation:
    def test_ready_when_active_slots_marked_and_unique(self):
        slots = [mc.ClientSlot(mode='fischen', hwnd=1),
                 mc.ClientSlot(mode='puzzle', hwnd=2)]
        assert mc.validate(slots, count=2) == []
        assert mc.is_ready(slots, count=2) is True

    def test_unmarked_active_slot_is_problem(self):
        slots = [mc.ClientSlot(hwnd=1), mc.ClientSlot(hwnd=None)]
        probs = mc.validate(slots, count=2)
        assert any('2' in p for p in probs)  # Slot 2 unmarkiert
        assert mc.is_ready(slots, count=2) is False

    def test_duplicate_hwnd_is_problem(self):
        slots = [mc.ClientSlot(hwnd=5), mc.ClientSlot(hwnd=5)]
        probs = mc.validate(slots, count=2)
        assert probs  # Doppelbelegung gemeldet
        assert mc.is_ready(slots, count=2) is False

    def test_only_active_count_validated(self):
        # Slot 2 unmarkiert, aber count=1 -> Slot 2 zaehlt nicht -> ready
        slots = [mc.ClientSlot(hwnd=1), mc.ClientSlot(hwnd=None)]
        assert mc.is_ready(slots, count=1) is True


class TestSpecs:
    def test_specs_only_active_marked(self):
        slots = [mc.ClientSlot(mode='fischen', hwnd=1),
                 mc.ClientSlot(mode='puzzle', hwnd=2),
                 mc.ClientSlot(mode='seher', hwnd=None)]
        specs = mc.specs_from_slots(slots, count=3)
        # Slot 3 unmarkiert -> nicht in Specs
        assert specs == [(1, 'fischen'), (2, 'puzzle')]

    def test_specs_respect_count(self):
        slots = [mc.ClientSlot(mode='fischen', hwnd=1),
                 mc.ClientSlot(mode='puzzle', hwnd=2)]
        assert mc.specs_from_slots(slots, count=1) == [(1, 'fischen')]
