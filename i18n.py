"""Laufzeit-Sprachumschaltung (English / Deutsch) fuer UI UND Logs.

Bewusst NUR Python-Standardbibliothek -> ueberall importierbar (auch in den
Bot-Modulen und in der headless-getesteten Logik), kein GUI-Toolkit noetig.

Benutzung ueberall::

    from i18n import t
    log.event(0, t('fishing.started'))
    label = t('ui.start_button')
    msg = t('ui.setting_changed', section='fishing', key='bait_time', value=7.5)

Die Uebersetzungstabelle liegt in :mod:`i18n_data` (key -> {'en': .., 'de': ..}).
Default-Sprache ist Englisch; ``set_lang('de')`` schaltet zur Laufzeit um und
benachrichtigt registrierte Beobachter (das UI rendert sich dann neu). Logs
werden zum Emit-Zeitpunkt uebersetzt -> neue Zeilen erscheinen in der aktuellen
Sprache, bereits geschriebene bleiben unveraendert (normales i18n-Verhalten).
"""

from i18n_data import TRANSLATIONS

LANGS = ('en', 'de')
_DEFAULT = 'en'
_lang = _DEFAULT
_observers = []


def get_lang():
    """Aktuelle Sprache ('en' oder 'de')."""
    return _lang


def set_lang(lang):
    """Setzt die Sprache und benachrichtigt die Beobachter. Wirft nie."""
    global _lang
    if lang in LANGS and lang != _lang:
        _lang = lang
        for callback in list(_observers):
            try:
                callback(lang)
            except Exception:
                pass


def on_change(callback):
    """Registriert ``callback(lang)`` fuer Sprachwechsel (z.B. UI-Neu-Render)."""
    if callable(callback) and callback not in _observers:
        _observers.append(callback)


def t(key, **fmt):
    """Uebersetzt ``key`` in die aktuelle Sprache.

    Fallback-Kette: aktuelle Sprache -> Englisch -> der Schluessel selbst (so
    bleibt nie etwas leer, auch wenn ein Schluessel fehlt). ``**fmt`` werden via
    ``str.format`` eingesetzt; ein Format-Fehler liefert defensiv den Rohtext.
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(_lang) or entry.get('en') or key
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text
