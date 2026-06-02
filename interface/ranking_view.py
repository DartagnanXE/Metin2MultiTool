# -*- coding: utf-8 -*-
"""Ranking tab body -- a LEADERBOARD-ONLY view (its OWN module so app.py does
not grow further).

Renders ONE block: the leaderboard table at the top of the view --

  * columns ``Rank | Name | Catches | Puzzles solved`` (a Refresh button + a
    notice line above it). Ranking criterion is CATCHES (descending); "Puzzles
    solved" is a DISPLAY column only and never affects the rank.
  * the TOP 20 are shown. When the local user's rank is > 20, the 20th displayed
    row is REPLACED by the user's OWN row showing their REAL rank (e.g. "#147").
    The user's row is HIGHLIGHTED wherever it lands.
  * fetched on a WORKER thread via ``telemetry.client.fetch_leaderboard`` and
    marshalled back with ``app.after(0, ...)`` (the worker NEVER touches Tk).
    Auto-loads when the Ranking tab opens. Refresh FIRST submits the user's
    current stats out-of-band (an immediate extra POST on the same worker) and
    THEN fetches, so the user's own row already reflects current data.
  * the board is always shown (anonymous always-on model); only a BLOCKED
    installation shows a notice instead of the board.

NO local-stats block, NO fishing/puzzle runtimes, NO fish-event info live here.

Defensive throughout: every render path is wrapped; a missing widget or a bad
snapshot can never crash the UI. All strings via ``i18n.t`` (EN/DE parity).
"""

import threading
from urllib.parse import urlencode

import customtkinter as ctk

from i18n import t
from interface import config as cfgmod
from interface.ranking_rows import (entry_fields as _entry_fields,
                                     hms as _hms, row_rank as _row_rank)
from interface.widgets import (PANEL, PANEL_LIGHT, TEAL, TEAL_BRIGHT, TEAL_SOFT,
                               TEXT, TEXT_FAINT, TEXT_MUTED)

# Top-N shown on the board. When the user's true rank is > TOP_N, the TOP_N-th
# displayed row is replaced with the user's own row (real rank). Mirrors the
# server's TOP_N so client + server agree on the cut.
TOP_N = 20

# Compact rows so 1 header + TOP_N(=20) data rows (one of which may be the
# replace-20-by-self row) all fit the fixed 470x608 window WITHOUT a scrollbar
# (the old size=11 rows fit only ~13 of 20). Kept >= 9 so it stays readable;
# the row-count/compact-intent test pins these constants without building Tk.
ROW_FONT_SIZE = 9
ROW_HEIGHT = 14         # fixed per-label height (px) -> tight, uniform rows


def build_ranking_view(app, parent):
    """Build the leaderboard-only ranking view into ``parent`` and return it.

    Stores live-update handles on ``app`` (``_rank_board_body``,
    ``_rank_notice``, ``_rank_refresh_btn``). Never raises.
    """
    view = parent
    try:
        view.grid_columnconfigure(0, weight=1)

        # One-line TRANSPARENCY notice (anonymous always-on model): sits above
        # the board so it is always visible. Honest basis for the always-on
        # counter -- mirrors the README + the Settings notice.
        transparency = ctk.CTkLabel(
            view, text=t('ui.ranking_transparency'), anchor='w', justify='left',
            text_color=TEXT_MUTED, wraplength=430,
            font=ctk.CTkFont(size=ROW_FONT_SIZE))
        transparency.grid(row=0, column=0, sticky='ew', pady=(0, 2))

        # -- Leaderboard card (the only block) ----------------------------
        board_card = _card(view, t('ui.leaderboard_title'))
        board_card.grid(row=1, column=0, sticky='ew', pady=(0, 2))
        head = ctk.CTkFrame(board_card.body, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew')
        head.grid_columnconfigure(0, weight=1)
        app._rank_refresh_btn = ctk.CTkButton(
            head, text=t('ui.leaderboard_refresh'), width=110, height=26,
            corner_radius=8, fg_color=PANEL_LIGHT, hover_color=TEAL_SOFT,
            text_color=TEXT, font=ctk.CTkFont(size=11),
            command=lambda: refresh_leaderboard(app, force=True))
        app._rank_refresh_btn.grid(row=0, column=1, sticky='e')

        # Notice line (banned / fetch-failed / loading / your-rank).
        app._rank_notice = ctk.CTkLabel(
            board_card.body, text='', anchor='w', justify='left',
            text_color=TEXT_FAINT, wraplength=430,
            font=ctk.CTkFont(size=ROW_FONT_SIZE))
        app._rank_notice.grid(row=1, column=0, sticky='w', pady=(2, 1))

        # Board body (compact rows of rank/name/catches/puzzles).
        app._rank_board_body = ctk.CTkFrame(board_card.body,
                                            fg_color='transparent')
        app._rank_board_body.grid(row=2, column=0, sticky='ew', pady=(1, 0))
        app._rank_board_body.grid_columnconfigure(1, weight=1)

        # Auto-fetch the leaderboard once on build.
        refresh_leaderboard(app)
    except Exception:
        pass
    return view


def _card(parent, title):
    """A titled panel card (mirrors interface.widgets.Section shape minimally).

    Paddings trimmed (vs the original 8/10) so the compact rows + header fit the
    fixed 608px window without scroll."""
    card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10)
    card.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(card, text=title, anchor='w', text_color=TEXT_FAINT,
                 font=ctk.CTkFont(size=11, weight='bold')).grid(
        row=0, column=0, sticky='w', padx=12, pady=(6, 1))
    body = ctk.CTkFrame(card, fg_color='transparent')
    body.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 6))
    body.grid_columnconfigure(0, weight=1)
    card.body = body
    return card


def _submit_current_stats(app):
    """Best-effort out-of-band single-shot submit of the user's CURRENT stats.

    Runs on the WORKER thread (never touches Tk). Reads the app's telemetry
    snapshot (``_telemetry_state``); only POSTs when the snapshot is enabled
    (install_id + submit_url present, not blocked) -- a chosen name is NOT
    required (the counter is anonymous). Swallows every error -- the subsequent
    fetch must proceed regardless. Returns nothing.

    Tests / dev tooling must NEVER submit to the live server: the
    ``M2FB_NO_TELEMETRY`` env var (set by tests/conftest.py + the GUI-smoke
    harness) short-circuits this. Production never sets it.
    """
    import os
    if os.environ.get('M2FB_NO_TELEMETRY'):
        return
    try:
        state_fn = getattr(app, '_telemetry_state', None)
        if not callable(state_fn):
            return
        state = state_fn() or {}
        if not state.get('enabled'):
            return
        url = str(state.get('submit_url') or '').strip()
        install_id = str(state.get('hwid') or '').strip()
        payload = state.get('payload') or {}
        if not url or not install_id or not payload:
            return
        from telemetry import client
        client.post_submit(url, payload)
    except Exception:
        pass


def _identity(app, cfg):
    """Return ``(install_id, username)`` for the leaderboard self-lookup.

    Username (chosen-or-empty) from config; the install id from the app's cache,
    else the stored config id, else a freshly resolved one (the same source the
    telemetry sender uses). The id is still sent to the server as ``?hwid=`` (the
    wire field name is unchanged; it now carries the random install id). Either
    value may be ''. Never raises."""
    username = ''
    install_id = ''
    try:
        username = str(cfg.get('username', '') or '')
    except Exception:
        username = ''
    try:
        install_id = getattr(app, '_install_id', None) or ''
        if not install_id:
            install_id = str(cfg.get('telemetry', {}).get(
                'install_id', '') or '')
        if not install_id:
            from telemetry import hwid as hwidmod
            install_id = hwidmod.get_hwid() or ''
    except Exception:
        install_id = ''
    return str(install_id), username


def _board_url(base_url, hwid_value, username):
    """Append ``?hwid=&username=`` (urlencoded, omitting empties) to ``base_url``.

    Lets the server return the caller's own ranked row. Old servers ignore the
    extra params, so this stays backward compatible. Never raises."""
    try:
        params = {}
        if hwid_value:
            params['hwid'] = hwid_value
        if username:
            params['username'] = username
        if not params:
            return base_url
        sep = '&' if '?' in base_url else '?'
        return base_url + sep + urlencode(params)
    except Exception:
        return base_url


def refresh_leaderboard(app, force=False):
    """Send the user's stats out-of-band, THEN fetch the board (worker thread).

    Anonymous always-on model: there is NO telemetry-off state -- the board
    always loads. Only a BLOCKED installation shows a notice and skips the
    network. Otherwise spawn a daemon thread that (1) POSTs the current stats
    once (best-effort, so the user's own row is current), then (2) GETs the board
    with the identity query so the server can return the user's true rank. The
    result is marshalled back via ``app.after(0)``; the worker NEVER touches Tk.
    Never raises.

    ``force`` (set by the explicit Refresh button) bypasses the client-side
    leaderboard cache so the board fetched right AFTER the out-of-band submit
    reflects the just-sent stats -- without it the 30s TTL could return a stale
    pre-submit snapshot and the user's own row would lag (the confusion this
    submit-then-fetch flow exists to prevent). The auto-load on tab-open leaves
    ``force=False`` so rapid re-opens still hit the cache.
    """
    try:
        cfg = app.controller.current_config()
        telemetry = cfg.get('telemetry', {})
        if getattr(app, '_ranking_banned', False):
            _set_notice(app, t('ui.ranking_banned'))
            _clear_board(app)
            return

        base_url = (telemetry.get('leaderboard_url')
                    or cfgmod.DEFAULT_LEADERBOARD_URL)
        hwid_value, username = _identity(app, cfg)
        url = _board_url(base_url, hwid_value, username)
        _set_notice(app, t('ui.leaderboard_loading'))

        def _worker():
            # 1) push current stats so the user's own row reflects NOW; 2) fetch
            #    the board. On an explicit Refresh (force=True) the fetch bypasses
            #    the client cache so the board reflects the submit we just sent
            #    (otherwise the 30s TTL could hand back a stale pre-submit board
            #    and the user's own row would lag -- exactly the confusion this
            #    submit-then-fetch flow is meant to avoid).
            _submit_current_stats(app)
            from telemetry import client
            data = client.fetch_leaderboard(url, force=force)
            try:
                app.after(0, lambda: _on_board(app, data, username))
            except Exception:
                pass

        threading.Thread(target=_worker, name='leaderboard-fetch',
                         daemon=True).start()
    except Exception:
        pass


def _on_board(app, data, username):
    """GUI-thread: render fetched leaderboard data (or a failure notice).

    Parses the extended envelope: ``entries`` is the top-20 (legacy ``all`` /
    ``daily`` fallbacks kept for older servers + existing tests); ``self`` (when
    present) is the caller's own ranked row used to replace the 20th displayed
    row when their rank is outside the top-20."""
    try:
        if not isinstance(data, dict):
            _set_notice(app, t('ui.leaderboard_fetch_failed'))
            _clear_board(app)
            return
        entries = (data.get('entries') or data.get('all')
                   or data.get('daily') or [])
        self_row = data.get('self') if isinstance(data.get('self'), dict) \
            else None
        if not entries:
            _set_notice(app, t('ui.leaderboard_empty'))
            _clear_board(app)
            return
        _set_notice(app, '')
        _render_board(app, entries, username, self_row=self_row)
    except Exception:
        _set_notice(app, t('ui.leaderboard_fetch_failed'))


def _render_board(app, entries, username, self_row=None):
    """Render up to TOP_N leaderboard rows with the 4th 'Puzzles solved' column.

    Replace-with-self: when ``self_row`` has a rank > TOP_N, the TOP_N-th
    displayed row is REPLACED by the user's own row (showing the real rank). The
    user's row is highlighted wherever it lands.

    Self-identification is RANK-AUTHORITATIVE when ``self_row`` is present: the
    server resolved the caller by install id and returned their true rank, so we
    highlight the single visible row whose rank == self_rank (and fall back to
    name-matching only on the legacy old-server path where no ``self`` was
    returned). This avoids double-highlighting when two installs picked the SAME
    chosen name. A self row already inside the top-N is NOT duplicated.

    The "your rank" notice ALWAYS surfaces the caller's real rank whenever the
    server returned one -- whether they are visibly on the board, were injected,
    or (on a stale top-20 cache) are a fresh in-window rank not yet present in
    the cached slice. Never raises."""
    try:
        body = getattr(app, '_rank_board_body', None)
        if body is None:
            return
        for child in body.winfo_children():
            child.destroy()
        # Header row (4 columns).
        _board_row(body, 0, t('ui.leaderboard_rank'), t('ui.leaderboard_player'),
                   t('ui.leaderboard_catches'), t('ui.stats_puzzles'),
                   header=True)

        top = list(entries[:TOP_N])
        self_name = ''
        self_rank = None
        if isinstance(self_row, dict):
            self_name = str(self_row.get('username', '') or '')
            try:
                self_rank = int(self_row.get('rank'))
            except Exception:
                self_rank = None

        # Is the caller already visible in the cached top-N slice? When we have
        # an authoritative self_row, a visible row is the caller only when it
        # matches BOTH the server-resolved rank AND the self display name -- rank
        # alone is ambiguous against a STALE cache (a DIFFERENT user may sit at
        # the same rank number in the lagging slice), and name alone is ambiguous
        # when two installs share a chosen name. Requiring both disambiguates
        # each case. Legacy/no-self path falls back to the display name only.
        if self_rank is not None:
            in_top = any(_row_rank(e, i) == self_rank
                         and str(e.get('username', '')) == self_name
                         for i, e in enumerate(top, start=1))
        else:
            in_top = bool(self_name) and any(
                str(e.get('username', '')) == self_name for e in top)

        # Inject the self row in place of the TOP_N-th row only when we KNOW the
        # user's rank is beyond the visible window and they are not already in it.
        inject_self = (self_rank is not None and self_rank > TOP_N
                       and not in_top and len(top) >= TOP_N)

        own_rank = None
        for i, entry in enumerate(top, start=1):
            try:
                if inject_self and i == TOP_N:
                    # Replace the last visible row with the user's own row.
                    name, catches, puzzles, rank = _entry_fields(self_row)
                    rank = self_rank
                    mine = True
                else:
                    name, catches, puzzles, rank = _entry_fields(entry)
                    if rank is None:
                        rank = i
                    # With an authoritative self_row, a visible row is the caller
                    # only on a rank AND name match (rank alone double-counts a
                    # stale-cache row at the same number; name alone double-counts
                    # duplicate chosen names). Legacy path: match the typed name.
                    if self_rank is not None:
                        mine = (rank == self_rank and name == self_name)
                    else:
                        mine = bool(username) and name == username
            except Exception:
                continue
            if mine:
                own_rank = rank
            _board_row(body, i, str(rank), name, str(catches), str(puzzles),
                       mine=mine)

        # Surface the caller's real rank whenever the server returned one: they
        # may be visible (own_rank set), injected, or -- on a STALE top-20 cache
        # -- a fresh in-window rank not yet in the cached slice (own_rank None,
        # not injected). In every case show the authoritative self_rank so the
        # user always learns where they stand. Otherwise reflect any name match.
        if self_rank is not None:
            _set_notice(app, t('ui.leaderboard_your_rank', rank=self_rank))
        elif own_rank is not None:
            _set_notice(app, t('ui.leaderboard_your_rank', rank=own_rank))
    except Exception:
        pass


def _board_row(body, row, rank, name, catches, puzzles, header=False,
               mine=False):
    """Render ONE compact board row (4 columns) at grid ``row``.

    Compact so 1 header + TOP_N data rows fit the fixed 608px window with no
    scroll: ``ROW_FONT_SIZE`` (>= 9, readable) + a fixed ``ROW_HEIGHT`` per label
    + zero inter-row pady. Header stays bold/teal-faint; the user's own row stays
    bold/teal-bright (``mine``)."""
    color = TEAL_BRIGHT if mine else (TEXT_FAINT if header else TEXT)
    weight = 'bold' if (header or mine) else 'normal'
    font = ctk.CTkFont(size=ROW_FONT_SIZE, weight=weight)
    ctk.CTkLabel(body, text=rank, width=30, height=ROW_HEIGHT, anchor='w',
                 text_color=color, font=font).grid(
        row=row, column=0, sticky='w', pady=0)
    ctk.CTkLabel(body, text=name, height=ROW_HEIGHT, anchor='w',
                 text_color=color, font=font).grid(
        row=row, column=1, sticky='w', padx=(4, 4), pady=0)
    ctk.CTkLabel(body, text=catches, width=46, height=ROW_HEIGHT, anchor='e',
                 text_color=color, font=font).grid(
        row=row, column=2, sticky='e', padx=(0, 6), pady=0)
    ctk.CTkLabel(body, text=puzzles, width=46, height=ROW_HEIGHT, anchor='e',
                 text_color=color, font=font).grid(
        row=row, column=3, sticky='e', pady=0)


def _clear_board(app):
    try:
        body = getattr(app, '_rank_board_body', None)
        if body is None:
            return
        for child in body.winfo_children():
            child.destroy()
    except Exception:
        pass


def _set_notice(app, text):
    try:
        notice = getattr(app, '_rank_notice', None)
        if notice is not None:
            notice.configure(text=text)
    except Exception:
        pass
