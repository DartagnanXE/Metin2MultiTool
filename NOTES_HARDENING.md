# Puzzle-Härtung (Sicherheit der Wahrnehmungs->Aktions-Pipeline)

Ziel: Open-Loop-Bot sicherer machen. Additiv, flag-gesteuert, V-Mathematik unberührt.
Auslöser: User-Report "extrem schnell, aber setzt evtl. falsche Steine"; Log-Analyse
zeigte (a) Finish-Bug (Single zerstört 1-Zug-Loch), (b) Open-Loop-Wahrnehmung.

## Schichten (Status) — ALLE implementiert, 30 neue Tests grün, V-Mathematik unberührt

- [x] (1) Platzierungs-AUDIT + Konfidenz-Log (puzzle.py: \_arm/\_verify_last_placement, \_log_color_confidence) — DEFAULT AN. EHRLICH: KEIN Closed-Loop — verhindert den falschen Klick NICHT, DETEKTIERT ihn 1 Runde später im Log (Footprint-Mismatch). Fängt "Stein nicht gelandet"/"Form-Mismatch", NICHT einen systematischen Brett-Lesefehler (steckt in Soll UND Ist gleich). Echter Schutz bleibt die Frisch-Neulesung pro Runde.
- [x] (2) Median-Sampling (puzzle_detect.\_sample_cell_bgr, Flag color_stat) — DEFAULT 'mean' (byte-stabil; median=Opt-in, LIVE-TEST vor Umlegen). Brett-Doppellesung NICHT umgesetzt (Single-Capture/Tick; (4)-Re-Read deckt Animationsframe ab)
- [x] (3) Konfidenz-/Margin-Gate (PIECE_MIN_MARGIN) auf Toleranz-Fallback + falsche Disjunktheits-Doku korrigiert — AN
- [x] (4) Brett-Farbplausibilität (Garbage-Zählung) -> bounded Re-Read (BOARD_READ_RETRY_S) — DEFAULT AN
- [x] (5) Frame-Anker: SEAM verdrahtet (auto_anchor, DEFAULT AUS). EHRLICH: find_puzzle_offset ist nur Stub (prüft nur Standardpos); echter Detektor = Folgearbeit
- [x] (6) Finish-Fix (one_piece_completable + FINISH_HARD_CAP) + Safe-Fail (DISCARD_STOP_LIMIT) + Deluxe-Bounds-Guard — AN. trained_solver.py NICHT angefasst (nur finish-Flag gesteuert)

## Fehlerklassen -> Schicht

F1 Brett binär ohne Farbcheck -> (4) ; F2 Einzel-Pixel -> (2) ; F3 kein Closed-Loop -> (1) ;
F4 keine Konfidenz -> (3) ; F5 Tolerant-Disjunktheit falsch -> (3)+Doku ; F6 fester Offset -> (5) ;
F7 Brett einmal gelesen -> (4) Re-Read ; F8 kein Verwerf-Stop -> (6) ; F9 deluxe blind -> Bounds-Guard

## Neue Dateien/Konstanten

- puzzle_safety.py (rein): centroid_metrics, confident_type, footprint(\_from_cells), expected_board_after, verify_placement, one_piece_completable, piece_can_complete
- puzzle.py: FINISH_HARD_CAP=20, DISCARD_STOP_LIMIT=60, PIECE_MIN_MARGIN=30, BOARD_MAX_GARBAGE=2, BOARD_READ_RETRY_S=0.6
- Config-Flags (defaults.py/validate.py/run_loop.apply_puzzle_config): verify_placements, board_plausibility, color_stat, auto_anchor

## Verifikation

- tests/test_puzzle_safety.py (20) reine Logik · tests/test_puzzle_hardening.py (10) Glue gegen echten puzzle.py (Win-Stubs)
- Gesamtsuite: 1058 passed; 5 vorbestehende Headless-Import-Errors (pydirectinput/win32/customtkinter) = KEINE Regression

## NOCH LIVE ZU TESTEN durch User (headless nicht validierbar)

- color_stat='median' am echten Spiel testen, DANN Default umlegen
- auto_anchor: echten Offset-Detektor implementieren (Folgearbeit), vorher nutzlos
- Audit-Logs (PIECE_COLOR_OK / PLACEMENT_VERIFY / PIECE_COLOR_LOWCONF) aus echtem Lauf sammeln -> (3)-Schwellen kalibrieren
