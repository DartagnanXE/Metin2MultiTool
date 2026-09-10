# -*- coding: utf-8 -*-
"""Die vier Solver-Stufen als reine Daten -- ohne einen einzigen Import.

Absicht: Der Okey-Reiter kann diese Tabelle anzeigen, ohne dass beim
Programmstart die Strategie, OpenCV oder sonst etwas geladen wird. Der Nutzer
hat ausdruecklich gesagt, dass nichts zu Rucklern oder langen Ladezeiten
fuehren darf; deshalb liegt hier nur ein Tupel aus Zahlen und Text, und die
eigentliche Rechen-Maschinerie wird erst geladen, wenn wirklich gespielt wird.

WOHER DIE ZAHLEN KOMMEN: 400 identische Kartenmischungen (fester Startwert 1),
alle vier Stufen auf DENSELBEN Mischungen -- sonst vergleicht man Wuerfel statt
Strategien. Gemessen am 2026-09-10 auf dem Entwicklungsrechner; die Zeit je Zug
faellt auf einem langsameren Rechner groesser aus, das Verhaeltnis der Stufen
zueinander bleibt.

Die Punkte sind ein MITTELWERT ueber 400 Partien. Eine einzelne Partie streut
stark -- wer einmal Gold zieht, hat nicht die bessere Stufe erwischt, sondern
die besseren Karten.
"""

#: Grenzen der Truhen (Wiki): unter 300 Bronze, ab 300 Silber, ab 400 Gold.
TRUHEN_GRENZEN = (300, 400)

#: Je Stufe: (schluessel, i18n-Name, Sekunden je Zug, Mittelwert Punkte,
#:            Gold-Anteil, Silber-Anteil, Bronze-Anteil, i18n-Erklaerung)
#: Wird unten aus MESSUNG aufgebaut, damit Zahlen und Text nicht auseinander
#: laufen koennen.
MESSUNG = {
    # schluessel: (s_je_zug, mittel, gold, silber, bronze)
    'beste':   (0.393571, 320.4, 0.1000, 0.5825, 0.3175),
    'stark':   (0.128772, 314.7, 0.0575, 0.6125, 0.3300),
    'schnell': (0.026132, 311.8, 0.0450, 0.5950, 0.3600),
    'sofort':  (0.000027, 280.1, 0.0325, 0.3825, 0.5850),
}

#: Reihenfolge in der Oberflaeche: die staerkste zuerst (= Voreinstellung).
REIHENFOLGE = ('beste', 'stark', 'schnell', 'sofort')

#: Wie viele Zuege eine Partie im Mittel braucht -- Mittel ueber alle vier
#: Stufen derselben Messung (13,9 / 13,0 / 13,3 / 13,8).
ZUEGE_JE_PARTIE = 13.5


def zeile(schluessel):
    """Eine Tabellenzeile als Dict -- fertig zum Anzeigen."""
    s_zug, mittel, gold, silber, bronze = MESSUNG[schluessel]
    return {
        'stufe': schluessel,
        's_je_zug': s_zug,
        's_je_partie': s_zug * ZUEGE_JE_PARTIE,
        'punkte': mittel,
        'gold': gold,
        'silber': silber,
        'bronze': bronze,
    }


def tabelle():
    """Alle vier Zeilen in Anzeige-Reihenfolge."""
    return [zeile(k) for k in REIHENFOLGE]
