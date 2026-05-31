# Changelog

Alle nennenswerten Aenderungen an diesem Projekt werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [1.0.0] — 2026-05-31

Erste oeffentliche Version dieser ueberarbeiteten Fassung. Sie basiert als Fork
auf [vncsms/Metin2FishBot](https://github.com/vncsms/Metin2FishBot) (Angel-
Mechanik und Puzzle-Erkennungs-Basis); alles Weitere ist neu/ueberarbeitet —
dateigenaue Herkunft in [`NOTICE`](NOTICE). Die urspruenglichen Faehigkeiten
bleiben als **Default** erhalten (byte-stabil); alle Neuerungen sind **optional**
im UI zuschaltbar.

### Neues Single-Window-UI (CustomTkinter, Dark/Teal)

- **Zweisprachig (EN/DE), live umschaltbar** ueber einen dezenten Schalter oben
  rechts: UI, Hinweise UND alle Log-Zeilen wechseln sofort; die Wahl wird in
  `config.json` gespeichert (Standard: Englisch). UI kompakt skaliert -> alles
  ohne Scrollen auf einer Seite.
- Ein Fenster mit Umschalter **Bot ⇄ Console** (integrierte Live-Konsole statt
  separatem Debug-Tool) — Konsole mit **Kopieren / Logdatei oeffnen / Leeren**.
- Grosser **START/STOP**-Button, Umschalter **Fishing | Puzzle** (exklusiv,
  waehrend des Laufs gesperrt).
- **Spiel-Erkennung im Status:** „● Metin2 detected — ready" (gruen), sobald das
  Spiel-Fenster gefunden ist, sonst „○ Waiting for Metin2…". Rein passiver
  Fenster-Check (`FindWindow`) — kein Prozessspeicher-Zugriff.
- Robuste Auswahl-Schalter (eigene Buttons statt des leer rendernden
  CTkSegmentedButton), **scrollbares** Layout (resize-fest), eigenes
  **Musketier-Icon** (Fenster + Taskleiste), Sofort-Render, **Auto-Speichern**
  der Einstellungen, **„?"-Hilfen** mit Referenzbild.
- Delay-Schieberegler **0.1–20 s** (Koeder / Auswurf / Minispiel-Start) plus
  „Stop nach X Minuten".

### Puzzle-Features (optional — Default bleibt unveraendert)

- **Solver-Methode:** _Default_ (Original-Greedy + Eroeffnungsbuch) oder
  _KI optimiert_ (beweisbar optimale Strategie per exakter MDP-Wertiteration;
  Tabelle wird einmalig in ~12 s berechnet und als `trained_V.npy` gecacht).
- **Board-Erkennung:** _Default_ (feste Position) / _Auto_ (Bildabgleich) /
  _Mark_ (selbst kalibrieren per Vollbild-Overlay mit Raster-Griffen, 4
  Sonderpunkten und eingeblendetem **Referenzbild**). Aufloesungsunabhaengig.
- **Farb-Sampling:** _Single_ (1 Pixel, Default) oder _Multi_ (robuster gegen
  leichte Farbabweichungen).

### Build & Auslieferung

- **Portable** (eine `.exe`, kein Install) **und Installer** (Inno Setup, mit
  Start-Menue-/Desktop-Verknuepfung und echtem Deinstaller).
- Gegen generische Viren-Heuristik gehaertet: **kein UPX**, echte **PE-Metadaten**,
  onedir-Variante. (Ohne Code-Signatur nicht garantiert eliminierbar — siehe
  README-Abschnitt zu Virenwarnungen.)
- Abhaengigkeiten als flexible Mindest-Versionen (laeuft auf Python 3.11–3.13).

### Tests

- Headless-Testsuite (reine Logik, ohne GUI/Spiel): **126 Tests gruen**.

### Unveraendert (bewusst, byte-stabil)

- **Angeln** (`fishingbot.py`, `fishfilter.py`, `hsvfilter.py`) und der
  **Standard-Puzzle-Solver** (Greedy in `tetris.py`): Verhalten wie im Original.
  Die KI bzw. die optionalen Modi laufen ausschliesslich, wenn explizit gewaehlt.
