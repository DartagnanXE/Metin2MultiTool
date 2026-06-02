# -*- coding: utf-8 -*-
"""Pure row-shaping helpers for the ranking leaderboard view.

Extracted from ``interface/ranking_view.py`` to keep that module focused (it
otherwise crept over the ~400-line soft cap). These are PURE: no Tk, no I/O,
never raise. ``ranking_view`` re-imports them so existing call sites + tests that
reference ``ranking_view._hms`` / ``._entry_fields`` keep working unchanged.
"""


def hms(total_seconds):
    """Seconds -> 'HH:MM:SS' (clamped >= 0). Never raises."""
    try:
        total = max(0, int(total_seconds))
    except Exception:
        return '00:00:00'
    return '{:02d}:{:02d}:{:02d}'.format(
        total // 3600, (total % 3600) // 60, total % 60)


def entry_fields(entry):
    """Extract ``(name, catches, puzzles, rank_or_None)`` from a board row dict.

    Catches read from 'fishing_catches' (legacy 'catches' fallback); puzzles
    from 'puzzles_solved'; rank from 'rank' when present. Never raises -- on a
    bad row returns a benign placeholder."""
    try:
        name = str(entry.get('username', '?'))
        catches = entry.get('fishing_catches', entry.get('catches', 0))
        puzzles = entry.get('puzzles_solved', 0)
        rank = entry.get('rank', None)
        return name, catches, puzzles, rank
    except Exception:
        return '?', 0, 0, None


def row_rank(entry, fallback):
    """Best-effort 1-based rank of a board row dict, else ``fallback`` (its
    position). Used to match the caller's authoritative self_rank against the
    visible slice. Never raises."""
    try:
        raw = entry.get('rank', None)
        return int(raw) if raw is not None else fallback
    except Exception:
        return fallback
