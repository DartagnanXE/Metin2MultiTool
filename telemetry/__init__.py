# -*- coding: utf-8 -*-
"""Ranking telemetry package (ANONYMOUS, always-on counter).

Import surface mirrors ``interface/__init__``: the PURE pieces (``hwid``,
``payload``, ``anon_name``) import with stdlib only, so headless tests can use
them WITHOUT pulling in threads/network. The IO ``client`` (urllib + daemon
thread) is exposed lazily via ``__getattr__`` so merely importing
:mod:`telemetry` never starts a thread or touches the network.

Anonymous model (replaces the old off-by-default opt-in + hardware HWID):
  * An always-on anonymous counter keyed by a RANDOM per-install uuid
    (``telemetry.install_id``) -- NOT a device fingerprint; a source editor can
    rotate it, so it is mass-protection only. There is NO opt-out of the
    anonymous counter; the app shows a one-line transparency notice instead.
  * Everyone appears on the ranking under a deterministic funny name derived
    from the random id (``anon_name``). The ONLY consent / "PII" is a self-chosen
    name: typing one reveals it on the board; clearing it returns to the anon
    name.
  * Nothing is sent while there is no install_id/url, or when the server has
    blocked this installation (see ``client.start_sender``).
"""

from telemetry import hwid, payload, anon_name   # pure, stdlib-only

__all__ = ['hwid', 'payload', 'anon_name', 'client']


def __getattr__(name):
    """Lazily import the network ``client`` only when actually accessed.

    Keeps ``import telemetry`` (and the pure tests) free of urllib/threads.
    Uses ``importlib`` (NOT ``from telemetry import client``) so this hook does
    not recurse into itself.
    """
    if name == 'client':
        import importlib
        return importlib.import_module('telemetry.client')
    raise AttributeError(
        '{!r} has no attribute {!r}'.format(__name__, name))
