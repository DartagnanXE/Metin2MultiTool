# Okey-Karten-Spiel: gemessene Ergebnisse

Stand 2026-09-08, nach der Gegenprüfung durch Codex ASTRA
(`PRUEFBERICHT_CODEX.md`). Mehrere Aussagen einer früheren Fassung waren
falsch und sind hier korrigiert; die betroffenen Stellen sind gekennzeichnet.

Alle `±`-Angaben sind **Standardfehler**, keine 95-%-Intervalle. Ein grobes
95-%-Intervall ist ungefähr das Doppelte in beide Richtungen.

## 1. Harte Fakten (exakt nachgerechnet, von Codex unabhängig bestätigt)

| Größe | Wert | Wie belegt |
|---|---|---|
| Karten im Deck | 24 (Werte 1–8 × Farben R/B/G, jede genau einmal) | erschlossen, **nicht bewiesen** — siehe Abschnitt 5 |
| Gültige Kombinationen | **170** (8 Drillinge + 18 farbrein + 144 gemischt) | vollständige Aufzählung |
| Kombinationen pro Spiel | höchstens **8** (24 Karten ÷ 3) | Abzählung |
| Theoretisches Maximum | **560 Punkte** | exakte Suche über alle Aufteilungen |

Die 560-Punkte-Partie besteht aus **genau acht** Kombinationen (3× farbrein
6-7-8, 3× farbrein 3-4-5, Drilling 1, Drilling 2). *Korrektur:* Eine frühere
Fassung schloss daraus, wer acht Kombinationen spiele, nehme zu viel Billiges
mit. Das ist falsch — das Maximum selbst braucht alle acht.

## 2. Strategien: vollständig gepaarter Vergleich

**100 identische Deals für jede Strategie**, Seed 4711. *Korrektur:* Der erste
Benchmark wertete PIMC auf 40 und die übrigen auf 300 Deals aus; die daraus
gezogenen Vergleiche waren nicht gepaart und teilweise irreführend.

| Strategie | Mittel | Median | P(Gold ≥400) | P(≥300) | Sekunden/Spiel |
|---|---|---|---|---|---|
| hellsichtig (**obere Schranke**) | 377,2 ± 4,0 | 380 | 31 % | 98 % | 0,09 |
| PIMC 16 | **321,1 ± 5,4** | 310 | 14 % | 66 % | 5,1 |
| Exakt≤10 + PIMC 16 | 315,7 ± 5,5 | 310 | 11 % | 64 % | 6,1 |
| Exakt≤10 + Rollout 48 | 313,4 ± 5,5 | 300 | 8 % | 60 % | 1,4 |
| Exakt≤10 + Netto-Regel | 312,0 ± 5,3 | 300 | 9 % | 63 % | 1,2 |
| Rollout 48 | 311,1 ± 4,9 | 300 | 8 % | 56 % | 0,44 |
| Netto-Regel (ohne Simulation) | 282,4 ± 5,8 | 280 | 3 % | 40 % | 0,001 |
| gierig (immer beste Kombination) | 260,5 ± 5,3 | 260 | 1 % | 23 % | 0,0002 |

**Gepaarte Differenzen** (dieselben Deals, eigener Standardfehler, 95-%-Intervall):

| Vergleich | Differenz | 95-%-Intervall |
|---|---|---|
| Netto-Regel − gierig | +21,9 ± 4,7 | +12,7 … +31,1 |
| Rollout 48 − Netto-Regel | +28,7 ± 5,1 | +18,8 … +38,6 |
| PIMC 16 − Rollout 48 | +10,0 ± 4,6 | +1,1 … +18,9 |
| Exakt≤10 + PIMC − PIMC allein | −5,4 ± 4,0 | −13,2 … +2,4 |
| **PIMC 16 − gierig** | **+55,2 ± 5,1** | **+45,2 … +65,2** |

Gutes Spiel bringt also gesichert rund **+45 bis +65 Punkte** gegenüber naivem.
Die Chance auf mindestens Silber steigt von 23 % auf 66 %.

## 2b. Truhen-Raten (die Zahl, die zählt)

Gemessen 2026-09-08, alle auf denselben Decks (Seed 2026). Naiv, Faustregel und
Rollout auf **1000 Partien**, die beste Strategie auf 400, die Schranke auf 1000.
Eckige Klammern = 95-%-Wilson-Intervall.

| Spielweise | Gold (≥400) | Silber (300–399) | Bronze (<300) | Mittel | s/Klick |
|---|---|---|---|---|---|
| naiv (beste Kombination) | 2,3 % [1,5–3,4] | 28,1 % [25,4–31,0] | 69,6 % [66,7–72,4] | 269,8 | — |
| Netto-Faustregel | 4,8 % [3,6–6,3] | 40,5 % [37,5–43,6] | 54,7 % [51,6–57,8] | 287,0 | <0,001 |
| **Rollout 48** | **6,1 %** | **57,9 %** | **36,0 %** | **313,9** | 0,03 |
| **PIMC 16 (beste)** | **9,5 % [7,0–12,8]** | **56,0 % [51,1–60,8]** | **34,5 % [30,0–39,3]** | **320,6** | 0,42 |
| hellsichtig (Schranke) | 28,8 % | 70,5 % | 0,7 % | 376,1 | — |

**Lesart.** Aus zehn Kartensets werden statt sieben Bronzetruhen nur noch gut
drei. Silber verdoppelt sich, Gold vervierfacht sich. Der Hauptgewinn liegt
beim Verlassen der Bronze-Zone, nicht bei Gold: Die 300-Punkte-Schwelle liegt
nahe am Mittelwert, deshalb hebt schon ein moderater Zugewinn viele Partien
darüber. Gold bei 400 bleibt selbst mit vollständiger Kartenkenntnis auf
28,8 % begrenzt.

**Empfehlung für die Auslieferung: Rollout 48.** Es holt 313,9 von 320,6
Punkten bei einem Vierzehntel der Rechenzeit und liegt beim Silber-Anteil sogar
leicht vorn. Die PIMC-Variante lohnt nur, wenn gezielt Gold das Ziel ist.
Beide brauchen **keine vorberechnete Tabelle und keine Ladezeit** — anders als
das Fischpuzzle, dessen 13-MB-Werte-Tabelle beim Start geladen werden muss.

### Feineinstellung der besten Variante (150 gepaarte Deals, Seed 31337)

| Variante | Mittel | Gold | Differenz zur Basis (95 %) | s/Partie |
|---|---|---|---|---|
| PIMC 16, top6 (Basis) | 326,7 | 14,7 % | — | 4,69 |
| **PIMC 16, top12 (gewaehlt)** | **329,6** | 14,0 % | +2,9 (−4,0 … +9,9) | 4,72 |
| PIMC 32, top8 | 328,3 | 16,0 % | +1,7 (−4,8 … +8,1) | 9,55 |
| Rollout 96, top12 | 321,7 | 12,0 % | −5,0 (−11,7 … +1,7) | 0,65 |

**Keine Variante ist statistisch besser.** Gewaehlt wurde top12, weil es bei
gleicher Laufzeit nominal vorn liegt und die Beschraenkung auf sechs Kandidaten
eine willkuerliche Sparmassnahme ohne Ersparnis war. Doppelte Stichprobenzahl
bringt nichts — das Verfahren ist auskonvergiert.

## 3. Wo die Grenze liegt — und wo nicht

**Mehr Stichproben helfen nicht mehr.** PIMC mit 32 Stichproben (313,3) ist
nicht besser als mit 16 (314,2, jeweils eigener Deal-Satz). Das Verfahren
konvergiert, aber gegen eine **verzerrte** Antwort: Es löst jede Stichprobe
hellsichtig und unterstellt damit Zukunftswissen, das real fast nichts wert
ist (bekannt als *strategy fusion*). Selbst mit unendlich vielen Stichproben
wäre PIMC kein exakter Löser.

**Das exakte Endspiel hilft ebenfalls kaum.** Bis zu zehn Restkarten lässt
sich die optimale Aktion exakt berechnen (`exact.py`, ~1,2 s). Vorgeschaltet
bringt das gegenüber PIMC allein **−5,4 Punkte, statistisch nicht von null
unterscheidbar**. Beides zusammen zeigt: Der Verlust sitzt **nicht im
Endspiel, sondern in den frühen Zügen**, solange über zehn Karten im Deck
liegen — genau dort, wo exakte Rechnung unbezahlbar ist.

**Wie gut sind die Verfahren wirklich?** In einem verkleinerten Spiel
(5 Feldkarten + 8 bzw. 10 Deckkarten) ist das echte Optimum exakt berechenbar:

| Verfahren | 5+8 Karten | 5+10 Karten |
|---|---|---|
| hellsichtig | 101,6 % | 103,7 % |
| **exaktes Optimum** | **100 %** | **100 %** |
| PIMC 16 | 99,5 % | 99,4 % |
| Rollout 48 | 96,7 % | 96,0 % |
| Netto-Regel | 81,5 % | 80,7 % |
| gierig | 76,3 % | 74,5 % |

Über kurze Horizonte ist PIMC also fast optimal. Im vollen Spiel mit rund
dreizehn Entscheidungen bleibt es dagegen deutlich unter der hellsichtigen
Schranke — die Fehler summieren sich.

**Was NICHT bewiesen ist.** *Korrektur:* Eine frühere Fassung nannte
„Optimum zwischen 318 und 376" als Intervall. Das ist keines. 377,2 ist ein
gemessener Mittelwert auf 100 Deals, keine harte Schranke, und der
Informationsvorteil der Hellsicht wächst mit der Decklänge (0,1 % bei 6
Restkarten, 1,4 % bei 8, 2,1 % bei 9, 3,7 % bei 10). Wie groß er bei 19
Restkarten ist, wurde **nicht gemessen**; jede Hochrechnung darauf wäre
Spekulation.

## 4. Was die starke Strategie tut (150 Deals protokolliert)

Sie spielt **wenig und teuer**: 4,7 Kombinationen und 8,4 Wegwürfe pro Spiel.

**Wahrscheinlichkeit, überhaupt eine Kombination zu spielen**, aufgeschlüsselt
nach dem Wert der *besten gerade verfügbaren*:

| beste verfügbar | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
|---|---|---|---|---|---|---|---|---|---|---|
| gespielt | 38 % | 55 % | 58 % | 40 % | 58 % | 64 % | 81 % | 81 % | 90 % | 81 % |

*Korrektur:* Das ist **nicht** die Annahmequote der jeweiligen Kombination.
Gezählt wird jeder Spielzug, auch wenn eine schwächere Kombination gewählt
wurde (in 150 Deals 38-mal). Die Tabelle misst
`P(irgendetwas spielen | beste verfügbare hat p Punkte)`.

Der Trend ist trotzdem eindeutig: **ab 70 Punkten wird fast immer gespielt,
darunter oft gewartet.** *Korrektur:* Die Delle bei 40 Punkten wurde früher
als Struktur gedeutet („nur die gemischte 4-5-6"). Das trifft nicht zu — auch
der Drilling 3,3,3 gibt 40 — und bei 57 Beobachtungen ist der Wert ohnehin
nicht von Rauschen zu trennen.

**Wegwürfe nach Kartenwert:**

| Wert | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Anteil | 25 % | 20 % | 14 % | 15 % | 13 % | **2 %** | **3 %** | 7 % |

Das ist der belastbarste Befund der ganzen Auswertung, und er hat einen
strukturellen Grund — die höchste Kombination, an der eine Karte überhaupt
beteiligt sein kann, und die Zahl der Reihen, in die sie passt:

| Karte | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| bestmögliche Kombination | 50 | 60 | 70 | 80 | 90 | **100** | **100** | **100** |
| in wie vielen Reihen? | 1 | 2 | 3 | 3 | 3 | **3** | 2 | 1 |

Die 6 ist die wertvollste Karte: höchster Wert **und** höchste Flexibilität.
Die 1 ist die schlechteste.

*Korrektur:* Früher stand hier, 91 % der Wegwürfe seien tote Karten. Die 91 %
bezogen sich auf einen internen Heuristikwert, nicht auf Punkte. Gemessen an
der tatsächlich noch bildbaren besten Kombination sind es **69,7 %** — und
„unter 70 Punkten" heißt nicht „tot".

## 5. Grenzen

* **Das Deck-Modell ist erschlossen, nicht bewiesen.** 24 Sammelkarten pro Set
  und 24 abgebildete Kartentypen erzwingen logisch nicht, dass jede Karte
  genau einmal vorkommt. Widerlegt wäre es, wenn in einem Durchgang dieselbe
  Karte zweimal erschiene oder insgesamt mehr als 24 Karten aufgedeckt würden.
* **Drei Ablauf-Annahmen** stehen in keiner Quelle (siehe `engine.py`, A1–A3):
  Nachziehen nach jedem Wegwurf, Wegwerfen auch bei spielbarer Kombination,
  kein Zeitlimit.
* **Die Netto-Parameter wurden auf denselben 300 Deals ausgewählt**, auf denen
  sie gemessen wurden. Ihr Vorsprung ist damit optimistisch geschätzt.
* **Im Spiel getestet ist nichts davon.** Alle Zahlen stammen aus dem Modell.
