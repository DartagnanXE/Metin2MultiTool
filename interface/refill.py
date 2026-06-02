# -*- coding: utf-8 -*-
"""Auto-refill: drag a bait into the quick-slot / a puzzle box onto the board.

This is the PURE brain + the input PRIMITIVE of the refill automation, kept free
of any live dependency (no ``pydirectinput``, no ``WindowCapture``) so it is unit
tested headlessly; the live loop injects the input API + the screenshot. The two
things that genuinely need the live window -- the exact quick-slot drop pixel and
the drag timing -- are isolated as the tunables ``QUICKSLOT_XY`` / ``DRAG_*``.

Game runs FIXED at 800x600, so every UI element sits at a constant client pixel;
the only per-run variable is the window's top-left on screen (``offset_x/y``,
exactly what fishingbot/puzzle already add to every click).

Quick-slot model (per the spec): exactly 8 slots, keys ``1 2 3 4`` (slots 1-4)
and ``F1 F2 F3 F4`` (slots 5-8) -- nothing else. The configured bait key both
selects the slot to drag INTO and is the key fishing presses to bait the rod.
"""

from inventory.constants import DEFAULT_CALIBRATION
from inventory.grid import lattice_from_calibration

try:  # pragma: no cover - numpy present in production
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

# The only 8 valid quick-slot keys (index 0 -> slot 1, ... index 7 -> slot 8).
QUICKSLOT_KEYS = ('1', '2', '3', '4', 'f1', 'f2', 'f3', 'f4')

# Drop-pixel CENTRE of each quick-slot in the 800x600 client (before the window
# offset). MEASURED from a real bottom action bar (slot 1 = the red potion "194"
# anchors the grid): slots 1-4 left of the divider (~x448), then a short gap,
# then 5-8. Pitch ~38px, row centre y~580.
QUICKSLOT_XY = {
    1: (324, 580), 2: (362, 580), 3: (400, 580), 4: (438, 580),
    5: (476, 580), 6: (514, 580), 7: (552, 580), 8: (590, 580),
}

# Item names eligible for each refill (recognised by the inventory engine).
BAIT_NAMES = ('Worm',)
BOX_NAMES = ('Fischpuzzlebox', 'Fischpuzzlebox_Deluxe')

# Inventory pages in scan order, and the grid shape.
PAGE_ORDER = ('I', 'II', 'III', 'IV')

# Drag timing (seconds) -- tunable on the live window.
DRAG_STEPS = 12        # intermediate moves so the game registers the drag
DRAG_SETTLE = 0.04     # pause after press / before release


def quickslot_index(key):
    """1..8 for a valid quick-slot key (case-insensitive), else ``None``."""
    try:
        return QUICKSLOT_KEYS.index(str(key).strip().lower()) + 1
    except (ValueError, AttributeError):
        return None


def is_quickslot_key(key):
    """True iff ``key`` is one of the 8 allowed quick-slot keys."""
    return quickslot_index(key) is not None


def quickslot_screen(slot_1to8, offset_x=0, offset_y=0):
    """Screen ``(x, y)`` to drop an item INTO quick-slot ``slot_1to8`` (1..8)."""
    cx, cy = QUICKSLOT_XY[int(slot_1to8)]
    return (int(offset_x + cx), int(offset_y + cy))


def inventory_slot_screen(row, col, offset_x=0, offset_y=0,
                          calib=DEFAULT_CALIBRATION):
    """Screen ``(x, y)`` of the CENTRE of inventory slot ``(row, col)``.

    Page-independent (switching tabs does not move the grid); the caller opens
    the right page first. Derived from the calibration grid (origin + pitch) so
    it tracks the user's own calibration, + the window offset like every other
    click in the bot.
    """
    lat = lattice_from_calibration(calib)
    ox, oy = lat.origin
    px, py = lat.pitch
    x = ox + col * px + px // 2
    y = oy + row * py + py // 2
    return (int(offset_x + x), int(offset_y + y))


def find_first(inv, names, pages=PAGE_ORDER):
    """First slot holding one of ``names``, in PAGE order then row-major.

    Returns ``(page, row, col)`` or ``None``. This is the documented refill
    order: inventory pages I->IV, each slot 1..45 top-to-bottom. Pure: works on
    any object exposing ``pages -> {page: [SlotResult]}``.
    """
    want = set(names)
    page_map = getattr(inv, 'pages', {}) or {}
    for page in pages:
        slots = page_map.get(page) or ()
        for s in slots:
            if getattr(s, 'state', None) == 'item' and getattr(s, 'name', None) in want:
                return (page, int(s.row), int(s.col))
    return None


def plan_refill(inv, names):
    """Decide the next refill action from a scan.

    Returns ``('drag', page, row, col)`` for the first matching item, or
    ``('empty',)`` when none is left (the caller stops the bot + warns).
    """
    loc = find_first(inv, names)
    return ('drag', loc[0], loc[1], loc[2]) if loc is not None else ('empty',)


def drag(api, x1, y1, x2, y2, steps=DRAG_STEPS, settle=DRAG_SETTLE,
         sleep=None):
    """Press-hold-move-release drag from ``(x1,y1)`` to ``(x2,y2)``.

    ``api`` is any object with ``moveTo(x, y)``, ``mouseDown()``, ``mouseUp()``
    (pydirectinput in production, a recorder in tests). Intermediate moves make
    the game register the drag rather than a teleport. ``sleep`` defaults to
    ``time.sleep``; tests pass a no-op. Never raises -> a failed drag must not
    crash the bot loop (it releases the button in a finally).
    """
    if sleep is None:
        import time
        sleep = time.sleep
    try:
        api.moveTo(int(x1), int(y1))
        sleep(settle)
        api.mouseDown()
        sleep(settle)
        n = max(1, int(steps))
        for i in range(1, n + 1):
            x = x1 + (x2 - x1) * i // n
            y = y1 + (y2 - y1) * i // n
            api.moveTo(int(x), int(y))
            sleep(settle / n)
        sleep(settle)
    finally:
        try:
            api.mouseUp()
        except Exception:
            pass


def quickslot_is_empty(screenshot_bgr, slot_1to8, radius=8, thr=42):
    """True iff quick-slot ``slot_1to8`` looks EMPTY (no bait icon).

    Samples a small patch at the slot's client pixel on the captured window
    (the screenshot IS the 800x600 window, so client == screenshot coords) and
    calls it empty when that patch is dark -- an occupied slot shows a bright
    item icon. Returns ``False`` (assume occupied -> do nothing) when numpy/the
    image is unavailable, so a vision hiccup never triggers a needless refill.
    """
    if _np is None or screenshot_bgr is None:
        return False
    try:
        cx, cy = QUICKSLOT_XY[int(slot_1to8)]
        arr = _np.asarray(screenshot_bgr)
        h, w = arr.shape[0], arr.shape[1]
        y0, y1 = max(0, cy - radius), min(h, cy + radius)
        x0, x1 = max(0, cx - radius), min(w, cx + radius)
        if y1 <= y0 or x1 <= x0:
            return False
        return float(arr[y0:y1, x0:x1, :3].mean()) < thr
    except Exception:
        return False


def tab_click(inp, calib, offset_x, offset_y, page):
    """Click an inventory page tab (I..IV) via the injected input api."""
    pt = ((calib or {}).get('tabs', {}) or {}).get(page)
    if pt:
        inp.click(x=int(offset_x + pt[0]), y=int(offset_y + pt[1]),
                  button='left')


def refill_from_inventory(item_names, target_xy, *, inp, wincap, db,
                          calib=DEFAULT_CALIBRATION, sleep=None):
    """Scan the (already open) inventory + drag the first matching item to
    ``target_xy``. Returns ``'dragged'`` / ``'empty'`` / ``'error'``.

    Reuses the headless scanner (tab-click page switch built from the
    calibration + window offset) + the tested find/coordinate/drag helpers.
    Strictly defensive -- a vision/input failure returns ``'error'`` and never
    raises into the bot loop.
    """
    if sleep is None:
        import time
        sleep = time.sleep
    try:
        from inventory.scanner import scan_inventory
        ox = int(getattr(wincap, 'offset_x', 0) or 0)
        oy = int(getattr(wincap, 'offset_y', 0) or 0)
        inv = scan_inventory(
            capture_fn=wincap.get_screenshot,
            switch_page_fn=lambda p: (tab_click(inp, calib, ox, oy, p),
                                      sleep(0.2)),
            db=db, calib=calib)
        loc = find_first(inv, item_names)
        if loc is None:
            return 'empty'
        page, row, col = loc
        tab_click(inp, calib, ox, oy, page)
        sleep(0.25)
        fx, fy = inventory_slot_screen(row, col, ox, oy, calib)
        drag(inp, fx, fy, int(target_xy[0]), int(target_xy[1]), sleep=sleep)
        sleep(0.15)
        return 'dragged'
    except Exception:
        return 'error'
