# INTENT — Multiclient für ALLE Mechaniken + Settings 1–4 Clients mit Fenster-Markierung

## Ziel (vom Nutzer)
Alle Bot-Mechaniken (Fischen, Puzzle, Energiesplitter, Seher) sollen multiclient-fähig
in der GUI nutzbar werden. In den Einstellungen darf man **1–4 Clients** festlegen.
Für den Fall, dass **mehr als 4 Spielfenster** offen sind, muss eine **ausgefeilte
Technik** den jeweiligen Client eindeutig zuordnen: beim Setzen der Einstellung markiert
der Nutzer jeden Client **direkt am echten Fenster**.

## Erfolgskriterien
1. GUI-Reiter „Multiclient": Anzahl 1–4 wählbar; je Client eine Zeile mit
   Modus-Auswahl (Fischen/Puzzle/Energiesplitter/Seher) + Fenster-Zuordnung + Status.
2. **Markieren = Klick-zum-Erfassen:** Knopf „Fenster markieren" → Nutzer klickt das
   echte Spielfenster → dessen Top-Level-HWND wird dem Slot zugeordnet; Bestätigung per
   kurzem Fenster-Blinken. Robust auch bei >4 offenen Fenstern (Nutzer zeigt physisch).
3. Doppelte Fenster-Zuweisung verhindert (ein Fenster = ein Client).
4. Persistenz in `config['multiclient']` (count, auto_restart, clients[]).
5. „Alle starten" leitet aus der Config die Launcher-Specs ab und startet die Worker.
6. Single-Client-Pfad bleibt byte-identisch (Default count=1, kein Regress).
7. Reine externe user32-Reads (WindowFromPoint/FlashWindow/GetCursorPos) — anti-cheat-neutral.

## Architektur (Trennung Logik ↔ GUI für Testbarkeit)
- `multiclient_settings.py` (PURE, headless-testbar): Slot-Modell, count-clamp 1–4,
  (de)serialize, dedup, validate, Launcher-Spec-Ableitung.
- `window_mark.py` (PURE-Kern, win32 injizierbar): `window_from_point`, `flash_window`,
  `ClickCapture`-Stepper (poll-basierte Klick-Erfassung).
- `interface/app/views_multiclient.py` (CTk, LIVE-only): Reiter-UI, dünn, delegiert.
- Wiring in `interface/app/__init__.py` (_views + Nav) + `defaults.py`/`validate.py`.

## Live-only (Nutzer muss testen — headless nicht verifizierbar)
GUI-Darstellung, echte Klick-Erfassung am Spielfenster, Fenster-Blinken,
realer 2–4-Client-Start (FD-Vererbung, Fokus-Gate). Headless deckt nur die Logik ab.

## Doktrin
Extern/OCR only, kein Prozess-Speicher. Eingabe-/GUI-/Capture-Änderungen MÜSSEN vor
Release live getestet werden (headless kann In-Game-Eingabe/Capture nicht validieren).

## Eingehende Intentionen (vom Autopilot zu triagieren)
- [ ] (2026-06-23T23:25:08+02:00) Metin2MultiTool Folge-Items: (1) Single-Client (Multiclient=1) MUSS byte-identisch wie frueher laufen (Legacy-Pfad absichern+testen, clean fuer Testphase); (2) Energie-Bot-Vogelperspektive vom Waffenhaendler EXAKT auch fuers Lagerfeuer im Inventory-Management nutzen (gleiche bewaehrte Kamera-Methode, Testbilder falls vorhanden); (3) Energie-Bot-Settings 'benutze Inventare 1-2-3-4' markierbar, damit der Bot weiss welche Inventar-Seiten er nutzt und wo er NICHT nachschaut.
  -> ABGEARBEITET 2026-06-23: alle drei Items gebaut+getestet+committet; Live-Test offen (PARKED_DECISION)
