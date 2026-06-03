"""Hover-clear cursor sweep -- the PURE part (no win32 / input).

WHY a hover sweep: a freshly-caught item GLOWS (its slot background is recoloured
lavender) until the mouse hovers it; hovering every slot of the open page clears
the glow, leaving the ~100%-recognised no-glow state. So before classifying a
page the scanner sweeps the cursor over all 45 slot centres (see
:mod:`inventory.scanner` / :mod:`interface.inventory_runner`).

This module is the deterministic, fully unit-testable core: it turns a locked
:class:`~inventory.grid.GridLattice` into the exact ordered list of slot-centre
points the cursor should visit, and offers the pure screen-mapping transform.
The live wrapper in :mod:`interface.inventory_runner` feeds :func:`slot_centres`
/ :func:`to_screen` straight to ``pydirectinput.moveTo`` -- so the ONLY non-pure
part (the actual cursor move) lives there, and the geometry stays headless.

Hover order is BOUSTROPHEDON (serpentine) row-major: row 0 left->right, row 1
right->left, row 2 left->right, ... This visits all 45 centres with 44 short
single-step hops and NO long carriage-return jumps back to the left edge, which
keeps the real sweep faster and less jittery than naive row-major.

Pure Python only (no numpy/cv2/PIL) so it is ALWAYS importable + testable
headless, matching :mod:`inventory.constants` / :mod:`geometry`.
"""

from typing import List, Tuple

from .constants import COLS, ROWS, SLOT_PX


# Slot CENTRE offset from the slot-box top-left corner. GridLattice.slot_box
# returns (ox+col*px, oy+row*py, 32, 32); the centre is half a slot in on each
# axis. 16 == SLOT_PX // 2.
_HALF = SLOT_PX // 2


def slot_centres(lattice) -> List[Tuple[int, int]]:
    """Ordered slot-box centres for the hover sweep (serpentine row-major).

    Returns the 45 ``(x, y)`` integer centre points of ``lattice`` (a
    :class:`~inventory.grid.GridLattice`) in BOUSTROPHEDON order: even rows
    left->right, odd rows right->left. The centre of slot ``(row, col)`` is
    ``lattice.slot_box(row, col)`` shifted by ``(+SLOT_PX//2, +SLOT_PX//2)``.

    Deterministic + pure -> the first centre for origin ``(2, 2)`` pitch
    ``(32, 32)`` is ``(18, 18)`` and the sequence serpentines from there.

    :param lattice: a locked grid lattice exposing ``slot_box(row, col)``.
    :return: ``[(x, y), ...]`` of length ``ROWS * COLS`` (45).
    """
    points: List[Tuple[int, int]] = []
    for row in range(ROWS):
        cols = range(COLS) if row % 2 == 0 else range(COLS - 1, -1, -1)
        for col in cols:
            box = lattice.slot_box(row, col)
            points.append((int(box[0]) + _HALF, int(box[1]) + _HALF))
    return points


def park_point(lattice) -> Tuple[int, int]:
    """An engine-space point clear of ALL slots, to park the cursor after a sweep.

    After the serpentine sweep the cursor rests on the LAST visited centre (a real
    slot), and the de-glowed re-capture happens with it parked there. If the OS
    includes the hardware cursor (or a tooltip it triggers) in the screenshot, that
    one slot could be occluded on the classified frame. Parking the cursor below
    the grid (one full pitch under the bottom-left slot's box) before the
    re-capture keeps it off every slot. Pure + deterministic so it is testable; the
    live wrapper maps it via :func:`to_screen` and moves there once.

    :param lattice: the locked grid lattice exposing ``slot_box(row, col)``.
    :return: an ``(x, y)`` engine-space point one pitch below the bottom row.
    """
    box = lattice.slot_box(ROWS - 1, 0)
    pitch_y = int(lattice.pitch[1])
    # Bottom-left slot's lower edge, then a full pitch further down -> clear of the
    # grid yet still near it (a small, safe MOVE, never a click).
    return (int(box[0]) + _HALF, int(box[1]) + SLOT_PX + pitch_y)


def tab_park_point(calib) -> Tuple[int, int]:
    """An engine-space point clear of BOTH the page tabs AND the slot grid.

    Used right AFTER a tab click (I/II/III/IV), BEFORE the page is captured. A
    plain ``pydirectinput.click`` leaves the cursor resting ON the tab button,
    which sits just ABOVE the grid: the hardware cursor (or the tooltip it
    triggers) can then bleed into the screenshot and occlude the TOP slot row,
    demoting it to unknown. We therefore move the cursor to a neutral spot to the
    LEFT of the grid's left edge -- past every slot (all at x >= grid.tl.x) and
    below the tabs row -- so the captured page has no cursor over any slot or tab.

    Unlike :func:`park_point` this works from the CALIBRATION alone (no locked
    lattice exists yet at tab-click time, since auto_align runs only after the
    capture). It reads ``calib['grid']`` (``tl``/``br``): x = one-and-a-half slot
    widths LEFT of the grid's left edge, y = the grid's vertical midpoint (well
    below the tabs, well inside the grid's height so it is never near a tab). Pure
    + deterministic -> the live wrapper maps it via :func:`to_screen` once.

    :param calib: the calibration dict (reads ``grid.tl`` / ``grid.br``).
    :return: an ``(x, y)`` engine-space point left of the grid, clear of tabs.
    """
    grid = (calib or {}).get('grid', {})
    tl = grid.get('tl', [0, 0])
    br = grid.get('br', [int(tl[0]) + SLOT_PX * COLS,
                         int(tl[1]) + SLOT_PX * ROWS])
    left = int(tl[0])
    top = int(tl[1])
    bottom = int(br[1])
    # 1.5 slot widths left of the grid's left edge -> clear of every slot (which
    # all sit at x >= left). Clamp at 0 so we never produce a negative screen x.
    park_x = max(0, left - (SLOT_PX + _HALF))
    # Vertical midpoint of the grid: far below the tabs row, safely inside the
    # grid's height so a small move (never a click) lands in dead space, not a tab.
    park_y = (top + bottom) // 2
    return (park_x, park_y)


def to_screen(centres, offset) -> List[Tuple[int, int]]:
    """Shift engine-space centre points into absolute SCREEN coordinates.

    ``screen = engine + offset`` per the verified capture convention
    (``screen_x = engine_x + wincap.offset_x``; equivalently
    ``wincap.get_screen_position``). Pure so the screen mapping is testable
    without a real window; the live wrapper passes
    ``(wincap.offset_x, wincap.offset_y)``.

    :param centres: ``[(x, y), ...]`` engine-space points (e.g. from
        :func:`slot_centres`).
    :param offset: ``(offset_x, offset_y)`` to add to every point.
    :return: a NEW list of shifted ``(x, y)`` integer points (input unchanged).
    """
    ox, oy = int(offset[0]), int(offset[1])
    return [(int(x) + ox, int(y) + oy) for (x, y) in centres]
