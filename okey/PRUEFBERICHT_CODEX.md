# Gegenprüfung der Okey-Analyse

Prüfdatum: 08.09.2026. Geprüft wurden die fünf beauftragten Python-Dateien, `ERGEBNISSE.md` und ergänzend die Herkunft der Verhaltensstatistiken in `derive_rules.py`. Alle eigenen Python-Läufe erfolgten mit `-B` beziehungsweise `PYTHONDONTWRITEBYTECODE=1`; keine bestehende Datei wurde bearbeitet.

Änderungskontrolle: Die vor dem Schreiben des Berichts erfassten vorhandenen Dateien sind laut SHA-256-Vergleich unverändert. Während der Berichtserstellung erschienen zusätzlich `okey/exact.py` und `okey/__pycache__/exact.cpython-312.pyc`; diese wurden nicht von mir angelegt oder verändert und sind nicht Gegenstand dieser Prüfung. Meine einzige angelegte Datei ist dieser Bericht.

**Gesamturteil:** Der kombinatorische Kern und die hellsichtige DP sind unter den Modellannahmen korrekt. Die Messwerte sind reproduzierbar, aber mehrere daraus gezogene Schlussfolgerungen sind falsch oder stärker als ihre Belege. Eine exakt optimale Strategie für das unbekannte Deck wurde hier nicht gefunden oder bewiesen.

## 1. Urteil zu B1–B7

### B1 — bestätigt

Ich habe unabhängig von `engine.combo_points` alle `C(24,3) = 2024` verschiedenen Dreierauswahlen erzeugt und anhand der Wert- und Farbbedingungen bewertet. Ergebnis:

| Typ | Eigene Anzahl |
|---|---:|
| Drei gleiche Werte | 8 |
| Drei aufeinanderfolgende Werte, eine Farbe | 18 |
| Drei aufeinanderfolgende Werte, mindestens zwei Farben | 144 |
| Gesamt | **170** |

Für jede der sechs möglichen Reihen gibt es `3³ = 27` Farbzuweisungen, davon drei einfarbige. Somit `8 + 6·3 + 6·24 = 170`. Die unabhängig erzeugte Menge einschließlich Masken, Karten-IDs und Punktzahlen stimmt vollständig mit `combos.ALL_COMBOS` überein. „Gemischt“ umfasst ausdrücklich auch zwei Karten derselben Farbe.

### B2 — bestätigt

Eine eigene Suche über **beliebige disjunkte gültige Kombinationen**, bei der Karten sogar ungenutzt bleiben dürfen, liefert **560**. Damit wurde auch ausgeschlossen, dass eine unvollständige Aufteilung mehr als die behauptete vollständige Aufteilung erzielt.

Verwendete Rekursion: Sei `P(S)` die maximale Punktzahl einer freien Packung aus Kartenmenge `S`, und `c` deren kleinste Karte. Dann

```
P(∅) = 0
P(S) = max(P(S\{c}), max[p(T) + P(S\T) für gültige T⊆S mit c∈T])
```

Jede Lösung lässt `c` entweder ungenutzt oder verwendet sie in genau einer solchen Kombination. Die Rekursion ist daher vollständig. Mit den unabhängig für B1 erzeugten Kombinationen wurden 496 verschiedene Restmengen ausgewertet; `P({0,…,23}) = 560`.

Die vorgelegte Konstruktion erreicht die Schranke: `3·100 + 3·70 + 20 + 30 = 560`. **560 ist auch mit dem Fünferfeld bei geeigneter Reihenfolge erreichbar**, etwa mit dieser getesteten Reihenfolge von Karten-IDs:

```
[0,1,2, 3,4,5, 6,9,12, 7,10,13, 8,11,14,
 15,18,21, 16,19,22, 17,20,23]
```

Man spielt jeweils die nächste Dreiergruppe; `clairvoyant` liefert dafür 560. Die ungefähr 376 Punkte in den Ergebnissen sind somit ein Stichprobenmittel der hellsichtigen Maxima, kein hartes Maximum des Fünferfelds.

### B3 — bestätigt, mit Präzisierung der Wegwurf-Buchhaltung

Zu jedem Zeitpunkt gilt unter M1/M3:

`24 = 3·k + d + |Feld| + |Restdeck|`,

wobei `k` gespielte Kombinationen und `d` Wegwürfe zählt. Am modellierten Spielende ist das Deck leer; verbleibende nicht verwertbare Feldkarten müssen weiterhin mitgezählt werden. Damit `k ≤ floor((24-d)/3) ≤ 8`.

„Ein Drittel einer möglichen Kombination“ ist als Verbrauch von Kartenressourcen richtig, **nicht als tatsächlicher marginaler Verlust**: Der erste Wegwurf senkt die rein rechnerische Obergrenze von acht auf sieben, der zweite und dritte senken sie nicht weiter, der vierte auf sechs. Ein Wegwurf kann zudem den erreichbaren Score erhöhen; er kostet keine fest definierte Punktzahl. Bei leerem Deck verbraucht er eine Feldkarte, keine neu gezogene Karte.

### B4 — bestätigt; die statistische Interpretation im Ergebnistext nicht

Für jede feste Reihenfolge `ω` kann der hellsichtige Optimierer dieselbe legale Aktionsfolge wählen wie jede nicht hellsichtige Strategie. Daher gilt pfadweise, auch für jede Realisierung eigener Strategie-Zufallszahlen `ξ`:

`Score(π,ω,ξ) ≤ CV(ω)`.

Erwartungsbildung ergibt `E[Score(π)] ≤ V* ≤ E[CV]`, wobei `V*` den optimalen erwarteten Score bei unbekannter Reihenfolge bezeichnet. Das setzt dieselben Regeln, erlaubten Aktionen und dasselbe Optimierungsziel voraus.

Zwei Fallen:

1. Ein **gemessener** Mittelwert von 375,6 ist keine harte Schranke für den unbekannten Populationsmittelwert. Er begrenzt die auf exakt diesen Deals erzielbaren durchschnittlichen Scores. Entsprechend ist „Optimum irgendwo zwischen 318 und 376“ in `ERGEBNISSE.md:36–38` kein bewiesenes Intervall für `V*`.
2. PIMC mittelt nach der ersten Aktion hellsichtige Fortsetzungen. Dabei dürfen spätere Entscheidungen innerhalb jeder Stichprobe deren Zukunft kennen. Allgemein gilt `E[max X] ≥ max E[X]`; mehr Stichproben beseitigen diesen Informationsvorteil der simulierten Fortsetzung nicht. `pimc_action` ist deshalb eine Heuristik und kein exakter MDP-Solver, auch bei unendlich vielen Stichproben und ohne Kandidatenbeschränkung.

Der Abstand `560 − E[CV]` entsteht durch Ankunftsreihenfolge und begrenzte Haltekapazität. Der hellsichtige Spieler kennt bereits alle künftigen Karten; diesen Abstand allein als Preis des Nichtsehens zu erklären (`ERGEBNISSE.md:17–18`) vermischt Information und Feldkapazität.

### B5 — bestätigt für eine feste Reihenfolge und einen dafür eigenen Cache

Die Rekursion `solver.py:54–82` prüft alle spielbaren Kombinationen und, solange Nachziehen möglich ist, alle Wegwürfe. `_refill` bildet M3 korrekt ab, auch wenn weniger als drei Karten im Deck verbleiben.

**Terminierung:** Die natürliche Zahl `len(order) − pos + popcount(field)` sinkt bei jeder Aktion um drei beziehungsweise eins. Nachziehen verschiebt Karten lediglich zwischen Deck und Feld. Damit gibt es keine Rekursionszyklen; sogar Wegwürfe ohne Ersatz würden die Terminierung nicht gefährden.

**Beschneidung:** Bei leerem Deck kann das Löschen einer Karte keine neue Dreierauswahl erzeugen. Jede anschließend noch spielbare Kombination war vorher bereits spielbar. Wegwerfen kann deshalb für den maximalen Score entfallen. Bei höchstens fünf Feldkarten ist im leeren Deck ohnehin höchstens eine weitere Kombination möglich; die beste vorhandene ist optimal.

**Zustand:** Für einen separat fixierten Deckverlauf genügen Position und Feldmenge. Der bereits erzielte Score ist beim additiven Ziel „maximaler Endscore“ eine irrelevante Konstante. Für eine Optimierung der Goldwahrscheinlichkeit braucht man dagegen zusätzlich den bisherigen Score beziehungsweise die noch fehlenden Punkte.

**Eigener Gegencheck:** Eine separate Referenz-DP mit sortierten Kartentupeln, eigener Punktefunktion und ausdrücklich erlaubten Wegwürfen bei leerem Deck stimmte in 300 zufällig erzeugten Zuständen mit insgesamt einer bis zwölf verfügbaren Karten vollständig mit `_cv` überein (Seed 915). Die Referenz verwendete weder `playable` noch `_cv` für ihre Berechnung.

**Einschränkung:** Der öffentlich übergebbare Cache kann über verschiedene Reihenfolgen hinweg falsch wiederverwendet werden. Das ist ein konkreter Schnittstellenfehler, siehe Abschnitt 3; die vorhandenen Benchmark- und PIMC-Aufrufe vermeiden ihn.

### B6 — unsicher hinsichtlich „nicht lösbar“; Größenordnung bestätigt

Die eigene Rechnung ergibt

`C(24,5) = 42 504`,

`42 504 · 2¹⁹ = 22 284 337 152` Zustände mit fünf Feldkarten.

Kürzere Felder treten in normalisierten Entscheidungszuständen nur bei leerem Deck auf; dafür kommen höchstens `Σ(j=0…4) C(24,j) = 12 951` Zustände hinzu. Die große Zahl ist nicht einfach durch Erreichbarkeit zu beseitigen: Mit beliebigen Startdeals und Wegwürfen lassen sich grundsätzlich alle disjunkten Paare mit fünf Feldkarten und beliebiger Restmenge erreichen.

Die Farbsymmetrie liefert ungefähr `3,714·10⁹`, nicht exakt einen Faktor sechs, weil manche Zustände unter Farbtausch unverändert bleiben. Sogar die genaue Anzahl der Farborbits für fünf Feldkarten lässt sich bestimmen: Eine Transposition fixiert den Koeffizienten von `x⁵` in `[(x+2)(x²+2)]⁸`, also 3 784 704 Zustände; ein Dreierzyklus fixiert keine, weil fünf nicht durch drei teilbar ist. Burnside ergibt

`(22 284 337 152 + 3·3 784 704)/6 = 3 715 948 544`.

Das ist für ein naives Python-Dictionary sehr groß. Es beweist aber **keine praktische oder mathematische Unlösbarkeit**. Nur ein dicht gespeicherter 64-Bit-Wert pro Farborbit benötigt etwa 29,7 GB, ohne Indizes, Arbeitsdaten oder Politik; bei 32 Bit etwa 14,9 GB, dann ohne Anspruch auf rechnerisch exakte rationale Werte. Der Übergangsaufwand bleibt erheblich: Ein Dreiernachzug kann bei 19 Restkarten 969 verschiedene ungeordnete Ergebnisse haben.

Eine praktikable Gesamtlösung ab Spielbeginn habe ich nicht nachgewiesen. Exakte Teilspiele sind dagegen bereits mit einfachem Python praktikabel; eine ausgeführte rationale MDP-Rechnung mit acht Restkarten steht in Abschnitt 4. Die Aussage in `solver.py:17–20` und `ERGEBNISSE.md:38`, die Zustandszahl mache das MDP schlechthin unlösbar, ist nicht belegt.

### B7 — widerlegt in der pauschalen Form; gemeinsamer Kern korrekt

`evaluate.run` erzeugt tatsächlich einen gemeinsamen Deal-Satz und verwendet ihn für alle Strategien und die Schranke. Die Ziehungen hängen nicht von der Reihenfolge der Strategieauswertung ab. Auch PIMC erhält nur eine sortiert aus der Maske rekonstruierte Restmenge, keine echte Restreihenfolge.

**Der veröffentlichte Benchmark vergleicht aber nicht durchgehend dieselben Stichproben:** `benchmark.py:40,54,60,68` wertet PIMC auf den ersten 40, die anderen Strategien und die Schranke auf 300 Deals aus. Der Konsolenhinweis und die Tabellenzeile nennen das, die pauschalen Aussagen in `ERGEBNISSE.md:3–5,20,40–43` berücksichtigen es nicht ausreichend. Beide Mittelwerte sind weiterhin sinnvolle Schätzer, ihr Unterschied ist aber kein vollständig gepaarter Vergleich.

Ich habe `python3 -B -m okey.benchmark 300` vollständig ausgeführt. Alle dort berichteten Mittelwerte, Standardfehler und Erfolgsquoten reproduzieren sich auf die angegebene Rundung; insbesondere 375,6, 318,0, 306,0, 299,5, 288,4, 265,7 und 83,9. Laufzeiten lagen hier beispielsweise bei 5,20 s für PIMC und 0,095 s für die hellsichtige DP. Die Netto-Regel wird von diesem Kommando nicht aufgerufen; separat mit Seed 1 auf denselben 300 Deals geprüft ergeben sich ebenfalls 281,7 Punkte, Standardfehler 3,655, 4,3 % Gold und 42,0 % mindestens Silber.

Der wirklich gemeinsame erste 40er-Satz ergibt:

| Strategie | Mittel auf den ersten 40 Deals |
|---|---:|
| Hellsichtig | 377,75 |
| PIMC 16 | 318,00 |
| Rollout 24, Basis Schwelle 60 | 305,00 |
| Rollout 24, Basis gierig | 295,25 |
| Gierig | 280,00 |

Der gepaarte PIMC-Vorsprung vor gierig beträgt dort **38,0 statt 52,3 Punkte**. Gierig erreicht dort bereits 40 % mindestens Silber, gegenüber 60 % für PIMC; der angeführte Sprung von 26 % auf 60 % stammt aus unterschiedlich großen Deal-Sätzen.

**Stichprobensicherheit:**

- Das ausgegebene `±` ist ein Standardfehler, kein 95-%-Intervall. PIMC ergibt grob `318 ± 1,96·9,2`, also etwa 300 bis 336 Punkte; das hellsichtige Mittel grob 371,5 bis 379,7. Es sind approximative statistische Intervalle, keine harten Grenzen.
- Fünf Goldspiele aus 40 ergeben 12,5 %, aber ein Wilson-95-%-Intervall von ungefähr **5,5–26,1 %**. Für 24 Silber-oder-Gold-Spiele aus 40 ergibt es **44,6–73,7 %**. „Meistens Silber“ ist deshalb als Populationsaussage noch nicht abgesichert.
- Für tatsächlich gepaarte Differenzen ist `SE = s(D)/√n` mit `Dᵢ = Score_Aᵢ − Score_Bᵢ` zu verwenden. Eigenständig nachgerechnet auf 300 Deals: Netto minus gierig `16,033 ± 3,524` Standardfehler, approximatives 95-%-Intervall **9,13–22,94** Punkte. Rollout 24/S60 minus Rollout 24/gierig: `6,467 ± 2,723`, Intervall **1,13–11,80**. Diese Vergleiche zeigen positive Effekte auf diesem Testsatz; das zweite Ergebnis ist wesentlich knapper.
- Die behauptete allgemeine Überlegenheit von PIMC gegenüber Rollout/S60 ist aus den publizierten Zusammenfassungen nicht abgesichert. Hierfür fehlen insbesondere die gepaarten Differenzen samt Unsicherheit auf dem gemeinsamen Satz. Gemeinsame Zufallszahlen reduzieren typischerweise Streuung, beseitigen aber keine Strategie-Deal-Wechselwirkungen.
- Die Netto-Parameter wurden laut `solver.py:330–331` auf 300 Deals ausgesucht. Ohne getrennte Testdeals sind ihre gemessene Verbesserung und die dazu berechnete Unsicherheit als Ergebnisse nach Parameterauswahl zu behandeln. Ein unabhängiger Testsatz ist für eine belastbare Verallgemeinerung erforderlich.

## 2. Regel-Modellierung M1–M4

**M1 ist plausibel, aber die angegebene Herleitung beweist Eindeutigkeit nicht.** Eine Eintrittswährung aus 24 Sammelobjekten und 24 verschiedene abgebildete Kartentypen erzwingen logisch kein Deck mit je genau einem Exemplar. Die aktuell eingesehene englische Wiki-Seite nennt zusätzlich ausdrücklich das Aufbrauchen von 24 Spielkarten als Endbedingung; das stützt die Deckgröße stärker als allein der Sammelkarten-Umtausch, beweist aber weiterhin nicht die Verteilung. [EN-Wiki, Regeln und Belohnungen](https://en-wiki.metin2.gameforge.com/index.php/Okey_Card_Game)

**Konkrete Widerlegung im Spiel:** Innerhalb eines einzigen ununterbrochenen Durchgangs erscheint dieselbe Kombination aus Wert und Farbe zweimal, etwa eine bereits gespielte oder weggeworfene rote Sechs erneut, oder zwei rote Sechsen gleichzeitig. Auch mehr als 24 insgesamt aufgedeckte Karten ohne Neustart widerlegen dieses endliche Deckmodell. Für eine positive Prüfung sollte ein vollständiger Durchgang mit allen aufgedeckten, gespielten und weggeworfenen Karten protokolliert werden; eine fehlerfreie Partie allein ist noch kein universeller Beweis.

Unter M1 ist `Game.remaining_unknown()` trotz Verwendung des echten Decksuffixes kein Informationsleck: Dessen Menge ist genau die aus dem vollständigen Deck und allen bereits gesehenen Karten rekonstruierbare Information. Ohne Eindeutigkeit wären dagegen Sets und Bitmasken ungeeignet, weil sie Mehrfachkarten verschlucken.

**M2 stimmt** mit sämtlichen vorgelegten Tabellenzeilen überein. Die deutsche Wiki-Seite bestätigt Punkte und Truhenschwellen sowie das Löschen mit anschließendem Ziehen. [DE-Wiki, Spielregeln und Punktzahlen](https://de-wiki.metin2.gameforge.com/index.php/Okey-Karten-Spiel)

**M3/M4 sind intern konsistent, aber bedingt:** Zu prüfen sind insbesondere das vollständige Auffüllen nach einer Kombination, freiwilliges Wegwerfen trotz spielbarer Kombination und die Auswertung letzter Kombinationen nach Leerwerden des Nachziehstapels. Ein zusätzlicher Klick zum Nachziehen ändert den Score nicht, sofern dazwischen keine weiteren entscheidungsrelevanten Aktionen möglich sind. Ein freiwilliger Ende-Knopf oder das Abräumen nutzloser Endkarten kann beim Ziel maximaler Punkte ohne Nachteil aus der Rechnung entfallen; Zeitkosten wären ein anderes Optimierungsziel.

**Zusätzliche Wahrscheinlichkeitsannahme:** Die Auswertung setzt eine gleichverteilte zufällige Permutation des eindeutigen Decks voraus. M1 allein impliziert das nicht. Nur unter dieser oder einer entsprechend begründeten Verteilung ist jede ungesehene Restreihenfolge bedingt auf die Beobachtungen gleich wahrscheinlich und „Feld + Restmenge“ der richtige stochastische Zustand. Die pfadweise hellsichtige Schranke benötigt hingegen keine Gleichverteilung.

Schließlich maximieren die Strategien Punkte. Maximale Goldwahrscheinlichkeit oder maximaler erwarteter Truhenwert sind andere Zielfunktionen und müssen gesondert gelöst werden.

## 3. Konkrete Code- und Auswertungsfehler

### 3.1 Falsches Resultat bei Wiederverwendung des hellsichtigen Caches

**Stellen:** `solver.py:34–41,54–58`, ebenso der optionale Cache von `clairvoyant_best_action` ab Zeile 85. Der Schlüssel `(pos, field)` enthält keinen Deckkontext. Folgender ausgeführter Fall verwendet zwei gültige vollständige Decks mit identischem Anfangsfeld:

```python
from okey.solver import clairvoyant
a = [3,1,5,14,2,4,7,18,11,22,17,20,0,10,23,19,16,8,6,9,12,21,15,13]
b = a[:5] + list(reversed(a[5:]))
memo = {}
assert clairvoyant(a, memo) == 430
assert clairvoyant(b, memo) == 430  # tatsächlich geliefert, aber falsch
assert clairvoyant(b) == 380        # korrekt mit eigenem Cache
```

**Auswirkung:** Falsche Scores und gegebenenfalls Aktionen bei deckübergreifender Wiederverwendung. **Abgrenzung:** Der Benchmark erzeugt je Deal einen eigenen Cache; PIMC setzt ihn in `solver.py:218` je Stichprobe neu auf und teilt ihn nur innerhalb derselben Reihenfolge. Die reproduzierten Ergebnisse sind von diesem Fehler nicht betroffen. Der Cache müsste an eine feste Reihenfolge gebunden oder entsprechend geschlüsselt werden.

### 3.2 Median für gerade Stichproben falsch berechnet

**Stelle:** `evaluate.py:104` verwendet `s[n // 2]`. Eigener Test: `summarize([100,200])['median']` liefert **200**, der übliche Stichprobenmedian ist **150**. Bei geradem `n` fehlt die Mittelung der beiden mittleren Werte. Mittelwert, Standardfehler und Erfolgsquoten werden dadurch nicht verändert.

### 3.3 Behauptete Rollout-Verbesserung ist nicht garantiert

**Stellen:** Garantie in `solver.py:248–251`; tatsächlich werden in Zeilen 266–273 endliche Stichproben maximiert. Der klassische Verbesserungsschritt verlangt korrekte Erwartungswerte und die Verfügbarkeit der Basisaktion. Stichprobenfehler können bereits bei 24 Rollouts eine schlechtere Aktion bevorzugen.

Ausgeführter Gegenfall, Karten-IDs entsprechend `combos.py`:

```
Feld = [9,17,0,20,6]
Restmenge = [13,5,19,12]
Basis = base_greedy
rollouts = 24, rng = random.Random(63), top_k = 8
```

Die Basis wirft Karte **0** weg, `rollout_action` dagegen Karte **20**. Vollständige Enumeration aller `4! = 24` Restreihenfolgen mit anschließender Basisstrategie ergibt für diese ersten Aktionen:

`Q_Basis(Wegwurf 0) = 175/2 = 87,5`,

`Q_Basis(Wegwurf 20) = 515/6 ≈ 85,8333`.

Damit ist konkret die Voraussetzung `Q_Basis(gewählte Aktion) ≥ V_Basis` verletzt, auf der das Verbesserungsargument beruht. Das ist kein Nachweis, dass die wiederholt angewandte Rollout-Strategie insgesamt schlechter ist; es widerlegt die behauptete Absicherung dieses Schritts. Die Heuristik darf so implementiert sein, ihre Garantie ist falsch. Zusätzlich kann `_shortlist` bei entsprechend kleinem `top_k` Basisaktionen ausschließen.

### 3.4 „91 % unter 70 erreichbaren Punkten“ verwechselt Heuristik und Punkte

**Stellen:** `derive_rules.py:136–140` prüft `card_potential`; dessen Definition in `solver.py:152–153` zieht für fehlende Partner jeweils zwölf Punkte ab. `ERGEBNISSE.md:83–85` interpretiert dies dagegen als höchste noch erreichbare Kombinationspunktzahl.

Eine noch mögliche farbreine 3–4–5 mit zwei ungesehenen Partnern zählt beispielsweise als `70 − 24 = 46` Potentialpunkte, obwohl 70 Spielpunkte erreichbar bleiben. Das ist keine fehlerhafte Implementierung der Heuristik, sondern eine falsche Interpretation ihres Messwerts.

Ich habe dieselben 150 Deals mit Seeds 42/43 erneut protokolliert und für jede weggeworfene Karte die **ungekürzte** beste Kombination aus Feld und Restmenge bestimmt. Ergebnis:

- Heuristikwert unter 70: **1145/1260 = 90,9 %**, wie veröffentlicht.
- Höchste überhaupt noch bildbare Kombination unter 70 Spielpunkten: **878/1260 = 69,7 %**.

Die behaupteten 91 % sind in der formulierten Bedeutung somit falsch. Auch „unter 70“ bedeutet nicht „tot“; eine Karte mit noch erreichbaren 60 Punkten ist weiterhin verwertbar.

### 3.5 Annahmequote zählt nicht die Annahme einer bestimmten Kombination

**Stellen:** `derive_rules.py:90,103` gruppiert nach `beste_moeglich`, zählt aber jedes `art == 'play'` als Annahme, unabhängig von den tatsächlich erzielten Punkten. In den reproduzierten 150 Deals wurde **38-mal eine schwächere Kombination als die beste vorhandene** gespielt.

Konkreter protokollierter Fall: Feld `2B,3R,4B,5R,6R`, fünf Restkarten. Beste Kombination: gemischte 4–5–6 für 40; tatsächlich gespielt: eine gemischte 2–3–4 für 20. Dieser Zug wird als „40 genommen“ gezählt.

Die Tabelle misst also `P(irgendeine Kombination spielen | beste vorhandene hat p Punkte)`. Als solche ist sie korrekt; als Annahmequote der p-Punkte-Kombination in `ERGEBNISSE.md:51–56` ist sie irreführend.

### 3.6 Weitere konkret falsche Interpretationen der Messdaten

- **`ERGEBNISSE.md:58–60`:** 40 Punkte sind nicht ausschließlich die gemischte 4–5–6; auch der Drilling **3,3,3** gibt 40. Aus 23 Spielentscheidungen gegenüber 34 Wegwürfen in diesem Bucket folgt außerdem kein Nachweis „kein Rauschen, sondern Struktur“. Der ungefähre Standardfehler der Quote 23/57 wäre schon unter unabhängigen Beobachtungen rund 6,5 Prozentpunkte; Züge derselben Partie sind zusätzlich abhängig.
- **`ERGEBNISSE.md:62–63`:** „Quer durch alle Werte“ steigende Annahme bei höchstens fünf Restkarten ist falsch. Die reproduzierte Ausgabe zeigt für 30 Punkte **62,9 %** bei mindestens zwölf Restkarten gegenüber **56,0 %** bei höchstens fünf. Für 40 Punkte steigt die Quote ebenfalls nicht monoton: **34,5 %, 58,3 %, 37,5 %** in den drei Deckgrößen-Buckets. Bei wirklich leerem Deck wird die beste vorhandene Kombination genommen; bei fünf Restkarten folgt das weder aus dem Code noch aus den Zahlen.
- **`ERGEBNISSE.md:49`:** Acht Kombinationen sind kein Beleg für zu viel Billiges. Die unter B2 ausgeführte 560-Punkte-Partie besteht gerade aus acht Kombinationen. Die geringere durchschnittliche Kombinationszahl guter Strategien ist eine Beobachtung typischer Deals, keine allgemeine Regel.

**Kein gefundener Regel- oder Übergangsfehler in `engine.py` oder `combos.py` auf gültigen M1-Eingaben.** Zusätzlich zum vollständigen Kombinationenvergleich habe ich Engine und schnellen Simulator auf 300 identischen Decks jeweils mit gieriger und Netto-Strategie verglichen: **600 vollständige Spiele ohne Score-Abweichung**, mit Prüfung der tatsächlich gespielten Kombinationen. Heuristische Entscheidungen und die Endspiel-Abkürzung von `smart_action` sind keine Fehler allein deshalb, weil sie nicht immer optimal sind.

## 4. Bessere Ansätze und praktische Exaktheit

### Exakte stochastische Endspiele statt hellsichtiger Fortsetzungen

Für gleichverteilte Restreihenfolgen lässt sich direkt rechnen. Sei `F` das Feld, `D` die Restmenge, eine Aktion entferne `A` und bringe `p(A)` Punkte. Setze `F' = F\A` und `k = min(5−|F'|, |D|)`. Dann

```
V(F,D) = max_A [p(A) +
    Σ_{T⊆D, |T|=k} V(F'∪T, D\T) / C(|D|,k)]
```

Bei leerem Deck ist `V(F,∅)` die beste vorhandene Kombination oder null. Die Reihenfolge innerhalb eines Nachziehpakets ist irrelevant, weil das Modell erst nach dem Auffüllen eine Entscheidung zulässt. Deshalb genügen Teilmengen statt aller Permutationen.

**Ausgeführter exakter Prototyp:** Mit memoisierten `(F,D)`-Masken und `fractions.Fraction`, also ohne Monte-Carlo- oder Rundungsfehler, ergab sich für

```
F = [1,10,15,18,0]
D = [9,19,16,14,8,5,20,23]
```

der optimale weitere Erwartungswert **5539/42 ≈ 131,880952**. Die Rechnung besuchte **47 906 Zustände** und dauerte hier etwa **1,19 Sekunden**. Es wurden sämtliche legalen ersten Aktionen und deren nicht hellsichtige Fortsetzungen berücksichtigt.

Für eine konkrete Stellung mit `m = 5+r` noch verfügbaren Karten gibt `C(m,5)·2^(m−5)` eine grobe Obergrenze der Zustände mit vollem Feld: bei acht Restkarten **329 472**, bei zehn Restkarten **3 075 072**, jeweils zuzüglich kleinerer Endfelder. Das ist erheblich kleiner als das universelle 24-Karten-MDP. Eine exakte Endspielstrategie ist somit praktisch möglich; die Beispielzeit ist keine Worst-Case-Garantie für alle Stellungen.

### Gesamtlösung und überprüfbare Schranken

Für eine vollständige optimale Startstrategie wären eine kompakte Implementierung, gemeinsame Farbumbenennung von Feld und Restdeck, Schichtung nach verbleibender Kartenanzahl und effiziente Erwartungswertbildung naheliegend. Wertumkehr ist keine kostenlose weitere Symmetrie, weil sie die Punktzahlen verändert. Karten, die an keiner Kombination der gesamten noch verfügbaren Menge beteiligt sind, bleiben dauerhaft nutzlos; ihre Identitäten lassen sich gegebenenfalls durch Anzahlen ersetzen, ihre belegten Feldplätze und ihr Einfluss auf Nachziehwahrscheinlichkeiten aber nicht einfach streichen.

Eine zusätzliche Möglichkeit ist Suche mit zertifizierten Unter- und Obergrenzen: Werte ausführbarer Strategien als Untergrenzen, freie Packungswerte beziehungsweise exakt gemittelte hellsichtige Werte als Obergrenzen. Eine Aktion darf nur dann sicher entfallen, wenn ihre Obergrenze unter der Untergrenze einer anderen liegt. **Stichprobenmittel allein sind keine solchen sicheren Grenzen.** Wie viele Zustände damit tatsächlich entfallen, müsste gemessen werden; ein praktikabler vollständiger Start-Solver folgt daraus noch nicht.

Für Gold statt Punkte lautet der Endnutzen `1[Score ≥ 400]`; der Zustand muss die verbleibende Punkteschwelle aufnehmen. Für erwarteten Truhenwert werden die drei Belohnungen entsprechend gewichtet. Diese Ziele können andere Aktionen als die vorhandenen Score-Heuristiken bevorzugen.

Eine sofort tragfähige Weiterentwicklung wäre daher: exakt gelöste Endspiele, davor eine getestete Heuristik, und ein separater Testsatz mit gepaarten Score-Differenzen und Unsicherheitsintervallen. Das ergibt eine bessere überprüfbare Strategie, aber noch keinen Beweis globaler Optimalität.

## 5. Fazit in drei Sätzen

Unter den ausdrücklich zu validierenden Deck- und Ablaufannahmen sind die 170 Kombinationen, das Maximum von 560 Punkten, die Acht-Kombinationen-Schranke und die hellsichtige DP mit eigenem Cache korrekt, und die veröffentlichten Hauptmesswerte lassen sich reproduzieren. Die Analyse ist als Modellbenchmark tragfähig, enthält aber einen Cache-Schnittstellenfehler, einen Medianfehler und mehrere belegbar falsche Auswertungsinterpretationen; insbesondere sind weder das Intervall 318–376 für den wahren Optimalwert noch eine generell optimale spielbare Strategie bewiesen. Exakte stochastische Endspiele sind bereits praktikabel, während die Eindeutigkeit des realen Decks, die übrigen Spielannahmen und die praktische Berechenbarkeit einer vollständigen optimalen Startstrategie offenbleiben.
