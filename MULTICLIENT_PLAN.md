# Multiclient-Plan: 1–4 Metin2-Clients gleichzeitig steuern

> Umsetzungsreifer Architektur-Plan. Verbindlich. Alle file:line beziehen sich auf den
> Stand des Repos `/mnt/c/Users/leonl/Downloads/testordner/Metin2FishBot`.
> Verifizierte Constraints dieser Session (NICHT in Frage stellen):
> (C1) Metin2 ignoriert Background-PostMessage/SendMessage-Klicks → Klick braucht den ECHTEN Cursor + Fenster-Aktivierung (click-to-activate).
> (C2) Capture via `GetWindowDC`+`BitBlt` (`windowcapture.py:270-325`) läuft OHNE Fokus → alle Clients parallel "sehbar".
> (C3) `SetForegroundWindow` ist durch Windows-Focus-Steal blockiert, wenn der aufrufende Prozess nicht selbst Vordergrund ist → NICHT darauf verlassen; click-to-activate + Vordergrund-Verifikation nutzen, Fenster tiled/non-overlapping.
> (C4) Last ist latenz-gebunden (~85–90 % Warten, ~10–15 % aktive Cursor-Zeit) → Time-Multiplexing EINES Cursors ≈ 3,7× Durchsatz bei 4 Clients.

---

## 0. Build-Status (Stand: laufende Umsetzung)

**FERTIG + headless verifiziert (72 neue Unit-/Integrationstests grün, 0 Regressionen):**

| Modul (neu/geändert) | Inhalt | Tests |
|---|---|---|
| `interface/config/paths.py` (geä.) | `client_data_dir()` + `ENV_DATA_DIR` → config/stats/log pro Client isoliert | `test_multiclient_isolation.py` |
| `windowcapture.py` (geä.) | `resync_offsets()` (G4: Offsets nach Tiling neu) | dito |
| `trained_solver.py` (geä.) | ENV-Gate `M2FB_TRAINED_V_READY` (G5: nie 4× rechnen / kein `np.save`-Race, inkl. Tier-2) | dito |
| `puzzle.py` (geä.) | `tetris`/`timer_action` Instanz- statt Klassen-Zustand | dito |
| `cursor_broker.py` | `LeaseScheduler` + `CursorBroker` (FIFO, Hard-Timeout, **Button-Neutralisierung b. Force-Revoke**, **Drag non-revocable**, EOF≠Hang) | `test_cursor_broker.py` |
| `cursor_broker_runtime.py` | `BrokerServer` (selectors-Loop über alle Worker-Pipes + Tick + Stop-Broadcast) | `test_broker_integration.py` |
| `cursor_client.py` | `CursorClient.burst` (neutralize→activate→settle→**Fokus-Gate**→atomare Sequenz mit **Stop-Poll**→finally mouseUp+release) | `test_cursor_client.py` |
| `worker_ipc.py` | blockierendes `acquire`→Grant, Heartbeat, Stop, EOF (echte Pipes) | `test_worker_ipc.py` |
| `supervisor.py` | Prozess-Lifecycle, **Crash-Isolation** (andere laufen weiter), Hang-Heartbeat, **Startup-Grace** (DA-Fix), dynamisch 1–4, Pre-Spawn-Gate | `test_supervisor.py` |
| `monitor_layout.py` | **Monitor-Erkennung + Kachelung** auf Monitor der Wahl, `choose_clients` (>N → markieren) | `test_monitor_layout.py` |
| `worker.py` | headless Entry: kein CTk, **keine Telemetrie**, `to_console=False`, per-Client data_dir, Heartbeat | `test_worker_entry.py` |

**Capstone-Beweis** (`test_broker_integration.py`): Broker-Thread + 2 Worker über echte `os.pipe()` → **nie halten zwei Worker gleichzeitig den Cursor** (`active.max==1`); Crash droppt Lease, FIFO + Stop-Broadcast belegt.

**Devil's-Advocate-Fund (gefixt):** `Supervisor` hätte einen langsam startenden Worker (lädt cv2/Templates/trained_V) fälschlich als „Hänger" gekillt → **Startup-Grace** eingeführt (Crash via Exit-Code gilt weiter sofort).

**Schritt 6 — Bot-Anbindung (Input-Backend-Naht):**
- `cursor_client.py`: `needs_activation`-Flag (Single-Client = aus = **byte-identisch**, Multiclient = an), `LeasedInput` + `make_leased_backend` (jede Bot-Aktion = EIN Lease-Burst). Tests grün.
- **`fishingbot.py` KERN-LOOP angebunden** (Auswerfen/Ködern/Minispiel/ESC/Mount-Tasten): `_DirectBackend` (form-exakt = test-identisch) + `set_input_backend`; atomare keyDown+keyUp. **114 Fishing-Tests grün, 0 Regress.** Tripwire `test_no_direct_input.py` (G6) aktiv.
- **NOCH OFFEN in Schritt 6 — geteilte Inventar-/Refill-Infrastruktur** (feuert WÄHREND des Fischens; für Multiclient zwingend, sonst Cross-Client-Drag-Korruption, Finding #1): `interface/inventory_runner.py`(7), `interface/inventory_discard_runner.py`(5, gehaltener Drag!), `interface/inventory_campfire_runner.py`(5), `inventory/hover.py`(2). `interface/refill.py` ist bereits `api`-injizierbar (kein direktes pydirectinput) → nur geleastes `api`. **Inventar = geteilt über fishing/puzzle/energiesplitter → einmal wiren deckt alle Modi.**
- OFFEN: `puzzle.py`(15), `interface/seher_runner.py`(9) analog; `worker.run_mode` Modus-Schleife headless (nutzt `make_leased_backend`); 1× Live-Smoke (Tasten-Hold/Drag via Lease-Pfad).

**OFFEN (braucht Live-Spiel / CTk — nicht headless verifizierbar):**
- **Q1** (harte Vorbedingung): click-to-activate-Zone pro Modus am echten Spiel bestätigen (`multiclient_probe.py activatetest` gebaut, aber Focus-Steal verhindert sauberes Headless-Messen → manuell durch Nutzer/Integration).
- **Schritt 13/14**: GUI-Multiclient-Bereich + Tray/F6 (braucht customtkinter + Desktop).
- **Schritt 11/12**: reale 2→4-Client-Integration + Occlusion-Capture-Test (offene Frage: GetWindowDC bei VERDECKTEM Fenster).

---

## 1. Ziel & Erfolgskriterien

**Ziel:** Aus EINER Bot-Steuerung 1–4 Metin2-Clients gleichzeitig fahren, jeden in
einem beliebigen der 4 Modi (Energiesplitter / Puzzle / Seherwettstreit / Fischen),
auch gemischt.

**Erfolgskriterien (alle messbar/prüfbar):**

1. **Variabel 1–4:** Nutzer wählt zur Laufzeit 1, 2, 3 oder 4 Clients; je Client ein
   eigenes Metin2-Fenster (HWND) per Picker. Hinzufügen/Entfernen ohne Neustart.
2. **Crash-Isolation (höchstgewichtet):** Stürzt EIN Client ab (Segfault in cv2/pydirectinput,
   OOM, unhandled Exception, harter Hang) → die übrigen laufen **beweisbar** weiter.
   Strukturell garantiert durch OS-Prozessgrenze (siehe §2).
3. **Alle 4 Modi** laufen je Client unverändert in ihrer State-Machine; nur die Außenkanten
   (Capture/Cursor/Log/Files/HWND) sind umgeleitet.
4. **Kein Datei-Cross-Talk:** je Client eigenes `%APPDATA%/Metin2FishBot/client-<idx>/`
   (stats.json, config-Overlay, results.jsonl, *_debug.log, Debug-PNG). Lost-Update,
   Truncation, Interleave verschwinden.
5. **Cursor-Korrektheit:** kein Klick landet im falschen Fenster (Serialisierung +
   click-to-activate + Vordergrund-Verifikation).
6. **Durchsatz:** ≥ 3,5× bei 4 Clients gegenüber 1 Client (Ziel 3,2–3,7×).
7. **Single-Client-Pfad bleibt unverändert schnell** (Broker unkontestiert, Overhead vernachlässigbar).
8. **F6** stoppt ALLE Clients sofort und stellt das Steuerfenster wieder her (Restore aus Tray/Iconbar).

---

## 2. Architektur-Überblick (Gewinner + Begründung + Grafts)

**Gewinner: Prozess-pro-Client + zentraler Cursor-Broker + Supervisor** (Judge-Score 8,7).

```
            ┌──────────────────────────────────────────────┐
            │  Steuer-Prozess (Supervisor + GUI + Broker)   │
            │                                               │
            │  - GUI (CTk): Client-Auswahl 1-4, Picker      │
            │  - Supervisor: dict {idx: subprocess.Popen}   │
            │  - CursorBroker: 1 Thread, FIFO+Aging-Queue   │
            │    serialisiert ALLE physischen Cursor-Bursts │
            │  - F6 StopHotkeyWatcher (global)              │
            └───────┬───────────┬───────────┬──────────────┘
   DEDIZIERTES IPC-Pipe-Paar pro Worker (NICHT stdin/stdout — siehe §4.1/§5.1:
   stdout ist von debuglog belegt, daher eigenes os.pipe()-Paar je Richtung)
                    │           │           │
        ┌───────────▼─┐ ┌───────▼─────┐ ┌───▼──────────┐
        │ Worker 0    │ │ Worker 1    │ │ Worker 2..3  │
        │ worker.py   │ │ worker.py   │ │ worker.py    │
        │ (headless,  │ │ (headless,  │ │ (headless,   │
        │  KEINE CTk- │ │  KEINE CTk- │ │  KEINE CTk-  │
        │  App!)      │ │  App!)      │ │  App!)        │
        │ --client 0  │ │ --client 1  │ │ --client N   │
        │ --hwnd ...  │ │ --hwnd ...  │ │ --hwnd ...    │
        │ EIN Bot     │ │ EIN Bot     │ │ EIN Bot       │
        │ (beliebiger │ │ (beliebiger │ │ (beliebiger   │
        │  Modus)     │ │  Modus)     │ │  Modus)       │
        └─────────────┘ └─────────────┘ └──────────────┘
```

**Warum dieses Modell:**

- **Fehler-Isolation strukturell statt durch Disziplin.** Jeder Worker ist ein eigener
  Python-Interpreter mit eigenem Heap/GIL/Namespace. Ein cv2-Segfault, OOM oder Hang
  beendet ausschließlich diesen Worker; der Supervisor erkennt den toten Prozess
  (`Popen.poll()` ≠ None oder Pipe-EOF) und lässt die anderen unberührt weiter laufen.
- **Die komplette Modul-Global-Hazard-Liste verschwindet per Konstruktion** —
  `_PREFERRED_HWND` (`windowcapture.py:30`), `pydirectinput.PAUSE`, `_TEMPLATE_CACHE`
  (`energiesplitter/detect.py:129`), `_V` (`trained_solver.py:61`), `log`-Singleton
  (`debuglog.py:233`), `_align_cache` (`inventory/grid.py:178-179`) sind pro Prozess
  privat. Keine Facade muss sie bewachen.
- **Kleinster Eingriff in die Geschäftslogik.** Die bestehenden Bot-State-Machines
  (`run_loop.py:81`) bleiben unverändert. Nur die **Input-Schicht** (jeder `pydirectinput`-Aufruf)
  geht hinter einen `CursorClient`-Adapter, der eine Lease beim Broker zieht.
  **ACHTUNG — hack.py ist KEIN Worker-Entry (Korrektur):** Die frühere Annahme, ein Worker sei
  einfach `hack.py` mit CLI-Args, ist gegen den Code falsch. `hack.py` hat **kein argparse**,
  baut bei `:66` die volle CTk-`App(cfg)` und geht bei `:79` in `app.mainloop()`; die GUI-App
  erzeugt intern **BEIDE** Bots (`interface/app/__init__.py:102-104: FishingBot()` **und**
  `PuzzleBot()`) und schaltet Modi exklusiv via RunLoop/Daemon-Thread. Ein Worker, der `hack.py`
  startet, würde also 4× die ganze GUI hochfahren. → Es wird ein **echter headless Worker-Entry
  `worker.py`** spezifiziert (§5.1, Build-Schritt 8), der OHNE CTk-App genau EINEN Modus-Bot baut
  und über `RunLoop`/`seher_runner` headless tickt.

**Preis (akzeptiert):** ~3,2–3,7× statt theoretischer 3,7× (IPC-Hop pro Burst, 4× Interpreter-RAM).
Da die Last latenzgebunden ist (C4), ist der IPC-Hop pro Burst (< 1 ms lokale Pipe)
vernachlässigbar gegen den Aktivierungs-Settle (30–150 ms). Einziger echter SPoF: der Broker —
zustandsarm und respawnbar, abgesichert per Lease-Hard-Timeout (einziger Hang-Detektor, mit
Button-Neutralisierung) + Pipe-EOF-Lease-Drop (nur Crash) — siehe §4.3, Findings #1/#2.

**Übernommene Grafts (aus den unterlegenen Plänen, hier verbindlich verankert):**

- **G1 (aus Plan 1) — Vordergrund-Verifikation als HARTE Gate vor JEDEM Burst:**
  Nach click-to-activate + Settle prüft der Worker `win32gui.GetForegroundWindow() == self.hwnd`.
  Mismatch → Burst abbrechen, Lease freigeben, retry (max 3×), dann Frame überspringen.
  Gilt für Maus- UND Tasten-Bursts. (Bestehender Pfad `windowcapture.py:160-180 focus_window` wird NICHT pro-Klick genutzt — er ist per C3 unzuverlässig.)
- **G2 (aus Plan 1) — atomare Sequenz pro Lease:** Eine ganze logische Aktion (z. B. Ctrl+E mit
  0,1 s Hold, oder ein Drag mouseDown→moveTo→mouseUp) wird in EINER Lease ausgeführt, nie über
  zwei Leases gesplittet. `pydirectinput.PAUSE` wird NUR innerhalb der gehaltenen Lease gesetzt.
- **G3 (aus Plan 2) — FIFO + Aging/Round-Robin im Broker + Burst-Längen-Cap:** Ein klickintensiver
  Modus (z. B. Inventar-Discard) wird in mehrere Leases gesplittet (max. Lease-Hold per Cap),
  die zwischendurch freigeben, damit kein Worker den Cursor dauerhaft belegt.
- **G4 (aus Plan 1/2) — Lease-geschütztes Re-Tiling:** Add/Remove eines Clients ordnet die Fenster
  neu (`MoveWindow`/`SetWindowPos`) NUR unter gehaltener globaler Cursor-Lease; danach friert jeder
  betroffene Worker `offset_x/offset_y` neu aus `GetWindowRect` ein (sonst stale-offset → Klick daneben).
- **G5 (aus Plan 1) — trained_V Pre-Spawn-Gate:** Supervisor baut/lädt `trained_V.npy` 1× VOR jedem
  Worker-Spawn (atomic tmp→`os.replace`), Worker prüfen beim Start nur noch Existenz (Assert) und laden read-only.
- **G6 (aus Plan 1/2) — Tripwire:** Kein direkter `pydirectinput`-/`SetForegroundWindow`-Aufruf außerhalb
  des `CursorClient`-Adapters; Lint/Grep-Test erzwingt das (siehe §9 T9).

---

## 3. Globaler-Zustand-Refactor (Tabelle)

Im Prozess-pro-Client-Modell sind Modul-Globals automatisch prozessprivat. Drei Klassen
von Maßnahmen bleiben dennoch nötig: **(A) Picker→HWND je Worker**, **(B) Datei-Pfade je Worker**,
**(C) Geometrie/Offset nach Window-Move neu lesen**.

| Modul-Global (Datei:Zeile) | Heute | Wird per-Client zu | Maßnahme |
|---|---|---|---|
| `windowcapture._PREFERRED_HWND` (`windowcapture.py:30`) | prozessweites Singleton, `set/get/clear_preferred_hwnd` (`:33-54`); `WindowCapture.__init__` liest es (`:231-235`) | je Worker EIN HWND, vom Supervisor per CLI `--hwnd <int>` übergeben | Worker ruft beim Start `windowcapture.set_preferred_hwnd(args.hwnd)` BEVOR `set_to_begin()` läuft. Da je Worker ein Prozess → kein Race. **Picker im Supervisor** nutzt `enumerate_game_windows("METIN2")` (`windowcapture.py:183-210`, liefert `{hwnd,w,h,x,y}`) zur Anzeige/Zuordnung. |
| Geometrie-Maße `BORDER_PIXELS=8`, `TITLEBAR_PIXELS=30` (`windowcapture.py:21-22`) | Modul-Konstanten, von `__init__` (`:258-263`) + `client_size`-Mathematik (`:145-146`) genutzt | unverändert geteilt (read-only, identisch für alle) | KEINE Änderung. Sie sind echte Konstanten, kein veränderlicher Zustand. |
| `WindowCapture.offset_x/offset_y` (`windowcapture.py:267-268`) | Instanz-Attribut, EINMALIG im `__init__` aus `GetWindowRect` eingefroren | je Worker korrekt, ABER nach Tiling-`MoveWindow` veraltet | Neue Methode `WindowCapture.resync_offsets()`: liest `win32gui.GetWindowRect(self.hwnd)` neu und setzt `offset_x/offset_y` neu (Code identisch zu `:242,267-268`). Supervisor sendet nach jedem Re-Tiling die IPC-Nachricht `{"cmd":"resync"}`; Worker ruft `self.wincap.resync_offsets()` (G4). |
| `pydirectinput.PAUSE` (gesetzt u. a. `fishingbot.py:2,629`; `puzzle.py:2,758-783`; `energiesplitter/bot.py:889`; `interface/seher_runner.py:201,438-459`) | Modul-Attribut, prozessweit | je Worker privat | KEINE Race-Mitigation nötig (Prozess-isoliert). ABER: alle Setzungen wandern in den `CursorClient`-Adapter, der `PAUSE` NUR innerhalb der gehaltenen Lease setzt (G2) und nach dem Burst restauriert. Direktzugriff verboten (G6). |
| `debuglog.log` Singleton (`debuglog.py:233`); `configure()` öffnet im `'w'`-Modus = truncate (`debuglog.py:43-55`); **stdout-Senke** `to_console=True` (`hack.py:51`) | prozessweiter Singleton, fester Pfad `%APPDATA%/Metin2FishBot/puzzle_debug.log` + **schreibt auf stdout** | je Worker eigene Logdatei, **stdout NICHT als Log-Senke** | Worker ruft `log.configure(path=<data_dir>/puzzle_debug.log, to_console=False)` mit `data_dir = %APPDATA%/Metin2FishBot/client-<idx>/`. **`to_console=False` ist Pflicht** (HIGH): liefe debuglog weiter auf stdout, vermischte sich der intensive Bot-Log mit dem geplanten JSON-IPC → Parser-Korruption beim Supervisor. Daher (a) Worker zwingt `to_console=False` UND (b) der IPC läuft NICHT über stdin/stdout, sondern über ein dediziertes `os.pipe()`-Paar (§4.1/§5.1). Da Pfad disjunkt → kein Truncation-Cross-Talk, kein Interleave. |
| `stats.DEFAULT_STATS_PATH` (`stats.py:34-37`); `save()` atomar aber ohne Cross-Proc-Lock (`stats.py:172-218`); `_TMP_SEQ`/`_TMP_SEQ_LOCK` (`stats.py:221-222`) | gemeinsame `stats.json` → Lost-Update | je Worker eigene `stats.json` unter `client-<idx>/` | Worker setzt vor `statsmod.load()` den Pfad auf `<data_dir>/stats.json`. Supervisor aggregiert für die Anzeige read-only über alle `client-*/stats.json`. `_TMP_SEQ` ist durch PID ohnehin kollisionsfrei → bleibt. |
| `config.json` (`interface/config/paths.py:80-95`) | gemeinsame Datei, Last-Writer-Wins beim Stop | Basis read-only geteilt + per-Client-Overlay | Supervisor liest die Basis-`config.json` 1×; jeder Worker bekommt seine Modus-/Key-Auswahl per CLI `--mode <name>` + lädt/schreibt ein **Overlay** `<data_dir>/config.json` (nur die client-spezifischen Felder). Basis-Datei wird von Workern NICHT mehr geschrieben. |
| `trained_solver._V` (`trained_solver.py:61`); `load_V` ohne Lock, `np.save` race (`:109-144`); **Tier-2-Pfad** gebündelte `trained_V.npz` via `respath` + optionaler `np.save`-Spiegel (`:118-144`) | 4× compute (4×12 s, ~536 MB Peak), korrumpierte `.npy`; **zusätzlich Tier-2 `np.save`-Race** auf den Spiegel | 1× shared read-only | Supervisor baut/lädt `trained_V.npy` 1× VOR Spawn (atomic tmp→`os.replace`), setzt ENV `M2FB_TRAINED_V=<pfad>` + `M2FB_TRAINED_V_READY=1`. `load_V` (`trained_solver.py:109-144`) bekommt einen frühen Pfad: ist `M2FB_TRAINED_V_READY` gesetzt → nur `np.load`, NIE `_compute_V`/`np.save`. **Wichtig (HIGH-Korrektur):** Das ENV-Gate G5 muss AUCH den Tier-2-Spiegel (`:118-144`) abdecken — im READY-Fall den optionalen `np.save`-Spiegel der gebündelten `.npz` ebenfalls überspringen, sonst bleibt der `np.save`-Race in Tier-2 bestehen. Worker-Assert: Datei existiert, sonst hartes Fail (G5). |
| `energiesplitter/detect.py:129 _TEMPLATE_CACHE`; `seher/detect.py:23 _title_tpl`; `seher/flow.py:26 _cache`; `fishing_chat._TEMPLATES_CACHE`/`_KNOWN_NAMES_CACHE`; `fishing_detect._golden_ok_cache` | prozessweite Lazy-Caches | je Worker privat (read-only ndarrays) | KEINE Änderung. Pro Prozess je ein Cache; read-only nach erstem Load; kein Race über Prozessgrenzen. |
| `PuzzleBot.tetris = Tetris()` (CLASS-Level, `puzzle.py:239`); `timer_action=time()` (`:241`); `stop_signal=NULL_SIGNAL` (`:261`) | Klassen-Attribut → von Instanzen geteilt (vor `set_to_begin`) | je Instanz eigener Zustand | In `PuzzleBot.__init__` verschieben: `self.tetris = Tetris()`, `self.timer_action = time()`. (Im Prozess-Modell harmlos, weil je Worker nur EINE Instanz — aber korrekt machen, sonst latente Falle bei Tests, die zwei Instanzen erzeugen.) `stop_signal` wird von `RunLoop` ohnehin per Lauf injiziert (`run_loop.py:101,189-202`). |
| `stop_signal.NULL_SIGNAL` (`stop_signal.py:370`) | Prozess-Singleton, Klassen-Default | je Worker privat | KEINE Änderung (wird nie gesetzt, nur Default; `RunLoop` ersetzt ihn). |
| `inventory.grid._align_cache`/`_align_cache_lock` (`inventory/grid.py:178-179`); `interface.inventory_runner._grid_lock_loaded` (`:444-445`) | prozessweiter Raster-Cache / One-Shot-Flag | je Worker privat | KEINE Änderung (Prozess-isoliert). Die per-Fenster richtige Geometrie ergibt sich aus dem per-Worker HWND. |
| `seher_runner` `RESULTS_FILENAME`/`_append_jsonl` (`interface/seher_runner.py:52,104-110`); `_save_debug_frame` feste Namen (`:479-486`) | gemeinsame `seherwettstreit_results.jsonl` + überschriebene PNGs | je Worker eigenes `client-<idx>/` | `results_path()` und `_save_debug_frame()` schreiben relativ zu `data_dir` (per ENV `M2FB_DATA_DIR` gesetzt). |
| **Telemetrie** `telemetry/client.py:38 _sender_thread` (modul-globaler Sender-Thread) + `:39 _stop_event` + `:42 _LEADERBOARD_CACHE`; gestartet per App-Lifecycle (`interface/app/lifecycle.py:62,143 _start_telemetry`) | EIN prozessweiter Sender-Thread, gebunden an die `install_id` aus der geteilten Basis-`config.json` | **im Worker DEAKTIVIERT** | **HIGH — vom Plan bisher übersehen.** 4 Worker würden 4 parallele Sender unter DERSELBEN `install_id` posten → Server-seitiger Cross-Talk/Doppelzählung. **Entscheidung (verbindlich): Telemetrie im Worker NICHT starten** — der headless `worker.py` ruft `_start_telemetry` NIE auf. Senden übernimmt allein der Supervisor (aggregiert über alle `client-*/stats.json`, read-only). Falls später doch Worker-Telemetrie gewünscht: pro Worker eigene `install_id` + Sender-Suppression. |
| **HWID** `telemetry/hwid.py:34 _process_id` (prozess-stabile Zufalls-ID; `get_hwid()` liefert pro Prozess eine ANDERE Identität) | pro Prozess eine eigene Zufalls-ID | je Worker ohnehin eigene ID — aber irrelevant, da Telemetrie im Worker aus | **HIGH-Teilbefund.** Da `get_hwid()` keine Maschinen-Hash, sondern eine prozess-zufällige ID ist, hätte jeder der 4 Worker eine andere „Identität" — würde die Telemetrie-Doppelzählung zusätzlich verschmutzen. Durch die Worker-Telemetrie-Abschaltung (Zeile darüber) entschärft; keine weitere Maßnahme nötig. |
| `fishing_chat._SLUG_TO_NAME` (`fishing_chat.py:492`) + `_KNOWN_NAMES_CACHE` (`:617`) + `_TEMPLATES_CACHE` (`:401`) | prozessweite Lazy-Caches | je Worker privat (read-only nach Load) | KEINE Änderung (Vollständigkeitshalber gelistet). Prozess-privat, read-only nach erstem Load → kein Cross-Proc-Race; kein Bruch. |

**Single Source of Truth für `data_dir`:** Worker liest beim Start ENV `M2FB_DATA_DIR`
(vom Supervisor gesetzt = `%APPDATA%/Metin2FishBot/client-<idx>/`, vom Supervisor `os.makedirs(exist_ok=True)`).
Eine zentrale Hilfsfunktion `interface/config/paths.py:client_data_dir()` liefert ihn; alle
pfadbildenden Stellen (`debug_log_path`, `DEFAULT_STATS_PATH`, `results_path`, `sibling_path`)
gehen über sie.

---

## 4. Cursor-Scheduler (Broker)

### 4.1 Mechanik

- **Ein Broker-Thread** im Supervisor-Prozess hält die einzige Cursor-Lease und eine
  **FIFO-Queue mit Aging** (G3). Worker fordern per IPC `{"cmd":"acquire","idx":N}` an,
  bekommen `{"grant":N}` und melden `{"cmd":"release","idx":N}` zurück.
- **Der Worker führt den physischen Burst selbst aus** (er hat `pydirectinput` + sein HWND);
  der Broker vergibt nur das exklusive Recht. Begründung: nur der Worker kennt seine
  Klick-Sequenz; der Broker bleibt zustandsarm/respawnbar (SPoF-Entschärfung).
- **CursorClient-Adapter** (neu, `cursor_client.py`) im Worker kapselt den kompletten Burst:

**IPC-Kanal (HIGH-Korrektur):** Der IPC läuft NICHT über stdin/stdout — stdout ist von der
debuglog-Senke belegt (§3) und würde das JSON-Protokoll korrumpieren. Stattdessen ein **dediziertes
`os.pipe()`-Paar pro Worker** (Supervisor erzeugt die FDs vor `Popen`, übergibt sie per `pass_fds=`
und CLI-Arg `--ipc-fd-in/--ipc-fd-out`). Worker setzt zusätzlich `log.configure(to_console=False)`.

```
# Pseudocode CursorClient.burst(actions, hwnd, mouse_pause, holds_button)
# holds_button=True markiert einen Burst, der eine Maustaste GEHALTEN über die
# Sequenz führt (Drag): energiesplitter/bot.py:970-973 (mouseDown right + 10x moveTo),
# inventory_discard.py:326-349 (mouseDown + 12-Schritt-Sweep). Solche Bursts sind
# unteilbar/non-revocable (siehe §4.3, Finding #1).
self._ipc_send({"cmd":"acquire","idx":self.idx,"holds_button":holds_button})
grant = self._ipc_wait_grant(timeout=LEASE_WAIT_TIMEOUT)   # FIFO-fair
try:
    # (Finding #1) Hardware-Button-State ZWANGSWEISE neutralisieren, BEVOR der Burst startet:
    # ein vorheriger Lease-Holder könnte nach Force-Revoke eine Maustaste physisch gedrückt
    # gelassen haben (EIN globaler OS-Cursor). Ohne dies zieht dessen Taste quer durch dieses
    # Fenster. Verletzt sonst Erfolgskriterium 5.
    pydirectinput.mouseUp(button='left'); pydirectinput.mouseUp(button='right')
    _click_to_activate(hwnd)                 # ein Klick in neutrale Zone ODER 1. Nutzklick (C1) — Q1 ist VOR Build empirisch zu klären (§10)
    sleep(ACTIVATION_SETTLE)                 # 30-150 ms (C3)
    if win32gui.GetForegroundWindow() != hwnd:   # G1 HARTE Gate
        raise FocusNotAcquired                # -> finally released, Worker retryt (max 3x)
    pydirectinput.PAUSE = mouse_pause         # G2: nur jetzt, innerhalb der Lease
    for a in actions:                         # unteilbare Sequenz (G2)
        if self._stop_requested():            # (Finding #4) Stop pollt JEDEN Schritt, nicht erst nach dem Burst
            raise BurstAborted                # -> finally garantiert mouseUp + release
        a()                                   # click / keyDown+keyUp / drag
finally:
    # (Finding #1/#4) Garantiert beide Tasten lösen, egal ob normaler Exit, Focus-Fail oder Stop-Abbruch:
    pydirectinput.mouseUp(button='left'); pydirectinput.mouseUp(button='right')
    self._ipc_send({"cmd":"release","idx":self.idx})
```

**Stop-Interruptibility im Worker (Finding #4):** Der `StopHotkeyWatcher`-Mechanismus
(`stop_signal.py:162-176`, sub-0.2 s Anspruch, Erfolgskriterium 8) muss im Worker repliziert
werden: ein eigener Daemon-Thread im Worker setzt ein abort-Flag (gespeist aus dem F6-Broadcast
des Supervisors UND optional lokalem GetAsyncKeyState), das `self._stop_requested()` im
`burst()`-Schleifenkopf abfragt. Ein reiner `{"cmd":"stop"}`-stdin-Broadcast genügt NICHT — der
Worker pollt während des laufenden atomaren Bursts (G2) keinen IPC, also würde Stop sonst erst
nach dem Burst (bis ~1,5 s Cap, im Drag-Fall mit gehaltener Taste) wirken. Beim Abbruch:
garantiertes `mouseUp` (siehe `finally`).

### 4.2 click-to-activate & tiled Layout

- **click-to-activate (C1/C3) — UNVERIFIZIERTE ANNAHME, vor Build klären (HIGH, Finding #3):**
  statt `SetForegroundWindow` soll der erste Klick des Bursts das Zielfenster aktivieren.
  **Die Annahme einer „garantiert harmlosen Zone" ist unbelegt:** In Metin2 ist ein Linksklick
  in die Spielfläche NICHT folgenlos (Charakter-Bewegung/Interaktion/Ziel-Wahl). Die bisherige
  Probe (`multiclient_probe.py`) hat click-to-activate NIE getestet — sie testete nur PostMessage
  (laut C1 tot). Es gibt also KEINE Evidenz, dass click-to-activate ohne Seiteneffekt aktiviert.
  Der bisher genannte Punkt `offset_x + w//2, offset_y + 5` (knapp unter Titelleiste) ist nur ein
  **Kandidat**, kein verifizierter Ankerpunkt.
  → **Pflicht vor Build-Schritt 5/6:** Q1 empirisch klären (§10). Pro Modus eine reaktionsfrei
  verifizierte Zone messen (Titelleiste ist seiteneffekt-sicherer, aktiviert aber evtl. nicht den
  Tastatur-Fokus identisch wie ein Spielflächen-Klick → messen). Alternativ den ersten **Nutz**klick
  als Aktivierungsklick nur dort verwenden, wo er ohnehin harmlos ist; sonst Aktivierung von Tasten-/
  Drag-Bursts trennen. Der `burst()`-Pseudocode (§4.1) setzt diese Zone NICHT mehr als gegeben voraus.
- **Tiled, non-overlapping Layout (Voraussetzung):** Supervisor ordnet die 1–4 Fenster beim
  Start/Add/Remove kachelweise an (`win32gui.SetWindowPos`/`MoveWindow`): 1=Vollbreite, 2=nebeneinander,
  3/4=2×2-Gitter, je auf Standard-Client-Größe (Spiel liefert 800×600 → Fensterrahmen +8/+30).
  Keine Verdeckung → click-to-activate greift verlässlich, kein fremdes Fenster fängt den Klick ab.
- Nach jedem `SetWindowPos` sendet der Supervisor `{"cmd":"resync"}` an alle betroffenen Worker (G4).

### 4.3 Fairness, Anti-Starvation, Anti-Deadlock

- **FIFO + Aging (G3):** Queue ist FIFO; ein wartender Worker, dessen Wartezeit ein Aging-Threshold
  übersteigt, wird vorgezogen → keine Dauer-Bevorzugung eines klickintensiven Modus.
- **Burst-Längen-Cap (G3):** ein Worker darf eine Lease max. `LEASE_HOLD_CAP` (z. B. 1,5 s) halten;
  lange Sequenzen (Inventar-Discard) splittet der Modus in mehrere `burst()`-Aufrufe.
- **Lease-Timeout (Anti-Deadlock, SPoF-Entschärfung):** hält ein Worker länger als `LEASE_HARD_TIMEOUT`
  (z. B. 5 s, > Cap), entzieht der Broker die Lease zwangsweise und vergibt weiter; der betroffene
  Worker wird als "verdächtig hängend" markiert (§5).
- **CRITICAL — Hardware-Button-State beim Force-Revoke neutralisieren (Finding #1):** Der Force-Revoke
  serialisiert nur das **logische** Lease-Recht, NICHT den **physischen** Maustasten-/Cursor-Zustand.
  Es gibt nur EINEN globalen OS-Cursor mit EINEM Button-State. Mehrere Bursts halten eine Maustaste real
  über Zeit gedrückt: `energiesplitter/bot.py:970` (`mouseDown(button='right')` + 10× `moveTo` `:972-973`),
  `inventory_discard.py:326` (`mouseDown()` + 12-Schritt-Sweep `:328-349`). Entzieht der Broker einem
  hängenden Worker A die Lease nach 5 s und vergibt an B, ist A's Taste am physischen Cursor **noch
  gedrückt** und der Cursor steht mitten in A's Drag → A's gehaltene Taste zieht quer durch B's Fenster,
  B's Klicks landen während A's Drag. Das ist kein Fairness-Ereignis, sondern **Cross-Client-Korruption**
  (verletzt Erfolgskriterium 5). **Fix (zweiteilig):**
  1. **Button-Neutralisierung vor jeder Lease-Vergabe (auch nach Force-Revoke):** Bevor der neue
     Lease-Holder seinen Burst startet, wird `mouseUp(left)`+`mouseUp(right)` (pydirectinput) erzwungen —
     zentral durch den neuen Holder im `burst()`-Eingang (§4.1) und zusätzlich vom Broker beim Revoke.
  2. **Drag-Bursts sind unteilbar/non-revocable:** Ein Burst mit gehaltener Taste (`holds_button=True`,
     §4.1) darf vom Hard-Timeout NIE unterbrochen werden → eigener, höherer Cap oder als „non-revocable"
     markiert. Force-Revoke gilt NUR für Bursts ohne gehaltene Taste.
- **Pipe-EOF-Lease-Drop deckt NUR Crash, NICHT Hang (HIGH-Korrektur, Finding #2):** Schließt ein Worker
  (Prozess-Tod/Crash) seine Pipe, während er die Lease hält, erkennt der Broker EOF und gibt die Lease
  sofort frei → kein **toter** Worker blockiert den Cursor. **Aber der EOF-Pfad rettet den HANG-Fall
  NICHT:** Ein Worker, der mitten im Burst HÄNGT (pydirectinput blockiert, Taste gedrückt, oder der
  injizierte `time.sleep(20)` aus dem Hang-Test §10), hält die Pipe OFFEN → kein EOF → der Cursor bleibt
  bis `LEASE_HARD_TIMEOUT` (5 s) blockiert, und dann greift Finding #1. **Konsequenz:** Der Hang-Fall ist
  vom Crash-Fall zu trennen — der Lease-Hard-Timeout ist der EINZIGE Detektor für den Hang und MUSS mit
  der Button-Neutralisierung (Finding #1) gekoppelt sein. Optional: ein Watchdog-Thread im Worker, der bei
  eigener Burst-Überlänge `mouseUp` auslöst.
- **Broker-Respawn:** stirbt der Broker-Thread (sollte nicht, zustandsarm), startet der Supervisor
  ihn neu; offene Leases werden invalidiert, laufende Bursts laufen aus, neue `acquire` warten kurz.

### 4.4 Duty-Cycle-Rechnung (~3,7× bei 4)

- Aktive Cursor-Zeit pro Client ≈ 10–15 % (C4); Wartezeit (Capture/Match/sleep/Settle) ≈ 85–90 %.
- Capture läuft echt parallel (C2, GIL-frei in `BitBlt`/`cv2`, je eigener Prozess) → kein Engpass.
- Mit Cursor-Auslastung `u ≈ 0,15` und 4 Clients sättigt der serialisierte Cursor erst bei
  `1/u ≈ 6,7` Clients. Praktisch deckelt der Aktivierungs-Settle (30–150 ms/Burst) + FIFO-Fairness
  den Durchsatz auf **≈ 3,7× bei 4** (2 Clients ≈ 1,9×, 3 ≈ 2,8×). Prozess-Variante zieht durch
  IPC-Hop + 4× Interpreter-RAM minimal auf **≈ 3,2–3,5×** ab — innerhalb des Erfolgskriteriums (≥ 3,5× Ziel, ≥ 3,2× akzeptiert).
- **Single-Client:** Broker unkontestiert, `acquire` ohne Wartezeit → Overhead = 1 lokaler Pipe-Roundtrip (< 1 ms) pro Burst, vernachlässigbar.

---

## 5. Fault-Tolerance

### 5.1 Supervisor

- Hält `clients: dict[int, ClientHandle]` mit `ClientHandle{idx, hwnd, proc: subprocess.Popen, mode, data_dir, last_heartbeat}`.
- **Worker-Entry ist `worker.py`, NICHT `hack.py` (CRITICAL-Korrektur, Finding #5):** `hack.py` hat kein
  argparse und startet die volle CTk-GUI (`:66 App(cfg)`, `:79 app.mainloop()`), die intern BEIDE Bots
  baut. Der Supervisor startet daher den **echten headless Entry**:
  `subprocess.Popen([sys.executable, "worker.py", "--client", str(idx), "--hwnd", str(hwnd), "--mode", mode, "--ipc-fd-in", ..., "--ipc-fd-out", ...], pass_fds=(...), env=...)`.
- **IPC über dediziertes `os.pipe()`-Paar, NICHT stdin/stdout (HIGH, Finding #7):** stdout ist von der
  debuglog-Senke belegt; JSON-IPC darüber würde korrumpieren. Supervisor erzeugt vor `Popen` zwei
  Pipe-Paare (je Richtung), reicht die FDs per `pass_fds=` + CLI durch. stderr→Logdatei
  `client-<idx>/worker_stderr.log`. Der Worker erzwingt `log.configure(to_console=False)` (§3).
- **Heartbeat:** Worker sendet alle 2 s `{"cmd":"hb","idx":N,"state":...}` über die IPC-Pipe; Supervisor speichert `last_heartbeat`.

### 5.2 Crash-Erkennung & "andere laufen weiter"

Drei unabhängige Detektoren (jeder isoliert von den anderen Workern):

1. **Prozess-Tod:** `proc.poll() is not None` → Exit-Code ≠ 0 = Crash (Segfault/OOM/unhandled).
2. **Pipe-EOF:** Lesen aus der **dedizierten IPC-Pipe** des Workers (nicht stdout — §5.1, Finding #7)
   liefert EOF → Worker-Prozess weg. **Deckt NUR Crash, NICHT Hang** (Finding #2: ein hängender Worker
   hält die Pipe offen).
3. **Heartbeat-Timeout:** `now - last_heartbeat > HB_TIMEOUT` (z. B. 8 s) → harter Hang (Worker lebt, antwortet nicht).
   Im Burst hängt der Worker → der **Lease-Hard-Timeout** (§4.3) ist der EINZIGE Detektor, der den
   blockierten Cursor löst (inkl. Button-Neutralisierung, Finding #1/#2); der Heartbeat-Timeout killt dann den Prozess.
   In diesem Fall: `proc.kill()` (SIGKILL/TerminateProcess) → erzwingt Tod, dann Cleanup.

Bei JEDER Erkennung: Lease des toten/gekillten Idx beim Broker droppen (Pipe-EOF tut das ohnehin),
Eintrag aus `clients` entfernen, GUI-Status auf "abgestürzt" setzen, Fehler in `client-<idx>/worker_stderr.log`
+ zentrale Konsole loggen. **Die anderen `Popen`-Prozesse sind physikalisch unberührt** → keine Aktion nötig.

### 5.3 Per-Worker try/except-Grenze

Jeder Worker (`worker.py`, headless) wickelt seine Tick-Schleife in ein Top-Level `try/except Exception`
(außer `KeyboardInterrupt`): Exception → in `client-<idx>/worker_stderr.log` schreiben,
Exit-Code 1 → Supervisor erkennt via poll(). Innerhalb des `RunLoop.tick` (`run_loop.py:706`)
bleibt die bestehende defensive Kapselung; ein Tick-Fehler beendet den Worker sauber statt still zu hängen.

### 5.4 Restart-Policy

- **Default: kein Auto-Restart** (ein crashender Modus crasht meist reproduzierbar → Restart-Loop vermeiden).
- **Opt-in (GUI-Checkbox "Auto-Neustart"):** bei Crash max. `RESTART_MAX` (z. B. 3) Neustarts
  innerhalb `RESTART_WINDOW` (z. B. 120 s); danach Client als "ausgefallen" markieren, kein weiterer Versuch.
  Vor jedem Restart: HWND noch gültig? (`win32gui.IsWindow`) — sonst Picker-Re-Auswahl anfordern.

### 5.5 Dynamisches Hinzufügen/Entfernen 1–4 zur Laufzeit

- **`add_client(hwnd, mode)`:** (1) globale Cursor-Lease ziehen (G4); (2) `data_dir` anlegen;
  (3) Layout neu kacheln (`SetWindowPos`); (4) `resync` an alle bestehenden Worker; (5) Lease freigeben;
  (6) neuen `Popen` spawnen. Spawnen NACH Lease-Release, damit kein Klick während des Fenster-Moves passiert.
- **`remove_client(idx)`:** (1) `{"cmd":"stop"}` per IPC senden → Worker beendet sauber (botting=False, teardown, exit 0);
  (2) `proc.wait(timeout=5)`; bei Timeout `proc.kill()`; (3) Lease droppen; (4) Eintrag entfernen;
  (5) globale Lease ziehen, Layout neu kacheln, `resync`, Lease frei.
- Obergrenze hart 4 (UI verhindert mehr); Untergrenze 1 (das ist der heutige Pfad).

---

## 6. Per-Modus-Integration

### Gemeinsames Client-Interface

Es wird KEIN neues async-Interface gebaut (Prozess-Modell). Stattdessen ein **dünner Adapter**:
jeder bestehende Bot bekommt seine Cursor-/Tasten-Aufrufe auf `cursor_client.CursorClient` umgeleitet.
`CursorClient` ist im Worker-Prozess ein Singleton, initialisiert in `worker.py` (§5.1, Finding #5) aus `--client`/`--hwnd`
+ den IPC-Pipes. Vertrag: `cc.click(sx, sy)`, `cc.right_click(sx, sy)`, `cc.key(key, hold)`,
`cc.drag(x1,y1,x2,y2)` — jede Methode ist intern ein `burst()` (§4.1) inkl. click-to-activate +
Vordergrund-Gate (G1) + atomarer Sequenz (G2). Direkter `pydirectinput`-Aufruf ist verboten (G6).
**`cc.drag(...)` setzt intern `holds_button=True`** → der Burst ist non-revocable und der Hard-Timeout
unterbricht ihn NICHT (§4.3, Finding #1). Jeder `burst()` neutralisiert am Eingang und im `finally`
den Hardware-Button-State (`mouseUp` left+right, §4.1).

### 6.1 Energiesplitter

- **Entry:** `run_loop.py:557 on_start` → `energiesplitter/bot.py:299 set_to_begin` → `:475 runHack` → `flow_dagger.py:29 _tick_dagger`.
- **Hooks:**
  - `set_to_begin` (`energiesplitter/bot.py:332`): `WindowCapture(constants.GAME_NAME)` bleibt — HWND kommt aus dem schon gesetzten `_PREFERRED_HWND` (Worker hat ihn beim Start gesetzt). Keine Signatur-Änderung nötig.
  - Klicks `_left_click`/`_right_click`/`_birdseye_drag` (PAUSE-Setzung `energiesplitter/bot.py:889,900,913,968`): jeden Body durch `cc.click/.right_click/.drag` ersetzen; PAUSE-Setzung entfällt (geht in CursorClient, G2).
  - Tasten (Inventar-Toggle, ESC) nach `_focus_game` (`energiesplitter/bot.py:661-683 SetForegroundWindow`): `_focus_game` ENTFERNEN; Tasten über `cc.key(...)` (click-to-activate + Gate übernimmt Aktivierung, C3).
- Counter/State bleiben Instanz-Attribute (`energiesplitter/bot.py:194-204`) — kein Sharing-Problem.

### 6.2 Puzzle

- **Entry (headless):** `worker.py` baut bei `--mode puzzle` GENAU EINEN `PuzzleBot()` (NICHT über die
  GUI `interface/app/__init__.py:102-104`, die beide Bots erzeugt — Finding #5) → `run_loop.py:808 puzzlebot.runHack()` → `puzzle.py:276 set_to_begin` → `:1164 runHack` (States 0–9).
- **Hooks:**
  - `puzzle.py:239,241` CLASS-Level `tetris`/`timer_action` → in `__init__` verschieben (§3).
  - `set_to_begin` (`puzzle.py:282 WindowCapture(...)`): HWND aus `_PREFERRED_HWND`; `log.configure` (`puzzle.py:279-281`) auf `data_dir` (§3) umlenken.
  - `pydirectinput.click(x,y)` (Solver-Platzierung, Confirm, Verwerfen, Cake): → `cc.click`/`cc.right_click`.
  - `_press_esc`/`_press_ctrl_e` (`puzzle.py:751-783`, PAUSE=0.1 + `focus_window`): Body → `cc.key('esc')` bzw. `cc.key('e', hold=0.1, with_ctrl=True)`; PAUSE-Setzung + `focus_window` entfernen (G1/G2 in CursorClient). **Wichtig:** Ctrl+E 0,1 s Hold ist EINE atomare Sequenz in EINER Lease (G2).
  - `trained_solver.load_V` (`trained_solver.py:109-144`): ENV-Gate (§3, G5) — nur `np.load`, nie compute/save im Worker.

### 6.3 Seherwettstreit

- **Entry:** `interface/app/views_seher.py:134 _on_seher_start_stop` → Daemon-Thread `seher-session` → `interface/seher_runner.py:716 run_seher_session` → `:732 WindowCapture(...)` → `:177 run_seher_game`.
- **Hooks:**
  - **Achtung Threading:** Seher läuft heute in einem eigenen Daemon-Thread (`views_seher.py:182-195`). Im Worker-Prozess ist das weiterhin EIN Thread — er muss den `CursorClient` (Singleton mit IPC-Pipe) thread-sicher nutzen: ein `threading.Lock` im CursorClient serialisiert den IPC-Versand innerhalb des Workers (der GUI-Thread des Workers könnte parallel z. B. Stop schicken).
  - `pydirectinput.click(screen_x, screen_y)` (`seher_runner.py:215-216,285-295`): → `cc.click`. `screen_xy = wincap.offset_x + anchor + rel` bleibt (Anchor wird pro Frame neu gefunden, `seher/detect.py:47-56`) — aber `wincap.offset_x` MUSS nach Re-Tiling resynct sein (G4).
  - `_press_ctrl_e`/`_press_esc` (`seher_runner.py:438-459`): → `cc.key(...)`, PAUSE-Setzung entfernen.
  - `_append_jsonl`/`results_path` (`seher_runner.py:104-110`) + `_save_debug_frame` (`:479-486`): auf `data_dir` umlenken (§3).
  - `_apply_preferred_hwnd` (`views_seher.py:163`, `window_picker.py:126-146`): im Worker einmalig aus `--hwnd`.

### 6.4 Fischen

- **Entry:** `hack.py:74-75 RunLoop.wire()` → `run_loop.py:706 tick` → `:803 fishbot.runHack()` → `fishingbot.py:546 set_to_begin` → `:636 runHack` (States 0–3).
- **Hooks:**
  - `set_to_begin` (`fishingbot.py:613 WindowCapture(...)`, `:629 PAUSE=0.1`, `:634 initialer Rechtsklick`): HWND aus `_PREFERRED_HWND`; initialen Rechtsklick über `cc.right_click` (dient auch als click-to-activate); PAUSE-Setzung raus.
  - `pydirectinput.keyDown/keyUp(bait_key/cast_key)` (`fishingbot.py:707-731`): → `cc.key(bait_key)`/`cc.key(cast_key)`. Diese Tasten brauchen Fokus → CursorClient aktiviert (G1).
  - `pydirectinput.click(x,y)` Minispiel-Haken (`fishingbot.py:780-813`): → `cc.click`. **Latenzkritisch:** der Haken-Klick muss schnell nach Erkennung kommen → Lease-Priorität ist FIFO-fair; bei 4 Clients ist die Wartezeit < ein paar Bursts (akzeptabel, da Minispiel-Fenster mehrere Sekunden offen).
  - `log.configure`/`stats`/`config`: im headless `worker.py` (nicht `hack.py`) auf `data_dir` (§3)
    setzen, dabei `to_console=False` erzwingen (§3, Finding #7) und Telemetrie NICHT starten
    (kein `_start_telemetry`, §3 Telemetrie-Zeile, Finding #6).

---

## 7. Config & GUI

### 7.1 Client-Auswahl 1–4 + Picker pro Client

> **STAND 2026-06-23 — GEBAUT** (`interface/app/views_multiclient.py`, Reiter „Multiclient").
> Die Markierung wurde gegenüber dem ursprünglichen reinen Dropdown auf **Klick-zum-Erfassen**
> gehoben (User-Wunsch „ausgefeilte Technik, auch bei >4 Fenstern"): Knopf „Fenster markieren"
> → Nutzer klickt das echte Spielfenster → `window_mark.window_from_point`
> (`WindowFromPoint`→`GetAncestor(GA_ROOT)`) löst das Top-Level-Fenster auf, validiert es gegen
> `enumerate_game_windows` und bestätigt per `FlashWindow`. Eindeutig auch bei >4 Fenstern, weil
> der Nutzer **physisch zeigt**. Persistenz `config['multiclient']={count,auto_restart,clients[]}`,
> Dedup „ein Fenster = ein Client", Validierung + Spec-Ableitung in `multiclient_settings.py`
> (headless getestet). „Alle starten" → `launcher.run(specs)` im Thread. **Offen: Live-Test** (GUI,
> echte Klick-Erfassung, realer Spawn). Der ClickCapture-Stepper ist rein/headless getestet.

- Neuer GUI-Bereich "Multiclient" im Steuerfenster (`interface/app/`): eine Liste mit bis zu 4 Zeilen.
  Jede Zeile: **Fenster-Dropdown** (gefüllt aus `enumerate_game_windows("METIN2")`, zeigt `hwnd@x,y`),
  **Modus-Dropdown** (Energiesplitter/Puzzle/Seher/Fischen), **Start/Stop**-Knopf, **Status-Label**
  (idle/läuft/abgestürzt). "+ Client hinzufügen" (max 4), "Client entfernen".
- "Alle starten" → `add_client` für jede konfigurierte Zeile (§5.5). Doppelte HWNDs verhindern (ein Fenster = ein Client).
- Config-Persistenz: `config['multiclient'] = {'clients':[{'hwnd_hint':..., 'mode':...}, ...], 'auto_restart':bool}` in der Basis-`config.json`.

### 7.2 Minimize-to-Tray beim Start + globaler F6-Toggle

- **Tray existiert bereits:** `interface/tray.py` (`available()`, `make_icon(...)` mit Menü Show/Quit),
  Config `window.minimize_to_tray`, `_hide_to_tray`/`_tray_icon` (`interface/app/__init__.py:173-177`,
  `interface/app/settings_effects.py:187-196`, Cleanup `lifecycle.py:32-33`).
- **Beim "Alle starten":** wenn `window.minimize_to_tray` true und `tray.available()` → `self._hide_to_tray()`
  aufrufen, damit das Steuerfenster minimiert/in Tray geht und die Spielfenster frei sichtbar tiled sind.
  Fallback ohne pystray: `self.iconify()` (Iconbar-Minimize).
- **Globaler F6-Toggle:** der bestehende `StopHotkeyWatcher` (`stop_signal.py:162-214`, gewired in
  `run_loop.py:174-176`) wandert in den **Supervisor**-Prozess. Bei F6:
  1. Broadcast `{"cmd":"stop"}` an ALLE Worker → jeder setzt `botting=False` (Pfad `run_loop.py:189-202`, lokal im Worker), stoppt sauber.
     **WICHTIG (Finding #4):** Ein reiner stdin/IPC-Broadcast genügt NICHT für „sofort", weil der
     Worker während eines laufenden atomaren Bursts (G2) keinen IPC pollt → Stop wirkte erst nach dem
     Burst (bis ~1,5 s Cap, im Drag-Fall mit gehaltener Taste). Daher setzt der Broadcast (bzw. ein
     Worker-eigener `StopHotkeyWatcher`, repliziert aus `stop_signal.py:162-176`) das abort-Flag, das
     `CursorClient.burst()` in JEDEM Schleifenschritt abfragt (§4.1 `self._stop_requested()`); der
     laufende Burst wird mit garantiertem `mouseUp` abgebrochen → sub-0,2 s Stop (Erfolgskriterium 8)
     auch für den Worker, der gerade die Lease hält.
  2. Steuerfenster wiederherstellen/vergrößern: `self.deiconify()` + (falls Tray) `self._tray_icon.stop()` + `self.lift()`/`self.focus_force()`.
  Damit ist F6 = Panik-Stop ALLER + Restore. (Innerhalb jedes Workers bleibt sein eigener Tick-Stop für lokale Sauberkeit.)
- Hotkey-String bleibt `controls.stop_hotkey` (Default `f6`); `key_provider` liest ihn wie heute (`run_loop.py:176`).

---

## 8. Build-Reihenfolge (nummeriert, bite-sized, inkrementell, je Schritt testbar)

> Reihenfolge: erst Datei-/HWND-Isolation (sofort mit 1 Prozess testbar), dann Broker (2 Clients),
> dann GUI/Supervisor (4 Clients), zuletzt F6/Tray + Härtung.

1. **`interface/config/paths.py`:** Funktion `client_data_dir()` hinzufügen, die ENV `M2FB_DATA_DIR`
   liest und `os.makedirs(exist_ok=True)`; Fallback = heutiger `%APPDATA%/Metin2FishBot/`. `debug_log_path`,
   `DEFAULT_STATS_PATH`-Bildung, `sibling_path` auf `client_data_dir()` umstellen. *Test:* `M2FB_DATA_DIR=...` setzen, `hack.py` starten, prüfen dass Log/Stats dort landen.
2. **`windowcapture.py`:** `resync_offsets()`-Methode hinzufügen (liest `GetWindowRect`, setzt `offset_x/offset_y` wie `:242,267-268`). *Test:* Fenster nach Init verschieben, `resync_offsets()`, Klick-Koordinate stimmt wieder.
3. **`trained_solver.py:load_V` (`:109-144`):** ENV-Gate (`M2FB_TRAINED_V`/`_READY`) → nur `np.load`, nie `_compute_V`/`np.save` wenn READY. *Test:* mit gesetztem READY + vorhandener `.npy` startet Puzzle/trained ohne 12 s-Compute.
4. **`puzzle.py:239,241`:** `tetris`/`timer_action` von CLASS-Level in `__init__` verschieben. *Test:* `tests/` für Puzzle laufen lassen; zwei `PuzzleBot()`-Instanzen teilen kein Board mehr.
5. **Q1 EMPIRISCH KLÄREN (Vorbedingung für 5b/6, Finding #3):** Pro Modus eine reaktionsfrei
   verifizierte click-to-activate-Zone messen (Titelleiste vs. Spielfläche; aktiviert sie den
   Tastatur-Fokus? löst sie eine Spielaktion aus?). Ergebnis als Konstante/Map dokumentieren, BEVOR
   der Burst-Pfad sie nutzt. *Test:* manuell pro Modus — Aktivierung greift, keine ungewollte Spielaktion.
5b. **Neu `cursor_client.py`:** `CursorClient`-Klasse mit `click/right_click/key/drag` + interner `burst()`
   (Button-Neutralisierung am Eingang+`finally` `mouseUp` left/right [Finding #1], click-to-activate mit
   der in Schritt 5 verifizierten Zone, Settle, `GetForegroundWindow`-Gate G1, atomare Sequenz G2,
   `holds_button`-Flag für Drags [Finding #1], `_stop_requested()`-Poll je Schritt [Finding #4],
   `threading.Lock` für IPC). In dieser Phase **lokaler Stub-Broker** (in-process Lock) statt IPC,
   damit Einzelprozess testbar bleibt.
   *Test:* neuer Unit-Test `tests/test_cursor_client.py` mit gemocktem `pydirectinput`+`win32gui` —
   prüft auch: `mouseUp` wird am Eingang UND im `finally` (auch bei Focus-Fail/Stop-Abbruch) gerufen;
   Stop-Abbruch bricht die Schleife sofort + löst Tasten.
6. **Bots auf `CursorClient` umstellen (je eine Datei, einzeln testbar):**
   6a. `fishingbot.py` (`:629,634,707-731,780-813`) → `cc.*`, PAUSE/Direkt-Klicks raus.
   6b. `puzzle.py` (`:751-783` + Solver-Klicks) → `cc.*`.
   6c. `energiesplitter/bot.py` (`:661-683` `_focus_game` raus; `:889,900,913,968` → `cc.*`).
   6d. `interface/seher_runner.py` (`:215-216,285-295,438-459`) → `cc.*` (+ thread-sichere IPC).
   *Test je Teilschritt:* zugehörige `tests/test_<modus>*.py` grün; 1 Client real fischt/puzzelt korrekt.
7. **Tripwire (G6):** `tests/test_no_direct_pydirectinput.py` — grep über `fishingbot.py`,`puzzle.py`,
   `energiesplitter/`,`interface/seher_runner.py`: kein `pydirectinput.click/keyDown/keyUp/moveTo` und kein
   `SetForegroundWindow` außerhalb `cursor_client.py`/`windowcapture.py`. *Test:* schlägt fehl bei Leak.
8. **Neu `worker.py` (echter headless Worker-Entry, CRITICAL — Finding #5):** NICHT `hack.py` erweitern als
   Default (`hack.py` startet die volle CTk-GUI mit BEIDEN Bots). Neue Datei `worker.py` mit argparse
   `--client`,`--hwnd`,`--mode`,`--ipc-fd-in`,`--ipc-fd-out`. Beim Start: `set_preferred_hwnd(args.hwnd)`;
   `M2FB_DATA_DIR`-getriebenes `data_dir`; `log.configure(to_console=False, path=<data_dir>/...)`
   (Finding #7); **Telemetrie NICHT starten** (kein `_start_telemetry`, Finding #6); GENAU EINEN Modus-Bot
   bauen (je `--mode`: `FishingBot`/`PuzzleBot`/Seher-Runner/Energiesplitter) und über `RunLoop`/
   `seher_runner` OHNE CTk-App headless ticken; `CursorClient` im **IPC-Modus** über das dedizierte
   `os.pipe()`-Paar (`--ipc-fd-in/-out`), NICHT stdin/stdout (Finding #7). Top-Level `try/except` (§5.3) +
   Heartbeat-Sender + Worker-eigener `StopHotkeyWatcher` (Finding #4).
   (Alternativ darf `hack.py` einen `if __name__=='__main__'`+argparse+`--headless`-Zweig bekommen, der
   denselben headless Pfad nimmt — aber kein Platzhalter, echter Code.)
   *Test:* `worker.py --client 0 --hwnd <ID> --mode fishing` als Standalone-Prozess fischt EIN Fenster,
   startet KEINE GUI, sendet KEINE Telemetrie, loggt nicht auf stdout.
9. **Neu `cursor_broker.py`:** Broker-Klasse (FIFO+Aging-Queue, Lease-Cap, Lease-Hard-Timeout, Pipe-EOF-Drop).
   **Force-Revoke neutralisiert den Button-State** (`mouseUp` left/right beim Revoke, Finding #1) und
   **respektiert `holds_button`/non-revocable Drag-Bursts** (kein Hard-Timeout-Entzug, Finding #1).
   Doku-Korrektur: EOF-Drop deckt nur Crash, der Hard-Timeout ist der einzige Hang-Detektor (Finding #2).
   *Test:* `tests/test_cursor_broker.py` — zwei simulierte Worker, FIFO-Reihenfolge, Aging, Timeout-Entzug,
   EOF-Drop; **Force-Revoke ruft `mouseUp` vor Neuvergabe**; ein `holds_button`-Burst wird NICHT entzogen.
10. **Neu `supervisor.py`:** `Supervisor` mit `clients`-dict, `add_client`/`remove_client`, Crash-Detektoren
    (poll/EOF/Heartbeat), Layout-Tiling (`SetWindowPos`), `resync`-Broadcast (G4), trained_V Pre-Spawn-Gate (G5),
    Restart-Policy (§5.4). *Test:* `tests/test_supervisor.py` mit gemockten `Popen` — Spawn von 2, Crash von 1 (Exit 1) → Detektion, anderer lebt; add/remove zur Laufzeit.
11. **Erst-Integration 2 Clients (headless):** Supervisor + Broker + 2 echte `worker.py`-Worker auf 2 Metin2-Fenster,
    beide Fischen. *Test (manuell + `multiclient_probe.py` erweitern):* beide angeln parallel, kein Klick im falschen Fenster, Crash von Worker 1 (`taskkill`) → Worker 0 läuft weiter.
12. **Hochskalieren 4 Clients, gemischte Modi:** 2× Fischen + 1× Puzzle + 1× Seher. *Test:* alle 4 laufen, Durchsatz messen (Erfolgskriterium ≥ 3,5×), Datei-Isolation prüfen (`client-0..3/`).
13. **GUI Multiclient-Bereich (`interface/app/`):** Picker (`enumerate_game_windows`), Modus-Dropdown, Start/Stop pro Zeile, Status, "+/–ient", `config['multiclient']`-Persistenz. *Test:* `tests/test_gui_smoke.py` erweitern; manuell Start/Stop/Add/Remove.
14. **Tray + F6-Global:** beim "Alle starten" `_hide_to_tray()`/`iconify`; `StopHotkeyWatcher` in den Supervisor,
    F6 → Broadcast `stop` + Restore (`deiconify`/`lift`). *Test:* F6 stoppt alle 4 + Steuerfenster kommt zurück.
15. **Re-Tiling unter Lease (G4) verifizieren:** add/remove während ein anderer Worker klickbereit ist → kein Klick daneben (Lease hält Layout-Move ab, danach resync). *Test:* gezielter Stresslauf add/remove im Sekundentakt.

---

## 9. Test-Plan

Das Projekt hat `tests/` (unittest, `conftest.py`, Fixtures). Neue Tests + Erweiterungen:

| ID | Test (Datei) | Prüft | Art |
|---|---|---|---|
| T1 | `tests/test_config_paths.py` (erw.) | `client_data_dir()` respektiert `M2FB_DATA_DIR`, legt an, Fallback ok | Unit |
| T2 | `tests/test_blockers.py` (erw.) | nach `resync_offsets()` stimmt `offset_x/y` für verschobenes (gemocktes) Rect | Unit |
| T3 | `tests/test_trained_solver*` (neu/erw.) | `load_V` mit READY-ENV ruft NIE `_compute_V`/`np.save` (Mock-Spy) | Unit |
| T4 | `tests/test_inventory_*`/Puzzle (erw.) | zwei `PuzzleBot()` teilen kein `tetris.board` mehr (CLASS→`__init__`) | Unit |
| T5 | `tests/test_cursor_client.py` (neu) | `burst()`: Reihenfolge mouseUp→activate→settle→Gate→Sequenz→mouseUp→release; bei `GetForegroundWindow≠hwnd` Abbruch+retry (G1); PAUSE nur innerhalb Lease (G2); **`mouseUp` left+right am Eingang UND im `finally` auch bei Focus-Fail/Stop (Finding #1)**; **Stop-Flag bricht die Schritt-Schleife sofort ab + löst Tasten (Finding #4)** | Unit (Mocks) |
| T6 | `tests/test_cursor_broker.py` (neu) | FIFO-Reihenfolge; Aging zieht Hungernden vor; Lease-Hard-Timeout entzieht; Pipe-EOF dropt Lease; **Force-Revoke ruft `mouseUp` vor Neuvergabe (Finding #1)**; **`holds_button`-Burst wird NICHT vom Hard-Timeout entzogen (Finding #1)** | Unit |
| T6b | `tests/test_worker_entry.py` (neu) | `worker.py` startet headless: KEINE CTk-`App`, genau EIN Bot je `--mode`, KEIN `_start_telemetry`, `to_console=False`, IPC über übergebene FDs (Findings #5/#6/#7) | Unit (Mocks) |
| T7 | `tests/test_supervisor.py` (neu) | **Crash-Isolation:** 3 gemockte `Popen`, einer Exit≠0 / einer Heartbeat-Timeout (→kill) → genau dieser entfernt, die anderen `proc`-Objekte unverändert/leben; add/remove zur Laufzeit konsistent | Unit (Mocks) |
| T8 | `tests/test_supervisor.py` (neu) | Pre-Spawn-Gate: trained_V wird 1× vor erstem Spawn erzeugt (atomic), READY-ENV gesetzt (G5) | Unit |
| T9 | `tests/test_no_direct_pydirectinput.py` (neu) | Tripwire: kein `pydirectinput.*`/`SetForegroundWindow` außerhalb `cursor_client.py`/`windowcapture.py` (G6) | Static/grep |
| T10 | `multiclient_probe.py` (erw.) + manuell | Integration 2→4 echte Worker: paralleles Capture, korrekte Klick-Zuordnung, Durchsatz ≥3,5×, Datei-Isolation | Integration |
| T11 | manuell | F6 stoppt alle + Restore; Tray-Hide beim Start | Manuell |

**Fehler-Isolation gezielt testen (Kernkriterium):**
- **T7 (automatisiert):** Supervisor mit gemockten `Popen`; Worker 1 setzt `poll()→1` (Crash) bzw.
  `last_heartbeat` weit in der Vergangenheit (Hang→kill). Assertion: Worker 0/2 `Popen.kill`/`terminate`
  wurde NICHT aufgerufen, sie bleiben in `clients`; Worker 1 entfernt, Lease gedropt.
- **T10 (real):** 4 Worker laufen; einen per `taskkill /PID` hart killen (simuliert Segfault/OOM).
  Beobachten: andere 3 angeln/puzzeln ungestört weiter; Supervisor meldet "Client N abgestürzt";
  Cursor-Broker hängt nicht (Lease war via Pipe-EOF gedropt).
- **Hang-Test (real, Crash≠Hang — Finding #2):** in einem Worker künstlich `time.sleep(20)` im Burst
  injizieren. Erwartung: die Pipe bleibt OFFEN (kein EOF — EOF deckt NUR Crash), daher greift NICHT der
  EOF-Drop, sondern der **Lease-Hard-Timeout** (§4.3) als einziger Hang-Detektor; er entzieht die Lease
  UND neutralisiert den Button-State (`mouseUp`, Finding #1), dann killt der Heartbeat-Timeout den Worker.
  Assertion: nach dem Entzug ist KEINE Maustaste mehr gedrückt; der nächste Worker klickt sauber im
  eigenen Fenster (kein Quer-Drag); die anderen laufen weiter.
- **Drag-Non-Revocability-Test (real, Finding #1):** ein Worker in einem langen `cc.drag`
  (`holds_button=True`) → der Hard-Timeout entzieht diesen Burst NICHT, der Drag läuft sauber mit
  `mouseUp` zu Ende; erst ein Burst OHNE gehaltene Taste ist revocable.

---

## 10. Risiken & offene Fragen

**Risiken (mit Mitigation):**

- **Focus-Steal trotz click-to-activate (C3):** fremdes Popup/anderer Worker im Settle klaut Fokus →
  Tasten-Burst ins falsche Fenster. *Mitigation:* G1 (`GetForegroundWindow==hwnd`-Gate) bricht ab + retry; tiled non-overlapping Layout.
- **Stale offsets nach manuellem Window-Move durch den Nutzer:** offsets veralten ohne `resync`.
  *Mitigation:* G4 nach Tiling; zusätzlich optional per-Burst re-validieren (`GetWindowRect`-Vergleich) wenn HWND existiert.
- **Broker-SPoF / Lease-Deadlock:** *Mitigation:* zustandsarm + respawnbar, Lease-Hard-Timeout, Pipe-EOF-Drop (§4.3).
- **IPC-Latenz bei latenzkritischem Fisch-Haken-Klick:** FIFO-Wartezeit könnte den Klick verzögern.
  *Mitigation:* Minispiel-Fenster ist mehrere Sekunden offen; Burst-Cap hält Leases kurz; bei Bedarf
  Mini-Priorität für Fisch-Haken-Bursts (offene Frage Q3).
- **4× Interpreter-RAM:** ~4× Basis-RAM + 4× Template-Caches. *Mitigation:* akzeptiert (Desktop-Kontext);
  trained_V als Datei geteilt (kein 4×536 MB), Templates pro Prozess klein.
- **HWND-Recycling nach Crash/Neustart eines Metin2-Clients:** alter HWND ungültig.
  *Mitigation:* vor Restart `win32gui.IsWindow`; sonst Picker-Re-Auswahl (§5.4).

**Offene Fragen (zur Klärung vor/während Build):**

- **Q1 (HOCHGESTUFT zu HARTER Vorbedingung, Finding #3):** Welche Klickzone pro Fenster aktiviert das
  Fenster OHNE Spielaktion-Seiteneffekt? In Metin2 ist ein Linksklick in die Spielfläche NICHT folgenlos;
  die „harmlose Zone" ist UNBELEGT (`multiclient_probe.py` hat click-to-activate nie getestet, nur das
  laut C1 tote PostMessage). → **Muss VOR Build-Schritt 5b/6 empirisch geklärt werden** (Build-Schritt 5),
  pro Modus, mit Messung ob Titelleiste den Tastatur-Fokus identisch setzt. Bis dahin ist der
  Aktivierungspfad nicht verifiziert.
- **Q2:** Soll `auto_restart` Default an oder aus sein? (Plan: aus — Crash meist reproduzierbar.)
- **Q3:** Braucht der Fisch-Haken-Klick echte Lease-Priorität (Bypass FIFO/Aging) oder reicht FIFO+kurze Bursts?
- **Q4:** Exaktes Tiling-Raster bei 3 Clients (2+1 vs. nebeneinander) und Verhalten bei Multi-Monitor?
- **Q5:** Stats-Aggregation: getrennt pro Client anzeigen, oder zusätzlich summiert in der GUI?
- **Q6:** Soll der Supervisor selbst auch als gefrorene EXE gebaut werden (PyInstaller spawnt `sys.executable`
  mit `--client`)? Build-Spec (`Metin2FishBot.spec`) muss den Worker-Entry abdecken.
