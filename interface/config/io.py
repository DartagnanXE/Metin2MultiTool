"""Laden/Speichern der Konfiguration + Ableitung des Fishing-``values``-Dicts.

Bewusst NUR Python-Standardbibliothek (``json``), damit dieses Modul auch ohne
GUI-Toolkit ueberall importier- und testbar bleibt und aus der gepackten ``.exe``
heraus funktioniert.

Die ``config.json`` liegt neben der EXE. Sie haelt ALLE UI-Optionen
(Modus, Fishing-Timings, Puzzle-Detection/Color/Solver, Log-Sichtbarkeit).

Grundregeln:
  * Laden wirft NIE -- fehlende/kaputte Datei -> Defaults.
  * Unbekannte/fehlende Schluessel werden mit Defaults gefuellt (Vorwaerts-/
    Rueckwaertskompatibilitaet zu alten config.json-Dateien).
"""

import json

from .defaults import DEFAULT_CONFIG_PATH, DEFAULTS
from .paths import FILENAME as _LEGACY_FILENAME
from .validate import validate


def _read_json(path):
    """Liest + parst JSON oder gibt ``None`` (fehlt/kaputt/Fehler). Wirft nie."""
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.loads(handle.read())
    except Exception:
        return None


def load(path=None):
    """Laedt und validiert die Konfiguration. Wirft NIE.

    ``path=None`` (der Normalfall, ``hack.py`` ruft ``cfgmod.load()``) liest den
    aktuellen Default-Pfad (``DEFAULT_CONFIG_PATH``, EXE-gebunden im frozen-Lauf).
    Fehlende/fehlerhafte Datei -> validierte Defaults (es wird nichts geschrieben;
    das uebernimmt erst :func:`save`).

    MIGRATION (nur impliziter Default-Load im frozen-Lauf): Seit der Pfad an die
    EXE gebunden ist (s. paths.py), kann eine alte ``config.json`` aus dem
    frueheren CWD-Pfad herumliegen. Fehlt die Datei am (neuen) Default-Pfad UND
    unterscheidet der sich vom nackten ``'config.json'`` (also: frozen), wird der
    CWD-Pfad EINMAL als Fallback gelesen -> ein Upgrader verliert seine
    Einstellungen nicht. Geschrieben wird beim naechsten :func:`save` an den
    neuen Pfad.

    Wichtig: bei EXPLIZIT uebergebenem ``path`` (Tests, Spezialaufrufe) gibt es
    KEINE CWD-Migration -- ein fehlender expliziter Pfad liefert sauber Defaults
    (sonst wuerde ein Test, der aus einem Verzeichnis MIT ``config.json`` laeuft,
    faelschlich diese aufsammeln).
    """
    explicit = path is not None
    if path is None:
        path = DEFAULT_CONFIG_PATH
    raw = _read_json(path)
    if raw is None and not explicit and path != _LEGACY_FILENAME:
        raw = _read_json(_LEGACY_FILENAME)
    if raw is None:
        return validate(DEFAULTS)
    return validate(raw)


def save(cfg, path=DEFAULT_CONFIG_PATH):
    """Schreibt die (validierte) Konfiguration als JSON. Wirft NIE.

    Gibt ``True`` bei Erfolg, sonst ``False`` (Aufrufer darf den Rueckgabewert
    ignorieren -- ein Speicherfehler darf den Bot nicht stoppen).
    """
    try:
        normalized = validate(cfg)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(normalized, indent=2, ensure_ascii=False))
        return True
    except Exception:
        return False


def to_values(cfg):
    """Baut den Fishing-``values``-Dict (frozen keys) aus der Konfiguration.

    Liefert exakt die Schluessel, die ``FishingBot.set_to_begin(values)`` liest
    (und die ``PuzzleBot.set_to_begin`` ignoriert). So bleibt die Wertekompati-
    bilitaet zu beiden Bots gewahrt, ohne FreeSimpleGUI.
    """
    normalized = validate(cfg)
    fishing = normalized['fishing']
    return {
        '-ENDTIMEP-': bool(fishing['stop_after_enabled']),
        '-ENDTIME-': str(fishing['stop_after_minutes']),
        '-BAITTIME-': float(fishing['bait_time']),
        '-THROWTIME-': float(fishing['throw_time']),
        '-STARTGAME-': float(fishing['start_game_time']),
        '-GOLDENTUNA-': int(fishing['golden_tuna_action']),
        # Mount-Animation-Cancel: an/aus + Taste -- vom FishingBot wie die
        # uebrigen frozen keys gelesen (Default AUS/'3' -> byte-stabil).
        '-MOUNT-': bool(fishing['mount_enabled']),
        '-MOUNTKEY-': str(fishing['mount_key']),
        # Angel-Whitelist an/aus (Default AUS -> byte-stabil). Die konkreten
        # Fisch-Entscheidungen (whitelist_states) injiziert der RunLoop separat
        # auf die Bot-Instanz -- hier nur der Master-Schalter.
        '-WHITELIST-': bool(fishing['whitelist_enabled']),
    }


__all__ = ['load', 'save', 'to_values']
