import numpy as np
import cv2 as cv

class HsvFilter:

    def __init__(self, hMin=None, sMin=None, vMin=None, hMax=None, sMax=None, vMax=None,
                    sAdd=None, sSub=None, vAdd=None, vSub=None):
        self.hMin = hMin
        self.sMin = sMin
        self.vMin = vMin
        self.hMax = hMax
        self.sMax = sMax
        self.vMax = vMax
        self.sAdd = sAdd
        self.sSub = sSub
        self.vAdd = vAdd
        self.vSub = vSub
        self._build_cache()

    def _build_cache(self):
        """Cache the per-frame-invariant pieces of :meth:`apply_hsv_filter`.

        The filter config never changes during a run, so the threshold bound
        arrays are precomputed once here instead of re-allocating them every
        frame. ``_any_shift`` records whether any saturation/value shift is
        actually non-zero: when all four are 0 the split/shift/merge block is a
        no-op (``shift_channel`` with ``amount == 0`` returns the channel
        untouched) and is skipped for the default config -- byte-identical
        output, less work in the ~30 Hz hot loop. Defensive: a missing/None
        bound leaves the cache empty and the slow path rebuilds it lazily.
        """
        try:
            self._lower = np.array([self.hMin, self.sMin, self.vMin])
            self._upper = np.array([self.hMax, self.sMax, self.vMax])
        except Exception:
            self._lower = None
            self._upper = None
        self._any_shift = bool(self.sAdd or self.sSub or self.vAdd or self.vSub)

    def shift_channel(self, c, amount):
        if amount > 0:
            lim = 255 - amount
            c[c >= lim] = 255
            c[c < lim] += amount
        elif amount < 0:
            amount = -amount
            lim = amount
            c[c <= lim] = 0
            c[c > lim] -= amount
        return c


    def apply_hsv_filter(self, original_image):
        # convert image to HSV
        hsv = cv.cvtColor(original_image, cv.COLOR_BGR2HSV)

        # add/subtract saturation and value -- but ONLY when a shift is actually
        # non-zero. For the default config (all shifts 0) the split+4 no-op
        # shift_channel calls+merge produce an identical array, so we skip them.
        if self._any_shift:
            h, s, v = cv.split(hsv)
            s = self.shift_channel(s, self.sAdd)
            s = self.shift_channel(s, -1*self.sSub)
            v = self.shift_channel(v, self.vAdd)
            v = self.shift_channel(v, -1*self.vSub)
            hsv = cv.merge([h, s, v])

        # Threshold bounds are precomputed in _build_cache (config is constant for
        # the run); fall back to a per-call build if the cache is missing.
        lower = self._lower
        upper = self._upper
        if lower is None or upper is None:
            lower = np.array([self.hMin, self.sMin, self.vMin])
            upper = np.array([self.hMax, self.sMax, self.vMax])
        # Apply the thresholds
        mask = cv.inRange(hsv, lower, upper)
        result = cv.bitwise_and(hsv, hsv, mask=mask)

        # convert back to BGR for imshow() to display it properly
        img = cv.cvtColor(result, cv.COLOR_HSV2BGR)

        return img