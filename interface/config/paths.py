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

FIX v1 (zu kurz gedacht): Pfad an die EXE gebunden (NEBEN der EXE). Das loeste
das CWD-Problem, war aber NICHT versions-/rebuild-stabil -- "neben der EXE" haengt
am EXE-ORDNER: eine neue Version, ein neuer Download oder ein Rebuild (anderer
bzw. geleerter Ordner) findet die alte Config NICHT -> Onboarding + neue
``install_id`` kamen ERNEUT.

FIX v2 (jetzt, bombenfest): Im gepackten Zustand (``sys.frozen``) liegt die Config
in ``%APPDATA%/Metin2FishBot/config.json`` -- ein PRO-NUTZER-Pfad, der sich NIE
aendert (kein Versionsname, kein EXE-Ordner darin). Damit ueberlebt die Identitaet
(``install_id``, gewaehlter Name, ``consented``, ``rating_prompted``) JEDE Version,
jeden Rebuild und jedes Verschieben der EXE -> das Onboarding erscheint pro Windows-
Nutzer HOECHSTENS EINMAL. Alte Speicherorte (neben der EXE = v1; CWD = vor-v1)
werden beim Laden EINMAL migriert (s. :func:`legacy_config_paths` + ``io.load``).
Im Dev-/Testbetrieb (nicht frozen) bleibt es ``'config.json'`` im CWD -> byte-stabil.

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
    """Versions-/ordner-/rebuild-STABILER ``config.json``-Pfad (s. Modul-Docstring).

    * nicht frozen (Dev/Test) -> ``'config.json'`` (CWD, unveraendert)
    * frozen (Portable-EXE)   -> ``%APPDATA%/Metin2FishBot/config.json``

    ``executable`` wird nicht mehr gebraucht (nur fuer Rueckwaerts-Kompat der
    Test-Signatur belassen). Wirft NIE -> jeder Fehler faellt auf den reinen
    Dateinamen (CWD) zurueck.
    """
    try:
        if frozen is None:
            frozen = bool(getattr(sys, 'frozen', False))
        if not frozen:
            return FILENAME
        return _appdata_path(appdata)
    except Exception:
        return FILENAME


def sibling_path(filename, appdata=None):
    """Pfad einer Datei im GLEICHEN stabilen Ordner wie die ``config.json`` --
    z.B. ``stats.json`` (Fang-/Puzzle-Zaehler). Dev/Test: ``filename`` im CWD;
    frozen: ``%APPDATA%/Metin2FishBot/<filename>``. So ueberlebt eine config-
    Geschwisterdatei Versionen/Rebuilds genauso wie die config. Wirft nie."""
    try:
        directory = os.path.dirname(config_path(appdata=appdata))
        return os.path.join(directory, filename) if directory else filename
    except Exception:
        return filename


def legacy_sibling_paths(filename, executable=None):
    """Frueheres Speicherorte einer config-Geschwisterdatei (``config.json`` /
    ``stats.json``) fuer die EINMALIGE Migration nach ``%APPDATA%`` -- in
    Praeferenz: (1) NEBEN der EXE (FIX v1) und (2) im CWD (vor-v1 / Dev). Wirft nie.
    """
    out = []
    try:
        exe = executable if executable is not None else sys.executable
        exe_dir = os.path.dirname(os.path.abspath(exe or FILENAME))
        out.append(os.path.join(exe_dir, filename))
    except Exception:
        pass
    out.append(filename)
    return out


def legacy_config_paths(executable=None):
    """Alte ``config.json``-Speicherorte (= :func:`legacy_sibling_paths` fuer
    ``config.json``). :func:`io.load` liest sie, wenn am %APPDATA%-Pfad noch nichts
    liegt -> ein Upgrader behaelt Identitaet + Einstellungen. Wirft nie."""
    return legacy_sibling_paths(FILENAME, executable=executable)


__all__ = ['config_path', 'legacy_config_paths', 'sibling_path',
           'legacy_sibling_paths', 'FILENAME', 'APP_DIR']
