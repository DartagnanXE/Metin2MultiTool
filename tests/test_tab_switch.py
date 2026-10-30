# -*- coding: utf-8 -*-
"""Reiter-Wechsel mit Beleg (:mod:`inventory.tab_switch`).

Gemeinsamer Baustein fuer Grillen und Wegwerfen: klicken, im Bild nachsehen,
notfalls ein zweites Mal klicken. Die Ablauf-Tests liegen in
``test_campfire_seitenwechsel`` und ``test_wegwerfen_seitenwechsel``; hier
steht nur der Vertrag des Bausteins selbst.
"""

import unittest

from inventory import tab_switch


class _Folge(object):
    """Liefert die gegebenen Seiten der Reihe nach; die letzte bleibt stehen."""

    def __init__(self, *seiten):
        self.seiten = list(seiten)
        self.n = 0

    def __call__(self):
        got = self.seiten[min(self.n, len(self.seiten) - 1)]
        self.n += 1
        return got


class TestSwitchChecked(unittest.TestCase):

    def setUp(self):
        self.klicks = []
        self.wartezeiten = []

    def _klick(self):
        self.klicks.append(1)

    def _warte(self, sekunden):
        self.wartezeiten.append(sekunden)
        return True

    def test_ohne_pruefung_genau_ein_blinder_klick(self):
        ok, gesehen = tab_switch.switch_checked('II', click_fn=self._klick)
        self.assertEqual((ok, gesehen), (True, None))
        self.assertEqual(len(self.klicks), 1)

    def test_erster_blick_stimmt(self):
        ok, gesehen = tab_switch.switch_checked(
            'II', click_fn=self._klick, verify_fn=_Folge('II'),
            wait_fn=self._warte)
        self.assertEqual((ok, gesehen), (True, 'II'))
        self.assertEqual(len(self.klicks), 1)
        self.assertEqual(self.wartezeiten, [])

    def test_zweiter_klick_rettet_den_wechsel(self):
        ok, gesehen = tab_switch.switch_checked(
            'II', click_fn=self._klick, verify_fn=_Folge('I', 'II'),
            wait_fn=self._warte)
        self.assertEqual((ok, gesehen), (True, 'II'))
        self.assertEqual(len(self.klicks), 2)
        self.assertEqual(self.wartezeiten, [tab_switch.RETRY_SETTLE_S])

    def test_scheitert_mit_der_zuletzt_gesehenen_seite(self):
        ok, gesehen = tab_switch.switch_checked(
            'III', click_fn=self._klick, verify_fn=_Folge('II'),
            wait_fn=self._warte)
        self.assertEqual((ok, gesehen), (False, 'II'))
        self.assertEqual(len(self.klicks), tab_switch.SWITCH_ATTEMPTS)

    def test_kein_bild_heisst_nicht_belegt(self):
        ok, gesehen = tab_switch.switch_checked(
            'II', click_fn=self._klick, verify_fn=_Folge(None),
            wait_fn=self._warte)
        self.assertEqual((ok, gesehen), (False, None))

    def test_not_aus_im_warten_steigt_sofort_aus(self):
        blick = _Folge('I', 'II')
        ok, gesehen = tab_switch.switch_checked(
            'II', click_fn=self._klick, verify_fn=blick,
            wait_fn=lambda _s: False)
        self.assertEqual((ok, gesehen), (False, 'I'))
        self.assertEqual(blick.n, 1)        # kein zweites Nachsehen mehr

    def test_werfende_teile_kippen_nichts(self):
        def _boom(*_a):
            raise RuntimeError('kaputt')

        ok, gesehen = tab_switch.switch_checked(
            'II', click_fn=_boom, verify_fn=_boom, wait_fn=_boom)
        self.assertEqual((ok, gesehen), (False, None))


if __name__ == '__main__':
    unittest.main()
