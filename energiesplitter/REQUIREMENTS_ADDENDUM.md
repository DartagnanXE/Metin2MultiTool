# Energiesplitter — verbindliche Präzisierungen (User)

Diese Punkte sind BINDEND und ergänzen/überschreiben die DESIGN.md, wo sie kollidieren.

## A0 — Umbau 2026-06-16: YANG ist vollständig entfernt

- **Kein Yang mehr:** kein Preis, kein Kontostand, keine Ausgabe-Verfolgung,
  kein Yang-Rechner, kein Gold-Reader, keine Yang-Ziffern-Templates,
  kein `gold_floor`/`max_gold_spend`/`yang_check`.
- Als OCR-unabhängige Backstops bleiben **`max_actions`** und
  **`consecutive_unverified_stop`** wirksam, dazu die **Erkennung-vor-Aktion**
  (Kauf/Drag nur auf template-verifizierte Ziele) und der Phase-0-GATE.
- Der Phase-0-GATE armt nur, wenn `detect.assets_ready(mode)` (Item-/NPC-
  Templates + Shop-Anker) UND `geometry.is_calibrated` (800×600) UND
  `detect.grid_present()` (Inventar-Raster auflösbar) grün sind. KEIN Yang-Teil.

## A1 — Kaufstrategie

- **Hammer (Aktion 1):** IMMER **200er-Stacks**. Die UI-Eingabe ist
  **`stack_count` (X) = Anzahl 200er-Stacks**. Pro Kauf-Schritt wird genau ein
  200er-Stack gekauft (per Template + `SHOP_HAMMER_ANCHOR`, der laut Kalibrierung
  der 200er ist), Re-Read-verifiziert (Hammer-Bestand stieg), bis X Stacks
  gekauft sind → Auto-Stop. Keine greedy 1/50/200-Logik mehr, kein `prefer_stack`.
- **Dolche (Aktion 2):** **nacheinander** verarbeitet. Eingabe
  **`daggers_per_round` = Dolche pro Runde** (default 1). Es gibt KEINE
  Massen-Verarbeitung und kein `process_mode`/`batch_size` mehr.

## A2 — Drag-and-Drop wiederverwenden (KEIN Neubau)

- Das Hammer→Dolch-Verarbeiten nutzt das **bereits erfolgreich eingesetzte
  Drag-and-Drop aus dem Inventar-Management** (`inventory_discard.drag`). Das
  bestehende Drag-Primitiv wiederverwenden, nicht neu erfinden.

## A3 — Dolch-Mechanik (sequenziell)

- EIN Drag eines Hammer-**STACKS** auf einen Dolch verbraucht **1 Hammer + 1
  Dolch** (NICHT den ganzen Stack).
- Ablauf (Aktion 2): Schleife bis keine Hämmer mehr im Inventar:
  1. `daggers_per_round` Dolche kaufen (template-verifiziert, Rechtsklick je Dolch).
  2. Die gekauften Dolche EINZELN NACHEINANDER verarbeiten: für JEDEN Dolch den
     Hammer-Stack-Slot (Template=Hammer) auf den Dolch-Slot (Template=Dolch)
     ziehen → Re-Read-Verifikation (Dolch-Slot leer + Hammer dekrementiert).
- **Kein Bestätigungsfenster.** Erkennung-vor-Aktion (src=Hammer, dst=Dolch live
  verifiziert) bleibt zwingend.
