# -*- coding: utf-8 -*-
"""Detect-/Geometry-Bruecken des Energiesplitter-Bots (Mixin).

Buendelt alle defensiven Read-Only-Adapter auf Agent A (``detect``/
``geometry``) und Agent B (``calc``): Item-/Slot-Erkennung, freie Plaetze,
Shop-Item-Lokalisierung, Inventar-Signatur/Diff sowie der greedy Stack-Plan.

Diese Methoden werden per Mehrfachvererbung Teil von
:class:`energiesplitter.bot.EnergiesplitterBot` -- die oeffentliche API der
Klasse bleibt damit identisch (alle Methoden haengen weiter am selben Objekt).
Die weich importierten Schwester-Module (``_detect``/``_geometry``/``_calc``)
werden ZUR LAUFZEIT aus ``energiesplitter.bot`` gelesen, damit das Test-
Patching-Seam (``mock.patch.object(esbot_mod, '_detect', ...)``) unveraendert
greift.

Alle Funktionen sind defensiv und werfen NIE -- ein fehlendes Modul / ein
abweichendes Capture wird als 'nicht erkannt' (None/0/False/[]) behandelt,
nie als Absturz. KEINE Klick-/Maus-Logik (das macht der Bot-Kern).
"""

from typing import List, Optional, Tuple

from debuglog import log
from i18n import t

from energiesplitter import bot as _b

try:  # pragma: no cover - calibration ist rein/headless, defensiv importiert
  from energiesplitter import calibration as _cal
except Exception:  # pragma: no cover
  _cal = None

# Fallback-Stack-Groessen, falls der Shop-Reader (Phase-0) noch ``None`` liefert.
# WAHRHEIT laut Addendum A1: Hammer-Stacks 1 / 50 / 200 (groesster zuerst fuer
# greedy 'largest_fit'). Frueher faelschlich (200,100,10,1) aus dem Shop-Bild.
FALLBACK_STACK_SIZES: Tuple[int, ...] = (200, 50, 1)

# Toleranz (Pixel), in der ein lokalisierter Shop-Hammer mit dem kalibrierten
# Shop-Anker uebereinstimmen muss (Erkennung vor Aktion). Abweichung groesser ->
# kein verifizierter Anker -> KEIN Kauf (sauberer Stopp im Bot-Kern).
SHOP_ANCHOR_TOL = 18


class BridgesMixin:
  """Detect-/Geometry-/Calc-Adapter (siehe Modul-Docstring)."""

  # -- Template-Laden -----------------------------------------------------
  def _template(self, key):
    """Holt ein NCC-Template ueber Agent A (lazy). ``None`` -> Detektor
    behandelt es defensiv (kein Treffer)."""
    if _b._detect is None or not hasattr(_b._detect, 'load_template'):
      return None
    try:
      return _b._detect.load_template(key)
    except Exception:  # pragma: no cover
      return None

  # -- Inventar/Shop-Lese-Bruecken (defensiv; Read-only) ------------------
  def _item_template_ready(self, item) -> bool:
    if _b._detect is None or not hasattr(_b._detect, 'item_template_available'):
      return False
    try:
      return bool(_b._detect.item_template_available(item))
    except Exception:  # pragma: no cover
      return False

  def _has_free_slot(self) -> bool:
    return self._free_slot_count() > 0

  def _free_slot_count(self) -> int:
    if _b._detect is None or not hasattr(_b._detect, 'free_slot_count'):
      return 0
    bgr = self._shot()
    if bgr is None:
      return 0
    try:
      return max(0, int(_b._detect.free_slot_count(bgr)))
    except Exception:  # pragma: no cover
      return 0

  def _bag_count_measurable(self) -> bool:
    """``True`` nur, wenn der Inventar-Hammer-Zaehler real messbar ist (Live-
    Asset P0.1/P0.4 vorhanden). Solange ``detect.count_item`` ein Phase-0-Stub
    ist (liefert defensiv 0), ist der Bag-Stack NICHT messbar -> der Bag-Beleg
    wird uebersprungen (der Gold-Delta-Beleg traegt den Kauf)."""
    if _b._detect is None or not hasattr(_b._detect, 'count_item'):
      return False
    return bool(getattr(_b._detect, 'count_item_ready', False))

  def _verify_bag_growth(self, bag_before, expected) -> bool:
    """Zweiter Kauf-Beleg (OCR-unabhaengig): der Hammer-Bestand im Beutel ist um
    ``expected`` gewachsen. NUR erzwungen, wenn der Bag-Stack real messbar ist
    (siehe :meth:`_bag_count_measurable`); ist er es NICHT (Phase-0-Stub), gilt
    der Beleg als erbracht (``True``) und der Gold-Delta-Beleg traegt allein.
    Read-only, wirft nie."""
    if not self._bag_count_measurable():
      return True
    if bag_before is None:
      return True
    now = self._count_hammers()
    if now is None:
      return True
    return now - int(bag_before) >= int(expected)

  def _count_hammers(self) -> int:
    if _b._detect is None or not hasattr(_b._detect, 'count_item'):
      return 0
    bgr = self._shot()
    if bgr is None:
      return 0
    try:
      return max(0, int(_b._detect.count_item(bgr, 'hammer')))
    except Exception:  # pragma: no cover
      return 0

  def _locate_shop_item(self, item):
    """Lokalisiert ``item`` im Shop-Panel per Template-NCC (A) UND verifiziert
    den Treffer gegen den kalibrierten Shop-Anker (Erkennung vor Aktion).

    Nur ein Treffer, der zum gemessenen Anker passt (Hammer: ``SHOP_HAMMER_
    ANCHOR``), gilt als verifiziert -> liefert dann den Klick-Punkt. Fehlt der
    Anker (Dolch: ``SHOP_DAGGER_ANCHOR=None`` -> Luecke) ODER weicht der Treffer
    ab -> ``None`` (kein Blind-Kauf). Read-only, wirft nie."""
    if _b._detect is None:
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    tpl = self._template(item)
    try:
      ok, pt, _ncc = _b._detect.find_shop_item(bgr, tpl)
    except Exception:  # pragma: no cover
      ok, pt = False, None
    if not ok or pt is None:
      return None
    anchor = self._shop_anchor(item)
    if anchor is None:
      return None  # kein verifizierter Anker (z.B. Dolch-Luecke) -> kein Kauf
    if abs(pt[0] - anchor[0]) > SHOP_ANCHOR_TOL or abs(pt[1] - anchor[1]) > SHOP_ANCHOR_TOL:
      return None  # Treffer passt nicht zum gemessenen Shop-Slot -> kein Kauf
    return pt

  def _shop_anchor(self, item):
    """Kalibrierter Shop-Slot-Anker fuer ``item`` (Hammer/Dolch) oder ``None``.

    Hammer -> ``calibration.SHOP_HAMMER_ANCHOR``; Dolch -> ``SHOP_DAGGER_ANCHOR``
    (derzeit ``None``, Luecke). Fehlende Kalibrierung -> ``None``. Wirft nie."""
    if _cal is None:
      return None
    try:
      if item == 'hammer':
        return getattr(_cal, 'SHOP_HAMMER_ANCHOR', None)
      if item in ('dolch', 'dagger'):
        return getattr(_cal, 'SHOP_DAGGER_ANCHOR', None)
    except Exception:  # pragma: no cover
      return None
    return None

  def _plan_stacks(self, target: int, free_slots: int) -> List[int]:
    """Greedy Stack-Plan ueber Agent B (LAUFZEIT-gelesene Stack-Groessen).
    Single-Modus -> nur 1er. Defensiv -> [] bei fehlendem calc/Read."""
    if target <= 0:
      return []
    sizes = self._read_shop_stack_sizes()
    if self.prefer_stack == 'singles':
      sizes = (1,)
    if _b._calc is None or not hasattr(_b._calc, 'plan_stack_purchase'):
      # Ohne Rechner: defensiv genau 1er-Stacks, sofern Platz.
      return [1] if free_slots > 0 else []
    try:
      return list(_b._calc.plan_stack_purchase(target, free_slots, sizes))
    except Exception:  # pragma: no cover
      return []

  def _read_shop_stack_sizes(self) -> Tuple[int, ...]:
    """Gelesene Stack-Groessen aus dem Shop (A); Fallback Shop-Bild-Tupel
    (Addendum A1: 1/50/200)."""
    if _b._detect is not None and hasattr(_b._detect, 'read_shop_stack_sizes'):
      try:
        sizes = _b._detect.read_shop_stack_sizes(self._shot())
        if sizes:
          return tuple(sizes)
      except Exception:  # pragma: no cover
        pass
    return FALLBACK_STACK_SIZES

  def _ensure_bag_open(self) -> bool:
    """Im Shop ist rechts oft 'Ausruestungsfenster' statt Tasche -> per
    panel_is_bag pruefen. Nicht-Bag -> Stop (kein blindes Drag-Ziel)."""
    if _b._detect is None or not hasattr(_b._detect, 'panel_is_bag'):
      return True  # Detektor liefert A; ohne ihn nicht blockieren (GATE deckt ab)
    bgr = self._shot()
    try:
      if bgr is not None and _b._detect.panel_is_bag(bgr):
        return True
    except Exception:  # pragma: no cover
      pass
    self._snapshot('bag_not_open')
    log.event(self.state, t('energiesplitter.shop_not_open'))
    self._stop('bag_not_open')
    return False

  def _inventory_signature(self):
    if _b._detect is None or not hasattr(_b._detect, 'inventory_signature'):
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    try:
      return _b._detect.inventory_signature(bgr)
    except Exception:  # pragma: no cover
      return None

  def _diff_landing_slot(self, before, after):
    if _b._detect is None or not hasattr(_b._detect, 'diff_landing_slot'):
      return None
    if before is None or after is None:
      return None
    try:
      return _b._detect.diff_landing_slot(before, after)
    except Exception:  # pragma: no cover
      return None

  def _classified_hammer_slot(self):
    """Liefert einen als HAMMER klassifizierten Quell-Slot (A), sonst None."""
    if _b._detect is None or not hasattr(_b._detect, 'find_inventory_item'):
      return None
    bgr = self._shot()
    if bgr is None:
      return None
    try:
      ok, slot = _b._detect.find_inventory_item(bgr, 'hammer')
      return slot if ok else None
    except Exception:  # pragma: no cover
      return None

  def _slot_is(self, item, slot) -> bool:
    if _b._detect is None or not hasattr(_b._detect, 'slot_is') or slot is None:
      return False
    bgr = self._shot()
    if bgr is None:
      return False
    try:
      return bool(_b._detect.slot_is(bgr, slot, item))
    except Exception:  # pragma: no cover
      return False

  def _slot_is_empty(self, slot, bgr=None) -> bool:
    """``True``, wenn ``slot`` jetzt LEER ist (Drag-Erfolgs-Beleg, neue
    Grundwahrheit: Dolch verbraucht -> Slot leer). Bevorzugt einen dedizierten
    Detektor ``detect.slot_is_empty``; fehlt der, defensiver Fallback:
    'weder Hammer NOCH Dolch erkannt' = leer. NotReady/Fehler -> ``False``
    (sicher: NICHT als leer behandeln -> verify_process schlaegt fehl, kein
    Blind-Dekrement). Read-only, wirft nie."""
    if slot is None:
      return False
    shot = bgr if bgr is not None else self._shot()
    if shot is None:
      return False
    if _b._detect is not None and hasattr(_b._detect, 'slot_is_empty'):
      try:
        return bool(_b._detect.slot_is_empty(shot, slot))
      except Exception:  # pragma: no cover
        return False
    # Fallback ueber slot_is: leer = nicht Dolch UND nicht Hammer.
    if _b._detect is None or not hasattr(_b._detect, 'slot_is'):
      return False
    try:
      is_dolch = bool(_b._detect.slot_is(shot, slot, 'dolch'))
      is_hammer = bool(_b._detect.slot_is(shot, slot, 'hammer'))
      return not is_dolch and not is_hammer
    except Exception:  # pragma: no cover
      return False

  def _slot_center(self, slot) -> Tuple[int, int]:
    if _b._geometry is not None and hasattr(_b._geometry, 'slot_center'):
      try:
        return _b._geometry.slot_center(slot)
      except Exception:  # pragma: no cover
        pass
    # Slot kann bereits ein (x, y)-Punkt sein.
    if isinstance(slot, (tuple, list)) and len(slot) == 2:
      return int(slot[0]), int(slot[1])
    return 0, 0
