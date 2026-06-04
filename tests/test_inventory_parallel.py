"""Tests for the TWO-PHASE fast scan: capture/recognise separation + parallel.

The fast path (``inventory.scanner.capture_pages`` + ``recognize_pages``) splits
the old interleaved scan into (1) a fast capture phase that only switches tabs +
buffers one raw frame per page and (2) a recognition phase that classifies the
buffered frames with the 180 slots fanned across a thread pool. These tests pin,
all headless (synthetic page images, no game / win32 / GUI):

  * CAPTURE SEAM -- ``capture_pages`` switches I->IV, buffers exactly one frame
    per page, does NO recognition between switches, and returns to the first tab.
  * PARALLEL == SERIAL -- the parallel ``recognize_pages`` yields the SAME
    InventoryMap (per-slot states/names) as a single-worker serial run and as
    the original ``recognize_page`` -- the engine is reused, only parallelised.
  * PROGRESS MONOTONICITY -- ``progress_fn(done, total)`` fires 1..total with
    ``total == pages*45``, strictly increasing, last == total -- on BOTH the
    pool and the serial (max_workers=1) path.
  * DEFENSIVE -- a raising slot worker degrades to UNKNOWN (never aborts); a
    raising progress callback never aborts; an empty buffer -> empty map; a
    failing aligner falls back to the calibration lattice.
"""

import threading
import unittest

from inventory import scanner
from inventory.itemdb import ItemDB
from inventory.constants import PAGES, COLS, ROWS, SLOTS_PER_PAGE
from inventory.grid import GridLattice
from inventory.types import (
    InventoryMap, STATE_ITEM, STATE_EMPTY, STATE_UNKNOWN,
)

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from tests import _inv_synth as synth
except Exception:  # pragma: no cover
    synth = None


# A fixed lattice matching the synth origin/pitch the page factory stamps at, so
# the parallel/serial recognisers see items exactly where they were drawn.
_FIXED_LATTICE = GridLattice(origin=(2, 2), pitch=(32, 32))


def _fixed_align(image, db, calib):
    return _FIXED_LATTICE


class TestCapturePages(unittest.TestCase):
    """PHASE 1: fast capture buffers one frame per tab, no recognition."""

    def test_buffers_one_frame_per_page_in_order_and_returns_to_first(self):
        switched = []
        captured_calls = [0]
        # Distinct sentinel object per page so we can prove the buffer keyed each
        # page to ITS OWN frame (no recognition needed -- these are opaque here).
        frames = {p: object() for p in PAGES}

        def switch_page_fn(page):
            switched.append(page)

        def capture_fn():
            captured_calls[0] += 1
            # Return the frame for the most-recently switched-to tab.
            return frames[switched[-1]]

        captured = scanner.capture_pages(capture_fn, switch_page_fn, pages=PAGES)

        # Every page buffered exactly its own frame, in I->IV order.
        self.assertEqual(list(captured.keys()), list(PAGES))
        for p in PAGES:
            self.assertIs(captured[p], frames[p])
        # Switched I,II,III,IV and then back to the FIRST page (return_to_first).
        self.assertEqual(switched, list(PAGES) + [PAGES[0]])
        # Exactly one capture per page (no extra recognition captures).
        self.assertEqual(captured_calls[0], len(PAGES))

    def test_skips_a_page_whose_capture_fails_without_raising(self):
        def switch_page_fn(_page):
            pass

        def capture_fn():
            return None        # every capture fails

        captured = scanner.capture_pages(capture_fn, switch_page_fn, pages=PAGES)
        self.assertEqual(captured, {})          # all skipped, no raise

    def test_no_return_to_first_when_disabled(self):
        switched = []
        captured = scanner.capture_pages(
            lambda: object(), switched.append, pages=PAGES,
            return_to_first=False)
        self.assertEqual(switched, list(PAGES))  # no trailing return click
        self.assertEqual(len(captured), len(PAGES))

    def test_verify_retries_wrong_tab_once_then_keeps(self):
        # First capture of page II reports the WRONG tab (III); the switch is
        # retried and the second capture verifies correctly -> page kept.
        switched = []
        flip = {'II': True}

        def switch_page_fn(page):
            switched.append(page)

        def capture_fn():
            return ('frame', switched[-1], len(switched))

        def verify_page_fn(img):
            page = img[1]
            if page == 'II' and flip['II']:
                flip['II'] = False
                return 'III'           # wrong on the first look only
            return page

        captured = scanner.capture_pages(
            capture_fn, switch_page_fn, pages=PAGES,
            verify_page_fn=verify_page_fn)
        self.assertEqual(set(captured), set(PAGES))   # II recovered on retry
        # Page II was switched twice (initial + one retry).
        self.assertEqual(switched.count('II'), 2)


@unittest.skipUnless(np is not None and synth is not None, 'numpy required')
class TestRecognizePagesParallel(unittest.TestCase):
    """PHASE 2: parallel recognise == serial recognise, engine reused."""

    def setUp(self):
        self.db = ItemDB.from_bundled()
        if not self.db.references():
            self.skipTest('bundled icons / numpy unavailable')
        self.refs = self.db.references()

    def _buffered_pages(self):
        """A buffer of 4 synthetic pages, each with a few known items + empties
        + one unknown blob, so the map exercises all three slot states."""
        captured = {}
        for i, label in enumerate(PAGES):
            layout = [None] * SLOTS_PER_PAGE
            layout[0] = {'ref': self.refs[i % len(self.refs)], 'number': True}
            layout[5] = {'ref': self.refs[(i + 1) % len(self.refs)]}
            page, _ = synth.synth_page(layout, origin=(2, 2))
            # Stamp an unknown silhouette at slot (1,0) (flat-field guard -> a
            # high-contrast blob reads UNKNOWN, not EMPTY).
            x = 2 + 0 * 32
            y = 2 + 1 * 32
            page[y + 6:y + 26, x + 6:x + 26, :] = np.array(
                [160, 20, 180], dtype=np.uint8)
            captured[label] = page
        return captured

    def _states(self, inv):
        """Flatten an InventoryMap to {(page,row,col): (state, name)}."""
        out = {}
        for page, slots in inv.pages.items():
            for s in slots:
                out[(page, s.row, s.col)] = (s.state, s.name)
        return out

    def test_parallel_equals_serial_and_recognize_page(self):
        captured = self._buffered_pages()

        par = scanner.recognize_pages(captured, self.db, align_fn=_fixed_align)
        ser = scanner.recognize_pages(captured, self.db, align_fn=_fixed_align,
                                      max_workers=1)

        # The parallel map and the single-worker serial map are identical.
        self.assertEqual(self._states(par), self._states(ser))
        # ...and identical to the ORIGINAL per-page recogniser (engine reused).
        ref_states = {}
        for page, image in captured.items():
            for s in scanner.recognize_page(image, self.db,
                                            lattice=_FIXED_LATTICE, page=page):
                ref_states[(page, s.row, s.col)] = (s.state, s.name)
        self.assertEqual(self._states(par), ref_states)

        # Sanity: the buffer really exercised all three states.
        states_seen = {st for (st, _n) in self._states(par).values()}
        self.assertIn(STATE_ITEM, states_seen)
        self.assertIn(STATE_EMPTY, states_seen)
        self.assertIn(STATE_UNKNOWN, states_seen)
        # Every page has exactly 45 slots.
        for label in PAGES:
            self.assertEqual(len(par.pages[label]), SLOTS_PER_PAGE)

    def test_stack_number_read_in_parallel_path(self):
        # The per-slot stack-number read must still run inside the workers (the
        # item at (0,0) was stamped with a number) -> count is set.
        captured = self._buffered_pages()
        inv = scanner.recognize_pages(captured, self.db, align_fn=_fixed_align)
        first = next(s for s in inv.pages['I'] if s.row == 0 and s.col == 0)
        self.assertEqual(first.state, STATE_ITEM)
        self.assertIsNotNone(first.count)

    def test_actually_runs_on_multiple_threads(self):
        # Prove real fan-out: record the distinct worker-thread names seen while
        # classifying. With a real pool (>1 worker) and 180 short tasks at least
        # two threads must participate. We wrap the per-slot unit to sample the
        # current thread name (the unit is what each future runs).
        captured = self._buffered_pages()
        seen = set()
        lock = threading.Lock()
        orig = scanner._classify_one_slot

        def spy(*a, **k):
            with lock:
                seen.add(threading.current_thread().name)
            return orig(*a, **k)

        scanner._classify_one_slot = spy
        try:
            scanner.recognize_pages(captured, self.db, align_fn=_fixed_align,
                                    max_workers=4)
        finally:
            scanner._classify_one_slot = orig
        self.assertGreaterEqual(
            len(seen), 2, 'expected the recognise work to span >=2 threads')

    def test_empty_buffer_returns_empty_map(self):
        inv = scanner.recognize_pages({}, self.db, align_fn=_fixed_align)
        self.assertIsInstance(inv, InventoryMap)
        self.assertEqual(inv.pages, {})

    def test_worker_exception_degrades_slot_to_unknown(self):
        # A slot whose classification RAISES must degrade to UNKNOWN, never abort
        # the whole recognise. Force every per-slot call to raise.
        captured = self._buffered_pages()
        orig = scanner._classify_one_slot

        def boom(*a, **k):
            raise RuntimeError('slot blew up')

        scanner._classify_one_slot = boom
        try:
            inv = scanner.recognize_pages(captured, self.db,
                                          align_fn=_fixed_align, max_workers=4)
        finally:
            scanner._classify_one_slot = orig
        # Full shape preserved; every slot is a defensive UNKNOWN.
        self.assertEqual(set(inv.pages), set(PAGES))
        for label in PAGES:
            self.assertEqual(len(inv.pages[label]), SLOTS_PER_PAGE)
            self.assertTrue(all(s.state == STATE_UNKNOWN
                                for s in inv.pages[label]))

    def test_failing_aligner_falls_back_to_calibration_lattice(self):
        # An aligner that raises must not abort -- the page still classifies
        # against the calibration lattice (degraded, but a full 45-slot page).
        captured = self._buffered_pages()

        def boom_align(image, db, calib):
            raise RuntimeError('align blew up')

        inv = scanner.recognize_pages(captured, self.db, align_fn=boom_align)
        self.assertEqual(set(inv.pages), set(PAGES))
        for label in PAGES:
            self.assertEqual(len(inv.pages[label]), SLOTS_PER_PAGE)


@unittest.skipUnless(np is not None and synth is not None, 'numpy required')
class TestRecognizeProgress(unittest.TestCase):
    """Progress callback monotonicity + totals, on pool and serial paths."""

    def setUp(self):
        self.db = ItemDB.from_bundled()
        if not self.db.references():
            self.skipTest('bundled icons / numpy unavailable')

    def _buffer(self, n_pages=4):
        captured = {}
        for label in list(PAGES)[:n_pages]:
            page, _ = synth.synth_page([None] * SLOTS_PER_PAGE, origin=(2, 2))
            captured[label] = page
        return captured

    def _collect(self, captured, **kw):
        ticks = []
        lock = threading.Lock()

        def progress(done, total):
            with lock:
                ticks.append((done, total))

        scanner.recognize_pages(captured, self.db, progress_fn=progress,
                                align_fn=_fixed_align, **kw)
        return ticks

    def _assert_monotonic(self, ticks, expected_total):
        self.assertTrue(ticks, 'progress was never called')
        # Total is constant and correct.
        self.assertTrue(all(t == expected_total for (_d, t) in ticks))
        dones = [d for (d, _t) in ticks]
        # Exactly `total` ticks, strictly increasing 1..total, last == total.
        self.assertEqual(len(dones), expected_total)
        self.assertEqual(dones[0], 1)
        self.assertEqual(dones[-1], expected_total)
        self.assertTrue(all(b - a == 1 for a, b in zip(dones, dones[1:])),
                        'progress must increase by exactly one each tick')

    def test_progress_monotonic_parallel(self):
        captured = self._buffer(4)
        total = 4 * SLOTS_PER_PAGE
        ticks = self._collect(captured, max_workers=4)
        self._assert_monotonic(ticks, total)

    def test_progress_monotonic_serial(self):
        captured = self._buffer(4)
        total = 4 * SLOTS_PER_PAGE
        ticks = self._collect(captured, max_workers=1)
        self._assert_monotonic(ticks, total)

    def test_progress_total_tracks_buffered_page_count(self):
        # A partial buffer (2 of 4 pages) -> total is 2*45, not 4*45.
        captured = self._buffer(2)
        ticks = self._collect(captured, max_workers=4)
        self._assert_monotonic(ticks, 2 * SLOTS_PER_PAGE)

    def test_raising_progress_callback_never_aborts(self):
        captured = self._buffer(4)

        def boom(done, total):
            raise RuntimeError('progress sink down')

        # Must complete + return a full map despite the callback raising on
        # every tick.
        inv = scanner.recognize_pages(captured, self.db, progress_fn=boom,
                                      align_fn=_fixed_align, max_workers=4)
        self.assertEqual(set(inv.pages), set(PAGES[:4]))
        for label in list(PAGES)[:4]:
            self.assertEqual(len(inv.pages[label]), SLOTS_PER_PAGE)


if __name__ == '__main__':
    unittest.main()
