# -*- coding: utf-8 -*-
"""DB layer over a DEDICATED sqlite file (its own volume; NOT shared with kilab).

sqlite (WAL mode) is plenty for a tiny honor-system leaderboard in a single
small container. The postgres swap path is documented inline. ALL queries are
parameterised (no string concatenation) -> no SQL injection.

Tables:
  submissions(id, username, hwid, fishing_catches, puzzles_solved,
              fishing_runtime_s, puzzler_runtime_s, app_version, ts, ip_hash)
  bans(id, kind 'install'|'name', value, reason, ts)

NOTE on the field name: ``hwid`` is the wire/DB/column name kept verbatim from
the old model; it now CARRIES the random per-install id (NOT a device hash). The
anti-cheat axes are ``install`` (block one installation -- matched on the ``hwid``
column) and ``name`` (hide a chosen name -- matched on the ``username`` column).
See migrations/0002_anti_cheat_axes.sql + THREAT_MODEL.md.

The leaderboard aggregates MAX(counter) per INSTALL id (a client only ever grows
its cumulative counters, so MAX is the latest truth and resists a single bad
submission lowering a score). Blocked installs are excluded; a hidden name is
blanked (so the row stays on the board under the anonymous name).
"""

import os
import sqlite3
import time
import threading

from .anon_name import anon_name, disambiguate

DEFAULT_DB_PATH = os.environ.get('DB_PATH', '/data/telemetry.db')

# One connection guarded by a lock (uvicorn workers in one process; for multiple
# workers switch to a connection-per-request or postgres -- see DEPLOY.md).
_LOCK = threading.Lock()
_CONN = None


def _connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA busy_timeout=5000')  # wait on a lock instead of erroring
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db(path=DEFAULT_DB_PATH):
    """Create tables/indexes if missing and cache the connection. Idempotent."""
    global _CONN
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    _CONN = _connect(path)
    _CONN.executescript(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            hwid TEXT NOT NULL,
            fishing_catches INTEGER NOT NULL,
            puzzles_solved INTEGER NOT NULL,
            fishing_runtime_s REAL NOT NULL,
            puzzler_runtime_s REAL NOT NULL,
            app_version TEXT NOT NULL,
            ts INTEGER NOT NULL,
            ip_hash TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_sub_hwid ON submissions(hwid);
        CREATE INDEX IF NOT EXISTS ix_sub_username ON submissions(username);
        CREATE INDEX IF NOT EXISTS ix_sub_ts ON submissions(ts);

        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('install','name')),
            value TEXT NOT NULL,
            reason TEXT,
            ts INTEGER NOT NULL,
            UNIQUE(kind, value)
        );
        """
    )
    _CONN.commit()
    return _CONN


def _conn():
    if _CONN is None:
        init_db()
    return _CONN


def last_for_identity(hwid):
    """Return the most recent submission row for an HWID (or None).

    Used by the anti-abuse check to reject implausible downward/huge jumps.
    """
    with _LOCK:
        cur = _conn().execute(
            'SELECT * FROM submissions WHERE hwid = ? '
            'ORDER BY ts DESC, id DESC LIMIT 1',
            (hwid,))
        return cur.fetchone()


def insert_submission(row):
    """Insert one submission (dict). Parameterised. Returns the new row id."""
    with _LOCK:
        cur = _conn().execute(
            """INSERT INTO submissions
               (username, hwid, fishing_catches, puzzles_solved,
                fishing_runtime_s, puzzler_runtime_s, app_version, ts, ip_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row['username'], row['hwid'], row['fishing_catches'],
             row['puzzles_solved'], row['fishing_runtime_s'],
             row['puzzler_runtime_s'], row['app_version'], row['ts'],
             row.get('ip_hash')))
        _conn().commit()
        return cur.lastrowid


def hidden_names():
    """Set of chosen names hidden by moderation (bans kind='name'). Never raises."""
    with _LOCK:
        cur = _conn().execute(
            "SELECT value FROM bans WHERE kind='name'")
        return {r['value'] for r in cur.fetchall()}


def _aggregate(period='all'):
    """Full aggregated+ranked board (MAX counters per INSTALL id), NO limit.

    Shared by :func:`leaderboard` (which slices the top-N) and :func:`self_rank`
    (which scans the whole board for one identity's rank). Keyed by the stable
    ``hwid`` (= random install id): one row per install, carrying the LATEST
    submitted ``username`` for that id (empty included -- so CLEARING a chosen
    name reverts the row to the anonymous funny name; opting out un-reveals).
    Rank is 1-based over the FULL board.

    Anti-cheat axes:
      * BLOCKED installs (bans kind='install') are excluded entirely.
      * HIDDEN names (bans kind='name') are NOT excluded -- the chosen name is
        blanked so the display name falls back to the anonymous funny name (the
        row stays on the board; only the label is moderated).

    Each row carries:
      * ``hwid``        -- the install id (for self-lookup + anon fallback);
      * ``username``    -- the chosen-or-blank name (blank if absent/hidden);
      * ``display_name``-- chosen name if set+not-hidden, else anon_name(hwid).

    Sort/tie-break: ``fishing_catches`` desc, then ``puzzles_solved`` desc, then
    the DISPLAY name asc -- a STABLE, deterministic order so a given install
    always lands on the same rank (the client relies on this for self-rank).
    """
    since = 0
    if period == 'daily':
        since = int(time.time()) - 86_400
    hidden = hidden_names()
    with _LOCK:
        cur = _conn().execute(
            """
            SELECT hwid,
                   MAX(fishing_catches)  AS fishing_catches,
                   MAX(puzzles_solved)   AS puzzles_solved,
                   MAX(fishing_runtime_s) AS fishing_runtime_s,
                   MAX(puzzler_runtime_s) AS puzzler_runtime_s,
                   MIN(ts)                AS first_ts,
                   (SELECT s2.username FROM submissions s2
                     WHERE s2.hwid = submissions.hwid AND s2.ts >= ?
                     ORDER BY s2.ts DESC, s2.id DESC LIMIT 1) AS username
            FROM submissions
            WHERE ts >= ?
              AND hwid NOT IN (SELECT value FROM bans WHERE kind='install')
            GROUP BY hwid
            """,
            (since, since))
        rows = [dict(r) for r in cur.fetchall()]
    # 1) Hidden-name moderation: a hidden chosen name is blanked (row stays on
    #    the board under the anonymous funny name).
    for r in rows:
        name = (r.get('username') or '').strip()
        if name and name in hidden:
            name = ''
        r['username'] = name
    # 2) Chosen-name OWNERSHIP (real uniqueness): a self-chosen name belongs to
    #    the EARLIEST install using it (by first_ts, then hwid). A LATER install
    #    carrying the SAME name (case-insensitive) does NOT get it -- its name is
    #    blanked so it falls back to its anonymous funny name. A chosen name thus
    #    appears at most ONCE on the board -- no "FishLover2" that wrongly implies
    #    a second owner. This is the server half of name uniqueness; the client
    #    warns up front via /check_name (-> :func:`name_owner`). `username` on the
    #    OWNER row stays intact so self-lookup by name still matches the owner.
    _owners = {}
    for r in sorted(rows, key=lambda r: (int(r.get('first_ts') or 0),
                                         str(r['hwid']))):
        nm = r['username']
        if not nm:
            continue
        key = nm.casefold()
        if key in _owners:
            r['username'] = ''              # not the owner -> revert to anon
        else:
            _owners[key] = r['hwid']
    # 3) Display name: the (owned) chosen name, else the anonymous funny name.
    for r in rows:
        r['display_name'] = r['username'] if r['username'] \
            else anon_name(r['hwid'], 'en')
    # 4) Anonymous-pool disambiguation: chosen names are unique now, but the
    #    100-name ANON pool can still collide. The EARLIEST install keeps the bare
    #    anon name; later ones get '2', '3', ... so the public board never shows
    #    two identical labels. Ordered by (first_ts, hwid) for a stable result.
    _by_name = {}
    for r in rows:
        _by_name.setdefault(r['display_name'], []).append(r)
    for _base, _group in _by_name.items():
        if len(_group) < 2:
            continue
        _group.sort(key=lambda r: (int(r.get('first_ts') or 0), str(r['hwid'])))
        for _pos, r in enumerate(_group):
            if _pos:
                r['display_name'] = disambiguate(_base, _pos)
    # Deterministic order by catches desc, puzzles desc, then DISPLAY name asc.
    rows.sort(key=lambda r: (-int(r['fishing_catches']),
                             -int(r['puzzles_solved']), r['display_name']))
    for i, r in enumerate(rows, start=1):
        r['rank'] = i
    return rows


def leaderboard(period='all', limit=100):
    """Aggregated board (MAX counters per install), excluding blocked installs.

    ``period`` 'daily' restricts to submissions from the last 24h; 'all' uses
    everything. Returns up to ``limit`` dicts ordered by fishing_catches desc
    (tie-break puzzles desc, then DISPLAY name asc), each carrying its 1-based
    rank, ``hwid`` (install id) + ``display_name`` (chosen-or-anon).
    """
    rows = _aggregate(period)
    return rows[:limit]


def self_rank(hwid=None, username=None, period='all'):
    """Return the requesting identity's ranked row over the FULL board, or None.

    Resolves the identity by ``hwid`` (install id) FIRST -- matching the row
    directly on the install id -- and falls back to the passed ``username`` when
    no hwid was supplied. The returned dict has the same shape as a
    :func:`leaderboard` row including the TRUE 1-based ``rank`` across the entire
    aggregated board (not just the top-N) + ``display_name``. Blocked installs
    are excluded, so a blocked install yields None. Never raises on a missing
    identity -- returns None.
    """
    rows = _aggregate(period)
    hwid = (hwid or '').strip()
    if hwid:
        for row in rows:
            if row['hwid'] == hwid:
                return row
        return None
    username = (username or '').strip()
    if not username:
        return None
    # Fallback by chosen name (only when no hwid was given): match on the
    # chosen (non-blank) username carried on the row.
    for row in rows:
        if row['username'] == username:
            return row
    return None


def name_owner(username, period='all'):
    """Install id that OWNS a chosen name (case-insensitive), or ``None``.

    Ownership mirrors the leaderboard exactly: :func:`_aggregate` resolves chosen
    names to the EARLIEST install (first_ts, then hwid) and blanks the name on
    every later install, so the OWNER is the single row whose ``username`` still
    equals the requested name. Used by ``/check_name`` so the client can warn a
    user that a name is already taken BEFORE they pick it. Never raises -> None on
    any error (the caller treats unknown as 'available').
    """
    target = (username or '').strip()
    if not target:
        return None
    try:
        for row in _aggregate(period):
            if (row.get('username') or '').casefold() == target.casefold():
                return row['hwid']
    except Exception:
        return None
    return None


def is_banned(kind, value):
    """True iff (kind, value) is banned. Parameterised."""
    with _LOCK:
        cur = _conn().execute(
            'SELECT 1 FROM bans WHERE kind = ? AND value = ? LIMIT 1',
            (kind, value))
        return cur.fetchone() is not None


def add_ban(kind, value, reason=None):
    """Insert/replace a ban. Returns True. Parameterised."""
    with _LOCK:
        _conn().execute(
            """INSERT INTO bans (kind, value, reason, ts) VALUES (?, ?, ?, ?)
               ON CONFLICT(kind, value) DO UPDATE SET reason=excluded.reason,
                                                      ts=excluded.ts""",
            (kind, value, reason, int(time.time())))
        _conn().commit()
    return True


def remove_ban(kind, value):
    """Delete a ban. Returns the number of rows removed."""
    with _LOCK:
        cur = _conn().execute(
            'DELETE FROM bans WHERE kind = ? AND value = ?', (kind, value))
        _conn().commit()
        return cur.rowcount


#: Whitelist of allowed erasure columns, keyed by ``kind``. Defence-in-depth:
#: the column name is interpolated into the SQL string (it cannot be a bound
#: parameter), so it MUST come from this fixed map and never from the caller --
#: even though admin._check_kind already validates upstream, this function is a
#: public DB API and must not rely on the caller for SQL safety.
_ERASE_COLUMNS = {'install': 'hwid', 'name': 'username'}


def delete_entries(kind, value):
    """GDPR erasure: delete all submissions for an install id or a chosen name.

    ``kind='install'`` matches the ``hwid`` column (the install id);
    ``kind='name'`` matches the ``username`` column. Returns the number of rows
    removed. The ``value`` is always bound; the column name is resolved through
    the fixed :data:`_ERASE_COLUMNS` whitelist (raises ``ValueError`` on an
    unknown kind) so no caller can inject an arbitrary column name.
    """
    column = _ERASE_COLUMNS.get(kind)
    if column is None:
        raise ValueError('invalid kind: {!r}'.format(kind))
    with _LOCK:
        cur = _conn().execute(
            'DELETE FROM submissions WHERE {} = ?'.format(column), (value,))
        _conn().commit()
        return cur.rowcount


def list_bans():
    """Return all bans as a list of dicts."""
    with _LOCK:
        cur = _conn().execute(
            'SELECT kind, value, reason, ts FROM bans ORDER BY ts DESC')
        return [dict(r) for r in cur.fetchall()]
