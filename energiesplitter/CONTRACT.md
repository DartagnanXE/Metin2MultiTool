# Energiesplitter — VERBINDLICHER BUILD-CONTRACT (Tech-Lead, 2026-06-16)

> Quelle der Wahrheit für ALLE Build-Agenten (A/B/C/D). Bei Konflikt gilt dieser
> Contract > DESIGN.md > REQUIREMENTS_ADDENDUM.md. Alle Andockpunkte unten sind am
> echten Code verifiziert (Zeilennummern als Orientierung, nicht als Patch-Anker).
>
> **Großumbau 2026-06-16: Yang/Gold-Subsystem KOMPLETT ENTFERNT.** Kein Preis, kein
> Kontostand, kein `gold_reader.py`, keine Yang-Ziffern-Templates, kein ROI/Rechner.
> Eingaben sind jetzt `stack_count` (Anzahl 200er-Stacks) und `daggers_per_round`
> (Dolche pro Runde). Sicherung allein über `max_actions` +
> `consecutive_unverified_stop` + Erkennung-vor-Aktion + Re-Read-Verifikation.
>
> **Projekt-Stil bindend:** 2-Space-Indent, Single-Quotes, Semikolon-frei (Python),
> kleine Dateien (<800 Z.), explizite Fehlerbehandlung, **KEIN `print`/`console.log`**
> (nur `debuglog.log` + i18n `t()`). Dieses Projekt nutzt **keine** Type-Annotations
> im Laufzeit-Code — die Signaturen unten sind als _Doc-Vertrag_ zu lesen; die Impl
> folgt dem Projektstil (Annotations optional, Verhalten bindend).
>
> **PHASE-0-STATUS: NO-GO für scharfe Läufe.** P0.1 (Item-Icons), P0.2 (Wortbild-
> Templates), P0.5 (Verarbeitungs-Crop) fehlen. Diese Phase baut
> **NUR** das Detection-Framework + Stubs + Tests gegen die vorhandenen 26 Bilder.
> **KEIN version-Bump, KEIN Release.** Der Bot DARF NICHT klicken/kaufen/draggen,
> solange das Phase-0-Gate (§2) nicht grün ist.

---

## 0. Modus-Modell (verbindlich)

Zwei Bots, EINE Reiter-Ansicht mit ZWEI Start/Stop-Buttons. Integration über den
**run_loop-Bot-Tick** (wie `fishbot`/`puzzlebot`), NICHT über einen eigenen Worker-
Thread (anders als `seher`). Begründung: Single-Authority (R9) + globaler F6-Stop +
Exklusivität laufen bereits über `run_loop.tick`.

- `APP_MODES += ('energiesplitter_hammer', 'energiesplitter_dagger')`
- Aktiver Modus über `controller.set_mode('energiesplitter_hammer'|'energiesplitter_dagger')`.
- `RAIL_ORDER` bekommt EIN Item `'energiesplitter'` (eine Ansicht, zwei Aktionen).

---

## 1. Klasse `EnergiesplitterBot` (energiesplitter/bot.py — Eigentümer D)

EINE Bot-Klasse mit Modus-Schalter (kein Vererbungs-Paar) → exklusives `runHack`,
Modus-Auswahl per Attribut. Spiegelt `FishingBot`/`PuzzleBot` (`set_to_begin`/
`botting`/`runHack`/`state`/`wincap`).

### 1.1 State-Machine-Konstanten (Klassen-Attribute, int)

```
# gemeinsam
ST_INIT             = 0
ST_INVENTORY_BASE   = 1
ST_APPROACH_NPC     = 2
ST_SELECT_NPC       = 3
ST_OPEN_DIALOG      = 4
ST_OPEN_SHOP        = 6
ST_STOP             = 99
# Hammer-Modus
ST_UNLOCK_DECIDE    = 5
ST_UNLOCK_STORY     = 7
ST_LOCATE_HAMMER    = 8
ST_BUY_LOOP         = 9
ST_CHECK_DONE       = 10
# Dolch-Modus
ST_LOCATE_DOLCH     = 11
ST_BUY_ONE_DOLCH    = 12
ST_PROCESS_DRAG     = 13
ST_VERIFY_PROCESS   = 14
ST_RESCAN           = 15
```

### 1.2 Modus-Konstanten (action-Auswahl)

```
MODE_HAMMER = 'hammer'   # Aktion 1 @ Alchemist
MODE_DAGGER = 'dagger'   # Aktion 2 @ Waffenhändler  (intern 'dagger'/'dolch' synonym)
```

`runHack` verzweigt am Anfang: `if self.mode == self.MODE_HAMMER: self._tick_hammer()
else: self._tick_dagger()`. Genau EIN Tick = Erkennung→Entscheidung→eine Aktion,
blockierend wie `seher_runner._click_until` (event-getrieben, kein Fixkadenz).

### 1.3 Attribute (von `set_to_begin(values)` gesetzt — eingefroren)

| Attribut                              | Typ           | Quelle / Bedeutung                                                                     |
| ------------------------------------- | ------------- | -------------------------------------------------------------------------------------- |
| `self.mode`                           | str           | `MODE_HAMMER`/`MODE_DAGGER` (vom run_loop vor set_to_begin gesetzt: `controller.mode`) |
| `self.botting`                        | bool          | run_loop-Flag; `set_to_begin` setzt NICHT (run_loop setzt True/False)                  |
| `self.state`                          | int           | aktueller State (Start: `ST_INIT`)                                                     |
| `self.wincap`                         | WindowCapture | `WindowCapture(constants.GAME_NAME)`; Fenster fehlt → STOP                             |
| `self.stop_signal`                    | StopSignal    | vom run_loop injiziert (vor set_to_begin) — Quelle für `abort_fn`                      |
| **Config (eingefroren aus `values`)** |               |                                                                                        |
| `self.stack_count`                    | int           | Anzahl 200er-Stacks (Aktion 1; Default 1)                                              |
| `self.energie_freischalten`           | bool          | Aktion 1: Freischaltung versuchen (sonst auto-skip)                                    |
| `self.daggers_per_round`              | int           | Dolche pro Runde (Aktion 2; Default 1)                                                 |
| `self.mouse_pause`                    | float         | per-Operation (Maus, Default 0.05)                                                     |
| `self.keyboard_pause`                 | float         | per-Operation (Tastatur, Default 0.10)                                                 |
| `self.speed_profile`                  | str           | `'safe'`\|`'fast'` → settle/poll-Skala                                                 |
| `self.jitter_pct`                     | float         | ±-Anteil auf ALLE Intervalle (Default 0.15)                                            |
| `self.birdseye_on_miss`               | bool          | bei NPC-Miss 1× Vogelperspektive-KEYPRESS                                              |
| `self.birds_eye_key`                  | str           | `'g'` (KEYPRESS, NICHT Rechtsklick-Drag)                                               |
| **Safety-Backstops (Attribute)**      |               |                                                                                        |
| `self.max_actions`                    | int           | Endlos-Cap (auto = round(1.2 × soll)); pro Kauf/Drag inkrementiert `self.actions_done` |
| `self.consecutive_unverified_stop`    | int           | Stop nach N nicht-verifizierten Aktionen in Folge (Default 3)                          |
| `self.dry_run`                        | bool          | **Default True bis Phase-0 armiert** — KEIN Klick/Kauf/Drag, nur Erkennung+Log         |
| `self.armed`                          | bool          | Phase-0-Gate-Resultat (siehe §2); `dry_run OR NOT armed` ⇒ niemals teure Aktion        |
| **Laufzeit-Zähler**                   |               |                                                                                        |
| `self.gekaufte_stacks`                | int           | gekaufte 200er-Stacks (verifiziert)                                                    |
| `self.hammer_remaining`               | int           | zu verarbeitende Hämmer (Dolch-Modus)                                                  |
| `self.actions_done`                   | int           | gegen `max_actions`                                                                    |
| `self.consecutive_unverified`         | int           | gegen `consecutive_unverified_stop`                                                    |

### 1.4 Methoden (öffentlicher Vertrag)

```
set_to_begin(values)   # erzeugt wincap, friert ALLE Config-Attribute aus `values` ein,
                       #   self.state=ST_INIT, alle Laufzeit-Zähler=0, ruft phase0_gate()
                       #   -> setzt self.armed; KEIN Klick. Fenster fehlt -> setzt
                       #   self._stop_reason + self.botting bleibt run_loop-gesteuert.
runHack()              # EIN blockierender Tick; verzweigt nach self.mode; bei
                       #   self.dry_run or not self.armed: nur Read-only-Erkennung +
                       #   log + Stop "Phase-0 nicht bereit". Stoppt sich SELBST
                       #   (self.botting=False) bei jeder Stop-Bedingung.
abort_fn()             # -> bool: True wenn self.stop_signal.stopped (Seam wie Manage
                       #   v1.1.6: run_loop ruft stop_signal.add_callback). NIE Polling.
phase0_gate()          # -> (armed: bool, missing: list[str]) ; siehe §2. Setzt self.armed.
```

**`set_to_begin`-Reset (verbindlich):** `set_to_begin` ist idempotent re-aufrufbar
und setzt JEDESMAL: `state=ST_INIT`, `gekaufte_stacks=0`, `hammer_remaining=0`,
`actions_done=0`, `consecutive_unverified=0`,
und liest `mode` frisch von der Instanz (run_loop setzt `bot.mode` vor dem Aufruf).
`max_actions` wird in `set_to_begin` aus `stack_count`/`daggers_per_round`
ABGELEITET, falls nicht explizit gesetzt.

---

## 2. PHASE-0-GATE (HARTER BLOCKER)

**Funktion (Eigentümer D, in bot.py; Detektoren liefert A):**

```
energiesplitter.bot.EnergiesplitterBot.phase0_gate(self) -> (armed, missing)
   wobei missing: list[str]  (Klartext-Schlüssel der fehlenden Artefakte)
```

Delegiert die reine Prüfung an A:

```
energiesplitter.detect.assets_ready(mode) -> (ready: bool, missing: list[str])
energiesplitter.detect.grid_present() -> bool            # Inventar-Raster auflösbar
energiesplitter.geometry.is_calibrated(wincap) -> bool   # True nur wenn Client ~800x600
```

**Bedingung (ALLE drei müssen erfüllt sein, sonst armed=False):**

1. **Assets vorhanden** — `detect.assets_ready(self.mode)` prüft (OHNE Yang/Gold):
   - `templates/de/` UND `templates/en/` enthalten die für den Modus nötigen
     Wortbild-Templates (Hammer-Modus: `laden_oeffnen`, `weiter`, `ok`,
     `eine_neue_technik`, `energiesplitter_extrahieren`, `laden_header`,
     `inventar_header`, `ausruestung_header`, `npc_alchemist`; Dolch-Modus
     zusätzlich `npc_waffenhaendler`, `ein_neuer_duft`).
   - **Item-Icons** in `inventory_icons/`: `hammer` (beide Modi), `dolch` +
     `energiesplitter` (Dolch-Modus). FEHLEN derzeit → Gate bleibt rot.
   - **Shop-Anker** `SHOP_HAMMER_ANCHOR`/`SHOP_DAGGER_ANCHOR` + Shop-Item-Templates.
     Jedes fehlende Artefakt landet als String in `missing` (z. B. `'item:hammer'`,
     `'tpl:de/laden_oeffnen'`).
2. **Kalibrierung** — `geometry.is_calibrated(wincap)`: Client-Größe via
   `windowcapture.client_size` ~800×600 (Toleranz `GAME_SIZE_TOLERANCE=8`, wie
   `interface/app/_common._probe_game`). Sonst `missing += ['calibration:800x600']`.
3. **Grid auflösbar** — `detect.grid_present()`: Inventar-Raster auflösbar
   (Slot1→Pixel; ersetzt das frühere `_grid_present`). Sonst `missing += ['grid']`.

**Verhalten bei armed=False (Logging, verbindlich):**

```
log.section(t('energiesplitter.section_hammer'|'_dagger'))
log.event('-', t('energiesplitter.phase0_not_ready', missing=', '.join(missing)))
self.botting = False           # sofortiger Selbst-Stop
# KEIN rightClick / KEIN drag / KEIN moveTo-Klick ist erreichbar (return vor Aktionen)
```

**Backstops als Attribute (zusätzlich, OCR-unabhängig, IMMER aktiv auch wenn armed):**
`max_actions`, `consecutive_unverified_stop` + Re-Read-Verifikation jeder Aktion.
Jede teure Aktion ist hinter `if self.dry_run or not self.armed: return` gekapselt.
Erststart-Default: `dry_run=True`, `max_actions=2` (erster scharfer Lauf konservativ).

---

## 3. Config-Schema (interface/config/defaults.py — Eigentümer C)

`APP_MODES = ('fishing', 'puzzle', 'energiesplitter_hammer', 'energiesplitter_dagger')`

`DEFAULTS['energiesplitter']` = Block mit drei Sub-Dicts `hammer`/`dagger`/`shared`.
Neue Modul-Konstanten (defaults.py, exportiert via `__all__`, von validate.py genutzt):
`SPEED_PROFILES=('safe','fast')`,
`ES_STACK_MIN=1`, `ES_STACK_MAX=10000`, `ES_PAUSE_MIN=0.03`, `ES_PAUSE_MAX=0.3`,
`ES_DAGGERS_MIN=1`, `ES_DAGGERS_MAX=200`, `ES_MAXACT_MIN=1`, `ES_MAXACT_MAX=100000`.

| Key (Pfad)                                           | Typ   | Default  | Range/Enum                                                                          |
| ---------------------------------------------------- | ----- | -------- | ----------------------------------------------------------------------------------- |
| `energiesplitter.hammer.stack_count`                 | int   | `1`      | clamp 1..10000 (UI: Anzahl 200er-Stacks)                                            |
| `energiesplitter.hammer.energie_freischalten`        | bool  | `True`   | — (an: prüft+schaltet frei falls Option da, sonst auto-skip; aus: nur Laden+kaufen) |
| `energiesplitter.dagger.daggers_per_round`           | int   | `1`      | clamp 1..200 (UI: Dolche pro Runde)                                                 |
| `energiesplitter.shared.speed_profile`               | enum  | `'fast'` | `'safe'`\|`'fast'`                                                                  |
| `energiesplitter.shared.mouse_pause`                 | float | `0.05`   | clamp 0.03..0.3                                                                     |
| `energiesplitter.shared.keyboard_pause`              | float | `0.10`   | clamp 0.03..0.3                                                                     |
| `energiesplitter.shared.max_actions`                 | int   | `0`      | `0` = auto round(1.2×soll); sonst clamp 1..100000                                   |
| `energiesplitter.shared.consecutive_unverified_stop` | int   | `3`      | clamp 1..20                                                                         |
| `energiesplitter.shared.jitter_pct`                  | float | `0.15`   | clamp 0.0..0.5                                                                      |
| `energiesplitter.shared.birdseye_on_miss`            | bool  | `True`   | — (KEYPRESS-Manöver)                                                                |
| `energiesplitter.shared.dry_run`                     | bool  | `True`   | **arm-Flag: True bis Phase-0 + User-Bestätigung; sicherer Erststart-Default**       |

`dagger.reserved_dolch_slot` lebt im Layout-Sidecar (`energiesplitter_layout.json`),
**NICHT** in der Config (auto, re-validiert).

**validate.py (C):** Block-Validator `_validate_energiesplitter(merged)`:
enums via `_enum`, int/float via `_clamp` + `_coerce_int`/`int(_clamp(...))`, bool via
`bool()`. `merge_defaults` füllt Sub-Dicts auf, unbekannte Keys verworfen. `max_actions`
bleibt Config-Wert (0=auto); die Auto-Ableitung passiert in
`set_to_begin` (nicht in validate — validate bleibt rein/deterministisch).
`merged['mode']` muss `APP_MODES` (inkl. der beiden neuen) akzeptieren.

**to_values-Brücke (C):** `run_loop.apply_energiesplitter_config()` legt die
gewählten Sub-Dict-Werte als `values['-ES_*-']`-Keys ab (analog `apply_puzzle_config`),
die `set_to_begin(values)` liest. Schlüssel-Namensraum: `-ES_STACK_COUNT-`,
`-ES_FREISCHALTEN-`, `-ES_DAGGERS_PER_ROUND-`, `-ES_SPEED-`,
`-ES_MOUSE_PAUSE-`, `-ES_KB_PAUSE-`, `-ES_MAX_ACTIONS-`, `-ES_UNVERIF_STOP-`,
`-ES_JITTER-`, `-ES_BIRDSEYE-`, `-ES_DRY_RUN-`, `-ES_MODE-`.

---

## 4. i18n-Keys (i18n_data.py — Eigentümer C; je `{'en','de'}`, Parität PFLICHT)

Test `tests/test_i18n_parity.py` verlangt für JEDEN Key beide Sprachen. Neue Keys:

| Key                                     | de                                                                                                                                                                                                                                                                                                    | en                                                                                                                                                                                                                                                                                                    |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ui.view_energiesplitter`               | `Energiesplitter`                                                                                                                                                                                                                                                                                     | `Energy Splinter`                                                                                                                                                                                                                                                                                     |
| `ui.energiesplitter_sub`                | `Kauft Hammer-Stacks und verarbeitet sie einzeln nacheinander mit Dolchen zu Energiesplittern`                                                                                                                                                                                                        | `Buys hammer stacks and processes them one at a time with daggers into energy splinters`                                                                                                                                                                                                              |
| `ui.group_energiesplitter`              | `Energiesplitter`                                                                                                                                                                                                                                                                                     | `Energy Splinter`                                                                                                                                                                                                                                                                                     |
| `ui.es_hammer_start_btn`                | `Hammer kaufen`                                                                                                                                                                                                                                                                                       | `Buy hammers`                                                                                                                                                                                                                                                                                         |
| `ui.es_dagger_start_btn`                | `Dolche kaufen + verarbeiten`                                                                                                                                                                                                                                                                         | `Buy daggers + process`                                                                                                                                                                                                                                                                               |
| `ui.es_stop_btn`                        | `Stoppen`                                                                                                                                                                                                                                                                                             | `Stop`                                                                                                                                                                                                                                                                                                |
| `ui.es_stopping`                        | `Stoppe ...`                                                                                                                                                                                                                                                                                          | `Stopping ...`                                                                                                                                                                                                                                                                                        |
| `ui.es_count_label`                     | `Anzahl 200er-Stacks`                                                                                                                                                                                                                                                                                 | `200-stacks count`                                                                                                                                                                                                                                                                                    |
| `ui.es_freischalten_label`              | `Energie freischalten (falls nötig)`                                                                                                                                                                                                                                                                  | `Unlock energy (if needed)`                                                                                                                                                                                                                                                                           |
| `ui.es_daggers_label`                   | `Dolche pro Runde`                                                                                                                                                                                                                                                                                    | `Daggers per round`                                                                                                                                                                                                                                                                                   |
| `ui.es_idle`                            | `Bereit`                                                                                                                                                                                                                                                                                              | `Idle`                                                                                                                                                                                                                                                                                                |
| `ui.es_running_hammer`                  | `Kaufe Stacks ... ({done}/{soll})`                                                                                                                                                                                                                                                                    | `Buying stacks ... ({done}/{soll})`                                                                                                                                                                                                                                                                   |
| `ui.es_running_dagger`                  | `Verarbeite ... ({rest} Hämmer übrig)`                                                                                                                                                                                                                                                                | `Processing ... ({rest} hammers left)`                                                                                                                                                                                                                                                                |
| `ui.es_help`                            | `Spiel im 800x600-Fenstermodus. Aktion 1 kauft am Alchemisten 200er-Hammer-Stacks; Aktion 2 kauft am Waffenhändler Dolche und verarbeitet sie einzeln nacheinander zu Energiesplittern. Solange Item-Icons/Templates fehlen oder das Fenster nicht 800x600 ist, läuft NUR die Erkennung (kein Kauf).` | `Run the game in 800x600 windowed mode. Action 1 buys 200-hammer stacks at the alchemist; action 2 buys daggers at the weapon trader and processes them one at a time into energy splinters. While item icons/templates are missing or the window is not 800x600, ONLY detection runs (no purchase).` |
| `ui.es_blocked_running`                 | `Es läuft bereits ein Bot – erst stoppen.`                                                                                                                                                                                                                                                            | `A bot is already running – stop it first.`                                                                                                                                                                                                                                                           |
| `energiesplitter.section_hammer`        | `Energiesplitter — Hammer`                                                                                                                                                                                                                                                                            | `Energy Splinter — Hammer`                                                                                                                                                                                                                                                                            |
| `energiesplitter.section_dagger`        | `Energiesplitter — Dolch`                                                                                                                                                                                                                                                                             | `Energy Splinter — Dagger`                                                                                                                                                                                                                                                                            |
| `energiesplitter.started`               | `Gestartet (Modus {mode}).`                                                                                                                                                                                                                                                                           | `Started (mode {mode}).`                                                                                                                                                                                                                                                                              |
| `energiesplitter.phase0_not_ready`      | `Phase-0 nicht bereit – fehlende Artefakte: {missing}. Es wird NICHT gekauft/gedraggt.`                                                                                                                                                                                                               | `Phase 0 not ready – missing artifacts: {missing}. No buying/dragging.`                                                                                                                                                                                                                               |
| `energiesplitter.no_window`             | `Kein Spiel-Fenster gefunden. Stoppe.`                                                                                                                                                                                                                                                                | `No game window found. Stopping.`                                                                                                                                                                                                                                                                     |
| `energiesplitter.no_space`              | `Kein freier Inventarplatz für den Kauf. Stoppe.`                                                                                                                                                                                                                                                     | `No free inventory slot for the purchase. Stopping.`                                                                                                                                                                                                                                                  |
| `energiesplitter.item_template_missing` | `Item-Template fehlt ({item}) – Bestand nicht messbar. Stoppe.`                                                                                                                                                                                                                                       | `Item template missing ({item}) – stock not measurable. Stopping.`                                                                                                                                                                                                                                    |
| `energiesplitter.npc_not_found`         | `NPC {npc} nicht gefunden. Stoppe.`                                                                                                                                                                                                                                                                   | `NPC {npc} not found. Stopping.`                                                                                                                                                                                                                                                                      |
| `energiesplitter.select_failed`         | `Anvisieren fehlgeschlagen (kein Selektions-Ring). Stoppe.`                                                                                                                                                                                                                                           | `Targeting failed (no selection ring). Stopping.`                                                                                                                                                                                                                                                     |
| `energiesplitter.dialog_timeout`        | `Dialog erschien nicht. Debug-Frame gespeichert. Stoppe.`                                                                                                                                                                                                                                             | `Dialog did not appear. Debug frame saved. Stopping.`                                                                                                                                                                                                                                                 |
| `energiesplitter.shop_not_open`         | `Laden öffnete nicht (uneindeutige Zeile?). Stoppe.`                                                                                                                                                                                                                                                  | `Shop did not open (ambiguous line?). Stopping.`                                                                                                                                                                                                                                                      |
| `energiesplitter.item_not_in_shop`      | `{item} nicht im Shop-Sortiment. Stoppe.`                                                                                                                                                                                                                                                             | `{item} not in shop inventory. Stopping.`                                                                                                                                                                                                                                                             |
| `energiesplitter.bought`                | `Gekauft: 200er-Stack (gesamt {done}/{soll}).`                                                                                                                                                                                                                                                        | `Bought: 200-stack (total {done}/{soll}).`                                                                                                                                                                                                                                                            |
| `energiesplitter.buy_unverified`        | `Kauf nicht verifiziert nach {retries} Versuchen. Stoppe.`                                                                                                                                                                                                                                            | `Purchase not verified after {retries} retries. Stopping.`                                                                                                                                                                                                                                            |
| `energiesplitter.processed`             | `Verarbeitet: 1 Hammer + 1 Dolch; übrig {rest} Hämmer.`                                                                                                                                                                                                                                               | `Processed: 1 hammer + 1 dagger; {rest} hammers left.`                                                                                                                                                                                                                                                |
| `energiesplitter.process_unverified`    | `Verarbeitung nicht verifiziert. Stoppe.`                                                                                                                                                                                                                                                             | `Processing not verified. Stopping.`                                                                                                                                                                                                                                                                  |
| `energiesplitter.drag_unsafe`           | `Drag abgebrochen – Quelle nicht Hammer ODER Ziel nicht Dolch. Stoppe (kein Drag).`                                                                                                                                                                                                                   | `Drag aborted – source not hammer OR target not dagger. Stopping (no drag).`                                                                                                                                                                                                                          |
| `energiesplitter.max_actions`           | `Aktions-Obergrenze ({n}) erreicht. Stoppe.`                                                                                                                                                                                                                                                          | `Action cap ({n}) reached. Stopping.`                                                                                                                                                                                                                                                                 |
| `energiesplitter.done`                  | `Fertig. Hämmer {hammers}, Dolche {daggers}. Grund: {reason}.`                                                                                                                                                                                                                                        | `Done. Hammers {hammers}, daggers {daggers}. Reason: {reason}.`                                                                                                                                                                                                                                       |
| `energiesplitter.debug_frame_saved`     | `Debug-Frame gespeichert: {path}`                                                                                                                                                                                                                                                                     | `Debug frame saved: {path}`                                                                                                                                                                                                                                                                           |
| `energiesplitter.toggled_birdseye`      | `NPC nicht gesehen – Vogelperspektive ({key}) ausgelöst.`                                                                                                                                                                                                                                             | `NPC not seen – triggered bird's-eye view ({key}).`                                                                                                                                                                                                                                                   |

---

## 5. Datei-Eigentums-Map (DISJUNKT — kein Agent schreibt fremde Dateien)

**Agent A — Vision/Geometrie (rein, kein IO außer Template-Laden):**

- `energiesplitter/detect.py` — reine Vision (numpy/cv2): `assets_ready(mode)`,
  `grid_present() -> bool`,
  `find_npc_name(bgr, word_template) -> (ok, pt, ncc)`,
  `selection_ring_present(bgr, near, y_min=240) -> bool`,
  `dialog_state(bgr) -> 'locked'|'unlocked'|None`, `shop_open(bgr) -> bool`,
  `panel_is_bag(bgr) -> bool`, `find_shop_item(bgr, item_template) -> (ok, pt, ncc)`,
  `read_shop_stack(slot_bgr) -> int|None`, `read_splitter_growth(before, after) -> int`.
- `energiesplitter/geometry.py` — ALLE Pixelkonstanten relativ zum 800×600-Client +
  `offset_x/y`; `is_calibrated(wincap) -> bool`; anker-relative ROIs (KALIBRIER-BAR).
- `tests/test_energiesplitter_detect.py` — Detektoren gegen 26 Fixtures.

**Agent B — Reine Rechen-Logik + UI:**

- `interface/app/views_energiesplitter.py` — `EnergiesplitterViewMixin._build_
energiesplitter_view`; EINE Ansicht, ZWEI Buttons (`ui.es_hammer_start_btn`/
  `ui.es_dagger_start_btn`) je `command=self._on_es_start_stop('hammer'|'dagger')`-
  Muster, je Settings-Block + Status/Log. Spiegelt
  `views_seher.py`-Aufbau (`_new_view`/`_view_header`/`Section`/`InfoBadge`).
  Start-Pfad: `_probe_game()`-Check → `controller.set_mode(...)` → `controller.
on_start_stop()` (run_loop-Tick übernimmt; KEIN eigener Worker-Thread).
- `energiesplitter/calc.py` — reine Rechner (siehe §6).
- `tests/test_energiesplitter_config.py` — defaults/validate/clamp/enum **+** calc.

**Agent C — Integration (nur EDITS an Bestand, keine neuen Modul-Dateien):**

- `run_loop.py` — `EnergiesplitterBot` instanziieren (`self.esbot`), `apply_
energiesplitter_config`, `on_start` setzt `esbot.mode`+`stop_signal`+`set_to_begin`+
  Exklusivität (verweigert 2. Start), `tick` ruft `esbot.runHack()` wenn
  `esbot.botting`, `stop_signal.add_callback` für abort, `botting`-Resets in allen
  Stop-Pfaden ergänzen (analog fishbot/puzzlebot).
- `interface/app/_common.py` — `RAIL_ORDER += ('energiesplitter',)`,
  `RAIL_GLYPHS['energiesplitter']` (Unicode, kein neues Asset, z. B. `'⚡'`),
  `WHICH_TO_CFG` falls Hotkey nötig (sonst unberührt).
- `interface/app/__init__.py` — `EnergiesplitterViewMixin` importieren + in `App`
  mischen; `set_mode`-Dispatch um die beiden ES-Modi erweitern.
- `interface/config/defaults.py` — `APP_MODES` + `DEFAULTS['energiesplitter']` +
  Range-Konstanten (§3).
- `interface/config/validate.py` — `_validate_energiesplitter` + Aufruf in `validate`.
- `i18n_data.py` — alle §4-Keys (de+en).

**Agent D — Bot-Kern:**

- `energiesplitter/__init__.py` — Paket-Init; exportiert `EnergiesplitterBot` +
  `MODE_HAMMER`/`MODE_DAGGER`; Soft-Imports für cv2/pydirectinput (headless
  importierbar).
- `energiesplitter/bot.py` — `EnergiesplitterBot` (§1), `phase0_gate` (§2),
  State-Maschinen (DESIGN §3), Helfer `verify_hammer_purchase`/`_verify_bag_growth`/
  `verify_process`/`approach_npc`/`open_shop_via_dialog`; **Drag NUR via
  `inventory_discard.drag(api, x1,y1,x2,y2)` — NICHT neu bauen** (A2).
- `tests/test_energiesplitter_flow.py` — State-Machine-Logik, Verarbeitungs-
  Schleife, Safety-Stops, Drag-abort-finally (gestubbtes pydirectinput/win32).

> **Geteilte Berührung — Konflikt-Regel:** Nur C editiert Bestandsdateien.
> A/B/D legen NUR neue Dateien unter `energiesplitter/` bzw. `tests/` an. `templates/`
>
> - `inventory_icons/`-Crops sind Phase-0-User-Lieferungen (kein Agent erfindet sie).

---

## 6. Pure-Funktions-Signaturen (Tests treffen EXAKT diese)

**energiesplitter/calc.py (Agent B):**

```
clamp_nonneg_int(value) -> int
    # klemmt einen Wert auf einen nicht-negativen int (negativ/None/ungültig -> 0);
    # reine Arithmetik; wirft nie. (Einzige verbliebene calc-Funktion — der
    # Yang/Gold-Rechner inkl. plan_hammer_yang/plan_stack_purchase wurde 2026-06-16
    # entfernt.)
```

**energiesplitter/detect.py (Agent A) — die test-relevanten Kernsignaturen:**

```
assets_ready(mode) -> (ready: bool, missing: list[str])     # mode in ('hammer','dagger')
grid_present() -> bool                                       # Inventar-Raster auflösbar
dialog_state(bgr) -> 'locked' | 'unlocked' | None
shop_open(bgr) -> bool
panel_is_bag(bgr) -> bool
find_npc_name(bgr, word_template) -> (ok: bool, pt: tuple|None, ncc: float)
selection_ring_present(bgr, near, y_min=240) -> bool
find_shop_item(bgr, item_template) -> (ok: bool, pt: tuple|None, ncc: float)
read_shop_stack(slot_bgr) -> int | None
read_splitter_growth(before, after) -> int     # Diff am Splitter-Slot; Fallback 0
```

---

## 7. Gate-Regel (eine Zeile, für jeden Agenten)

> **Der Bot ruft NIE rightClick/click/drag/keyDown, solange
> `self.dry_run or not self.armed` wahr ist; `armed` wird allein von
> `phase0_gate()` gesetzt (Assets via `detect.assets_ready` UND `geometry.
is_calibrated` UND `detect.grid_present`); ist es False, loggt der Bot
> `energiesplitter.phase0_not_ready` mit der `missing`-Liste und setzt
> `self.botting=False` — vor jeder teuren Aktion. Zusätzlich greifen IMMER die
> Backstops `max_actions`, `consecutive_unverified_stop` + Re-Read-Verifikation
> jeder Aktion.**

---

## 8. Test-/Release-Pflichten (Phase-2)

- Alle 26 PNGs → `tests/fixtures/energiesplitter/`; Detektoren + Entscheidungslogik
  headless grün (pydirectinput/win32/WindowCapture gestubbt wie
  `tests/test_puzzle_hardening.py`; cv2/numpy echt).
- `test_i18n_parity` muss mit den §4-Keys grün bleiben (de+en lückenlos).
- **KEIN version-Bump, KEIN Release in dieser Phase.** `test_version` NICHT anfassen.
- Ehrlich: headless-grün ≠ live-funktioniert. Erster scharfer Lauf erst nach
  Phase-0-Lieferungen, mit `dry_run=False` NUR manuell + `max_actions=2` +
  Live-Beobachtung.
