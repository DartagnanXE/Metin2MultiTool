# -*- coding: utf-8 -*-
"""Deterministic, funny ANON-NAME generator (PURE, stdlib-only).

From a random install id derive a stable display name of the shape
``<Adjective><Animal>#<4 digits>`` (e.g. ``TapfererThunfisch#4711``). The SAME
install id + language always yields the SAME name; different ids (almost surely)
differ. Fishing-flavoured, tasteful EN + DE word lists with REAL umlauts in DE.

Derivation (deterministic, never raises):
  * ``h = sha256(install_id).digest()``
  * adjective index = ``h[0:2]`` mod len(ADJECTIVES[lang])
  * animal index    = ``h[2:4]`` mod len(ANIMALS[lang])
  * 4-digit suffix  = ``h[4:6]`` mod 10000, zero-padded
On a junk id (non-str / unhashable) it falls back to hashing ``repr(id)``.

NOTE: a logically-identical copy lives in ``server/app/anon_name.py`` -- the SAME
word lists + algorithm (the server package is import-isolated from ``telemetry/``,
so the code is duplicated rather than shared). The two are NOT byte-identical (the
docstrings differ); a shared EN/DE test vector pins the OUTPUT so they can never
silently drift.
"""

import hashlib

# Fishing-flavoured adjectives. EN and DE lists are the SAME length so the index
# space matches across languages (a given id maps to the same SLOT in either).
ADJECTIVES = {
    'en': (
        'Brave', 'Nimble', 'Golden', 'Silent', 'Lucky', 'Mighty', 'Sly',
        'Calm', 'Swift', 'Bold', 'Shiny', 'Wise', 'Wild', 'Royal', 'Frosty',
        'Sunny',
    ),
    'de': (
        'Tapferer', 'Flinker', 'Goldener', 'Stiller', 'Glücklicher',
        'Mächtiger', 'Schlauer', 'Ruhiger', 'Schneller', 'Kühner',
        'Glänzender', 'Weiser', 'Wilder', 'Königlicher', 'Frostiger',
        'Sonniger',
    ),
}

# Fishing-flavoured animals (fish + water creatures). Same length EN == DE.
ANIMALS = {
    'en': (
        'Tuna', 'Pike', 'Carp', 'Trout', 'Salmon', 'Perch', 'Eel', 'Catfish',
        'Shark', 'Crab', 'Squid', 'Marlin', 'Herring', 'Bass', 'Ray',
        'Lobster',
    ),
    'de': (
        'Thunfisch', 'Hecht', 'Karpfen', 'Forelle', 'Lachs', 'Barsch', 'Aal',
        'Wels', 'Hai', 'Krabbe', 'Tintenfisch', 'Marlin', 'Hering', 'Barsch',
        'Rochen', 'Hummer',
    ),
}


def _digest(install_id):
    """sha256 digest of ``install_id`` (or its repr on junk). Never raises."""
    try:
        data = install_id.encode('utf-8', 'replace')
    except Exception:
        data = repr(install_id).encode('utf-8', 'replace')
    return hashlib.sha256(data).digest()


def anon_name(install_id, lang='en'):
    """Return a stable funny ``<Adj><Animal>#NNNN`` name for ``install_id``.

    Deterministic for the same ``(install_id, lang)``; different ids (almost
    surely) differ. ``lang`` outside ``ADJECTIVES`` falls back to ``'en'``.
    Pure, no I/O, never raises.
    """
    if lang not in ADJECTIVES:
        lang = 'en'
    adjectives = ADJECTIVES[lang]
    animals = ANIMALS[lang]
    h = _digest(install_id)
    adj = adjectives[int.from_bytes(h[0:2], 'big') % len(adjectives)]
    animal = animals[int.from_bytes(h[2:4], 'big') % len(animals)]
    suffix = int.from_bytes(h[4:6], 'big') % 10000
    return '{}{}#{:04d}'.format(adj, animal, suffix)


__all__ = ['ADJECTIVES', 'ANIMALS', 'anon_name']
