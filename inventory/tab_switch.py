# -*- coding: utf-8 -*-
"""Reiter-Wechsel mit Beleg: klicken, im Bild nachsehen, notfalls zweimal.

WARUM (Nutzer-Meldung 2026-10-30, "Grillen: Seite I klappt fast immer, II-IV
fast nie"): Das Spiel kann Reiter-Klicks verschlucken -- belegt seit v1.1.2
("Scan blieb auf Seite I"). Der Haupt-Scan prueft deshalb jeden Wechsel nach
(``inventory.scanner._scan_one_page``). Grillen und Wegwerfen klickten blind:
Blieb der Klick aus, stand noch die alte Seite offen, und der Zug griff dort an
derselben Stelle zu. Beim Grillen landete so ein fremdes Item im Feuer, beim
Wegwerfen auf dem Boden.

Gemeinsamer Baustein fuer beide Ablaeufe (:mod:`inventory_campfire`,
:mod:`inventory_discard`). Rein: Klick, Nachsehen und Warten kommen von aussen.
Wirft nie.
"""

#: Wie oft ein Reiter angeklickt und nachgeprueft wird, bevor die Seite als
#: "laesst sich nicht aufschlagen" gilt. 2 = ein zweiter Klick, genau wie im
#: Haupt-Scan.
SWITCH_ATTEMPTS = 2

#: Pause vor dem ZWEITEN Nachsehen. Nur auf dem Fehlerpfad bezahlt; etwas
#: laenger als ``INPUT_SETTLE_S``, damit ein Spiel, das die Seite nur
#: verspaetet zeichnet, nicht faelschlich als "nicht umgeschaltet" gilt.
RETRY_SETTLE_S = 0.15


def switch_checked(page, click_fn, verify_fn=None, wait_fn=None,
                   attempts=SWITCH_ATTEMPTS, retry_settle_s=RETRY_SETTLE_S):
    """Reiter ``page`` anklicken und BELEGEN, dass die Seite offen ist.

    Ablauf: klicken, nachsehen; stimmt die Seite nicht, ein zweites Mal klicken,
    kurz warten, nachsehen. Ein Klick auf den schon offenen Reiter ist harmlos.

    :param click_fn: ``() -> None``, klickt den Reiter (samt eigener Pause).
    :param verify_fn: ``() -> Seite | None``: welche Seite ist JETZT offen?
        ``None`` = nicht pruefen -- dann bleibt es beim einen blinden Klick,
        Klick fuer Klick wie bisher.
    :param wait_fn: ``(sekunden) -> bool``, wartet vor dem zweiten Nachsehen;
        ``False`` heisst Not-Aus, dann sofort aussteigen.
    :return: ``(ok, gesehen)``. ``ok`` ist ``True``, wenn die Seite belegt offen
        ist (oder nicht geprueft wird) -- wer ``False`` bekommt, darf auf dieser
        Seite NICHTS anfassen. ``gesehen`` ist die zuletzt im Bild gelesene
        Seite (``None``: kein Bild oder nicht geprueft), damit die Console
        zeigt, WAS statt der gewuenschten Seite offen war.
    """
    _ohne_wurf(click_fn)
    if verify_fn is None:
        return True, None
    gesehen = None
    for versuch in range(max(1, int(attempts))):
        if versuch > 0:
            _ohne_wurf(click_fn)
            if wait_fn is not None and not _warten(wait_fn, retry_settle_s):
                return False, gesehen
        try:
            gesehen = verify_fn()
        except Exception:
            gesehen = None
        if gesehen == page:
            return True, gesehen
    return False, gesehen


def _ohne_wurf(fn):
    try:
        fn()
    except Exception:
        pass


def _warten(wait_fn, sekunden):
    """``wait_fn`` aufrufen; ein Fehler darin ist kein Not-Aus."""
    try:
        return bool(wait_fn(sekunden))
    except Exception:
        return True


__all__ = ['SWITCH_ATTEMPTS', 'RETRY_SETTLE_S', 'switch_checked']
