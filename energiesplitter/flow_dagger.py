# -*- coding: utf-8 -*-
"""Dolch-Modus-State-Maschine (Aktion 2 @ Waffenhaendler) als Mixin.

Kauft am Waffenhaendler EINZELNE Dolche (A1) und verarbeitet sie 1:1 per Drag
(Hammer -> verifizierter Dolch-Slot) zu Energiesplittern. Diese Methoden werden
per Mehrfachvererbung Teil von
:class:`energiesplitter.bot.EnergiesplitterBot`; sie operieren auf der Bot-
Instanz (``self``). Verhalten unveraendert -- reine Extraktion aus ``bot.py``.
"""

from debuglog import log
from i18n import t

# Anti-Drift: Differenz gekaufte Dolche vs. verarbeitete Splitter, ab der ohne
# erkennbare Verarbeitung gestoppt wird (R10/R5).
PROCESS_DRIFT_MAX = 2


class DaggerFlowMixin:
  """Dolch-Kauf + 1:1-Verarbeitung (siehe Modul-Docstring, CONTRACT §1)."""

  def _tick_dagger(self):
    st = self.state
    if st == self.ST_INIT:
      self._log_section()
      log.event(st, t('energiesplitter.started', mode=self.mode))
      self.state = self.ST_INVENTORY_BASE
      return

    if st == self.ST_INVENTORY_BASE:
      if not self._item_template_ready('hammer'):
        log.event(st, t('energiesplitter.item_template_missing', item='hammer'))
        self._stop('item_template_missing')
        return
      if not self._item_template_ready('dolch'):
        log.event(st, t('energiesplitter.item_template_missing', item='dolch'))
        self._stop('item_template_missing')
        return
      self.hammer_remaining = self._count_hammers()
      if self.hammer_remaining <= 0:
        self._stop('done')
        return
      self.state = self.ST_APPROACH_NPC
      return

    if st == self.ST_APPROACH_NPC:
      pt = self.approach_npc('npc_waffenhaendler')
      if pt is None:
        return
      self._npc_pt = pt
      self.state = self.ST_SELECT_NPC
      return

    if st == self.ST_SELECT_NPC:
      if not self._select_npc(self._npc_pt):
        return
      self.state = self.ST_OPEN_DIALOG
      return

    if st == self.ST_OPEN_DIALOG:
      if not self._open_dialog(self._npc_pt):
        return
      self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_OPEN_SHOP:
      if not self.open_shop_via_dialog():
        return
      if not self._ensure_bag_open():
        return
      self.state = self.ST_LOCATE_DOLCH
      return

    if st == self.ST_LOCATE_DOLCH:
      slot = self._locate_shop_item('dolch')
      if slot is None:
        log.event(st, t('energiesplitter.item_not_in_shop', item='dolch'))
        self._stop('item_not_in_shop')
        return
      self._dolch_shop_slot = slot
      self.state = self.ST_BUY_ONE_DOLCH
      return

    if st == self.ST_BUY_ONE_DOLCH:
      self._dagger_buy_one()
      return

    if st == self.ST_PROCESS_DRAG:
      self._dagger_process_drag()
      return

    if st == self.ST_VERIFY_PROCESS:
      self._dagger_verify_process()
      return

    if st == self.ST_RESCAN:
      # Drift-Korrektur (glow-aware Re-Scan via A); Fortschritt am Splitter,
      # nicht am Hammer-Bestand. Read-only -> direkt weiter.
      if self.hammer_remaining > 0:
        self.state = self.ST_BUY_ONE_DOLCH
      else:
        self._stop('done')
      return

    self._stop('unknown_state')

  def _dagger_buy_one(self):
    """Kauft GENAU 1 Dolch (A1), bestimmt den realen Lande-Slot per Diff."""
    if self._action_cap_hit():
      return
    cost = int(self.price_per_item)
    gold_before = self.gold_guard(cost)
    if gold_before is None:
      return

    before = self._inventory_signature()
    self._right_click(*self._dolch_shop_slot)
    self.actions_done += 1

    ok, gold_after = self.verify_purchase(gold_before, cost)
    if not ok:
      self._buy_retries += 1
      if self._buy_retries > 2 or self._note_unverified():
        if self.botting:
          log.event(self.state, t('energiesplitter.buy_unverified',
                                  retries=self._buy_retries))
          self._stop('buy_unverified')
      return

    after = self._inventory_signature()
    land = self._diff_landing_slot(before, after)
    if land is None:
      # Kauf verifiziert (Gold sank), aber Lande-Slot unklar -> kein Drag.
      self._snapshot('dolch_slot_unknown')
      self._stop('process_unverified')
      return

    self._dolch_inv_slot = land
    self._dolche_gekauft += 1
    self.gold_spent += (gold_before - (gold_after or gold_before))
    self.consecutive_unverified = 0
    self._buy_retries = 0
    self.state = self.ST_PROCESS_DRAG

  def _dagger_process_drag(self):
    """Drag 1 Hammer -> verifizierter Dolch-Slot. NUR wenn Quelle=Hammer UND
    Ziel=Dolch (beide Template-positiv). Sonst Stop, KEIN Drag (R11)."""
    if self._action_cap_hit():
      return
    src = self._classified_hammer_slot()
    dst_ok = self._slot_is('dolch', self._dolch_inv_slot)
    if src is None or not dst_ok:
      log.event(self.state, t('energiesplitter.drag_unsafe'))
      self._stop('drag_unsafe')
      return

    self._before_proc = self._shot()
    sx, sy = self._slot_center(src)
    dx, dy = self._slot_center(self._dolch_inv_slot)
    self._drag(sx, sy, dx, dy)
    self.actions_done += 1
    self.state = self.ST_VERIFY_PROCESS

  def _dagger_verify_process(self):
    """Verifiziert: Splitter-Stack gewachsen. NUR dann dekrementieren (R5)."""
    after = self._shot()
    growth = self.verify_process(self._before_proc, after)
    if growth > 0:
      self.splitter_summe += growth
      self.hammer_remaining -= 1
      self.consecutive_unverified = 0
      log.event(self.state, t(
          'energiesplitter.processed', value=growth,
          sum=self.splitter_summe, rest=self.hammer_remaining))
      # Anti-Drift: kauft ohne zu verarbeiten? (R10/R5-Abbruch)
      if self._dolche_gekauft - self.splitter_summe > PROCESS_DRIFT_MAX:
        log.event(self.state, t('energiesplitter.process_unverified'))
        self._stop('process_unverified')
        return
      self.state = self.ST_RESCAN
    else:
      if not self._note_unverified():
        log.event(self.state, t('energiesplitter.process_unverified'))
        self._stop('process_unverified')
