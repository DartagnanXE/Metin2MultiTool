"""Pfad-Helfer fuer Assets, der aus dem Quellcode UND aus der mit PyInstaller
(--onefile) gebauten EXE funktioniert.

Problem: ``cv.imread("images/x.png")`` und ``open("pieces_second.json")`` nutzen
RELATIVE Pfade. In der gepackten --onefile-EXE entpackt PyInstaller die
gebundelten Daten in ein temporaeres Verzeichnis (``sys._MEIPASS``); ein relativer
Pfad ins Arbeitsverzeichnis geht dann ins Leere -> die EXE verhaelt sich anders
als der Start aus dem Quellcode. ``resource_path()`` loest das robust auf:

  * gebundelte EXE  -> ``<sys._MEIPASS>/<rel>``, falls dort vorhanden
  * sonst (Quellcode / Entwicklung) -> ``<rel>`` (Verhalten unveraendert)

Die Funktion faellt IMMER auf den relativen Originalpfad zurueck, sodass nichts
kaputtgeht, wenn die Assets neben der EXE statt eingebettet liegen.
"""

import os
import sys


def resource_path(relative_path):
    """Liefert einen funktionierenden Pfad zu einer Asset-Datei."""
    base = getattr(sys, '_MEIPASS', None)
    if base:
        candidate = os.path.join(base, relative_path)
        if os.path.exists(candidate):
            return candidate
    return relative_path
