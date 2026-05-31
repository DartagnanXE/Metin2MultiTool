import numpy as np
import win32gui, win32ui, win32con
from i18n import t

# Optionales Diagnose-Logging. Bewusst weich eingebunden: faellt der Import
# (z.B. unter WSL/Test ohne Abhaengigkeiten) aus, bleibt die Capture-Logik
# unveraendert lauffaehig. Logging darf den Bot nie zum Absturz bringen.
try:
    from debuglog import log
except Exception:  # pragma: no cover - nur Fallback, falls Modul fehlt
    log = None


def _log_error(msg, exc=None):
    """Leitet eine Fehlermeldung an den Logger weiter, falls vorhanden.

    Schluckt jeden Logger-eigenen Fehler still, damit das Logging niemals
    den Capture-Pfad stoert.
    """
    if log is None:
        return
    try:
        log.error(msg, exc=exc)
    except Exception:
        pass


class WindowCapture:

    # properties
    w = 0
    h = 0
    hwnd = None
    cropped_x = 0
    cropped_y = 0
    offset_x = 0
    offset_y = 0

    # constructor
    def __init__(self, window_name):
        # find the handle for the window we want to capture
        self.hwnd = win32gui.FindWindow(None, window_name)
        if not self.hwnd:
            msg = t('capture.window_not_found', window_name=window_name)
            _log_error(t('capture.init_failed', msg=msg))
            raise Exception(msg)

        # get the window size
        window_rect = win32gui.GetWindowRect(self.hwnd)
        self.w = window_rect[2] - window_rect[0]
        self.h = window_rect[3] - window_rect[1]

        # Plausibilitaet der Fenstergroesse pruefen: ein 0/negativ grosses
        # Fenster (minimiert/zerstoert) wuerde spaeter beim Capture zu einer
        # leeren oder fehlerhaften Bitmap fuehren -> frueh und klar melden.
        if self.w <= 0 or self.h <= 0:
            msg = t('capture.invalid_window_size',
                    window_name=window_name, w=self.w, h=self.h)
            _log_error(t('capture.init_failed', msg=msg))
            raise Exception(msg)

        # account for the window border and titlebar and cut them off
        border_pixels = 8
        titlebar_pixels = 30
        self.w = self.w - (border_pixels * 2)
        self.h = self.h - titlebar_pixels - border_pixels
        self.cropped_x = border_pixels
        self.cropped_y = titlebar_pixels

        # set the cropped coordinates offset so we can translate screenshot
        # images into actual screen positions
        self.offset_x = window_rect[0] + self.cropped_x
        self.offset_y = window_rect[1] + self.cropped_y

    def get_screenshot(self):

        # get the window image data
        wDC = win32gui.GetWindowDC(self.hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, self.w, self.h)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (self.w, self.h), dcObj, (self.cropped_x, self.cropped_y), win32con.SRCCOPY)

        # convert the raw data into a format opencv can read
        #dataBitMap.SaveBitmapFile(cDC, 'debug.bmp')
        signedIntsArray = dataBitMap.GetBitmapBits(True)

        # Roh-Puffer defensiv pruefen: leere/zu kleine Bilddaten (z.B. Fenster
        # in der Zwischenzeit minimiert/geschlossen) wuerden beim Umformen unten
        # zu einem kryptischen Shape-Fehler fuehren -> hier klar melden.
        expected_bytes = self.w * self.h * 4
        if not signedIntsArray or len(signedIntsArray) < expected_bytes:
            # Ressourcen trotzdem freigeben, damit kein GDI-Leak entsteht.
            dcObj.DeleteDC()
            cDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, wDC)
            win32gui.DeleteObject(dataBitMap.GetHandle())
            msg = t('capture.screenshot_too_little_data',
                    actual=0 if not signedIntsArray else len(signedIntsArray),
                    expected=expected_bytes)
            _log_error(t('capture.get_screenshot_failed', msg=msg))
            raise Exception(msg)

        # np.frombuffer statt des in NumPy >= 2 entfernten np.fromstring
        # (fromstring im Binaermodus wirft dort ValueError). frombuffer liefert
        # ein schreibgeschuetztes Array; .copy() macht es beschreibbar, damit
        # die nachfolgende Zuweisung img.shape = ... nicht fehlschlaegt.
        img = np.frombuffer(signedIntsArray, dtype='uint8').copy()
        img.shape = (self.h, self.w, 4)

        # free resources
        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())

        # drop the alpha channel, or cv.matchTemplate() will throw an error like:
        #   error: (-215:Assertion failed) (depth == CV_8U || depth == CV_32F) && type == _templ.type() 
        #   && _img.dims() <= 2 in function 'cv::matchTemplate'
        img = img[...,:3]

        # make image C_CONTIGUOUS to avoid errors that look like:
        #   File ... in draw_rectangles
        #   TypeError: an integer is required (got type tuple)
        # see the discussion here:
        # https://github.com/opencv/opencv/issues/14866#issuecomment-580207109
        img = np.ascontiguousarray(img)

        return img

    # find the name of the window you're interested in.
    # once you have it, update window_capture()
    # https://stackoverflow.com/questions/55547940/how-to-get-a-list-of-the-name-of-every-open-window
    def list_window_names(self):
        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                print(hex(hwnd), win32gui.GetWindowText(hwnd))
        win32gui.EnumWindows(winEnumHandler, None)

    # translate a pixel position on a screenshot image to a pixel position on the screen.
    # pos = (x, y)
    # WARNING: if you move the window being captured after execution is started, this will
    # return incorrect coordinates, because the window position is only calculated in
    # the __init__ constructor.
    def get_screen_position(self, pos):
        return (pos[0] + self.offset_x, pos[1] + self.offset_y)