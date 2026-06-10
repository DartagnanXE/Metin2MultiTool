# Changelog

Alle nennenswerten Aenderungen an diesem Projekt werden hier festgehalten.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [1.1.6] — 2026-06-10

### Behoben (Live-Feedback aus v1.1.5)

- **Offen-Erkennung auf entfernten Standorten:** Die Inventar-Tab-Leiste ist
  leicht transparent — je nach Szene dahinter (Wasser/Steg) lasen inaktive
  Tabs bis zu MAD 8,7 und die Schwelle 8 meldete fälschlich „zu" (die
  Abbrüche im Nutzer-Log). Schwelle auf 15 (Landschaft bleibt ≥26, weiter
  große Marge); mit den 4 gelieferten Seiten-Screenshots (I–IV) als
  Test-Fixtures abgesichert.
- **Goldfisch-Bestätigung: Fenster wandert!** Der Bestätigungs-Dialog steht
  nicht an fester Position (Höhe hängt vom Text ab; Live-Referenzen: OK bei
  y=250 vs. y=202). Der OK-Knopf wird jetzt per Template über den ganzen
  Frame GESUCHT (zweistufig: Knopf-NCC ≥0,70 + flache Leisten-Flanken) und
  exakt am Fund geklickt.
- **Inventar-Management-Grid:** letzte Spalte war abgeschnitten → 8 Spalten
  (eine Reihe mehr), per Tk-Messung verifiziert (Grid endet bei x=514 von 555).

### Verbessert

- **Wegwerfen/Grillen ~2× schneller:** Der Drag-Pfad (12 Zwischen-Moves)
  zahlte pro Move den globalen 0,05s-Hold (~0,6 s/Item nur fürs Ziehen);
  reine Maus-Moves laufen jetzt mit PAUSE=0 (nur Down/Up behalten ihren Hold).
- **„Inventar managen" zeigt den Lauf:** Knopf wird zu „läuft … [F6] stoppt"
  (gesperrt); **F6 bricht Grillen/Wegwerfen sauber nach dem aktuellen Item
  ab** (Status „gestoppt", Log zeigt den Stand).
- **Cleanup-Timer:** Countdown 40 s → **30 s**; läuft bei 00:00 noch ein
  Grill-/Wegwerf-Worker, wird er aktiv gestoppt (Abbruch nach dem aktuellen
  Item) und das Angeln startet direkt danach neu (User-Spez).
- **Inventar-Seite bleibt erhalten:** Nach Scan/Grillen/Wegwerfen klickt der
  Bot die Seite (I–IV) wieder an, die vor dem Lauf offen war.

## [1.1.5] — 2026-06-10

### Neu

- **Zeitlimit-Aktion „Inventar-Cleanup" (entweder/oder):** Beim „Stoppen nach
  Zeit (Min.)" lässt sich jetzt wählen, was nach Ablauf passiert: **Stoppen**
  (wie bisher) ODER **Inventar-Cleanup** — der Bot stoppt, stellt sicher, dass
  das Inventar offen ist (neue Offen-Erkennung), scannt es, wendet die
  Behalten/Entfernen/Lagerfeuer-Markierungen an (grillen + wegwerfen) und
  startet das Angeln nach einem sichtbaren **40-Sekunden-Countdown** im
  Top-Timer automatisch neu — der Zeit-Timer beginnt dann von vorn
  (Dauerbetrieb mit periodischem Aufräumen). Abbruch jederzeit per Stop-Hotkey
  oder manuellem Start.
- **Start-Knopf kontextabhängig:** Starten ist nur noch in den Ansichten
  _Fishing_ und _Puzzle_ möglich (dort ist eindeutig, was gestartet wird) — in
  Inventar/Rangliste/Roadmap/Console/Einstellungen ist der Start-Knopf
  ausgegraut. Stoppen bleibt bei laufendem Bot in jeder Ansicht möglich.

### Behoben

- **Puzzle: Steine wurden sofort verworfen statt gesetzt (User-Report):** Der
  Bot las die Stein-Farbe genau EINMAL, ~0,1–0,3 s nach dem Holen — da war der
  Stein oft noch nicht gerendert (Log: Hintergrund-Grau b=31 g=34 r=36 am
  Sample-Punkt) → `new_piece=None` → sofortiges Wegwerfen, bei jedem Stein.
  Jetzt liest State 4 bis zu 2 s lang pro Frame ein frisches Capture nach
  (Erfolg beendet die Schleife sofort; erst nach Ablauf greift der bisherige
  Verwerfen-Pfad, voll geloggt). Zusätzlich war das BLAU-Fenster zu eng: der
  live gemessene blaue Stein (255,74,0) fiel mit g 100–115 durch → auf
  g 60–130 verbreitert (kollisionsfrei; kein anderes Fenster hat b>240 und
  r<10). On top: **Toleranz-Klassifikation** als zweite Stufe (±40/Kanal gegen
  die 6 Referenz-Zentroide, eindeutig oder gar nicht) — erkennt JEDEN künftig
  gedrifteten Farbton sofort, beweisbar verwechslungsfrei (kleinste Kanal-Lücke
  zweier Steinfarben 85 > 2×40; Invarianten-Test pinnt das, bei 45 hätten
  Orange/Gelb überlappt) und Hintergrund/Garbage trifft konstruktiv nie. Neue
  Tests: `TestColorReadRetry` + `TestClassifyPieceTolerant` +
  `TestTolerantFallbackWiring` (test_puzzle_glue), Disjunktheits-Invariante +
  Sweep-Kontrakt in test_color_sampling.
- **Goldener Thunfisch: Bestätigungs-Fenster wurde nie geklickt (Bot hing):**
  Nach dem Options-Klick (z. B. Freilassen) antwortet der Server mit einem
  zweiten Fenster mit OK-Knopf. Der alte Code klickte OK blind 0,1 s nach dem
  Options-Klick — praktisch immer BEVOR das Fenster existierte; und da dieses
  Fenster die Bildecken nicht schwärzt, sah die Tagesbelohnungs-Erkennung es
  nie → Dialog blieb offen. Jetzt: eigene Erkennung des Bestätigungs-Dialogs
  (Template-Match der Knopf-Leiste, beidseitig des OK-Knopfs, hover-sicher;
  Selbst-Match 0.0 vs. nächster Negativfall ≥27) und OK-Klick erst, wenn der
  Dialog wirklich im Frame steht (bis 10 s Wartefenster, retry-sicher).
  OK-Position präzise nachgemessen: Client (403,250) Knopf-Mitte (alt 399,246
  = Knopfrand). Templates `images/golden_confirm_bar_{l,r}.png`, Referenz
  `FischOCR/GoldenerThunfischAuswahlbestätigen.png`; neue Tests
  `tests/test_golden_confirm.py`.

- **„Bot laeuft los" bei Scan/Manage (Klick in die Landschaft):** Die
  Inventar-Taste ist ein TOGGLE — war der Beutel schon offen (z. B. direkt nach
  einem Scan, der ihn absichtlich offen laesst), schloss der blinde
  Oeffnen-Druck ihn wieder, und die folgenden Tab-Klicks bzw. Drag-Quellen
  landeten als Links-Klicks in der 3D-Welt → der Charakter lief los. Alle drei
  Live-Fluesse (Scan, Lagerfeuer-Braten, Wegwerfen) pruefen den Offen-Status
  jetzt VOR jedem Tastendruck und bei Misserfolg brechen sie ab, BEVOR
  irgendetwas geklickt wird (`inventory.scan_not_open` /
  `campfire.status_not_open` / `discard.status_not_open`).

### Neu

- **Selbststaendige Offen-Erkennung (`inventory/open_probe.py`):** Template-
  Match der vier Seiten-Reiter (I–IV) an den kalibrierten Positionen — die je
  eine AKTIVE (hellere) Seite matcht ihr Inaktiv-Template nicht, die anderen
  drei matchen pixelgenau. Regel „≥3 von 4 matchen = offen". Vermessen auf
  echten Captures: offen 0.0–0.6 MAD (inaktiv) vs. 39–53 (aktiv) vs. 26–69
  (geschlossen/Landschaft); adversarialer Sweep mit 73.170 Platzierungen ueber
  die Landschaft: **0 Falsch-Offen**. Templates gebuendelt unter
  `inventory_tab_templates/` (beide .spec-Dateien), Extraktor
  `tools/extract_tab_templates.py`.
- **Toggle-Selbstheilung:** Liest ein offener Beutel wegen Tooltip/Cursor auf
  der Tab-Reihe faelschlich „zu", schliesst Druck 1 ihn sauber und Druck 2
  oeffnet ihn verifiziert wieder (max. 2 Druecke, Cursor wird vor jeder Probe
  geparkt).
- **Test-Fenster zeichnet die Tab-Reihe** (echte Templates), damit der Scan
  gegen das Fake-Inventar weiterhin funktioniert; neue Testdatei
  `tests/test_inventory_open_probe.py` (Synthese + echte Open-/Closed-Shots
  inkl. Seite-II-aktiv).

## [1.1.5] — Run-1 Haertung (Statistik/Ranking/Telemetrie-Server, Teil desselben Releases)

### Behoben

- **Statistik-Persistenz bei Absturz/Update:** Akkumulierte Laufzeit ging auf
  manchen Beenden-Pfaden verloren (Fenster schliessen ohne Fang/Loesen, harter
  `os._exit` beim Auto-Update). Jeder Exit-Pfad sichert die `stats.json` jetzt
  final atomar (`App._flush_stats` -> in `hack.py` registrierter Hook).
- **Atomares Speichern unter Last:** `stats.save()` schreibt pro Aufruf in einen
  eindeutigen Temp-Namen und wiederholt `os.replace` kurz bei transienten
  Windows-Sharing-Violations (WinError 5). Damit gehen unter gleichzeitigen
  Schreibern keine Schreibvorgaenge mehr verloren (0/300 statt ~128/300 Fehler),
  und der Nebenlaeufigkeits-Test ist deterministisch gruen.
- **Telemetrie nur ueber HTTPS:** Die URL-Validierung lehnt jetzt `http://`
  (und alle Nicht-`https`-Schemata) ab und faellt auf den HTTPS-Default zurueck
  — Username/HWID/Stats gehen nie im Klartext ueber die Leitung.

### Server (Artefakte) — Defense-in-Depth

- **IP-Spoofing-Schutz:** Die App vertraut `X-Real-IP` bzw. dem rechtesten
  `X-Forwarded-For`-Hop (von nginx angehaengt), nie dem faelschbaren linken
  Eintrag; nginx-`real_ip`-Hinweise im Server-Block + DEPLOY.md.
- **Beschraenkter Rate-Limiter:** Die In-Process-Bucket-Map wird global geleert
  (periodisch + ab Obergrenze), schliesst die unbeschraenkte Speicher-Wachstum.
- **nginx leerer-X-HWID-Bypass geschlossen** (Map auf `$binary_remote_addr`).

### Tests / Doku

- Testsuite auf **533 Tests** aktualisiert (Doku-Zahl korrigiert, vormals
  faelschlich „126"); Server-Suite **44** gruen. Thread-Timing-Flakiness in den
  Telemetrie-Sender-Tests beseitigt (ereignisgesteuert statt `sleep`).

## [1.1.4] — 2026-06-07

### Behoben / Verbessert (Angel-Chat-Erkennung)

- **3 gemeldete Faenge wurden nicht erkannt:** _Karpfen_ und _Aal_ lieferten
  `UNKNOWN` (der Glyphen-Atlas kannte die Zeichen `A`/`f` nicht, daher fiel die
  Fuzzy-Aehnlichkeit unter die Schwelle; bei _Aal_ zusaetzlich fatal, weil der
  Name nur 3 Buchstaben hat). _Schwarzes Haarfärbemittel_ funktionierte schon,
  ist jetzt aber stabiler. Aus den gelieferten Chat-Bildern nachtrainiert:
  3 neue Whole-Name-Templates + die Atlas-Glyphen `A`/`f`/`z`. Die neuen Glyphen
  verbessern auch bestehende Namen (Spiegelkarpfen, alle Haarfärbemittel lesen
  jetzt das `f`). Bestehende Templates bleiben byte-identisch.
- **Sicherheitsnetz gegen stille Luecken:** Neuer Test deckt JEDEN fangbaren
  Namen (`ITEM_NAMES`) gegen Atlas+Fuzzy ab. Aktuell 41/44 sicher erkennbar;
  dokumentierte Rest-Luecken (`Ayu`, `Blondes`/`Braunes Haarfärbemittel` —
  fehlende Glyphen `y`/`B`) degradieren SICHER (UNKNOWN → Fisch wird behalten,
  nie faelschlich abgebrochen). Ein neuer, nicht erkennbarer Fisch laesst den
  Test kuenftig sofort anschlagen.
- Neues Dev-Tool `tools/synthesize_chat_reference.py` (Chat-Crop → 802×632
  Referenzframe) fuer reproduzierbares Nachtrainieren weiterer Faenge.

### Oberflaeche

- **Schrift im ganzen Interface groesser/besser lesbar:** Die globale
  Widget-Skalierung wurde von `0.85` (~15% kompakter) auf `1.0` angehoben und der
  zuvor sehr kleine, graue Abschnitts-Untertitel ("Infos", z.B. _„Scan the
  inventory and locate tracked items"_) vergroessert. Damit der No-Scroll-Aufbau
  erhalten bleibt, sind die fixen Fenstergroessen (Hauptfenster + Onboarding-,
  Effekt- und Fenster-Auswahl-Dialog) proportional mitgewachsen.

Erkennungs-/Template- + reine UI-Skalierungs-Aenderung — KEINE Eingabe-/Timing-
Aenderung (headless getestet; die optische Schriftgroesse bitte einmal im Spiel
gegenpruefen).

## [1.0.4] — 2026-06-01

Grosses UI- und Funktions-Update: komplett neu gestaltete, kompakte Oberflaeche
plus viele neue Komfort- und Erkennungs-Funktionen. Empfohlenes Update fuer alle.

### Neue Oberflaeche (Cockpit-Sidebar)

- Komplett neues, **kompaktes** Single-Window-Layout mit schlanker **Icon-
  Navigationsleiste** links: Angeln, Puzzle, Console, Roadmap, Einstellungen.
- **START/STOP ganz oben** (zeigt waehrend des Laufs, ob Angeln oder Puzzle
  laeuft) mit **Lauf-Timer daneben** (zaehlt bei gesetztem Limit herunter, sonst
  die Laufzeit hoch).
- Spiel-Erkennung dezent unten rechts: **blendet sich aus**, sobald Metin2
  (800x600) gefunden ist; **prueft jetzt auch die Fenstergroesse** und bietet bei
  falscher Groesse einen **Ein-Klick "Auf 800x600 setzen"** (resized das Spiel).
- Inhalt oben gruppiert, feste Fenstergroesse, **kein Scrollen** noetig.
- Dezente **Versions-/Update-Anzeige** unten links (leuchtet nur bei verfuegbarem
  Update auf) mit Herkunfts-Tooltip.

### Neue Einstellungen

- **In den Tray minimieren**, **Immer im Vordergrund**, **Schliessen wenn Metin2
  schliesst**, **Schliessen wenn der Timer ablaeuft**, **Angel-Hotkeys umbelegen**
  (Koeder-/Angel-Taste frei waehlbar), **Overlay-Deckkraft** regelbar.
- **Einstellungen zuruecksetzen** (Werkseinstellungen, mit Bestaetigung).

### Board-Erkennung

- **"?"-Hilfebild** zurueck (zeigt, wo die Punkte hingehoeren).
- Detection-Modi mit **Sicht-Overlay**: **Default/Auto** zeigen ~5 s die Punkte
  ueber dem Desktop (Ausrichtung pruefen); **"Manuell"** (vorher "Mark") oeffnet
  beim Umschalten direkt das Markier-Overlay. **Overlay-Deckkraft** einstellbar.
- Mehrere Metin2-Fenster offen? **Fenster-Auswahl per Klick**.

### Sonstiges

- **Deutsch jetzt mit echten Umlauten** (ae/oe/ue/ss -> ä/ö/ü/ß).
- Kleiner **"Testfenster"-Knopf** unter Console (oeffnet ein Test-"METIN2"-Fenster
  zum Ausprobieren ohne echtes Spiel).
- Neuer **Roadmap-Tab** mit den geplanten Funktionen.
- **Installer entfaellt:** Auslieferung jetzt ausschliesslich als **Portable**
  (eine `.exe`, kein Setup, keine Installation) — ein Download, weniger Reibung.

## [1.0.3] — 2026-05-31

Zwei neue Funktionen: **eingebaute Update-Benachrichtigung** und eine
**konfigurierbare Goldener-Thunfisch-Aktion**.

### Neu

- **Auto-Update (ab jetzt eingebaut):** Beim Start prueft die App im Hintergrund
  (eigener Thread, blockiert das UI nie) die GitHub-Releases. Gibt es eine
  neuere Version, erscheint ein dezentes Banner — **ein Klick laedt die neue
  Portable, ersetzt sie an Ort und Stelle und startet neu.** Bewusst
  **nutzer-initiiert** (kein stilles Auto-Download -> schont die AV-Lage),
  Admin-bewusst. Die Installer-Variante oeffnet stattdessen die Release-Seite.
  Neue `version.py` als einzige Versions-Quelle (auch fuer beide Specs).
- **Goldener-Thunfisch-Aktion waehlbar:** In den Einstellungen festlegen, was der
  Bot beim Fang eines goldenen Thunfischs tut — **1 = Freilassen, 2 =
  Aufschneiden, 3 = Als Koeder benutzen**. **Default jetzt 3** (vorher das
  mittlere Feld). Der Bot loggt die geklickte Position zur Verifikation.

## [1.0.2] — 2026-05-31

**Wichtiges Fix-Update — behebt, dass das Angeln in der EXE nicht funktionierte.**

### Behoben (kritisch)

- **Angeln erkannte das Minispiel nie / spielte es nicht** (in der gepackten
  EXE): Die Angel-Vorlagenbilder (`fiss.jpg`, `clock.jpg`) wurden mit einem
  nackten Pfad geladen, der nur im Quellcode-Start (Arbeitsverzeichnis = Projekt)
  funktioniert — **in der EXE lagen sie im PyInstaller-Bundle und wurden zu
  `None`**, sodass die Bilderkennung nie etwas fand. Jetzt ueber `resource_path()`
  geladen (wie das Puzzle es bereits tat). Der Bot warf zuvor brav Koeder/Angel
  aus, „sah" das Spiel aber nicht.
- **Eingaben erreichten das Spiel nicht** (Maus bewegte sich, Klicks/Tasten kamen
  nicht an): Das Spiel laeuft meist als Administrator, die EXE nicht — Windows
  **UIPI** blockt dann die Eingaben. Die EXE **fordert jetzt automatisch Admin an**
  (UAC-Manifest, `uac_admin`); kein „Als Administrator ausfuehren" mehr noetig.

### Verbessert (Selbstdiagnose)

- Beim Start wird klar geloggt, falls Vorlagenbilder **nicht geladen** werden
  konnten (statt stiller Fehlerkennung).
- Pro Angel-Runde wird die **Minispiel-Trefferguete** geloggt (`>0,90 = erkannt`)
  — so ist sofort sichtbar, ob die Uhr erkannt wird oder die Schwelle/Position
  nachjustiert werden muss.

## [1.0.1] — 2026-05-31

Stabilitaets- und Diagnose-Update ueber 1.0.0 (gleiche Funktionen, nur robuster
und mit klareren Logs). Empfohlenes Update fuer alle.

### Behoben

- **Angeln stuerzte auf manchen Systemen sofort ab** (`cv2.matchTemplate`-
  Assertion bei abweichender Capture-Form/DPI-Skalierung). Die Vorlagensuche ist
  jetzt robust (kontiguierlich, Kanal-/Groessen-Abgleich, jeder cv2-Fehler
  abgefangen) -> **kein Absturz mehr**; im Zweifel „nicht erkannt" statt Crash.
- **UI verschob die `Bot | Console`- und `EN | DE`-Schalter**, wenn der Status-
  Text laenger wurde -> die Buttons sind jetzt fest am rechten Rand verankert.
- Puzzle-Stopmeldung zeigte unausgefuellte Platzhalter (`{valid}` …) -> echte
  Zahlen.

### Verbessert (Selbstdiagnose)

- **Angeln meldet sich selbst:** unterscheidet „echte Runde beendet" von
  **„kein Biss — kein Minispiel erschienen"** und warnt nach mehreren Leer-
  Auswuerfen klar mit Checkliste (Angel ausgeworfen? Koeder auf Taste 2? Spiel
  in 800x600?). Stoppt nicht — meldet aber, statt stumm weiterzuloopen.
- **Puzzle-Erkennung praeziser:** klassifiziert die 24 Zellen in _echte
  Steinfarbe / leer / Garbage_ und unterscheidet sauber **leeres Brett /
  volles Brett / „Board nicht erkannt"** (z.B. falsche Fensterposition / kein
  echtes Puzzle) — jeder Stopp mit glasklarer Begruendung.

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

- Headless-Testsuite (reine Logik, ohne GUI/Spiel): **533 Tests gruen**.

### Unveraendert (bewusst, byte-stabil)

- **Angeln** (`fishingbot.py`, `fishfilter.py`, `hsvfilter.py`) und der
  **Standard-Puzzle-Solver** (Greedy in `tetris.py`): Verhalten wie im Original.
  Die KI bzw. die optionalen Modi laufen ausschliesslich, wenn explizit gewaehlt.
