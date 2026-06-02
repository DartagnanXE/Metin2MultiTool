# -*- coding: utf-8 -*-
"""Random per-install id for the ranking (NO hardware/device derivation).

Anonymous model: the install id is a uuid4 generated ONCE on first run and
stored locally in config (``telemetry.install_id``). It is NOT a device
fingerprint -- there is no winreg / volume-serial / hostname read here. Because
the client is open source, a source editor can rotate the id, so it is
mass-protection only (the server can block one installation by its handle), NOT
an authentication token. This is documented honestly in server/THREAT_MODEL.md.

The physical module keeps the filename ``hwid.py`` so existing imports stay
byte-stable (the WIRE/DB field is still named ``hwid`` -- it now simply CARRIES
this random install_id value; see the design + THREAT_MODEL.md).

API:
  * ``new_install_id()``     -> a fresh uuid4 hex (32 chars), PURE wrapper.
  * ``ensure_install_id(getter, setter)`` -> read the stored id; generate +
    persist one on first use; never raises.
  * ``get_hwid()``           -> compat shim: a PROCESS-STABLE random id (cached
    in a module global). NOT a machine hash. Prefer the config ``install_id``.

Stdlib only (uuid).
"""

import uuid

# Defensive length cap (uuid4 hex is 32 chars; full str form 36). Mirrors
# interface.config.INSTALL_ID_MAXLEN + the server HWID_MAXLEN.
INSTALL_ID_MAXLEN = 64

# Process-stable random id for the get_hwid() compat shim (lazily generated +
# cached). NOT persisted, NOT a machine hash -- just a bounded hex string that is
# stable within one process so old call sites keep a consistent handle.
_process_id = None


def new_install_id():
    """Return a fresh random install id (uuid4 hex, 32 chars). PURE; never raises."""
    try:
        return uuid.uuid4().hex
    except Exception:
        # uuid4 effectively never fails, but stay defensive -> a fixed-shape id.
        return uuid.UUID(int=0).hex


def _valid(value):
    """A stripped, lowercased, capped id string, or '' on None/junk/empty.

    ``None`` is treated as empty (NOT the literal 'none') so a missing stored id
    triggers generation. Never raises."""
    if value is None:
        return ''
    try:
        s = str(value).strip().lower()
    except Exception:
        return ''
    return s[:INSTALL_ID_MAXLEN]


def ensure_install_id(cfg_get, cfg_set):
    """Return the stored install id, generating + persisting one on first use.

    ``cfg_get()`` -> the current ``telemetry.install_id`` (str or ''); if empty/
    invalid a fresh id is minted via :func:`new_install_id`, handed to
    ``cfg_set(new_id)`` to persist, and returned. Never raises: on any failure
    it returns a freshly generated in-memory id so a submit can still go out
    (the caller may simply not have persisted it yet).
    """
    try:
        current = _valid(cfg_get() if callable(cfg_get) else None)
    except Exception:
        current = ''
    if current:
        return current
    new_id = new_install_id()
    try:
        if callable(cfg_set):
            cfg_set(new_id)
    except Exception:
        pass
    return new_id


def get_hwid():
    """Compat shim: a PROCESS-STABLE RANDOM id (NOT a machine hash).

    Kept so older call sites / tests that imported ``get_hwid`` keep working.
    Prefer the config ``install_id`` (resolved via :func:`ensure_install_id`).
    Returns a bounded hex string, stable within one process. Never raises.
    """
    global _process_id
    if _process_id is None:
        _process_id = new_install_id()
    return _process_id
