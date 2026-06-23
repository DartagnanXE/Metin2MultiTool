# Roadmap — Metin2 MultiTool

**Stand:** 2026-06-21 · App-Version 1.4.2 · Zielgruppe: Laien-EXE · Architektur-Doktrin: **rein extern** (Screenshot + OpenCV/Template + OCR + simulierte Eingabe), **kein** Memory-Read / Injection / Packets, **kein** Open-World-Combat/Pathing.

> Diese Datei wurde am 2026-06-21 vom reinen *Kandidaten-Ranking* auf den **Ist-Stand** umgestellt: das frühere „Fishing Bot" ist zum **Metin2 MultiTool** gewachsen — mehrere Minispiel-Module sind gebaut und ausgeliefert. §1 = was steht, §2 = Multi-Client (neue Architektur, parallele Clients), §3–§6 = was noch kommt (Kandidaten + ehrliche Risiken).

---

## 1. Gebaut & ausgeliefert (Referenz-Architektur)

Alle Module folgen demselben Muster: **fixe-UI-Erkennung (Template/OCR) → Solver/Policy → simulierte Eingabe**, mit Detect-before-Action (Fehlkalibrierung → sicherer Stopp statt Fehlklick), Stop-Hotkey **F6** und Timing-Jitter.

| Modul | Status | Kern |
| ----- | ------ | ---- |
| **Angeln** (Fishing) | ✅ Core, seit v1.0 | Auto-Köder/Auswurf + Fang-Minispiel; Chat-OCR (Glyphen-Atlas); Whitelist (KEEP/REMOVE/CAMPFIRE); Köder-Nachlegen aus dem Inventar; Lagerfeuer-Grill (35-s-Limit) |
| **Stein-Puzzle** (Fischpuzzle) | ✅ inkl. Deluxe + Härtung | Beweisbar optimaler Solver (MDP-Value-Iteration / Default-Greedy); Board-Detektion default/auto/mark; **Deluxe-Box (2×3 Magenta)**; Open-Loop-Härtung (`puzzle_safety`); Box-Auto-Nachlegen aus dem Inventar (Fokus-fest) |
| **Seherwettstreit** | ✅ seit v1.2.0 | Karten-Event-Autoplayer (Ctrl+E → spielen → Belohnung → Schleife); event-getriebene Erkennung (Board stabil → Zug → Quittung via Kreuz); JSONL-Protokoll; Nach-Aktion (Charwechsel/Client-Beenden) |
| **Energiesplitter** | ✅ Hammer + Dolch | Hammer kaufen (Alchemist) + Dolche kaufen/verarbeiten (Waffenhändler); „Erst verarbeiten"-Modus (Seite-1-Dolche zuerst); in Sekunden steuerbare Ablauf-Delays; bewusster Simulation↔Scharf-Schalter (Default Simulation) |
| **Inventar** | ✅ | Scan (Ziffern-OCR + Stack-Summen), Cleanup/Wegwerfen, Box-/Köder-Nachlege-Engine, Kalibrierung (Grid-Lock-Cache) |

**Querschnitt:** Single-Window-CTk-UI mit Icon-Rail (Angeln/Puzzle/Inventar/Seher/Energie/Rangliste/Roadmap/Console/Settings), anonyme Online-Rangliste, Auto-Update (GitHub-Release), EN/DE, Onboarding. **Start landet auf der Angeln-Ansicht.**

---

## 2. Multi-Client (1–4 Clients parallel) — neue Architektur

**Ziel:** mehrere Spiel-Clients gleichzeitig botten, mit **EINER** physischen Maus (eine pro PC), prozess-isoliert und anti-cheat-neutral (rein extern).

### Architektur (gebaut)

```
Supervisor  ──spawnt/überwacht──>  Worker-Prozess ×N (1–4, headless, EIN Modus)
   │  (Crash-Isolation via OS-Prozessgrenze, Heartbeat, Auto-Restart)        │
   │                                                                          ▼
CursorBroker  <──Lease (FIFO+Aging, Hard-Timeout, Button-Neutralisierung)── CursorClient
   (serialisiert die EINE physische Maus; Drag/Akkord = non-revocable)
```

- **Lease-Burst:** jede logische Aktion (Klick / Tasten-Akkord / Drag) läuft als **ein** atomarer Burst: Lease anfordern → Button-State neutralisieren → click-to-activate + Fokus-Gate (Zielfenster nach vorn) → Aktionen mit Stop-Poll je Schritt → Tasten lösen → Lease frei. Adversarial gehärtet (`cursor_client.py`).
- **Eingabe-Seam je Modus:** jeder Bot hat `set_input_backend()`. Default = echtes `pydirectinput` → **Single-Client byte-identisch**. Multi-Client injiziert `LeasedPydirectinput` (pydirectinput-API-Shim), der Klick/`Ctrl+E`-Akkord/Drag zu je einem Lease-Burst bündelt. Tripwire-Test (`test_no_direct_input`) verhindert Regressionen.
- **Datenisolation:** jeder Worker bekommt einen privaten `%APPDATA%`-Unterordner (`M2FB_DATA_DIR`) → keine Config/Stats-Kollision.

### Status je Modus

| Modus | Eingabe-Seam | Worker-Treiber (`worker_modes.py`) | Headless getestet | Live getestet |
| ----- | :----------: | :--------------------------------: | :---------------: | :-----------: |
| Angeln | ✅ | ✅ `run_fishing` (+ Köder-Refill-Lease) | ✅ | ❌ |
| Puzzle | ✅ | ✅ `run_puzzle` | ✅ | ❌ |
| Energiesplitter | ✅ | ✅ `run_energiesplitter` (hammer/dagger) | ✅ | ❌ |
| Seher | ✅ | ✅ `run_seher` (über `abort_fn`) | ✅ | ❌ |

### GUI-Einstellungen (1–4 Clients + Fenster-Markierung) — ✅ gebaut

- **Reiter „Multiclient"** (`interface/app/views_multiclient.py`): Anzahl 1–4 wählbar; je Client eine Zeile mit Modus-Dropdown (Fischen/Puzzle/Seher/Energiesplitter), „Fenster markieren", Blinken-Bestätigung und Status.
- **Ausgefeilte Markier-Technik (Klick-zum-Erfassen):** statt aus einer `hwnd@x,y`-Liste zu raten, klickt der Nutzer das **echte Spielfenster** an. `window_mark.window_from_point` löst per `WindowFromPoint`→`GetAncestor(GA_ROOT)` das Top-Level-Fenster auf, validiert gegen die METIN2-Fensterliste und bestätigt per `FlashWindow`. Das ist **auch bei >4 offenen Fenstern eindeutig** (der Nutzer zeigt physisch). Reiner user32-Read → anti-cheat-neutral.
- **Logik headless getestet** (`multiclient_settings`, `window_mark`: 49 Tests): count-Clamp 1–4, Dedup (ein Fenster = ein Client), Validierung, Launcher-Spec-Ableitung, ClickCapture-Stepper. Persistenz in `config['multiclient']`.
- **„Alle starten"** leitet via `multiclient_settings.specs_from_slots` die Specs ab und ruft `launcher.run` im Hintergrund-Thread (Stop über `should_run`).

### Offen (Multi-Client)

1. **Live-Verifikation** — GUI-Darstellung, echte Klick-Erfassung am Spielfenster, Fenster-Blinken, **realer 2–4-Client-Start** (FD-Vererbung, click-to-activate-Zone Q1, Fokus-Gate-Latenz, Occlusion-Capture PrintWindow vs. BitBlt). Nur am echten Windows-Mehrfach-Client prüfbar; headless deckt nur die Logik.
2. **Puzzle auto/mark-Offset** im Worker (Default-Offset ist angebunden; auto/mark sind Screenshot-/Kalibrier-abhängig → Live-Folgeschritt).
3. **CLI-Launcher** (`launcher.py --list/--client/--auto`) existiert weiterhin als headless-Pfad parallel zur GUI.

---

## 3. Nächste Minispiel-Kandidaten (extern/Pixel/OCR)

Gemessen an der gebauten Referenz-Architektur. Verfügbarkeits-Stand der Events: Gameforge terminiert Events erst kurzfristig → jedes Event-Modul braucht eine „Event-aktiv?"-Probe (analog `event_window.py`).

### A-Tier — sauberer Fit, lohnenswert

- **Okey-Karten-Spiel** — 5 feste Slots, beste 3er-Kombi wählen/verwerfen + Nachziehen. Fixe UI, kein Timing, kein Wander-Dialog → Seher-UI-Schicht 1:1 wiederverwendbar. **Neu = EV/Discard-Policy** (`okey/policy.py`) bei verdecktem Deck. Läuft 2×/Jahr.
- **Schnapp den König / Catch the King** — 5×5-Grid, verdeckte Karten aufdecken + Werte vergleichen. Reuse Puzzle/Seher-Grid. **Neu = schwellen-bewusste EV-Heuristik** (Zustands-Tracking 25 Zellen + Resthand + 400/550-Schwelle) + Wander-Dialog-Anchoring. Gold = Glückssache (ehrlich kommunizieren).
- **Canavar Üçlüsü / Monster-Trio** — Memory-Matching (27 Karten), feste Positionen, Bilder template-matchbar (OCR-frei) → sauberste Automation. **Dämpfer:** evtl. 2026 nicht im Event-Kalender — Schaltung vor Investition prüfen.

### B-Tier — echte Neu-Algorithmik oder Einschränkung

- **Fishing Jigsaw (Angel-Puzzle)** — Polyomino-Tiling (NICHT das bestehende Fest-Slot-Puzzle!) → **neuer BFS/Tiling-Solver** nötig. Aufwand high.
- **Yutnori** — Yut-Brettspiel vs. KI; höchste Logik-Last (verzweigtes Brett + Shortcuts), saisonal (Halloween). Würfelglück → Gold nicht erzwingbar.
- **Fischzucht (Karpfen→Truhe)** — dünner NPC-Abgabe-Wrapper aufs schon gebaute Angeln; nur am ~2-h-Event-Termin.
- **Blumensystem (Öffnen-Loop)** — Batch-Öffnen vorgefarmter Stapel (Samen-Farm = Combat, off-limits) → reiner Convenience-Wert.

### C-Tier — ökonomisch fragwürdig / negativer EV

- **Item-Aufwertung / Schmied** — fester Dialog, ABER Item-Zerstörung = Geld-Verbrenner, negativer EV; für Laien nur mit hartem Zerstörungs-sicheren Modus + Pflicht-Stop.
- **Mining** — Abbau trivial, ABER Vein-Discovery + Welt-Navigation = Architektur-Sprung, fragil.
- **Drachensteinalchemie / Dorfschmied** — kein geschlossener Loop bzw. NPC-Drag im 3D-Weltbild.

### D-Tier — aussortiert (§4)

Tägliche Quest · Biologe · Erntefest · Auto-Hunt · Tombola/Spin the Wheel · Metin Showers · Catch the Carp (als eigenes Modul) · Adventskalender.

---

## 4. Aussortiert (und warum) — unverändert gültig

- **Welt-Combat / Mob-Farm** (Tägliche Quest, Biologe, Erntefest, Metin Showers): Architektur-Sprung in die 3D-Welt + höchstes Ban-Risiko; der einfache UI-Teil ist nicht abkoppelbar.
- **Auto-Hunt-Orchestrierung**: das bezahlte Auto-Hunt läuft selbst full-afk; wertvoller Teil = Welt-Logik + eigentliches Ban-Risiko.
- **Catch the Carp (eigenes Modul)**: das „Fangen" IST das gebaute Angeln; nur trivialer NPC-Tausch übrig.
- **Tombola / Spin the Wheel**: verbrennt Echtgeld (Premium-Coins) auf RNG; Belohnung im Item-Shop-Depot (sensibelste Bot-Oberfläche).
- **Adventskalender / Anwesenheit**: 1 Klick/24 h, kein Loop; Abholung im web-/overlay-gerenderten Item-Shop.

---

## 5. Live-Verifikation nötig (vor Bau/Ship)

Die offiziellen Wikis dokumentieren **keine** Pixel-Koordinaten/Button-Labels → jedes neue Minispiel-UI braucht **echte 800×600-Screenshots im laufenden Event**.

- **Multi-Client (alle 4 Modi):** click-to-activate-Zone, Fokus-Gate, Occlusion-Capture — nur am echten Mehrfach-Client prüfbar. Aktuell headless verdrahtet + getestet, **noch nicht live**.
- **Okey/Catch the King:** Slot-/Zell-Koordinaten, Deck-/Nachzieh-Mechanik, Wander-Dialog-Verhalten.
- **Monster-Trio/Yutnori:** Event-Schaltung 2026 + Brett-State-Tracking.
- **Energiesplitter & Puzzle (Single-Client):** Maus-/Pixeltreue bleibt nur live verifizierbar — bei Eingabe-/Timing-Änderungen Pflicht (headless kann In-Game-Eingabe nicht validieren).

---

## 6. Ehrlicher ToS-/Ban-Hinweis

**Jede** Automation auf offiziellen Gameforge-Servern verstößt gegen die Metin2-ToS — **auch rein extern** (Screenshot + OCR + simulierte Eingabe). Bann-relevant, unverändert.

- **Rein extern erspart:** keine Injection-/Memory-/Packet-Fläche, kein xhunter1-Modulscan-Signal — der einzige verteidigbare Weg (Memory-Read wäre ein Sicherheits-Downgrade).
- **Bleibt bestehen:** Verhaltens-Heuristiken (stundenlanges identisches Spiel, perfekte Effizienz) + GM-/Spieler-Reports greifen methoden-unabhängig. Bei Top-10-Leaderboards (Okey, Catch the King, Yutnori) zusätzlich sozial auffällig. **Multi-Client erhöht das Muster-Risiko** (mehrere identische Sessions gleichzeitig).
- **Für die Laien-EXE Pflicht:** Risiken ehrlich kommunizieren, Timing-Jitter + Stop-Timer beibehalten, bei Item-Aufwertung harte Zerstörungs-Sicherung. **Keine Evasion/Anti-Detection** — die Linie ist „extern bleiben + aufklären", nicht „unentdeckbar machen".
```
