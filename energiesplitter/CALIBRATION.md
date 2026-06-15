# Energiesplitter — Kalibrierung & Asset-Extraktion (Phase 1)

Gemessen 2026-06-15 code-gestuetzt (Python + OpenCV) aus den ECHTEN
Screenshots. Alle Pixel-Werte gelten im normierten **800x600-Client**.
Verbindliche Konstanten: `energiesplitter/calibration.py`.

## Mess-Grundlage

| Bild                    | Pfad                                                                      | Rohgroesse | Inhalt                                  |
| ----------------------- | ------------------------------------------------------------------------- | ---------- | --------------------------------------- |
| Alchemist-Inventar      | `tests/fixtures/energiesplitter/inventar_alchemist.png` (yKo7rQ4BUz)      | 802x632    | Szene + offenes Inventar + Yang 207.295 |
| Waffenhaendler-Inventar | `tests/fixtures/energiesplitter/inventar_waffenhaendler.png` (VjWdxCoJqJ) | 802x632    | Szene + offenes Inventar + Yang 192.295 |
| Hammer-Shop             | `energiesplitter/Einkauf Hammer/Shopgeoeffnetalchemist.png`               | 802x632    | Alchemist-Laden offen                   |
| Dolch-Shop              | `energiesplitter/Einkauf Dolche/Shopgeoeffnet.png`                        | 802x632    | Waffenhaendler-Laden offen              |

Kopien der beiden Inventar-Bilder liegen zusaetzlich unter
`energiesplitter/Inventar+Verarbeitung/`.

**Normierung:** Fixtures sind 802x632 (1px-Rahmen + 30px-Titelleiste). Client =
`[31:631, 1:801]` -> 800x600. Bestaetigt das bestehende
`geometry.CLIENT_X0=1 / CLIENT_Y0=31`. Live croppt `WindowCapture` den Rahmen
bereits weg; `geometry.to_client` normiert defensiv beides.

## 1) Inventar-Raster (Seite I, 5 Spalten)

| Groesse                 | Wert       | Wie gemessen                                                  |
| ----------------------- | ---------- | ------------------------------------------------------------- |
| Spalten                 | 5          | sichtbar + slot-Verifikation                                  |
| Pitch x / y             | 32 / 32 px | Zeilen-Helligkeits-Autokorrelation (Peak @ Lag 32)            |
| Slot-1-Mittelpunkt      | (648, 258) | erste Potion (Stack "18"), pixelgenau zentriert               |
| Slot-1 obere-linke Ecke | (632, 242) | Gridlinien-Helligkeit (Tab-Unterkante y239, Gap, Zeile1 y242) |

`slot = (zeile-1)*5 + spalte` (1-basiert). `slot_center(s)`:
`x = 648 + ((s-1)%5)*32`, `y = 258 + ((s-1)//5)*32`.

### Verifikation gegen User-Grundwahrheit (de)

Per Crop + Hammer/Dolch-Template-NCC an den errechneten Mittelpunkten:

| Slot   | Grundwahrheit                         | Gemessen                   | NCC (Hammer / Dolch) |
| ------ | ------------------------------------- | -------------------------- | -------------------- |
| 18     | 2 Haemmer (Stack)                     | HAMMER, Stack "2" sichtbar | 1.00 / 0.39          |
| 19, 20 | Dolch                                 | DAGGER                     | 0.39 / 1.00          |
| 23, 24 | Dolch                                 | DAGGER                     | 0.39 / 1.00          |
| 25     | Hammer                                | HAMMER (leuchtend)         | 0.82 / 0.13          |
| 28, 29 | Hammer (leuchtend)                    | HAMMER (leuchtend)         | 0.82 / 0.13          |
| 30     | leuchtender Dolch (nur Waffenh.-Bild) | DAGGER (leuchtend)         | 0.24 / 0.79          |

ALLE 8 verifizierten Slots klassifizieren korrekt; Gewinner-NCC >= 0.79,
Verlierer <= 0.39 -> **konfusionsfrei** bei Schwelle `NCC_ITEM=0.70`. Slot 21
(Schwert, kein Hammer/Dolch) liegt bei 0.18/0.46 -> wird korrekt verworfen.

> Abweichung zur GT-Notiz: Im Alchemist-Bild ist Slot 25 bereits leuchtend (GT
> beschrieb ihn als nicht-leuchtend) und Slot 30 leer; im Waffenhaendler-Bild
> ist Slot 30 der leuchtende Dolch. Das ist ein Zustands-Unterschied der zwei
> Screenshots, KEINE Geometrie-Abweichung — die Slot-Typen (Hammer/Dolch)
> stimmen exakt. Saubere Beleg-Crops: siehe `rows456`-Analyse im Mess-Log.

## 2) Yang-Reader (RECHTE Zahl = rohes Yang)

- Waehrung = **Yang**. Unten rechts; die **RECHTE** Zahl ist rohes Yang
  (deutsch, `.` = Tausendertrenner): `207.295` / `192.295`. Die LINKE Zahl =
  Won (1 Won = 100 Mio Yang) -> **ignoriert**.
- **ROI_YANG = (747, 552, 44, 9)** (x,y,w,h). Ziffernband y552..558
  (Glyph-Hoehe **7px**, identisch zu `gold_reader.DIGIT_BAND_H`), rechtsbuendig
  bis ~x788. Beide Bilder + beide Shop-Zustaende gleiche Stelle. Deckt sich mit
  der bestehenden `geometry.ROI_GOLD`.

### Ziffern-Templates `templates/yang_digits/`

Aus 207.295 + 192.295 ableitbar: **0, 1, 2, 5, 7, 9** + `.` (dot). Dekodier-Test
(Luecken-Segmentierung + NCC, normiert) liest beide Zahlen exakt zurueck
(`207.295`, `192.295`).

**GESCHLOSSEN (2026-06-15): 3, 4, 6, 8 nachgeliefert.** Aus neuen Beleg-Bildern
extrahiert (Crop an `ROI_YANG`, weisse Glyph-Maske, Hoehe 7, gespeichert als
`<glyph>__waf.png`):

| Ziffer | Quelle (Fixture)  | Lese-Beleg                                           |
| ------ | ----------------- | ---------------------------------------------------- |
| `3`    | `yang_131895.png` | 2. Stelle (auch `gold_digits/` hatte 3)              |
| `6`    | `yang_161495.png` | 2. Stelle                                            |
| `8`    | `yang_129895.png` | liest exakt `129895`                                 |
| `4`    | `yang_161495.png` | 4-9-Paar (beruehrend, template-getrieben gesplittet) |

Der Ziffernsatz ist jetzt **vollstaendig** (0..9 + dot) ->
`gold_reader.templates_complete()` ist **True** und `detect.assets_ready` meldet
`yang_digits` NICHT mehr als fehlend (das Phase-0-Gate KANN gruen werden).
Verifiziert: der Reader liest **207.295 / 192.295 / 161.495 / 129.895 / 312.295**
exakt zurueck.

**Ehrlichkeit zur Beleg-Lieferung:** Das Bild `yang_131895.png` rendert am echten
Pixel `131.495` (die 4. Stelle ist ein `4`, byte-identisch zur 4-9-Gruppe in
`yang_161495.png`), NICHT `131.895` wie in der Beleg-Notiz angegeben. Der Reader
liest korrekt, was gerendert ist; der saubere `8`-Beleg kommt aus
`yang_129895.png`. (Beruehrende Ziffernpaare wie 4-9 werden template-getrieben am
besten Schnitt geteilt; jede Teil-Ziffer muss EINZELN ueber `CONF_MIN` matchen --
keine Aufweichung der "nie raten"-Invariante.)

## 3) Item-Templates `templates/`

| Datei        | Quelle                                     | Groesse | Zweck            |
| ------------ | ------------------------------------------ | ------- | ---------------- |
| `hammer.png` | Slot 18 (nicht-leuchtend, ohne Stack-Zahl) | 22x22   | Hammer-Erkennung |
| `dolch.png`  | Slot 19 (nicht-leuchtend, sauber)          | 24x24   | Dolch-Erkennung  |

NCC-tolerant gegen Glow (leuchtende Slots matchen ~0.80). Empfohlene Schwelle
**0.70** (deckt leuchtend + nicht-leuchtend, trennt Fremd-Items klar ab).

### Glow ("frisch gekauft, noch nicht gehovert")

Metrik = Glow-Anteil im 4px-Slot-Randring (Pixel mit `min(B,G,R) > 80`):

| Zustand         | Glow-Anteil             | Rand min-Kanal-Mittel |
| --------------- | ----------------------- | --------------------- |
| nicht-leuchtend | <= 0.115 (meist < 0.06) | ~11..21               |
| leuchtend       | >= 0.65                 | ~141                  |

**GLOW_FRACTION_THR = 0.35** (mittig in der Luecke 0.115..0.65) ->
provably konfusionsfrei. `GLOW_REF_BGR=(203,177,176)` = Projekt-`GLOW_REF`
(RGB 176,177,203) als BGR; die robustere Entscheidung ist der Glow-Anteil.

## 4) Shop-Anker (Erkennung vor Aktion)

- **Hammer-Shop (Alchemist):** Energiesplitter-Hammer (200er-Stack) per
  `hammer.png`-NCC lokalisiert bei Zell-Mitte **(425, 121)**. `SHOP_BUY_BUTTON`
  ~ (425, 273) (grob, "Kaufen"). Stack-Groessen lt. Spec 1/50/200 — in diesem
  Screenshot nur der **200er** sichtbar.
  **LUECKE:** 1er-/50er-Stack-Positionen (separater Shop-Screenshot noetig).
- **Dolch-Shop (Waffenhaendler): GESCHLOSSEN (2026-06-15).** Der vom User rot
  markierte Dolch-Slot liegt in der **oberen Shop-Reihe**. Im SAUBEREN,
  unannotierten Screenshot (`Einkauf Dolche/Shopgeoeffnet.png`) ist der Dolch per
  `dolch.png`-NCC **eindeutig** bei Zell-Mitte **(556, 59)** lokalisiert: NCC
  **1.00** und der EINZIGE Treffer >= 0.6 im gesamten Client; das Hammer-Template
  trifft diesen Slot NICHT (konfusionsfrei). `SHOP_DAGGER_ANCHOR = (556, 59)`.
  Sauberes Shop-Template **`templates/shop_dolch.png`** (24×24, aus der
  unannotierten Vorlage gecroppt, OHNE rote Markierung). `find_shop_item('dolch')`
  / `_locate_shop_item('dolch')` finden den Slot jetzt am Anker (anker-zentrierte
  Such-ROI via `detect.shop_item_roi`). Erkennung vor Aktion bleibt gewahrt.

## 5) NPC-Erkennung `templates/npc/`

| Datei                | Quelle                             | Fundort (Client) | Selbst-NCC |
| -------------------- | ---------------------------------- | ---------------- | ---------- |
| `alchemist.png`      | Alchemist-Bild, gruenes Label      | (339, 228)       | 1.00       |
| `waffenhaendler.png` | Waffenhaendler-Bild, gruenes Label | (396, 211)       | 1.00       |

Cross-NCC (Alchemist-Tmpl im Waffenh.-Bild bzw. umgekehrt) <= 0.34 ->
diskriminiert klar bei `NCC_WORD=0.80`.

- **Such-Region** `ROI_NPC_SEARCH = (150,100,470,320)` (= `geometry.ROI_SCENE`).
- **Detektions-Hinweise:**
  - _Gelber Abwaerts-Pfeil_ ueber dem anvisierten NPC (gemessen gesaettigtes
    Gelb `R>180,G>160,B<120` im oberen Szenen-Drittel) = Ziel-Hinweis.
  - _Rote Auswahl-Markierung_ an den NPC-Fuessen erscheint NACH Rechtsklick.
  - **Ansprech-Reihenfolge:** ERST Rechtsklick (rote Markierung bestaetigt das
    Ziel) DANN Linksklick. Drag-Primitiv wiederverwenden: `inventory_discard.drag`.
  - Gruener Name-NCC ist der **primaere** Anker; Pfeil/rote Markierung dienen
    als Bestaetigung, nicht als alleiniger Klick-Punkt.

## Verarbeiten (Hammer -> Dolch)

KEIN Bestaetigungsfenster. Verifikation ueber **Re-Read**: nach dem Drag
Dolch-Slot LEER + Hammer-Stack dekrementiert (per Template/Stack-OCR). Energie-
splitter-Ergebnis muss NICHT erkannt/gezaehlt werden.

## Konfidenz & Luecken

**Hohe Konfidenz:**

- Grid-Geometrie (Pitch 32, Ursprung (648,258)) — an 8 Slots + Autokorrelation
  verifiziert, beide Bilder identisch.
- Yang-ROI + **vollstaendiger** Ziffernsatz 0..9 + dot — 207.295/192.295/161.495/
  129.895/312.295 exakt dekodiert (3/4/6/8 am 2026-06-15 nachgeliefert).
- Hammer/Dolch-Templates + Glow — konfusionsfrei an 11 Slot-Instanzen.
- NPC-Wortbilder Alchemist/Waffenhaendler — self 1.0, cross <= 0.34.
- Hammer-Shop-Anker (200er) — NCC-lokalisiert.
- **Dolch-Shop-Anker (556,59)** — NCC 1.00, einziger Treffer; `shop_dolch.png`.

**Geschlossene Luecken (2026-06-15):**

1. Yang-Ziffern **3, 4, 6, 8** — extrahiert; Ziffernsatz vollstaendig,
   `templates_complete()` True. (Hinweis: `yang_131895.png` rendert real
   `131.495`; sauberer `8`-Beleg aus `yang_129895.png`.)
2. **Dolch-Shop-Slot** — `SHOP_DAGGER_ANCHOR = (556, 59)` + `shop_dolch.png`.

**Verbleibende Luecken (ehrlich):**

3. Hammer-Stacks **1 / 50** im Shop nicht sichtbar (nur 200er).
4. `SHOP_BUY_BUTTON` nur grob (kein Knopf-Template).
5. ALLES an FIXTURES gemessen -> Live-Re-Verifikation (P0.6) Pflicht vor scharf
   (bei `yang_check=TRUE`; `yang_check=FALSE` entfernt die live Gold-Wand —
   RISIKO, dann begrenzen nur `max_actions` + fester `max_gold_spend`-Deckel).

> Sicherheits-Invariante bleibt oberste Prioritaet: gekauft/gedraggt wird NUR
> bei live per Template verifiziertem Item (Quelle=Hammer, Ziel=Dolch). Jede
> Abweichung/fehlender Anker -> sauberer Stopp, nie Blind-Aktion.
