# -*- coding: utf-8 -*-
"""Okey-Kartenspiel: Regeln, Strategie, Erkennung und Ablauf."""

import os


def templates_dir():
    """Ordner mit den Okey-Schablonen -- aus dem Quellcode UND aus der EXE.

    ``respath.resource_path`` faellt im Entwicklungsfall auf einen RELATIVEN
    Pfad zurueck; der zeigt ins Leere, sobald das Programm aus einem anderen
    Arbeitsverzeichnis gestartet wird. Deshalb hier dieselbe Absicherung wie im
    Seherwettstreit-Teil: erst den gebundelten Pfad versuchen, sonst den
    absoluten Ordner NEBEN diesem Paket nehmen. Der Rueckgabewert ist damit
    unabhaengig davon, wo jemand das Programm gestartet hat.
    """
    try:
        from respath import resource_path
        kandidat = resource_path('okey_templates')
        if os.path.isdir(kandidat):
            return kandidat
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'okey_templates')
