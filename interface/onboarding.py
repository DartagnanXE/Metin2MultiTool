# -*- coding: utf-8 -*-
"""First-run onboarding: choose a display name (the ONLY consent) + a notice.

Shown ONCE, on the first EXE start where the config has no username yet AND the
onboarding was never decided. A themed ``CTkToplevel`` (matching the existing
``_confirm_dialog`` dark/teal style) asks for an OPTIONAL self-chosen name
(length-capped, stripped, with a "no personal data" hint) and shows a short
TRANSPARENCY notice. There is NO opt-in checkbox any more: usage stats are an
always-on ANONYMOUS counter keyed by a random install id; entering a name only
REVEALS that name on the leaderboard. Leaving it empty (Save or Skip) is a valid
choice -- you simply appear under a generated anonymous name.

On Save/Skip the dialog writes ``username`` (via ``app._set_username``) and marks
``telemetry.consented = True`` (consent = "decided", so the dialog shows once).
Strictly defensive -- if the dialog fails to build, it still marks consent so it
does not loop, and the app continues.

All strings via ``i18n.t`` (EN/DE parity). Reuses interface.widgets colors.
"""

import threading

import customtkinter as ctk

from i18n import t
from interface import config as cfgmod
from interface.widgets import (AMBER, BG, INK, PANEL_HOVER, PANEL_LIGHT, TEAL,
                               TEAL_HOVER, TEXT, TEXT_FAINT, TEXT_MUTED)


def needs_onboarding(cfg):
    """True iff the first-run dialog should be shown.

    Condition: no username chosen yet AND the onboarding was never decided
    (``telemetry.consented`` is False). Never raises -> on a malformed cfg
    returns False (skip the dialog rather than risk a crash on startup).
    """
    try:
        username = str(cfg.get('username', '') or '').strip()
        consented = bool(cfg.get('telemetry', {}).get('consented', False))
        return (username == '') and (not consented)
    except Exception:
        return False


def open_onboarding(app, on_done=None):
    """Open the themed first-run dialog. Never raises.

    Writes the chosen ``username`` + ``telemetry.consented`` to the config via
    ``app.controller`` and then calls ``on_done({'username': ..})`` if given. An
    empty name is valid (stay anonymous). If anything fails to build, consent is
    still marked (so it does not loop) and the app continues.
    """
    try:
        dlg = ctk.CTkToplevel(app)
        dlg.title(t('ui.onboarding_title'))
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.geometry('494x494')  # mitgewachsen mit widget_scaling 0.85->1.0
        try:
            dlg.transient(app)
        except Exception:
            pass
        dlg.grid_columnconfigure(0, weight=1)

        # -- Title + intro ------------------------------------------------
        ctk.CTkLabel(dlg, text=t('ui.onboarding_title'), text_color=TEXT,
                     font=ctk.CTkFont(size=15, weight='bold')).grid(
            row=0, column=0, sticky='w', padx=18, pady=(16, 2))
        ctk.CTkLabel(dlg, text=t('ui.onboarding_intro'), text_color=TEXT_MUTED,
                     justify='left', wraplength=380,
                     font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky='w', padx=18, pady=(0, 8))

        # -- Name entry + hint -------------------------------------------
        ctk.CTkLabel(dlg, text=t('ui.onboarding_username_label'),
                     text_color=TEXT, anchor='w',
                     font=ctk.CTkFont(size=12, weight='bold')).grid(
            row=2, column=0, sticky='w', padx=18, pady=(0, 2))
        entry = ctk.CTkEntry(dlg, width=384,
                             placeholder_text=t('ui.onboarding_username_label'))
        entry.grid(row=3, column=0, sticky='ew', padx=18)
        ctk.CTkLabel(dlg, text=t('ui.onboarding_username_hint'),
                     text_color=TEXT_FAINT, justify='left', wraplength=380,
                     font=ctk.CTkFont(size=10)).grid(
            row=4, column=0, sticky='w', padx=18, pady=(2, 8))

        # -- Transparency notice (anonymous-by-default; name only reveals) -
        ctk.CTkLabel(dlg, text=t('ui.onboarding_transparency'),
                     text_color=TEXT_MUTED, justify='left', wraplength=380,
                     font=ctk.CTkFont(size=10)).grid(
            row=5, column=0, sticky='w', padx=18, pady=(0, 4))
        ctk.CTkLabel(dlg, text=t('ui.onboarding_whatissent'),
                     text_color=TEXT_FAINT, justify='left', wraplength=380,
                     font=ctk.CTkFont(size=10)).grid(
            row=6, column=0, sticky='w', padx=18, pady=(0, 8))

        # -- inline status/warning line (e.g. "name already taken") -------
        warn = ctk.CTkLabel(dlg, text='', text_color=AMBER, justify='left',
                            wraplength=380, font=ctk.CTkFont(size=10))
        warn.grid(row=7, column=0, sticky='w', padx=18, pady=(0, 2))

        btns = ctk.CTkFrame(dlg, fg_color='transparent')
        btns.grid(row=8, column=0, sticky='e', padx=18, pady=(0, 14))

        def _close():
            try:
                dlg.grab_release()
            except Exception:
                pass
            try:
                dlg.destroy()
            except Exception:
                pass

        def _commit(username):
            """Write the (possibly empty) name + consent IMMEDIATELY, then close.

            Empty name = stay anonymous (valid). persist_now -> the dialog never
            reappears, even on a hard close right after."""
            try:
                app.controller.update_config('telemetry', 'consented', True)
                app._set_username(username)
                app.controller.persist_now()
            except Exception:
                pass
            _close()
            if callable(on_done):
                try:
                    on_done({'username': username})
                except Exception:
                    pass

        def _set_busy(on):
            """Disable the buttons while the (async) name check runs."""
            try:
                state = 'disabled' if on else 'normal'
                save_btn.configure(state=state)
                skip_btn.configure(state=state)
                if on:
                    warn.configure(text=t('ui.onboarding_checking'),
                                   text_color=TEXT_FAINT)
            except Exception:
                pass

        def _on_check(username, result):
            """Back on the GUI thread with the availability verdict."""
            _set_busy(False)
            if result.get('available', True) or result.get('owner_is_self'):
                _commit(username)
            else:
                # Taken by someone else -> warn + keep the dialog open so the
                # user can choose another (or Skip to stay anonymous).
                try:
                    warn.configure(text=t('ui.onboarding_name_taken'),
                                   text_color=AMBER)
                    entry.focus_set()
                except Exception:
                    _commit(username)        # never trap the user on a UI error

        def _attempt_save():
            """Save: check name availability (async, never blocks), then commit."""
            try:
                username = entry.get().strip()[:cfgmod.USERNAME_MAXLEN]
            except Exception:
                username = ''
            if not username:
                _commit('')                  # anonymous -> no check needed
                return
            _set_busy(True)

            def _worker():
                result = {'available': True, 'owner_is_self': False}
                try:
                    from telemetry import client
                    cfg = app.controller.current_config()
                    lb_url = cfg.get('telemetry', {}).get('leaderboard_url', '')
                    hwid = getattr(app, '_install_id', '') or ''
                    result = client.check_name(lb_url, username, hwid)
                except Exception:
                    result = {'available': True, 'owner_is_self': False}
                try:
                    app.after(0, lambda: _on_check(username, result))
                except Exception:
                    pass

            threading.Thread(target=_worker, name='onboarding-checkname',
                             daemon=True).start()

        def _skip():
            try:
                entry.delete(0, 'end')
            except Exception:
                pass
            _commit('')

        def _commit_typed():
            """Window-close (X): commit whatever is typed WITHOUT a check (closing
            must ALWAYS work); the server enforces uniqueness regardless."""
            try:
                username = entry.get().strip()[:cfgmod.USERNAME_MAXLEN]
            except Exception:
                username = ''
            _commit(username)

        # Skip leaves the name empty; Save checks availability then takes the
        # typed name. Both record consent (decided) so the dialog shows only once.
        skip_btn = ctk.CTkButton(
            btns, text=t('ui.onboarding_skip'), width=100, height=32,
            corner_radius=8, fg_color='transparent', hover_color=PANEL_HOVER,
            text_color=TEXT_MUTED, border_width=1, border_color=PANEL_LIGHT,
            command=_skip)
        skip_btn.grid(row=0, column=0, padx=(0, 8))
        save_btn = ctk.CTkButton(
            btns, text=t('ui.onboarding_save'), width=120, height=32,
            corner_radius=8, fg_color=TEAL, hover_color=TEAL_HOVER,
            text_color=INK, command=_attempt_save)
        save_btn.grid(row=0, column=1)

        dlg.protocol('WM_DELETE_WINDOW', _commit_typed)
        try:
            dlg.after(60, dlg.grab_set)
            dlg.lift()
            entry.focus_set()
        except Exception:
            pass
        return dlg
    except Exception:
        # Build failed -> app continues. Best-effort: still mark consent decided
        # (and persist it immediately) so we do not loop on every start.
        try:
            app.controller.update_config('telemetry', 'consented', True)
            app.controller.persist_now()
        except Exception:
            pass
        return None
