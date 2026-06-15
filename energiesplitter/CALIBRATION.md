# Energiesplitter — Kalibrierung & Asset-Extraktion (Phase 1)

Gemessen 2026-06-15 code-gestuetzt (Python + OpenCV) aus den ECHTEN
Screenshots. Alle Pixel-Werte gelten im normierten **800x600-Client**.
Verbindliche Konstanten: `energiesplitter/calibration.py`.

> **Großumbau 2026-06-16:** Yang/Gold-Subsystem KOMPLETT ENTFERNT — der
> Yang-Reader, die Yang-/Gold-Ziffern-Templates (`yang_digits/`, `gold_digits/`)
> und `ROI_YANG`/`ROI_GOLD` sind gestrichen. Sicherung läuft über `max_actions`
>
> - `consecutive_unverified_stop` + Erkennung-vor-Aktion + Re-Read-Verifikation.
>   Grid-, Glow-, Item-, NPC- und Shop-Anker-Kalibrierung bleiben unverändert.

## Mess-Grundlage

| Bild                    | Pfad                                                                      | Rohgroesse | Inhalt                     |
| ----------------------- | ------------------------------------------------------------------------- | ---------- | -------------------------- |
| Alchemist-Inventar      | `tests/fixtures/energiesplitter/inventar_alchemist.png` (yKo7rQ4BUz)      | 802x632    | Szene + offenes Inventar   |
| Waffenhaendler-Inventar | `tests/fixtures/energiesplitter/inventar_waffenhaendler.png` (VjWdxCoJqJ) | 802x632    | Szene + offenes Inventar   |
| Hammer-Shop             | `energiesplitter/Einkauf Hammer/Shopgeoeffnetalchemist.png`               | 802x632    | Alchemist-Laden offen      |
| Dolch-Shop              | `energiesplitter/Einkauf Dolche/Shopgeoeffnet.png`                        | 802x632    | Waffenhaendler-Laden offen |

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

## 2) Item-Templates `templates/`

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

## 3) Shop-Anker (Erkennung vor Aktion)

- **Hammer-Shop (Alchemist):** `SHOP_HAMMER_ANCHOR = (425, 121)` = die Zell-Mitte
  des **200er-Hammer-Stacks** (per `hammer.png`-NCC lokalisiert). Aktion 1 kauft
  IMMER diesen 200er-Slot, `stack_count`-mal. `SHOP_BUY_BUTTON` ~ (425, 273)
  (grob, "Kaufen"). In diesem Screenshot ist nur der 200er sichtbar; 1er-/50er-
  Stacks werden NICHT mehr gebraucht (greedy Stack-Plan entfernt).
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

## 4) NPC-Erkennung `templates/npc/`

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
- Hammer/Dolch-Templates + Glow — konfusionsfrei an 11 Slot-Instanzen.
- NPC-Wortbilder Alchemist/Waffenhaendler — self 1.0, cross <= 0.34.
- Hammer-Shop-Anker (200er) `SHOP_HAMMER_ANCHOR=(425,121)` — NCC-lokalisiert.
- **Dolch-Shop-Anker (556,59)** — NCC 1.00, einziger Treffer; `shop_dolch.png`.

**Geschlossene Luecken (2026-06-15):**

1. **Dolch-Shop-Slot** — `SHOP_DAGGER_ANCHOR = (556, 59)` + `shop_dolch.png`.

**Verbleibende Luecken (ehrlich):**

2. `SHOP_BUY_BUTTON` nur grob (kein Knopf-Template).
3. ALLES an FIXTURES gemessen -> Live-Re-Verifikation (P0.6) Pflicht vor scharf.
   Sicherung im scharfen Lauf: `max_actions` + `consecutive_unverified_stop` +
   Re-Read-Verifikation jeder Aktion (kein Yang/Gold-Backstop mehr).

> Sicherheits-Invariante bleibt oberste Prioritaet: gekauft/gedraggt wird NUR
> bei live per Template verifiziertem Item (Quelle=Hammer, Ziel=Dolch). Jede
> Abweichung/fehlender Anker -> sauberer Stopp, nie Blind-Aktion.
