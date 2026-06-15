# Energiesplitter — Implementierungsreifes Design (Synthese-Lead)

> Stand 2026-06-16. Synthese aus Bild-Grundwahrheit (26 Referenzbilder, 4 Gruppen),
> Design-Entwurf und 3 Red-Team-Verdikten. **Großumbau 2026-06-16: Yang/Gold-
> Subsystem KOMPLETT ENTFERNT** (kein Preis, kein Kontostand, kein Gold-Reader,
> keine Yang-Ziffern-Templates, kein ROI/Rechner). Die Sicherung läuft nur noch
> über `max_actions` + `consecutive_unverified_stop` + Erkennung-vor-Aktion +
> Re-Read-Verifikation. Architektur und Sicherheitsdenken bleiben tragfähig; die
> verbleibenden Subsysteme ohne Bild-Ground-Truth sind Item-Templates und
> Verarbeitungs-Feedback. Dieses Dokument macht die Blocker explizit und beschreibt
> den verantwortbaren Bauplan **nach** ihrer Behebung.
>
> **Verbindlich vorrangig:** `energiesplitter/REQUIREMENTS_ADDENDUM.md` (User).

---

## 0. Phase-0-GATE (HARTER BLOCKER — vor jeder Item-/Kauf-Logik)

`armed = detect.assets_ready(mode)` (Item-/NPC-Templates + Shop-Anker, OHNE
Yang-Ziffern) **AND** `geometry.is_calibrated(wincap)` (Client ~800×600) **AND**
`detect.grid_present()` (Inventar-Raster auflösbar, Slot1→Pixel; ersetzt das
frühere `_grid_present`). Es gibt **keine** Gold-/Content-Calibration-Prüfung mehr.

Verifiziert gegen den echten Code (nicht behauptet):

- `grep -riE "tesseract|pytesseract|easyocr"` über `*.py` → **0 Treffer.** Einziger
  „Text"-Leser mit OCR-Bezug ist `fishing_chat.py` = **fester Pixel-Glyphen-Atlas**
  (kein freies OCR; Docstring sagt explizit „KEIN Tesseract").
- `inventory_icons/` enthält **kein** Hammer/Dolch/Energiesplitter-Icon (44 Dateien,
  alle Fische/Färbemittel/Keys/Boxen). `inventory/types.py`: Nicht-DB-Item →
  `STATE_UNKNOWN`; `find()`/`stack_total()` filtern auf `STATE_ITEM` →
  **`stack_total('Hammer')` ist strukturell IMMER 0.**
- `inventory_discard.drag()` existiert mit `mouseUp` im `finally` (Zeile 347–349) →
  **das ist das wiederzuverwendende Drag-Primitiv.**

**Das Modul DARF NICHT klicken/kaufen/draggen, solange nicht vorliegt:**

| #    | Phase-0-Artefakt                                                                                                                                                                                                                                                  | Wofür                                                                                                          | Status                             |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| P0.1 | Live-Crops: Hammer-, Dolch-, Energiesplitter-Icon **im Inventar**                                                                                                                                                                                                 | `inventory_icons/` + itemdb-Templates; ohne sie kein Bestand, keine Kauf-Verifikation, kein sicheres Drag-Ziel | **FEHLT**                          |
| P0.2 | Wortbild-Templates (de+en) aller zu klickenden Dialogzeilen + NPC-Namen + Header (`Laden öffnen`, `Eine neue Technik!`, `Energiesplitter extrahieren`, `Ein neuer Duft`, `Weiter`, `OK`, `Alchemist`, `Waffenhändler`, `Laden`, `Inventar`, `Ausrüstungsfenster`) | Text-Diskriminierung per **NCC**, da kein freies OCR existiert                                                 | **FEHLT**                          |
| P0.4 | Screenshot des **Waffenhändler-Shops geöffnet** (Gruppe „Waffenschmied" hat keinen)                                                                                                                                                                               | shop_open/Dolch-Slot kalibrieren                                                                               | nur 1× aus Gruppe „Einkauf Dolche" |
| P0.5 | Screenshot des **Verarbeitungs-Vorgangs** (Drag Hammer-Stack→Dolch, Splitter-Ergebnis)                                                                                                                                                                            | `process_drag`/Result-Reader                                                                                   | **FEHLT komplett**                 |
| P0.6 | Re-Kalibrierung aller Geometrie am echten **800×600-Client** (Bilder sind 802×632 mit OS-Rahmen)                                                                                                                                                                  | jede Pixel-Konstante                                                                                           | offen                              |

Solange P0.1/P0.2/P0.5 fehlen, ist nur Read-only-Detektor-Kalibrierung
zulässig — **kein scharfer Kauf-/Verarbeitungs-Lauf.**

---

## 1. Erfolgskriterien-Rubric (R1–R12)

Erweitert um die Red-Team-Pflichten. „Erfüllt" heißt: gegen Fixtures grün **und**
(für Live-Schritte) am echten Client verifiziert.

- **R1 Reiter & zwei Aktionen:** `'energiesplitter'` in `RAIL_ORDER`/`RAIL_GLYPHS`;
  `_build_energiesplitter_view` rendert ZWEI getrennte Start/Stop-Sektionen
  (Aktion 1 „Hammer kaufen" @ Alchemist, Aktion 2 „Dolche kaufen + verarbeiten"
  @ Waffenhändler), je eigener Settings-Block + Status/Log-Panel.
- **R2 Bild-Treue (ehrlich):** Dialog-Diskriminierung via **NCC-Wortbild-Templates**
  (NICHT „OCR"): LOCKED = Zeile `Eine neue Technik!` vorhanden; UNLOCKED = Zeile
  `Energiesplitter extrahieren` vorhanden; `Laden öffnen` existiert in BEIDEN
  Zuständen → für reinen Hammerkauf ausreichend.
- **R3 Kauf-Schutz (hart, ergebnisgebunden):** Jeder Kauf wird per **Re-Read**
  verifiziert (Hammer-/Dolch-Bestand stieg via Template-Diff); nicht verifiziert →
  Retry, dann Stop. Backstops sind OCR-unabhängig: `max_actions` (Aktions-Obergrenze)
  - `consecutive_unverified_stop` (N nicht-verifizierte Aktionen in Folge → Stop).
    Kein Yang-/Budget-Check mehr.
- **R4 NPC-Robustheit:** NPC lagenunabhängig per Grün-Maske + NCC-Wortbild
  (`Alchemist` / `Waffenhändler` — NICHT „Waffenschmied"); Selektion = **erst
  Rechtsklick → roten Ring formbasiert bestätigen → dann Linksklick**; kein Ring →
  Retry/Vogelperspektive (**Keypress, nicht Rechtsklick-Drag**), nie blind Linksklick.
- **R5 Sequenzielle Verarbeitung (Dolche pro Runde, einzeln nacheinander):**
  Aktion 2 kauft pro Runde `daggers_per_round` Dolche (Rechtsklick je Dolch,
  template-verifiziert), verarbeitet sie dann **EINZELN NACHEINANDER**: je Dolch
  den Hammer-STACK-Slot (Template=Hammer) via `inventory_discard.drag` auf den
  Dolch-Slot (Template=Dolch) ziehen. **EIN Drag verbraucht 1 Hammer + 1 Dolch
  (NICHT den ganzen Stack).** Dekrement NUR nach positiver Re-Read-Verifikation
  (Dolch-Slot leer UND Hammer dekrementiert). Kein blindes logisches `-1`, KEIN
  Bestätigungsfenster.
- **R6 Smartes persistentes Inventar:** Layout-Sidecar + Re-Validierung; freie
  Slots/Hammer-Stacks **glow-aware** (GLOW_REF=(176,177,203) verifiziert) mit
  Hover-Clear; Item-Identität NUR via P0.1-Templates; nie auf Vorrat über Bedarf.
- **R7 Tempo/Render-Disziplin:** `pydirectinput.PAUSE` pro Operation (Maus 0.05,
  Tastatur 0.1); Drag fährt intern mit PAUSE=0 (wie `discard.drag`); nach jeder
  erkennungsrelevanten Aktion event-getrieben warten bis Bildzustand STABIL;
  **Timing-Jitter ±15 % auf ALLE Intervalle** (Anti-Cheat, Red-Team).
- **R8 Headless-testbar:** alle 26 Bilder als Fixtures; Detektoren + Entscheidungs-
  logik laufen mit gestubbtem win32/pydirectinput grün; `test_i18n_parity` für neue
  `t()`-Keys; `test_version` bei Release gebumpt.
- **R9 Single-Authority:** `hammer XOR dagger XOR fishing XOR puzzle`; zweiter Start
  bei laufendem Bot → **verweigert** (kein paralleler Worker); F6 bricht via
  `abort_fn`-Seam ab (nicht Polling — `stop_signal`-Tick konsumiert zu schnell).
- **R10 Endlos-Schutz (ergebnisgebunden):** `max_actions` als das ~1.2-fache der
  Sollzahl (NICHT 5000); zusätzlich `consecutive_unverified ≥ 3 → Stop`; jede
  Schleife hat eine Abbruchbedingung, die am beobachtbaren Ergebnis hängt
  (Kauf-Re-Read + Verarbeitungs-Fortschritt), nicht an einer logischen Zählung.
- **R11 Drag-Sicherheit:** Drag NUR von einem als **Hammer** klassifizierten
  Quell-Slot auf einen als **Dolch** klassifizierten Ziel-Slot (beide P0.1-Templates,
  positiv bestätigt). Bei Unklarheit → Stop, kein Drag (sonst Equipment-Verlust).
  `mouseUp` garantiert im `finally`; abort NICHT mitten im Drag, erst danach prüfen.
- **R12 Ehrliche Methode:** Im Code & Doku steht „NCC-Wortbild-Template pro bekanntem
  String", nirgendwo „OCR", solange kein OCR-Dependency eingebunden ist.

---

## 2. Finale Dateistruktur + Andockpunkte

Neue Dateien:

```
energiesplitter/__init__.py        Paket-Init; exportiert HammerBot, DaggerBot,
                                   public detect/geometry. Soft-Imports für
                                   cv2/pydirectinput → headless importierbar.
energiesplitter/geometry.py        ALLE Pixelkonstanten relativ zum 800×600-Client
                                   + WindowCapture.offset_x/y. Anker-RELATIV (Header-
                                   NCC) statt absolut. ALLES als KALIBRIER-BAR markiert.
energiesplitter/detect.py          reine Vision (numpy/cv2, kein IO):
                                     assets_ready(mode) Phase-0-Asset-Check (OHNE Yang)
                                     grid_present() Inventar-Raster auflösbar (Slot1->Pixel)
                                     find_npc_name(bgr, word_template) Grün+NCC
                                     selection_ring_present(bgr, near, y_min=240) formbasiert
                                     dialog_state(bgr) -> 'locked'|'unlocked'|None (NCC-Marker)
                                     shop_open(bgr) 'Laden'-Header-NCC
                                     panel_is_bag(bgr) 'Inventar' vs 'Ausrüstungsfenster'
                                     find_shop_item(bgr, item_template)
                                     read_shop_stack(slot_bgr) Digit-Reader (Shop-Geometrie!)
                                     read_splitter_growth(before, after) Diff
energiesplitter/bot.py             HammerBot + DaggerBot, seher_runner-Stil:
                                   set_to_begin(values), botting-Flag, runHack()
                                   (ein Tick = Erkennung→Entscheidung→Aktion),
                                   abort_fn=stop_signal. Gemeinsame Helfer:
                                   approach_npc, open_shop_via_dialog, buy_rightclick,
                                   verify_hammer_purchase, verify_process,
                                   _verify_bag_growth.
energiesplitter/templates/         NCC-Templates (aus P0.2-Crops):
                                   de/ + en/ je Wortbild; laden_header, inventar_header,
                                   ausruestung_header, dialog-Buttons.
                                   HINWEIS: Item-Icons leben in inventory_icons/ (P0.1).
interface/energiesplitter_runner.py  Live-Runner analog seher_runner.py:
                                     run_hammer_session(cfg, abort_fn),
                                     run_dagger_session(cfg, abort_fn);
                                     _click_until/_wait_for/_click_screen/
                                     _save_debug_frame/_log_diagnosis;
                                     bindet run_inventory_scan + Layout-Sidecar;
                                     JSONL energiesplitter_results.jsonl in %APPDATA%.
interface/app/views_energiesplitter.py  EnergiesplitterViewMixin:
                                     _build_energiesplitter_view; zwei Sektionen
                                     (Hammer/Dolch) je Start/Stop + Settings +
                                     Status/Log; mirror views_seher.
tests/test_energiesplitter_detect.py   Detektoren gegen 26 Fixtures.
tests/test_energiesplitter_flow.py     State-Machine-Logik, Verarbeitung, Stops.
tests/test_energiesplitter_config.py    defaults/validate/clamp/enum.
```

Edits an Bestand (Andockpunkte, alle verifiziert vorhanden):

| Datei                                  | Edit                                                                                                                                                                                                                                        |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run_loop.py`                          | HammerBot+DaggerBot instanziieren; `apply_energiesplitter_config`; `on_start` erzwingt **Exklusivität** (verweigert 2. Start); `tick` für Modi `energiesplitter_hammer`/`_dagger`; abort via `stop_signal.add_callback` (wie Manage v1.1.6) |
| `interface/app/_common.py`             | `RAIL_ORDER` + `'energiesplitter'`; `RAIL_GLYPHS['energiesplitter']` Glyph; `WHICH_TO_CFG` erweitern                                                                                                                                        |
| `interface/app/__init__.py`            | `EnergiesplitterViewMixin` in `App` mischen + import                                                                                                                                                                                        |
| `interface/config/defaults.py`         | `APP_MODES` + `'energiesplitter'`-Block + Ranges                                                                                                                                                                                            |
| `interface/config/validate.py`         | `energiesplitter`-Block clampen/enum                                                                                                                                                                                                        |
| `i18n_data.py`                         | neue `t()`-Keys de+en                                                                                                                                                                                                                       |
| `version.py` + `tests/test_version.py` | bei Release bumpen (Memory-Gotcha!)                                                                                                                                                                                                         |
| `Metin2FishBot.spec` + `_onefile.spec` | `energiesplitter/templates/` als Daten packen (sonst crasht EXE — analog tzdata-Gotcha)                                                                                                                                                     |

---

## 3. State-Machines

Beide im `seher_runner`-Tick-Stil (ein `runHack()` = ein kurzer, blockierender
Tick). Pflicht-Abbruchbedingungen (rot) stammen aus dem Red-Team.

### 3.1 HammerBot (Aktion 1 — „Hammer kaufen" @ Alchemist)

```
init
  set_to_begin(values): WindowCapture('METIN2'), config einfrieren
    (stack_count, energie_freischalten, max_actions, consecutive_unverified_stop)
  Fenster fehlt -> STOP 'kein Fenster'

inventory_baseline
  run_inventory_scan -> InventoryMap; freie Slots + Hammer-Stacks
    [ABBRUCH] P0.1-Hammer-Template fehlt -> STOP 'Item-Template fehlt'
  0 freie Slots UND Kauf nötig -> STOP 'kein Platz'

approach_npc
  find_npc_name(bgr, 'Alchemist')  [Grün-Maske + NCC]
  nicht gefunden nach N -> (1× Vogelperspektive KEYPRESS) -> STOP 'NPC nicht gefunden'
    [ABBRUCH] KEIN 'größter-grüner-Cluster'-Blindfallback in Stadt-Szene

select_npc
  Rechtsklick auf NPC-Punkt
  selection_ring_present(near, y_min=240, FORM-Test) ?
    JA -> open_dialog
    NEIN -> Retry(max 3)/Vogelperspektive -> STOP 'Anvisieren fehlgeschlagen'
    [ABBRUCH] NIE blind Linksklick ohne Ring (sonst läuft Char)

open_dialog
  Linksklick NPC -> _wait_for dialog_state != None (poll bis stabil)
  Timeout -> _save_debug_frame + STOP

unlock_decide
  dialog_state=='locked'  (Marker 'Eine neue Technik!') UND freischalten=ON -> unlock_story
  dialog_state=='unlocked'(Marker 'Energiesplitter extrahieren') ODER freischalten=OFF
      -> open_shop  (Hammerkauf braucht in BEIDEN Fällen nur 'Laden öffnen')

unlock_story
  klicke 'Eine neue Technik!' -> 'Weiter' -> 'Weiter' -> 'OK' (NCC-Buttons,
    _click_until bis nächster Bildzustand) -> Re-Open Dialog -> open_shop
    [ABBRUCH] Negativliste: 'Veredelung'/'Bonuswandel'/'extrahieren'/'herstellen'
      NIE klicken (verbrauchen Equipment/Splitter)

open_shop
  finde+klicke Dialogzeile 'Laden öffnen' (NCC, eindeutiger Match >=0.85)
  shop_open(bgr) ? sonst Timeout -> Snapshot + STOP
    [ABBRUCH] uneindeutige/durchscheinende Zeile -> Snapshot + STOP statt Klick

locate_hammer
  find_shop_item(bgr, hammer_icon) in Shop-Zeile 1; read_shop_stack je Slot
  kein Hammer-Icon -> STOP 'Hammer nicht im Shop' (Sortiment-Mismatch loggen)

buy_loop
  Kauft IMMER 200er-Stacks, stack_count-mal: pro Kauf-Schritt EIN 200er-Stack.
  max_actions / consecutive_unverified_stop erreicht -> STOP
  Rechtsklick 200er-Stack-Slot (Template + SHOP_HAMMER_ANCHOR = der 200er)
  verify_hammer_purchase / _verify_bag_growth: Hammer-Bestand stieg via Re-Read
    (neuer Hammer-Slot ODER bestehender Hammer-Stack +200 via Diff)
    nicht verifiziert -> max 2 Retry, danach STOP 'Kauf nicht verifiziert'
    [ABBRUCH] kein Retry-Rechtsklick bevor bewiesen, dass voriger NICHT kaufte
      (Doppelkauf-Schutz)
  gekauft += 1 (Stack); glow-aware Re-Scan freier Platz nach Stack-Kauf

check_done
  gekaufte_stacks >= stack_count -> Auto-Stop ; sonst buy_loop

stop
  Shop schließen (X) optional, Cursor parken, Bilanz loggen, botting=False, JSONL
```

### 3.2 DaggerBot (Aktion 2 — „Dolche kaufen + verarbeiten" @ Waffenhändler)

```
init
  set_to_begin: wincap, config (daggers_per_round default 1, max_actions,
    consecutive_unverified_stop, speed). Fenster fehlt -> STOP

inventory_baseline
  run_inventory_scan -> Hammer-Bestand + Slots
    [ABBRUCH] P0.1-Hammer/Dolch-Template fehlt -> STOP 'Item-Template fehlt'
              (NICHT auf stack_total==0 als 'fertig' schließen)
  Hammer==0 (template-verifiziert) -> STOP 'keine Hämmer zum Verarbeiten'

approach_npc
  find_npc_name(bgr, 'Waffenhändler')  [NICHT 'Waffenschmied']
  nicht gefunden -> Vogelperspektive KEYPRESS -> STOP

select_npc
  Rechtsklick -> selection_ring_present(FORM) ? JA weiter / NEIN Retry -> STOP
    [ABBRUCH] nie blind Linksklick

open_dialog
  Linksklick -> _wait_for Dialog. Zeilen ['Ein neuer Duft','Laden öffnen','Schließen']
    [ABBRUCH] erste Zeile 'Ein neuer Duft' NIE blind klicken

open_shop
  finde+klicke 'Laden öffnen' (NCC) -> shop_open ? sonst STOP
  panel_is_bag prüfen: rechts ist im Shop oft 'Ausrüstungsfenster', NICHT die Tasche
    [ABBRUCH] Tasche nicht offen -> open_probe toggeln bis 'Inventar'-Header bestätigt

locate_dolch
  find_shop_item(bgr, dolch_icon)  [Template, NICHT feste Koordinate]
  kein Dolch -> STOP 'Dolch nicht im Shop'

buy_round  (daggers_per_round Dolche pro Runde kaufen)
  Schleife bis keine Hämmer mehr im Inventar:
  daggers_per_round mal: Rechtsklick Dolch-Slot je Dolch (template-verifiziert)
    _verify_bag_growth: realen Lande-Slot per Inventar-Diff bestimmen
      (Glow per Hover-Clear entfernen vor Diff)
      [ABBRUCH] nicht verifiziert -> Retry -> STOP
    max_actions / consecutive_unverified_stop erreicht -> STOP

process_drag  (EINZELN NACHEINANDER, je gekauftem Dolch)
  Quell-Slot = der HAMMER-STACK-Slot (Template=Hammer, P0.1, positiv)
  Ziel-Slot  = der jeweilige verifizierte Dolch-Slot (Template=Dolch, P0.1, positiv)
    [ABBRUCH] Quelle nicht Hammer ODER Ziel nicht Dolch -> STOP (kein Drag)
  inventory_discard.drag(api, x_hammer, y_hammer, x_dolch, y_dolch)
    EIN Drag verbraucht 1 Hammer + 1 Dolch (NICHT den ganzen Stack); KEIN
    Bestätigungsfenster.
    (mouseUp im finally; abort erst NACH dem atomaren Drag prüfen)
  _wait_for Bildzustand stabil

verify_process
  Dolch-Slot jetzt LEER ? UND Hammer-Stack dekrementiert (Re-Read) ?
    JA -> hammer_remaining -= 1 (NUR jetzt)
    NEIN -> max 1 Retry -> STOP 'Verarbeitung nicht verifiziert'

decrement / re-scan
  alle K=~10 Iter glow-aware Re-Scan zur Drift-Korrektur; Fortschritt am
  beobachtbaren Bestand festmachen (Re-Read), NICHT an logischer Zählung

check_done
  hammer_remaining > 0 -> buy_round ; ==0 -> stop

stop
  Shop schließen, Cursor parken, Bilanz (verarbeitet, Dolche), JSONL
```

---

## 4. Erkennungsplan pro UI-Element (geerdet an Bildern)

Format: Element — Datei(en) — Region (802×632, **re-kalibrieren!**) — Methode — Schwelle.

| Element                               | Beleg-Bild                                                           | Region (roh)                            | Methode                                                                     | Schwelle                          |
| ------------------------------------- | -------------------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------- | --------------------------------- |
| NPC-Name Alchemist                    | Alchemist BlRG/Fmx/PeEEl/… (wandert)                                 | Vollbild Spielbereich x150–620,y100–420 | Grün-HSV (G>120,G−R>25,G−B>25) → CC → **NCC-Wortbild** `Alchemist`          | NCC ≥0.8; **kein** Blindfallback  |
| NPC-Name Waffenhändler                | Einkauf Dolche `angesprochen1`; Waffenschmied ARiPje/bTTNAi          | gleiche Maske                           | Grün+NCC `Waffenhändler` (umlaut-/varianten-tolerant)                       | NCC ≥0.8                          |
| Selektions-Ring                       | BlRG/PeEEl/TYu/jSBNb/s4nZ/x9TD; angesprochen1; ARiPje/bTTNAi/VEmBIfd | ~80px um NPC, **y>240**                 | Rot-HSV (R>120,R−G>30,R−B>40) + **Ring-FORM** (elliptisch, Loch mittig)     | Cluster ≥ MIN_RING_PX, ringförmig |
| (Negativ) eigene HP-Leiste / X-Button | Waffenschmied (rot unter gelbem Namen), Titel-X y<32                 | —                                       | y<32 maskieren; HUD x>595 maskieren; nur near-NPC werten                    | MUSS False liefern                |
| Dialog locked                         | `erstgespräch1.png`                                                  | Dialog-Zeilenblock (dynamisch)          | NCC-Marker `Eine neue Technik!` vorhanden                                   | ≥0.85                             |
| Dialog unlocked                       | `nachErstgesprächnormal.png`                                         | dito                                    | NCC-Marker `Energiesplitter extrahieren` vorhanden                          | ≥0.85                             |
| Dialogzeile `Laden öffnen`            | erstgespräch1 / angesprochen1                                        | Zeilen-Y **dynamisch** (6 vs 7 Zeilen!) | NCC-Wortbild, eindeutig (kein 2. Treffer nah)                               | ≥0.85                             |
| Story-Buttons `Weiter`/`OK`           | erstgespräch2/3 (`Weiter`), erstgespräch4 (`OK`)                     | Box rechts-unten                        | NCC                                                                         | ≥0.8                              |
| Shop offen (Alchemist)                | `Shopgeöffnetalchemist.png`                                          | Header x350–545,y50–70                  | NCC `Laden`-Header                                                          | ≥0.7                              |
| Shop offen (Waffenhändler)            | Einkauf Dolche Shop (P0.4 dünn)                                      | Header x412–552,y56–75                  | NCC `Laden`                                                                 | ≥0.7                              |
| Panel Bag vs Equip                    | Inventar.png vs alle Shop-Bilder                                     | Header rechts                           | NCC `Inventar` vs `Ausrüstungsfenster`                                      | ≥0.7                              |
| Hammer-Slot im Shop (200er)           | Shopgeöffnetalchemist Zeile1 (nur 200er sichtbar)                    | SHOP_HAMMER_ANCHOR=(425,121)            | `find_shop_item(hammer_icon)`                                               | NCC ≥0.7                          |
| Dolch-Slot im Shop                    | Einkauf Dolche Shop, obere Reihe                                     | SHOP_DAGGER_ANCHOR=(556,59)             | `find_shop_item(dolch_icon)` Template                                       | NCC ≥0.7                          |
| Inventar-Slot frei/belegt             | alle Inventar-Bilder                                                 | grid_lock-relativ                       | Helligkeit/Varianz **glow-aware** (GLOW_REF) + Hover-Clear                  | EMPTY-Klassifikation              |
| Hammer/Dolch/Splitter im Inventar     | **FEHLT in allen 26**                                                | —                                       | itemdb-Template (P0.1)                                                      | **Blocker**                       |
| Inventar-Tabs I–IV                    | BlRG / Shopgeöffnetalchemist                                         | y~205–272                               | NCC pro Tab; aktiv per Helligkeit, **MAD-Schwelle ~15** (semi-transparent!) | aktiv > inaktiv                   |

Kauf-Mechanik: **Rechtsklick auf Slot-Center** (kein Preis-/Mengenfeld im Bild).
Re-Read-Verifikation PFLICHT über §3 (Bestand stieg). Aktion 1 kauft IMMER den
200er-Stack (SHOP_HAMMER_ANCHOR = der 200er-Slot), `stack_count`-mal.

---

## 5. Smartes persistentes Inventar-Management

- **Sidecar** `energiesplitter_layout.json` in `%APPDATA%/Metin2FishBot` (analog
  `grid_lock.json`): reservierter Dolch-Slot (Seite,row,col), bekannte Hammer-
  Stack-Slots, freie-Slot-Karte, Schema-Version. **Beim Start GELADEN und per
  frischem `run_inventory_scan` RE-VALIDIERT** → bei Mismatch (Fenster-Drift,
  manuelle Änderung) cold-rebuild.
- **Slot-Koordinaten IMMER aus dem re-validierten `grid_lock` ableiten**
  (offset_x/y), nie aus persistierten Absolut-Pixeln (Fenster-Move-Schutz).
- **Frei-Platz-Scan glow-aware:** frisch gekaufte Items leuchten lavendel
  (GLOW_REF=(176,177,203) verifiziert). Vor jeder Frei-Zählung Hover-Clear
  (`inventory.hover`), erst dann zählen. „frei" = positiv als **EMPTY**
  klassifiziert, nicht „nicht-Item".
- **Dolch-Reserveslot (Aktion 2):** EIN freier Slot auf **Seite I** nahe einem
  Hammer-Stack (kurze Drag-Distanz), persistiert. **Bei jedem Loop als EMPTY
  re-verifizieren**; ist er belegt und der Inhalt NICHT zweifelsfrei der frische
  Dolch → neuen freien Slot wählen + Layout nachführen (nie blind nutzen, sonst
  Drag auf Fremd-Item = Verlust).
- **Lande-Slot des Dolch-Kaufs** wird per Vorher/Nachher-Diff bestimmt, NICHT
  angenommen (Neukauf landet im nächsten freien, nicht garantiert im reservierten).
- **Min Seitenwechsel:** solange Hammer-Stacks + Dolch-Slot + Splitter-Ziel auf
  Seite I (max I+II) liegen, kein Tab-Wechsel. Vor jeder seitenabhängigen Aktion
  aktiven Tab UND Panel verifizieren; nach Tab-Klick event-getrieben bis Stabil.
- **Drift-Wahrheit = der Scan**, nicht die logische Zählung. Fortschritt von
  Aktion 2 am **beobachtbaren Bestand** messen (Re-Read), nicht an logischer Zählung.
- **Kaufmenge Aktion 1:** `stack_count` 200er-Stacks (UI-Eingabe „Anzahl 200er-Stacks",
  default 1); kauft IMMER den 200er, X-mal; begrenzt durch freie Slots
  (200er braucht ≥1 EMPTY) + `max_actions`.
- **Kaufmenge Aktion 2:** `daggers_per_round` Dolche pro Runde, dann einzeln
  nacheinander verarbeiten; Schleife bis keine Hämmer mehr.
- **Verschmelzen:** ein gekaufter Stack kann mit bestehendem Hammer-Stack
  VERSCHMELZEN → Verifikation deckt „neuer Slot ODER bestehender Stack +stack" ab.

---

## 6. Config-Schema

`APP_MODES += ('energiesplitter_hammer','energiesplitter_dagger')`.
`DEFAULTS['energiesplitter'] = { 'hammer': {...}, 'dagger': {...}, 'shared': {...} }`.

```
hammer.energie_freischalten   bool   default False
hammer.stack_count            int    default 1   clamp 1..10000   (UI: Anzahl 200er-Stacks)
dagger.daggers_per_round      int    default 1   clamp 1..200     (UI: Dolche pro Runde)
shared.speed_profile          enum   ('safe'|'fast')  default 'fast'  (-> settle/poll, nie
                                     unter Render-Minimum)
shared.mouse_pause            float  default 0.05  clamp 0.03..0.3   (intern pro Operation)
shared.keyboard_pause         float  default 0.10  clamp 0.03..0.3
shared.max_actions            int    default = round(1.2*soll)  clamp 1..100000  (NICHT 5000)
shared.consecutive_unverified_stop int default 3
shared.jitter_pct             float  default 0.15  (Anti-Cheat, alle Intervalle)
shared.birdseye_on_miss       bool   default True  (KEYPRESS-Manöver)
```

`dagger.reserved_dolch_slot` lebt im Layout-Sidecar, NICHT in der Config (auto).
`validate.py`: enums via `_enum`, int/float via `_clamp`, bool via `bool()`,
`merge_defaults` für Vorbelegung, unbekannte Keys verworfen.

---

## 7. Logging-Schema

- `log.section('Energiesplitter — Hammer')` bzw. `'— Dolch'` beim Start.
- `log.event(state, msg, **fields)` je State-Übergang: `state`, `dialog_state`,
  `shop_open`, `gekaufte_stacks/soll`, `hammer_remaining`, `verified`, `retries`.
- `log.snapshot(name, bgr=frame)` bei JEDEM unerwarteten Zustand (Dialog fehlt,
  Ring fehlt, Kauf/Verarbeitung nicht verifiziert) →
  Debug-PNG (mirror `seher_runner._save_debug_frame`/`_log_diagnosis`).
- JSONL `%APPDATA%/Metin2FishBot/energiesplitter_results.jsonl`: pro Kauf/Verar-
  beitung ein Record `{timestamp, action, verified, retries}`.
- **Bilanz** am Ende: Hämmer gekauft/verarbeitet, Dolche, Stop-Grund.
- **Kein `console.log`** (Projektregel) — alles über `debuglog` + Log-Panel.
- UI-Live-Feedback: aktueller State + Fortschritt (gekaufte Stacks/soll bzw.
  verarbeitet/Bestand) im Status-Label (mirror Manage-Running v1.1.6).

---

## 8. Testplan gegen die 26 Bilder (Fixtures)

Alle headless: `pydirectinput` + `win32` + `WindowCapture` gestubbt; `cv2`/`numpy`
echt auf Fixtures. **Ehrlich: headless-grün ≠ live-funktioniert** — Live-Klick/
Drag/Kauf-Verifikation am echten Client sind NICHT headless validierbar (Memory-
Regel; 2 kaputte Releases v1.1.1/v1.1.2 stammten genau daher).

- **Fixtures:** alle 26 PNGs → `tests/fixtures/energiesplitter/` (8 Alchemist,
  6 Einkauf Hammer, 3 Einkauf Dolche, 9 Waffenschmied), BGR geladen.
- `test_dialog_state`: erstgespräch1→`locked`; nachErstgesprächnormal→`unlocked`;
  angesprochen1→Dialog mit `Laden öffnen`, kein Unlock-Marker.
- `test_shop_open`: Shopgeöffnetalchemist + Aktion-2-Shop→True; alle Overworld→False.
- `test_panel_is_bag`: Inventar.png→Bag; Shop-Bilder mit Equip rechts→nicht-Bag.
- `test_npc_green`: Alchemist/Waffenhändler-Bilder→Treffer an variabler Position;
  NPC-lose Bilder (2JJQT/KwAgg/Vzkvy/jlJmS)→kein Treffer (kein FP auf gelbem Namen).
- `test_selection_ring`: Ring-Bilder→True; ohne→False; Titel-X (y<32) + eigene
  HP-Leiste→**kein FP** (Maskentest).
- `test_buy_amount_logic`: `stack_count` 200er-Stacks → Auto-Stop nach X Stacks;
  200er nur bei ≥1 EMPTY; `max_actions`/`consecutive_unverified_stop` stoppen.
- `test_process_loop`: gestubbt → kauft `daggers_per_round` Dolche/Runde, verarbeitet
  EINZELN NACHEINANDER (je 1 Drag = 1 Hammer + 1 Dolch); Schleife bis Hammer==0;
  Stop bei 0; **Fortschritt am Re-Read-Bestand, nicht an logischer Zählung**.
- `test_safety_stops`: kein-Platz / NPC-nicht-gefunden / Ring-fehlt /
  Kauf-nicht-verifiziert / Verarbeitung-nicht-verifiziert / Item-Template-fehlt →
  je sauberer Stop **ohne weiteren Klick** (mock-assert: kein rightClick/Drag nach Guard).
- `test_drag_abort_finally`: abort mitten im Drag → `mouseUp` wurde aufgerufen
  (kein hängender Button).
- `test_config`: defaults/validate/clamp/enum; out-of-range korrigiert.
- `test_i18n_parity`: alle neuen `t()`-Keys de UND en.
- `test_version`: version-pin gebumpt (Release-Checkliste — Memory-Gotcha!).

---

## 9. Konsolidierte Risiko-Tabelle (Severity + Gegenmaßnahme)

| #   | Sev      | Risiko                                                                                                                                                  | Gegenmaßnahme                                                                                                                                                                                 |
| --- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | CRITICAL | **Kein freies OCR im Projekt** — Dialog-Diskriminierung wie beschrieben nicht baubar                                                                    | Methode ehrlich auf **NCC-Wortbild-Template pro String** (P0.2, de+en) umstellen; ODER bewusst Tesseract als Dependency (tessdata in beide .spec packen). Kein Klick ohne geladene Templates. |
| 2   | CRITICAL | **Item-Icons Hammer/Dolch/Splitter fehlen** in allen 26 Bildern + `inventory_icons/`                                                                    | P0.1 Live-Crops → itemdb-Templates (Workflow wie chat_ocr). `find('Hammer')` strukturell leer bis dahin → Modul startet nicht, loggt „Item-Template fehlt".                                   |
| 5   | CRITICAL | **Verarbeitungs-Drag wenig belegt** (P0.5); Drag auf Fremd-Item = Equipment-Verlust                                                                     | P0.5 anfordern; Drag NUR Hammer-STACK→Dolch (beide Template-verifiziert); decrement NUR nach `verify_process` (Dolch leer + Hammer dekrementiert); KEIN Bestätigungsfenster.                  |
| 7   | HIGH     | **Ring-FP** durch eigene HP-Leiste / rote Tränke / X-Button                                                                                             | Rot-Maske nur near-NPC + y>240; HUD x>595 + y<32 maskieren; **Ring-FORM-Test** (Ellipse mit Loch), nicht nur Pixelzahl; Negativ-Fixtures. Live-Test Pflicht.                                  |
| 8   | HIGH     | **Vogelperspektive** als Rechtsklick-Drag (Spec) ist im Code ein **Keypress** (`birds_eye_key='g'`); Rechtsklick-Drag = Kamera-Pitch → Fehl-Anvisierung | Vogelperspektive über `_hold_key` (wie campfire), NICHT Rechtsklick-Drag; Rechtsklick nur für NPC-Anvisierung.                                                                                |
| 9   | HIGH     | **Geometrie aus 802×632** (OS-Rahmen) auf 800×600 → systematischer y-Offset (vgl. v1.1.0 grid.tl 275→244)                                               | Alles am echten Client re-kalibrieren (P0.6); Klicks **anker-relativ** (Header-NCC) statt absolut; Shop-Item per Template statt fester Koordinate.                                            |
| 10  | HIGH     | **max_actions=5000** wertlos als Endlos-Backstop                                                                                                        | Cap = ~1.2× Sollzahl; +`consecutive_unverified≥3→Stop`; Fortschritt am Re-Read-Bestand.                                                                                                       |
| 11  | HIGH     | **Dialogzeile daneben** → teure Aktion (Veredelung/Bonuswandel/Splitter herstellen)                                                                     | Eindeutiger NCC-Match ≥0.85; **Negativliste** dieser Zeilen NIE klicken; nach Klick shop_open verifizieren, sonst Stop.                                                                       |
| 12  | MEDIUM   | **Glow** verfälscht Frei/Belegt + Lande-Slot-Zuordnung im kritischen Moment                                                                             | Glow-aware Pipeline (GLOW_REF) + Hover-Clear vor jeder Zählung/Diff.                                                                                                                          |
| 13  | MEDIUM   | **Tab/Panel-Verwechslung** (semi-transparente Tab-Reihe; Shop zeigt Equip statt Bag)                                                                    | Vor Scan Panel per Header verifizieren; Tab aktiv per MAD~15; nach Tab-Klick bis Stabil warten; bei Unklarheit Stop statt Drag.                                                               |
| 14  | MEDIUM   | **NPC-Name** 3 Schreibvarianten (`Waffenhändler`/`Waffenhandler`/Spec „Waffenschmied")                                                                  | NCC toleranzbehaftet auf echten Schriftzug (P0.2); kein größter-Cluster-Blindfallback in Stadt. **Offene Frage 9.**                                                                           |
| 15  | MEDIUM   | **200er-Kauf ohne realen Platz** (Glow-FP) → Klick ohne Item / Doppelkauf                                                                               | Frischer glow-bereinigter Scan vor jedem 200er-Kauf; 200er nur bei ≥1 EMPTY; nach Stack-Kauf per Re-Read verifizieren, dass Stack wirklich landete.                                           |
| 16  | MEDIUM   | **Anti-Cheat:** neue repetitive Rechtsklick/Drag-Signatur (server-seitige Verhaltens-Detektion)                                                         | Jitter ±15 % auf ALLE Intervalle; Drag-Endpunkte ±2–3 px; variable Kadenz; ehrliche ToS-Notiz in UI/README; optional Aktionen/Min-Cap. Bleibt read-only/extern (Memory-Linie).                |
| 17  | MEDIUM   | **Persistenter Reserveslot stale** zwischen Sessions (fremdes Item liegt drin)                                                                          | Re-Validierung als EMPTY bei jedem Loop; belegt + nicht-Dolch → neuen Slot + Layout nachführen.                                                                                               |
| 18  | LOW      | **Single-Authority** / zweiter Start-Button parallel                                                                                                    | `on_start` global botting-Flag, verweigert 2. Start; F6 via abort_fn-Seam bricht beide ab; Test: 2. Start startet keinen 2. Worker.                                                           |
| 19  | LOW      | **version-pin / test_version** vergessen                                                                                                                | Release-Checkliste; headless-grün ≠ live; erster scharfer Lauf mit `max_actions=2`.                                                                                                           |

---

## 10. OFFENE FRAGEN AN DEN USER (nur echte Blocker, nicht aus Bild/Spec lösbar)

1. **Verarbeitungs-Vorgang (P0.5):** Bitte einen Screenshot des Hammer-Stack→Dolch-
   Drags liefern — bestätigt, dass EIN Drag genau 1 Hammer + 1 Dolch verbraucht
   (nicht den ganzen Stack) und KEIN Bestätigungsfenster erscheint. Ohne dieses
   Bild ist Aktion 2 nicht sicher baubar.
2. **Item-Icons (P0.1):** Bitte Live-Crops eines Inventars **mit gekauften Hämmern,
   einem Dolch und entstandenen Energiesplittern** — diese drei Icons fehlen in
   allen 26 Bildern; ohne sie keine Bestandszählung, keine Kauf-Verifikation, kein
   sicheres Drag-Ziel.
3. **Waffenhändler-Shop (P0.4):** Ein Screenshot des **geöffneten** Waffenhändler-
   Shops (die Gruppe „Waffenschmied" enthält keinen) — zum Kalibrieren von
   shop_open und der Dolch-Slot-Position an DIESEM HUD.
4. **Rechtsklick = Sofortkauf?** Ist Rechtsklick auf den Shop-Slot wirklich
   Sofortkauf ohne Mengen-/Bestätigungs-Popup? Falls Popup → zusätzlicher State nötig.
   (Waffenhändler-Shop hat zusätzlich einen „Kaufen"-Button — Fallback-Pfad?)
5. **NPC-Schriftzug:** Wie heißt der NPC für Aktion 2 am echten Client exakt
   gerendert — `Waffenhändler` oder `Waffenhandler` (ohne Umlaut)? Und ist es
   derselbe NPC wie der in der Spec genannte „Waffenschmied"?
6. **Energie-Freischaltung:** Soll Aktion 1 die Freischaltung (Story `Eine neue
Technik!` → Weiter/Weiter/OK) bei Bedarf durchführen, oder strikt überspringen,
   wenn bereits freigeschaltet? (Default: optional per `energie_freischalten`,
   da reiner Hammerkauf in beiden Zuständen nur `Laden öffnen` braucht.)

---

## Ehrliche Einordnung (Synthese-Verdikt)

Architektur, Sicherheitsdenken und die Wiederverwendung bewährter Seams
(`seher_runner`-Tick + abort_fn, `inventory_discard.drag` mit mouseUp-finally,
`run_inventory_scan`, grid_lock, glow-aware Scan, Single-Authority, ergebnis-
gebundener Endlos-Schutz) sind tragfähig und an v1.1.x-Lehren angelehnt. Aber das
Modul ist **erst nach Phase-0** verantwortbar baubar: zwei Subsysteme (NCC-Text
statt OCR, Item-Templates) und das Verarbeitungs-Feedback haben weder
Bild-Ground-Truth noch Code-Backing. Bis dahin: nur Read-only-Detektor-
Kalibrierung, **kein scharfer Kauf-/Verarbeitungs-Lauf**. Erster scharfer Lauf
zwingend **live** (headless validiert weder In-Game-Input, Glow, Tab-Race noch
Drag-Treffer) mit `max_actions=2`. Sicherung läuft über `max_actions` +
`consecutive_unverified_stop` + Erkennung-vor-Aktion + Re-Read-Verifikation.
