# Prüfauftrag: Spieltheorie-Lösung für das Metin2 Okey-Karten-Spiel

Du prüfst eine fertige Analyse **gegnerisch**. Ziel ist nicht Zustimmung,
sondern das Finden von Fehlern. Wenn alles stimmt, sag das kurz und klar —
erfundene Kritik ist genauso schädlich wie übersehene Fehler.

## 1. Die Regeln (aus den offiziellen Wikis, wörtlich zitiert)

Quelle DE (`de-wiki.metin2.gameforge.com/index.php/Okey-Karten-Spiel`, Rohtext):

> Erledige Monster, um Karten zu erhalten. Sobald du 24 Okey-Karten gesammelt
> und gestapelt hast, erhältst du automatisch ein Okey-Kartenset und kannst
> spielen.
>
> * Auf dem Spielfeld erscheinen 5 zufällige Karten.
> * 3 Karten können ausgewählt werden um Punkte zu erhalten.
> * Man kann Karten löschen und eine neue ziehen
> * Ziel des Spiels ist es, eine hohe Punktzahl zu erreichen

Quelle EN (`en-wiki.metin2.gameforge.com/index.php/Okey_Card_Game`, Rohtext):

> * Open the Event UI and press start to play. You have to pay 30.000 Yang and
>   give 1 Card Set.
> * Click on the deck and 5 random cards will be shown on the field.
> * 3 cards must be selected in either:
>   * 3 identical numbers with different colours
>   * 3 ascending cards with different or indifferent colours
> * There can be no gap between the selected cards.
> * If none of the cards on the field are suitable, you can throw one out by
>   right-clicking.

Punktetabellen (DE-Wiki, vollständig übernommen):

| Drilling | Pkt | Reihe gleiche Farbe | Pkt | Reihe gemischt | Pkt |
|---|---|---|---|---|---|
| 1,1,1 | 20 | 1-2-3 | 50 | 1-2-3 | 10 |
| 2,2,2 | 30 | 2-3-4 | 60 | 2-3-4 | 20 |
| 3,3,3 | 40 | 3-4-5 | 70 | 3-4-5 | 30 |
| 4,4,4 | 50 | 4-5-6 | 80 | 4-5-6 | 40 |
| 5,5,5 | 60 | 5-6-7 | 90 | 5-6-7 | 50 |
| 6,6,6 | 70 | 6-7-8 | 100 | 6-7-8 | 60 |
| 7,7,7 | 80 | | | | |
| 8,8,8 | 90 | | | | |

Belohnung: unter 300 Bronze, 300–399 Silber, ab 400 Gold.

Die Wiki-Bilder zeigen genau drei Farben (Rot, Blau, Gelb) und die Werte 1–8.

## 2. Mein Modell — genau das ist zu prüfen

**M1 Deck.** 8 Werte × 3 Farben = 24 Karten, **jede genau einmal**. Begründung:
24 Sammelkarten ergeben 1 Set, und 8×3 = 24. Folge: die Karten*menge* im
Rest-Deck ist dem Spieler jederzeit bekannt (Kartenzählen), nur die
*Reihenfolge* nicht.

**M2 Punkte-Formeln** (aus den Tabellen abgelesen):
- Drilling Wert v → `10v + 10` (v = 1..8 → 20..90)
- Reihe farbrein, kleinste Karte u → `10u + 40` (u = 1..6 → 50..100)
- Reihe gemischt, kleinste Karte u → `10u` (u = 1..6 → 10..60)

**M3 Ablauf.** Feld hat 5 Karten. Pro Zug entweder eine gültige 3er-Kombination
spielen (3 Karten weg) oder eine Karte wegwerfen (1 Karte weg). Danach wird aus
dem Deck auf 5 aufgefüllt, solange das Deck nicht leer ist. Ende, wenn Deck
leer ist und keine Kombination mehr im Feld liegt.

**M4 Angenommen, nicht belegt** (steht so in keiner Quelle):
- A1 Nach jeder entfernten Karte wird nachgezogen, bis das Deck leer ist.
- A2 Wegwerfen ist immer erlaubt, nicht nur wenn keine Kombination da ist.
- A3 Kein Zug- oder Zeitlimit außer dem Deck selbst.

## 3. Behauptungen, die du nachrechnen sollst

**B1** Es gibt genau **170** gültige Kombinationen: 8 Drillinge + 18 farbreine
Reihen (6 Startwerte × 3 Farben) + 144 gemischte Reihen (6 × (3³ − 3)).
*Rechne unabhängig nach.*

**B2** Das theoretische Maximum bei freier Aufteilung aller 24 Karten in acht
3er-Gruppen ist **560 Punkte**. *Unabhängig nachrechnen.* (Meine Rechnung:
3× farbreine 6-7-8 = 300, 3× farbreine 3-4-5 = 210, Drillinge 1 und 2 = 50.)

**B3** Aus M1/M3 folgt eine harte Obergrenze von **8 Kombinationen** pro Spiel
(24 Karten / 3). Jedes Wegwerfen kostet eine Deck-Karte, also ein Drittel einer
möglichen Kombination. *Ist diese Buchhaltung korrekt, inklusive Endspiel?*

**B4** Der „hellsichtige" Wert (maximaler Score bei BEKANNTER Deck-Reihenfolge,
exakt per DP) ist eine **gültige obere Schranke für jede Strategie**, die die
Reihenfolge nicht kennt. *Stimmt das Argument? Gibt es eine Falle?*

**B5** Die DP in `solver.py::_cv` ist korrekt und terminiert. Zustand =
`(deck_position, feld_bitmaske)`. Beschneidung: Wegwerfen bei leerem Deck ist
verboten, weil es eine Karte ohne Ersatz entfernt und den Score nie erhöhen
kann. *Ist diese Beschneidung wirklich verlustfrei? Ist der Zustand vollständig?*

**B6** Das exakte MDP (Zustand = Feld + Rest-*Menge*) ist nicht lösbar:
C(24,5) × 2^19 ≈ 2·10^10 Zustände, mit Farbsymmetrie (Faktor 6) immer noch
~3·10^9. *Stimmt die Abschätzung? Gibt es eine Zustandsreduktion, die ich
übersehe und die exakte Lösung doch möglich macht?*

**B7** Messmethodik: alle Strategien laufen über dieselben gemischten Decks
(gemeinsame Zufallszahlen), das hellsichtige Optimum auf denselben Deals.
*Ist der Vergleich fair? Reichen die Stichproben für die berichteten
Unterschiede?*

## 4. Was du liefern sollst

Prüfe die Dateien `okey/engine.py`, `okey/combos.py`, `okey/solver.py`,
`okey/evaluate.py`, `okey/benchmark.py` und die Messergebnisse in
`okey/ERGEBNISSE.md`.

Schreibe deine Antwort in **genau eine Datei**: `okey/PRUEFBERICHT_CODEX.md`.
Ändere **keine** andere Datei. Struktur:

1. **Urteil je Behauptung B1–B7**: bestätigt / widerlegt / unsicher, mit
   Begründung und eigener Rechnung. Bei Widerlegung: konkrete Stelle und Beleg.
2. **Regel-Modellierung**: Fehler in M1–M4? Besonders M1 (24 eindeutige Karten)
   — welche Beobachtung im Spiel würde das widerlegen?
3. **Code-Fehler**: konkrete Zeile + auslösender Fall. Keine Stilkritik.
4. **Bessere Ansätze**: gibt es einen Weg zur exakt optimalen Strategie, der
   praktikabel ist? Wenn ja, skizziere ihn mit Aufwandsabschätzung.
5. **Fazit in drei Sätzen**: Ist die Lösung tragfähig, und wo ist ihre Grenze?

Belege statt Behauptungen: wenn du etwas nachgerechnet hast, zeig die Rechnung.
Du darfst Python ausführen, um zu prüfen — aber **keine Quelldatei ändern**.
