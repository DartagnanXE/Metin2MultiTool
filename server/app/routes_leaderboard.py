# -*- coding: utf-8 -*-
"""GET /leaderboard?period=daily|all -- cached top-20, aggregated, excludes banned.

A short in-process cache (CACHE_TTL_S, default 30s) blunts scraping and repeated
refresh clicks. The cache holds ONLY the period-keyed top-20 (identity-agnostic).
The optional caller identity (``?hwid=`` = install id, and/or ``?username=``) is
resolved FRESH per request via :func:`db.self_rank` (install id FIRST) -- so two
different installs never receive each other's self-row from the cache, and the
user's own row reflects the latest submission even when the cached top-20 lags up
to the TTL. Each row's display name (``username`` field) is the chosen name when
set + not hidden, else the anonymous funny name computed server-side from the
install id. The aggregation (MAX counters per install, blocked excluded, hidden
names blanked) lives in db.
"""

import os
import time
import threading
from typing import Optional

from fastapi import APIRouter, Query

from .schemas import LeaderboardOut, LeaderboardEntry, LeaderboardSelf
from . import db

router = APIRouter()

CACHE_TTL_S = int(os.environ.get('CACHE_TTL_S', '30'))
_CACHE_LOCK = threading.Lock()
_CACHE = {}                 # period -> (fetched_at, [LeaderboardEntry])

# Top-N shown on the public board (spec: top-20; the client may replace the
# 20th visible row with the caller's own row when their rank is > 20).
TOP_N = 20


def _cached_entries(period):
    """Return the cached (period-keyed) top-20 entry list, refreshing on TTL."""
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(period)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    rows = db.leaderboard(period=period, limit=TOP_N)
    entries = [
        LeaderboardEntry(
            rank=r['rank'], username=r['display_name'],
            fishing_catches=r['fishing_catches'],
            puzzles_solved=r['puzzles_solved'],
            fishing_runtime_s=r['fishing_runtime_s'],
            puzzler_runtime_s=r['puzzler_runtime_s'])
        for r in rows
    ]
    with _CACHE_LOCK:
        _CACHE[period] = (now, entries)
    return entries


def _self_row(hwid, username, period):
    """Resolve the caller's own ranked row FRESH (uncached). None when absent."""
    if not hwid and not (username or '').strip():
        return None
    row = db.self_rank(hwid=hwid, username=username, period=period)
    if not row:
        return None
    return LeaderboardSelf(
        rank=row['rank'], username=row['display_name'],
        fishing_catches=row['fishing_catches'],
        puzzles_solved=row['puzzles_solved'],
        fishing_runtime_s=row['fishing_runtime_s'],
        puzzler_runtime_s=row['puzzler_runtime_s'])


@router.get('/leaderboard', response_model=LeaderboardOut)
async def leaderboard(
        period: str = Query('all', pattern='^(all|daily)$'),
        hwid: Optional[str] = Query(None, max_length=64),
        username: Optional[str] = Query(None, max_length=32)):
    """Return the cached top-20 for ``period`` plus the caller's own ranked row.

    Identity inputs are optional + length-capped (strict 422 on overflow). The
    top-20 is cached per period; ``self`` is computed fresh from hwid (preferred)
    then username. Backward compatible: omit the identity -> ``self`` is null.
    """
    entries = _cached_entries(period)
    me = _self_row(hwid, username, period)
    return LeaderboardOut(period=period, entries=entries, self=me)


@router.get('/check_name')
async def check_name(
        username: str = Query(..., max_length=32),
        hwid: Optional[str] = Query(None, max_length=64)):
    """Is a self-chosen ``username`` still available (case-insensitive)?

    Returns ``{name, available, owner_is_self}``. A name is AVAILABLE when no
    install owns it yet, or when the OWNER is the caller's own ``hwid`` (a
    returning user re-confirming their own name is never told it is taken). An
    empty/whitespace name is always available (staying anonymous is allowed).
    The first-run onboarding calls this to warn BEFORE a collision -- the server
    half (ownership = earliest install) lives in :func:`db.name_owner`. Strictly
    defensive: any error -> treated as available (never blocks a user).
    """
    name = (username or '').strip()
    if not name:
        return {'name': '', 'available': True, 'owner_is_self': False}
    try:
        owner = db.name_owner(name)
    except Exception:
        owner = None
    me = (hwid or '').strip()
    owner_is_self = bool(owner and me and owner == me)
    available = (owner is None) or owner_is_self
    return {'name': name, 'available': available,
            'owner_is_self': owner_is_self}
