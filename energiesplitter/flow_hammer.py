# -*- coding: utf-8 -*-
"""Hammer-Modus-State-Maschine (Aktion 1 @ Alchemist) als Mixin.

Kauft am Alchemisten die gewuenschte Hammer-Anzahl in greedy gewaehlten Stacks
(1/50/200, groesster zuerst). Diese Methoden werden per Mehrfachvererbung Teil
von :class:`energiesplitter.bot.EnergiesplitterBot`; sie operieren auf der Bot-
Instanz (``self``) und nutzen deren Eingabe-Wrapper, Backstops und Bruecken.
Verhalten unveraendert -- reine Extraktion aus ``bot.py``.
"""

from debuglog import log
from i18n import t


class HammerFlowMixin:
  """Hammer-Kauf-State-Maschine (siehe Modul-Docstring, CONTRACT §1)."""

  def _tick_hammer(self):
    st = self.state
    if st == self.ST_INIT:
      self._log_section()
      log.event(st, t('energiesplitter.started', mode=self.mode))
      self.hammer_remaining = max(0, int(self.hammer_count))
      self.state = self.ST_INVENTORY_BASE
      return

    if st == self.ST_INVENTORY_BASE:
      # Item-Template Pflicht -- ohne Hammer-Icon kein messbarer Bestand.
      if not self._item_template_ready('hammer'):
        log.event(st, t('energiesplitter.item_template_missing', item='hammer'))
        self._stop('item_template_missing')
        return
      if not self._has_free_slot():
        log.event(st, t('energiesplitter.no_space'))
        self._stop('no_space')
        return
      self.state = self.ST_APPROACH_NPC
      return

    if st == self.ST_APPROACH_NPC:
      pt = self.approach_npc('npc_alchemist')
      if pt is None:
        return  # approach_npc hat ggf. schon gestoppt / Vogelperspektive
      self._npc_pt = pt
      self.state = self.ST_SELECT_NPC
      return

    if st == self.ST_SELECT_NPC:
      if not self._select_npc(self._npc_pt):
        return  # _select_npc stoppt selbst bei Miss
      self.state = self.ST_OPEN_DIALOG
      return

    if st == self.ST_OPEN_DIALOG:
      if not self._open_dialog(self._npc_pt):
        return
      self.state = self.ST_UNLOCK_DECIDE
      return

    if st == self.ST_UNLOCK_DECIDE:
      ds = self._dialog_state()
      if ds == 'locked' and self.energie_freischalten:
        self.state = self.ST_UNLOCK_STORY
      else:
        self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_UNLOCK_STORY:
      # Freischalt-Story: Weiter/Weiter/OK (NCC-Buttons). Negativliste NIE
      # klicken (Veredelung/Bonuswandel/extrahieren) -- Detection von A liefert
      # nur die freigegebenen Buttons; ist keiner da, weiter zum Shop.
      self._click_story_buttons()
      self.state = self.ST_OPEN_SHOP
      return

    if st == self.ST_OPEN_SHOP:
      if not self.open_shop_via_dialog():
        return
      self.state = self.ST_LOCATE_HAMMER
      return

    if st == self.ST_LOCATE_HAMMER:
      slot = self._locate_shop_item('hammer')
      if slot is None:
        log.event(st, t('energiesplitter.item_not_in_shop', item='hammer'))
        self._stop('item_not_in_shop')
        return
      self._hammer_slot = slot
      self.state = self.ST_BUY_LOOP
      return

    if st == self.ST_BUY_LOOP:
      self._hammer_buy_step()
      return

    if st == self.ST_CHECK_DONE:
      if self.gekauft >= int(self.hammer_count):
        self._stop('done')
      else:
        self.state = self.ST_BUY_LOOP
      return

    self._stop('unknown_state')

  def _hammer_buy_step(self):
    """Ein Kauf-Schritt: Stack greedy waehlen, gold_guard, Rechtsklick,
    verify_purchase. Alle Backstops vorgeschaltet."""
    if self._action_cap_hit():
      return
    remaining = int(self.hammer_count) - self.gekauft
    free = self._free_slot_count()
    stacks = self._plan_stacks(remaining, free)
    try:
      log.event(self.state, 'ABSICHT: Hammer-Kaufplan (greedy)',
                rest=remaining, ziel=self.hammer_count, gekauft=self.gekauft,
                freie_slots=free, plan=list(stacks), prefer_stack=self.prefer_stack)
    except Exception:  # pragma: no cover
      pass
    if not stacks:
      # Kein sicherer Kaufplan (kein Platz / Zielzahl erreicht).
      if remaining <= 0:
        self.state = self.ST_CHECK_DONE
      else:
        log.event(self.state, t('energiesplitter.no_space'))
        self._stop('no_space')
      return

    stack = stacks[0]
    cost = stack * int(self.price_per_item)
    try:
      verb = ('[SIM] wuerde' if not self.scharf else 'SCHARF:')
      log.event(self.state, verb + ' Hammer-Stack kaufen', stack=stack,
                kosten=cost, slot=getattr(self, '_hammer_slot', None))
    except Exception:  # pragma: no cover
      pass
    gold_before = self.gold_guard(cost)
    if gold_before is None:
      return  # gold_guard hat gestoppt

    if self._guarded():
      # Sollte hier nie erreichbar sein (GATE in runHack) -- doppelter Riegel.
      self._stop('phase0_not_ready')
      return

    # ERKENNUNG VOR AKTION (pro Kauf): den Shop-Hammer JEDESMAL per TEMPLATE
    # neu lokalisieren -- nie eine fixe/stale Koordinate rechtsklicken. Schlaegt
    # die Re-Lokalisierung fehl, faellt der Bot auf den in ST_LOCATE_HAMMER
    # verifizierten Slot zurueck; ist auch der unbekannt -> sauberer Stop, KEIN
    # Blind-Klick.
    slot = self._locate_shop_item('hammer')
    if slot is None:
      slot = getattr(self, '_hammer_slot', None)
    if slot is None:
      log.event(self.state, t('energiesplitter.item_not_in_shop', item='hammer'))
      self._stop('item_not_in_shop')
      return
    self._hammer_slot = slot

    # Bag-Stack VOR dem Kauf merken (zweiter, OCR-unabhaengiger Verifikations-
    # Beleg: der Hammer-Bestand im Beutel muss nach dem Kauf um ``stack``
    # gewachsen sein -- nicht nur das Gold gesunken).
    bag_before = self._count_hammers()

    try:
      verb = ('[SIM] wuerde' if self._guarded() else 'SCHARF:')
      log.event(self.state, verb + ' Hammer rechtsklicken (Kauf)',
                ziel=tuple(slot), stack=stack, kosten=cost,
                gold_before=self._fmt_gold(gold_before))
    except Exception:  # pragma: no cover
      pass
    self._right_click(*slot)
    self.actions_done += 1
    # GEPLANTE Ausgabe (echte Stack-Kosten = stack*price) OCR-unabhaengig
    # fortschreiben -- Bezugsgroesse des yang_check=FALSE-Deckels, der sonst bei
    # Stacks>1 die bereits getaetigte Ausgabe unterzaehlt (Safety-Audit MEDIUM).
    self._note_planned_spend(cost)

    ok, gold_after = self.verify_purchase(gold_before, cost)
    # Cap-Drift-Haertung: die REAL GELESENE Yang-Abnahme IMMER fortschreiben --
    # auch wenn der Kauf gleich als nicht-verifiziert gewertet wird -- damit der
    # max_gold_spend-Deckel die tatsaechliche kumulierte Abnahme begrenzt (sonst
    # advanciert ein bezahlter, aber unverifizierter Kauf den Deckel nicht).
    self._note_real_spend(gold_before, gold_after)
    bag_ok = self._verify_bag_growth(bag_before, stack)
    if ok and bag_ok:
      self.gekauft += stack
      self.consecutive_unverified = 0
      self._buy_retries = 0
      log.event(self.state, t(
          'energiesplitter.bought', stack=stack, done=self.gekauft,
          soll=self.hammer_count, gold_before=gold_before,
          gold_after=self._fmt_gold(gold_after)))
      self.state = self.ST_CHECK_DONE
    else:
      # Doppelkauf-Schutz: NICHT sofort erneut rechtsklicken.
      self._buy_retries += 1
      if self._buy_retries > 2 or self._note_unverified():
        if self.botting:  # _note_unverified hat evtl. schon gestoppt
          log.event(self.state, t('energiesplitter.buy_unverified',
                                  retries=self._buy_retries))
          self._stop('buy_unverified')
