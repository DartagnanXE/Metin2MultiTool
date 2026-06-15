# -*- coding: utf-8 -*-
"""Energiesplitter-Paket -- Paket-Init (Eigentuemer D, CONTRACT §5).

Exportiert die oeffentliche Paket-Oberflaeche: die Bot-Klasse
``EnergiesplitterBot`` und die Modus-Konstanten ``MODE_HAMMER``/``MODE_DAGGER``.

LAZY-Export (PEP 562): ``bot`` wird ERST beim ersten Zugriff auf eines dieser
Symbole importiert -- nicht schon beim Paket-Import. Damit aendert dieses
``__init__`` den Import-Graphen der Schwester-Module NICHT: ``from
energiesplitter import calc`` (bzw. ``detect``/``geometry``)
zieht ``bot`` (und dessen weichen ``pydirectinput``-Import) nicht mit herein.
Das haelt die Headless-Tests isoliert: wer den Eingabe-Treiber stubben will
(``tests/test_energiesplitter_flow.py``), importiert ``energiesplitter.bot``
selbst -- erst dann wird der Treiber gebunden.

Der Bot-Import bleibt headless-sicher: ``bot.py`` importiert
``pydirectinput``/``windowcapture``/die Vision-Module WEICH (try/except), sodass
``from energiesplitter import EnergiesplitterBot`` auch ohne Windows-Treiber
nicht crasht (der Phase-0-GATE meldet fehlende Stuecke als ``missing``).
"""

__all__ = ['EnergiesplitterBot', 'MODE_HAMMER', 'MODE_DAGGER']


def __getattr__(name):
  if name in __all__:
    from energiesplitter import bot as _bot
    return getattr(_bot, name)
  raise AttributeError('module %r has no attribute %r' % (__name__, name))


def __dir__():
  return sorted(list(globals().keys()) + __all__)
