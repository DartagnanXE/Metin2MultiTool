# Energiesplitter — verbindliche Präzisierungen (User, 2026-06-15)

Diese Punkte sind BINDEND und ergänzen/überschreiben die DESIGN.md, wo sie kollidieren.
Sie fließen in Phase 2 (Implementierung) ein.

## A1 — Kaufstrategie (Stack-Größen)

- **Hammer:** Es gibt 3 Stack-Größen (1 / 50 / 200). Immer die **größtmöglichen Stacks**
  kaufen (200er bevorzugt) → minimiert Klicks/Zeit. Kleinere Stacks (50/1) nur,
  um die **Zielanzahl exakt zu treffen** oder um in den verbleibenden freien
  Inventarplatz zu passen (200er passt nicht in zu wenig freien Platz).
- **Dolche:** immer **einzeln (1)**.

## A2 — Drag-and-Drop wiederverwenden (KEIN Neubau)

- Das Hammer→Dolch-Verarbeiten nutzt das **bereits erfolgreich eingesetzte
  Drag-and-Drop aus dem Inventar-Management** (inventory manage/refill). Das
  bestehende Drag-Primitiv finden und wiederverwenden, nicht neu erfinden.

## A3 — Eingabe = Hammer-ANZAHL + Yang-Rechner (statt Cash-Betrag)

- Eingabe in der UI ist die **Anzahl Hammer (XX)**, nicht ein Geldbetrag.
- Ein **Rechner** zeigt live die benötigten Yang an, inkl. Aufschlüsselung:
  - Hammer: XX × 15.000 Yang
  - Dolche: XX × 15.000 Yang (1:1)
  - **Summe** = XX × 30.000 Yang
    (Energie-Freischaltung-Kosten ggf. separat ausweisen, falls relevant.)
- Sicherheits-Check bleibt: Gold muss reichen (pro Hammer 1 Dolch); sonst
  sauberer Stopp statt Blind-Kauf.

## Status

- Phase 1 (Bildanalyse + Design + Adversarial, Workflow wf_309fff8a-cc6) läuft.
- Diese Addenda werden beim Phase-2-Start eingearbeitet (Config/UI: Hammer-Count
  - Rechner; Detection: Stack-Größen-Auswahl 200/50/1; Reuse: Inventar-Drag).
