# -*- coding: utf-8 -*-
"""Der Okey-Reiter: Einstellungen, Stufen-Tabelle, Texte, Auslieferung.

Der sichtbare Aufbau des Reiters wird vom GUI-Smoke-Test mitgeprueft (er geht
alle Eintraege in ``RAIL_ORDER`` durch, und "okey" steht jetzt darin). Hier
stehen die Teile, die auch KOPFLOS pruefbar sind -- und genau die, an denen ein
Fehler still bliebe: eine Stufe ohne Uebersetzung, eine Zahl, die zur Stufe
darueber nicht passt, oder eine Schablone, die im gebauten Programm fehlt.
"""

import os
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEinstellungen(unittest.TestCase):
    def test_voreinstellung(self):
        from interface.config.defaults import DEFAULTS
        self.assertEqual(DEFAULTS['okey']['decks'], 1)
        self.assertEqual(DEFAULTS['okey']['solver'], 'beste',
                         'Voreinstellung soll die staerkste Stufe sein')

    def test_validierung_klemmt_und_faellt_zurueck(self):
        from interface.config.validate import validate
        self.assertEqual(validate({})['okey'], {'decks': 1, 'solver': 'beste'})
        self.assertEqual(validate({'okey': {'decks': -5}})['okey']['decks'], 0)
        self.assertEqual(validate({'okey': {'decks': 5000}})['okey']['decks'],
                         999)
        self.assertEqual(validate({'okey': {'decks': '7'}})['okey']['decks'], 7)
        self.assertEqual(
            validate({'okey': {'solver': 'gibtsnicht'}})['okey']['solver'],
            'beste')

    def test_jede_stufe_ist_auch_einstellbar(self):
        from interface.config.validate import validate
        from okey.strategy import STAERKEN
        for stufe in STAERKEN:
            self.assertEqual(
                validate({'okey': {'solver': stufe}})['okey']['solver'], stufe)

    def test_null_decks_heisst_endlos_und_ist_erlaubt(self):
        from interface.config.validate import validate
        self.assertEqual(validate({'okey': {'decks': 0}})['okey']['decks'], 0)


class TestStufenTabelle(unittest.TestCase):
    def test_vier_stufen(self):
        from okey import stufen
        from okey.strategy import STAERKEN
        self.assertEqual(len(stufen.REIHENFOLGE), 4)
        self.assertEqual(set(stufen.REIHENFOLGE), set(STAERKEN),
                         'Tabelle und Strategie kennen verschiedene Stufen')
        self.assertEqual(stufen.REIHENFOLGE[0], 'beste',
                         'die staerkste Stufe steht oben')

    def test_tabelle_ist_vollstaendig(self):
        from okey import stufen
        zeilen = stufen.tabelle()
        self.assertEqual(len(zeilen), 4)
        for z in zeilen:
            for feld in ('stufe', 's_je_zug', 's_je_partie', 'punkte', 'gold',
                         'silber', 'bronze'):
                self.assertIn(feld, z)
            self.assertGreater(z['punkte'], 0, '%s ohne Messwert' % z['stufe'])
            self.assertAlmostEqual(sum((z['gold'], z['silber'], z['bronze'])),
                                   1.0, places=2,
                                   msg='%s: Truhen-Anteile ergeben nicht 100 %%'
                                       % z['stufe'])

    def test_mehr_rechenzeit_bringt_mehr_punkte(self):
        """Die Tabelle soll die Wahl BEGRUENDEN. Waere eine langsamere Stufe
        schwaecher, waere sie sinnlos -- und die Tabelle irrefuehrend."""
        from okey import stufen
        zeilen = stufen.tabelle()
        for oben, unten in zip(zeilen, zeilen[1:]):
            self.assertGreaterEqual(
                oben['punkte'], unten['punkte'] - 1.0,
                '%s ist langsamer als %s, aber nicht besser'
                % (oben['stufe'], unten['stufe']))
            self.assertGreater(
                oben['s_je_zug'], unten['s_je_zug'],
                '%s soll mehr Rechenzeit brauchen als %s'
                % (oben['stufe'], unten['stufe']))

    def test_die_beste_stufe_bleibt_unter_einer_sekunde_je_zug(self):
        """Zusage an den Nutzer: "die beste, die ca. 0,4 s pro Zug braucht"."""
        from okey import stufen
        self.assertLess(stufen.zeile('beste')['s_je_zug'], 1.0)

    def test_eine_ganze_partie_dauert_ertraeglich(self):
        from okey import stufen
        self.assertLess(stufen.zeile('beste')['s_je_partie'], 20.0,
                        'ein Kartenset wuerde spuerbar haengen')

    def test_stufen_modul_laedt_ohne_schwere_abhaengigkeiten(self):
        """Der Reiter zeigt die Tabelle beim Aufbau -- er darf dafuer NICHT
        OpenCV oder die Strategie laden (Ladezeit)."""
        quelle = open(os.path.join(WURZEL, 'okey', 'stufen.py'),
                      encoding='utf-8').read()
        for zeile in quelle.splitlines():
            self.assertFalse(zeile.startswith(('import ', 'from ')),
                             'okey/stufen.py importiert etwas: %r' % zeile)


class TestTexte(unittest.TestCase):
    def test_jede_stufe_hat_namen_und_erklaerung_in_beiden_sprachen(self):
        from i18n_data import TRANSLATIONS
        from okey.strategy import STAERKEN
        for stufe in STAERKEN:
            for muster in ('ui.okey_level_%s', 'ui.okey_how_%s'):
                key = muster % stufe
                self.assertIn(key, TRANSLATIONS, 'fehlt: %s' % key)
                for sprache in ('en', 'de'):
                    self.assertTrue(TRANSLATIONS[key].get(sprache),
                                    '%s ohne %s' % (key, sprache))

    def test_truhen_namen(self):
        """Auch der Fall OHNE Truhe braucht einen Namen: eine abgebrochene
        Runde zahlt nichts aus, und der Reiter darf dort keinen rohen
        Schluesselnamen anzeigen."""
        from i18n_data import TRANSLATIONS
        for truhe in ('gold', 'silber', 'bronze', 'none'):
            self.assertIn('ui.okey_chest_%s' % truhe, TRANSLATIONS)
        quelle = open(os.path.join(WURZEL, 'interface', 'app',
                                   'views_okey.py'), encoding='utf-8').read()
        self.assertIn("spiel.truhe or 'none'", quelle)

    def test_alle_okey_texte_sind_zweisprachig(self):
        from i18n_data import TRANSLATIONS
        luecken = [k for k, v in TRANSLATIONS.items()
                   if k.startswith(('okey.', 'ui.okey'))
                   and not (v.get('en') and v.get('de'))]
        self.assertEqual(luecken, [])


class TestReiterIstVerdrahtet(unittest.TestCase):
    def test_okey_steht_in_der_leiste(self):
        quelle = open(os.path.join(WURZEL, 'interface', 'app', '_common.py'),
                      encoding='utf-8').read()
        self.assertIn("'okey'", quelle)

    def test_jedes_leisten_element_hat_eine_zeile(self):
        """Der dokumentierte Fallstrick: ein Eintrag ohne Zeilennummer faellt
        stumm aus der Leiste -- und Konsole/Einstellungen duerfen nicht auf der
        wachsenden Abstandszeile landen."""
        import re
        quelle = open(os.path.join(WURZEL, 'interface', 'app', 'shell.py'),
                      encoding='utf-8').read()
        block = re.search(r'rows = \{(.*?)\}', quelle, re.S).group(1)
        zeilen = dict(re.findall(r"'(\w+)': (\d+)", block))
        # Genau die Abstandszeile der LEISTE, nicht die des Fensters --
        # ein unverankertes Muster traf vorher die erste beliebige Zeile.
        spacer = int(re.search(r'rail\.grid_rowconfigure\((\d+), weight=1\)',
                               quelle).group(1))
        gemeinsam = open(os.path.join(WURZEL, 'interface', 'app', '_common.py'),
                         encoding='utf-8').read()
        order = re.search(r'RAIL_ORDER = \((.*?)\)', gemeinsam, re.S).group(1)
        for name in re.findall(r"'(\w+)'", order):
            self.assertIn(name, zeilen, '%s fehlt in shell.rows' % name)
            self.assertNotEqual(int(zeilen[name]), spacer,
                                '%s liegt auf der Abstandszeile %d'
                                % (name, spacer))
        self.assertEqual(len(set(zeilen.values())), len(zeilen),
                         'zwei Leisten-Elemente auf derselben Zeile')


class TestSpeichernRuftRichtigAuf(unittest.TestCase):
    """Der Reiter muss update_config(Bereich, Schluessel, Wert) benutzen.

    Ein Dict-Aufruf waere im try/except still gescheitert -- die Einstellung
    haette nach jedem Neustart wieder auf Anfang gestanden, ohne Fehlermeldung.
    Deshalb wird die Aufrufform hier festgehalten (kopflos pruefbar, weil der
    Reiter selbst customtkinter braucht).
    """

    def test_drei_argumente_je_einstellung(self):
        # Am QUELLTEXT geprueft, nicht am Import: der Controller zieht
        # customtkinter mit, das es kopflos nicht gibt.
        steuerung = open(os.path.join(WURZEL, 'interface', 'app',
                                      'controller.py'), encoding='utf-8').read()
        self.assertIn('def update_config(self, section, key, value):',
                      steuerung)
        quelle = open(os.path.join(WURZEL, 'interface', 'app',
                                   'views_okey.py'), encoding='utf-8').read()
        self.assertIn("update_config('okey', 'decks'", quelle)
        self.assertIn("update_config('okey', 'solver'", quelle)
        self.assertNotIn("update_config({", quelle,
                         'Dict-Aufruf -- so speichert nichts')


class TestAuslieferung(unittest.TestCase):
    """Ohne diese Eintraege waere der Reiter im gebauten Programm blind."""

    def test_schablonen_und_module_stehen_in_beiden_bauplaenen(self):
        for spec in ('Metin2FishBot.spec', 'Metin2FishBot_onefile.spec'):
            quelle = open(os.path.join(WURZEL, spec), encoding='utf-8').read()
            self.assertIn("('okey_templates', 'okey_templates')", quelle,
                          '%s liefert die Schablonen nicht mit' % spec)
            for modul in ('interface.okey_runner', 'okey.flow', 'okey.vision',
                          'okey.partie', 'okey.stufen'):
                self.assertIn("'%s'" % modul, quelle,
                              '%s fehlt in %s' % (modul, spec))


if __name__ == '__main__':      # pragma: no cover
    unittest.main()
