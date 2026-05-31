# Metin2 Fishing Bot — Redesign- & Härtungs-Spec

> Verbindliche Bau-Vorlage. Vom Nutzer freigegeben (Vertrauensvorschuss, keine formale Abnahme nötig).
> UI-Sprache: **Englisch**. Fenstertitel: **„Metin2 Fishing Bot"**.

## 0. Leitplanken (NICHT verletzen)

- Zielplattform Windows, Spiel in **800×600 Fenstermodus** (einzige unterstützte Auflösung — bewusst).
- **Angeln ist Hauptfeature und MUSS funktional unangetastet bleiben.** `fishingbot.py`, `fishfilter.py`, `hsvfilter.py`: Verhalten byte-stabil; nur minimal-nötige UI-Anbindung erlaubt.
- Angeln & Puzzle **nie gleichzeitig** (exklusiv).
- Verteilung als Windows-EXE für **Laien** (Doppelklick / Installer).
- **Nichts Bestehendes geht verloren** — alle Alt-Funktionen bleiben, nur moderner.

## 1. UI-Redesign

- **Toolkit: CustomTkinter** (modern, dark/rounded, PyInstaller-tauglich). Ersetzt FreeSimpleGUI in `interface/`.
- **Single-Window** (keine Tabs), Stil **Teal/Dark** (freigegebenes Mockup):
  - Titel „🎣 Metin2 Fishing Bot" + „800×600"-Badge.
  - **Ein großer START/STOP-Button** (toggelt je nach aktivem Modus).
  - **Segmented „Fishing | Puzzle"** — genau einer wählbar, **während Lauf gesperrt**. START startet den gewählten Modus.
  - **SETTINGS-Sektion**: Delay (§2), Board Detection (§3), Color Sampling (§4), Stop-after Time(min), Puzzle Solver (§7).
  - **LIVE-LOG-Sektion** (§5), dauerhaft aktualisierend, „● live".
  - Fishing visuell primär, Puzzle sekundär.
- **Settings-Persistenz**: alle Optionen in `config.json` neben der EXE (laden/speichern).

## 2. Delay / Timings

- Die **drei bestehenden Fishing-Timings beibehalten** (bait / throw / start-game) — Angeln nicht kaputtmachen.
- Slider-Range **0.1s – 20s** (Schritt 0.1). Werte fließen wie bisher in `FishingBot.set_to_begin(values)`.

## 3. Puzzle Board Detection — 3 Modi (selektierbar, persistiert)

Feste Board-Größe 260×170 (Offset im Fensterinhalt).

- **Default**: aktuelles Verhalten, feste Position (270,227). Fallback, unverändert.
- **Auto**: cv2-Template-Matching findet das Board (feste Größe → Single-Scale), leitet Offset ab; bei Misserfolg → Fallback Default + Log.
- **Mark** (Lightshot/Snipping-Style): transparentes, immer-vorne, draggbares Overlay in Board-Größe mit gezeichneten **24 Sample-Punkten**; „Bestätigen" speichert Offset.
- Gewählter Offset speist die Board-Position in `puzzle.py`.

## 4. Color Sampling — Toggle

- **Single px** (aktuell, Default): 1 Pixel/Zelle bzw. am Farb-Sample (110,150).
- **Multi px (avg)**: kleiner Patch (3×3/5×5) um den Zellmittelpunkt, Mittelwert + Klassifikation per **nächster Referenzfarbe** (statt enger ±-Fenster).
- Betrifft `set_puzzle_state` (Board) und `get_new_piece_color` (Stein). Umschaltbar, altes Verhalten garantiert erhalten.

## 5. Integriertes Live-Log

- Bisheriges separates Debug-Tool → **ins UI integriert**: Live-Log-Panel zeigt `debuglog`-Events in Echtzeit (thread-safe Sink). Datei-Log `puzzle_debug.log` **bleibt zusätzlich**. Im UI zuschaltbar.

## 6. Build / Wacatac-Remediation („best possible")

- `Metin2FishBot.spec`: **`upx=False`**, **`--onefile` → `--onedir`** (exclude_binaries + COLLECT), **PE-Metadaten** (version-Resource).
- `requirements.txt`: **exakte Versionen pinnen** (gegen real installierte verifizieren).
- **Installer** (`installer.iss`, Inno Setup) um den onedir-Output → für Laien weiter ein Doppelklick, signierbar.
- `build.bat` anpassen (onedir + Installer). `README`: Nutzer-Aufgaben (WDSI-FP-Meldung, VirusTotal, optional Signing) + ehrliches Restrisiko.

## 7. Puzzle Solver — optionaler „Trained"-Mode (vorerst Platzhalter)

- Greedy-Solver (`tetris.py`) bleibt **Default**.
- Neuer **`trained_solver.py`**: Interface `choose_placement(board, piece, deluxe_available) -> action`, delegiert **vorerst an den Greedy-Solver** (Platzhalter). Wird mit der optimalen Min-Boxen-Strategie gefüllt, sobald der Strategie-Workflow validiert ist.
- UI-Toggle „Puzzle Solver: Standard | Trained".

## 8. Architektur / Datei-Ownership (disjunkt, für parallele Umsetzung)

- **A UI**: `interface/__init__.py`, `interface/app.py`, `interface/widgets.py`, `interface/log_panel.py`, `interface/config.py`, `debuglog.py` (UI-Sink).
- **B Detection**: `detection.py`, `overlay_mark.py`.
- **C Puzzle-Core**: `puzzle.py` (Color-Toggle, Detection-Offset, Solver-Hook), `trained_solver.py`.
- **D Build**: `Metin2FishBot.spec`, `build.bat`, `requirements.txt`, `installer.iss`, `README_BENUTZUNG.md`.
- **Integration**: `hack.py` (Event-Loop gegen neues UI; CTk-Mainloop + Bot-Tick via `after()`/Thread).
- **Angel-Module: NICHT anfassen.**

## 9. Tests & Abnahme

- Bestehende **35 Solver-Tests müssen grün bleiben**. Neue Tests: Config-Persistenz, Multi-Color-Sampling, Auto-Detection (Mock-Screenshot), Mark-Offset.
- `py_compile` aller Module. GUI-Smoke soweit ohne Display möglich; sonst dokumentieren (Windows-Verifikation nötig).
- Angeln byte-stabil (Diff = nur UI-Glue).

## 10. Akzeptanzkriterien

- Modernes UI, alle Alt-Funktionen vorhanden, English, „Metin2 Fishing Bot".
- 3 Detection-Modi + Color-Toggle + Solver-Toggle, alle persistiert.
- Live-Log im UI. Delay 0.1–20s (3 Timings).
- Build: upx=False/onedir/Installer/Metadaten, pinned deps.
- Angeln funktional unverändert; Angeln/Puzzle exklusiv.
