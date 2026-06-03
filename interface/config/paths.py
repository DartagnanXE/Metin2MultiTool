# -*- coding: utf-8 -*-
"""Stabile On-Disk-Position der ``config.json``.

HISTORIE / BUG: Frueher war der Pfad ein nackter ``'config.json'`` -- relativ
zum *Arbeitsverzeichnis* (CWD). Bei einer doppelgeklickten Portable-EXE ist das
CWD NICHT verlaesslich die EXE-Position (Verknuepfung mit anderem "Ausfuehren
in", Start aus einem anderen Ordner, "Als Admin" -> System32, manche Launcher).
Folge: die Config wurde mal hier, mal da gesucht -> bei jedem Start "frische
Defaults" -> Onboarding-Dialog kam erneut, ``install_id`` wurde neu gewuerfelt
(zersplitterte Leaderboard-Eintraege -- "zwei FishLover"), das GitHub-Rating-
Popup erschien erneut.

FIX: Im gepackten Zustand (``sys.frozen``) liegt die Config NEBEN der EXE
(Portable -- sie wandert mit dem Ordner und ueberlebt Neustarts), exakt wie es
der ``io.py``-Docstring immer behauptet hat und wie ``trained_solver._cache_path``
es nebenan bereits korrekt macht. Ist der EXE-Ordner ausnahmsweise nicht
schreibbar (z.B. Program Files ohne Admin, read-only-Mount), faellt der Pfad auf
``%APPDATA%/Metin2FishBot`` zurueck (immer schreibbar). Im Dev-/Testbetrieb
(nicht frozen) bleibt es das bisherige ``'config.json'`` im CWD -> Tests und
Entwicklungslauf sind byte-stabil.

Bewusst NUR Standardbibliothek (os, sys). Wirft NIE -- jeder Fehlerpfad faellt
auf den (immer funktionierenden) Dev-Default zurueck.
"""

import os
import sys

#: Reiner Dateiname -- Dev-/Test-Fallback (CWD-relativ, unveraendert).
FILENAME = 'config.json'

#: Unterordner im per-user App-Data fuer den read-only-EXE-Fallback.
APP_DIR = 'Metin2FishBot'

_WRITE_PROBE = '.m2fb_write_test'


def _dir_writable(directory):
    """True, wenn in ``directory`` eine Datei angelegt werden kann. Wirft nie.

    Macht einen echten (winzigen) Schreib-/Loeschversuch statt nur ``os.access``
    -- Letzteres luegt unter Windows bei manchen ACL-Konstellationen.
    """
    try:
        if not directory or not os.path.isdir(directory):
            return False
        probe = os.path.join(directory, _WRITE_PROBE)
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('')
        os.remove(probe)
        return True
    except Exception:
        return False


def _appdata_path(appdata=None):
    """``%APPDATA%/Metin2FishBot/config.json`` (Ordner wird angelegt). Wirft nie."""
    base = appdata if appdata is not None else os.environ.get('APPDATA')
    if not base:
        base = os.path.expanduser('~')
    target = os.path.join(base, APP_DIR)
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        pass
    return os.path.join(target, FILENAME)


def config_path(frozen=None, executable=None, appdata=None):
    """Liefert den aufzuloesenden ``config.json``-Pfad (s. Modul-Docstring).

    Parameter sind nur fuer Tests da -- in Produktion alle ``None`` -> es zaehlen
    ``sys.frozen`` / ``sys.executable`` / ``%APPDATA%``. Wirft NIE: jeder Fehler
    faellt auf den reinen Dateinamen (CWD) zurueck.

    * nicht frozen (Dev/Test) -> ``'config.json'`` (CWD, unveraendert)
    * frozen + EXE-Ordner schreibbar -> ``<exe-dir>/config.json`` (Portable)
    * frozen + EXE-Ordner read-only -> ``%APPDATA%/Metin2FishBot/config.json``
    """
    try:
        if frozen is None:
            frozen = bool(getattr(sys, 'frozen', False))
        if not frozen:
            return FILENAME
        exe = executable if executable is not None else sys.executable
        exe_dir = os.path.dirname(os.path.abspath(exe or FILENAME))
        if _dir_writable(exe_dir):
            return os.path.join(exe_dir, FILENAME)
        return _appdata_path(appdata)
    except Exception:
        return FILENAME


__all__ = ['config_path', 'FILENAME', 'APP_DIR']
