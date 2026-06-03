# -*- coding: utf-8 -*-
"""LIVE shell for the Lagerfeuer-Braten -- the ONLY win32 / pydirectinput part.

Thin wrapper the UI calls (on a worker thread) to actually grill the
CAMPFIRE-marked fish. It adds NO logic: it opens the capture window, builds the
RGB-capture + inventory-scan callbacks :func:`inventory_campfire.run_campfire`
expects, and hands ``pydirectinput`` in as the input api.

Same discipline as :mod:`interface.inventory_runner` / :mod:`windowcapture`: the
hard deps (``pydirectinput``, :class:`WindowCapture`, ``cv2``) are SOFT-imported
so this module stays importable headless, and the whole flow is unit-tested by
monkeypatching these module-level names + injecting synthetic frames (no game
needed). The PURE brain lives in :mod:`inventory_campfire`.

The inventory must be OPEN for the scan (the campfire tool + the fish live there).
This wrapper presses the configured inventory hotkey first -- exactly like the
inventory scan -- and the same TOGGLE caveat applies (documented there).
"""

import time

import constants
from inventory.constants import DEFAULT_CALIBRATION, PAGES, OPEN_SETTLE_S
from i18n import t

import inventory_campfire as campfire

# -- soft imports (live deps; module stays importable headless) -------------
try:  # pragma: no cover - present only on the Windows build/runtime
    import pydirectinput
except Exception:  # pragma: no cover
    pydirectinput = None

try:  # pragma: no cover
    import cv2 as _cv
except Exception:  # pragma: no cover
    _cv = None

try:  # pragma: no cover
    from windowcapture import WindowCapture
except Exception:  # pragma: no cover
    WindowCapture = None

try:  # pragma: no cover - reiner Fallback
    from debuglog import log
except Exception:  # pragma: no cover
    log = None


def _emit(state, key, **fmt):
    """Console/log line (best-effort)."""
    if log is None:
        return
    try:
        log.event(state, t(key, **fmt))
    except Exception:
        pass


def _bgr_to_rgb(bgr):
    """Convert a captured BGR frame to RGB (what the matcher expects). Soft.

    Uses cv2 when present, else a numpy channel-flip, else returns the input
    unchanged (the matcher degrades to a low score rather than crashing).
    """
    if bgr is None:
        return None
    try:
        if _cv is not None:
            return _cv.cvtColor(bgr, _cv.COLOR_BGR2RGB)
    except Exception:
        pass
    try:
        return bgr[:, :, ::-1]
    except Exception:
        return bgr


def run_campfire_grill(cfg, states, *, log_fn=None, db=None,
                       calib=DEFAULT_CALIBRATION):
    """Open the window + inventory and grill every CAMPFIRE-marked fish.

    :param cfg: current config dict (reads ``inventory.hotkey`` to open the bag,
        and ``fishing.bait_key`` only to know what NOT to grill is already handled
        by the name exclusion -- no key needed here).
    :param states: the inventory-manage ``{name: KEEP|REMOVE|CAMPFIRE}`` map from
        the GUI (which fish the user marked for the fire).
    :param db: an :class:`~inventory.itemdb.ItemDB` to reuse (default: the cached
        bundled DB via :func:`interface.inventory_io._get_db`).
    :return: the :class:`inventory_campfire.CampfireResult`.

    Defensive: with no marked fish / no window it returns a clear status and never
    raises. The caller (UI) is idle-only-gated exactly like the inventory scan, so
    no concurrent bot run can race the cursor.
    """
    # Nothing marked -> skip everything (no window work at all).
    if not campfire.campfire_fish_names(states):
        _emit('-', 'campfire.no_fish_marked')
        return campfire.CampfireResult('no_fish')

    if WindowCapture is None or pydirectinput is None:
        _emit('-', 'campfire.live_unavailable')
        return campfire.CampfireResult('error')

    if db is None:
        try:
            from interface.inventory_io import _get_db
            db = _get_db()
        except Exception:
            db = None

    try:
        wincap = WindowCapture(constants.GAME_NAME)
    except Exception as exc:
        _emit('-', 'campfire.no_window', detail=str(exc)[:120])
        return campfire.CampfireResult('error')

    offset = (int(getattr(wincap, 'offset_x', 0) or 0),
              int(getattr(wincap, 'offset_y', 0) or 0))

    # Open the inventory (TOGGLE; see inventory_runner docstring) so the scan can
    # see the tool + fish.
    hotkey = (cfg or {}).get('inventory', {}).get('hotkey', 'i')
    try:
        pydirectinput.keyDown(hotkey)
        pydirectinput.keyUp(hotkey)
    except Exception:
        pass
    time.sleep(OPEN_SETTLE_S)

    def capture_rgb_fn():
        try:
            return _bgr_to_rgb(wincap.get_screenshot())
        except Exception:
            return None

    def scan_fn():
        """One headless I->IV inventory scan (tab-click page switch + offset)."""
        try:
            from inventory.scanner import scan_inventory
            ox, oy = offset

            def _switch(page):
                pt = ((calib or {}).get('tabs', {}) or {}).get(page)
                if pt:
                    try:
                        pydirectinput.click(x=int(ox + pt[0]), y=int(oy + pt[1]))
                    except Exception:
                        pass
                    time.sleep(0.2)

            return scan_inventory(
                capture_fn=wincap.get_screenshot,
                switch_page_fn=_switch,
                db=db, calib=calib, pages=PAGES)
        except Exception:
            return None

    _emit('0', 'campfire.started')
    result = campfire.run_campfire(
        states,
        inp=pydirectinput,
        capture_rgb_fn=capture_rgb_fn,
        scan_fn=scan_fn,
        offset=offset,
        calib=calib)
    return result
