# Analyse + Plan: „Warum merkt der Bot nicht, dass etwas schiefging?"

> Erstellt 2026-08-06 nach dem Live-Log vom 2026-07-30 07:31 und der Spielmeldung
> „Du kannst die Aktion nicht ausführen während du angelst".
> Belege sind mit `datei:zeile` angegeben — jede Behauptung hier ist am Code nachlesbar.

## Die gemeinsame Ursache

Die drei gemeldeten Probleme (Köder nachlegen, automatisch grillen, die Spielmeldung)
sind **kein Zufall nebeneinander**. Sie sind drei Ausprägungen desselben Defekts:

**Der Bot sendet Eingaben und nimmt an, dass sie gewirkt haben.**
Es gibt keinen einzigen Rückkanal aus dem Spiel, der eine Aktion bestätigt.
Der Client kann jede dieser Aktionen ablehnen — und lehnt sie im Angel-Zustand
nachweislich ab —, ohne dass der Bot davon je erfährt.

Deshalb kommt zuerst die Messung, dann der Fix. Ein Fix ohne Sensor wäre wieder
nur eine Vermutung, die sich „richtig anfühlt".

---

## Befund 1 — Woher die Spielmeldung kommt (starke Hypothese, noch nicht bewiesen)

`_abort_minigame()` in `fishingbot.py:459-489` drückt ESC und datiert danach den
Timer so vor, dass der nächste Tick **ohne jede Pause** die Köder-Taste drückt:

```python
self.state = 0
self.timer_action = time() - max(self.bait_time, self.throw_time, self.game_time) - 1.0
```

Im Live-Log liegen deshalb drei Aktionen in **derselben Sekunde**:

```
07:31:04 | STATE 0 | Whitelist: unwanted catch (Handschuh weiser Kaiser) -> aborting minigame (esc)
07:31:04 | STATE 1 | Bait set (key 2)
07:31:04 | STATE 2 | Cast out (key 1)
```

Der Client hat den Angel-Zustand zu diesem Zeitpunkt noch nicht verlassen. Eine
Quickslot-Taste ist für ihn eine Item-Aktion → er antwortet mit genau dieser Meldung
und **verwirft den Tastendruck**. Passend dazu endete der Wurf um 07:31:14 fünf
Sekunden später mit „No bite" — das Bild eines Wurfs ohne angebrachten Köder.

Zum Vergleich: jeder andere Pfad hat Luft. Rundenende 07:31:13 → Köder 07:31:14,
Fehlwurf 07:31:19 → Köder 07:31:20. **Nur der Abbruch-Pfad wartet null Sekunden.**

**Ehrlich:** bewiesen ist das nicht. Der Bot liest die Systemmeldung nicht, also
kann niemand sagen, welche der drei Tasten sie ausgelöst hat. Genau diese Lücke
schließt Stufe 1.

## Befund 2 — Das Nachlegen meldet einen Erfolg, den es nie geprüft hat

`interface/refill.py:505-507`, das Ende von `refill_from_inventory`:

```python
drag(inp, fx, fy, int(target_xy[0]), int(target_xy[1]), sleep=sleep)
_napped(0.15)
return 'dragged'
```

`'dragged'` heißt „ich habe die Maus bewegt" — **nicht** „der Köder liegt im Slot".
`fishingbot.py:664` loggt darauf „nachgelegt". Verwirft der Client den Drag, steht
im Log trotzdem Erfolg.

Verschärfend: `_maybe_refill_bait` läuft in **State 0** (`fishingbot.py:1125`), also
unmittelbar nach dem Fang — im selben Fenster, in dem der Char noch angelt. Der
Drag trifft damit systematisch den Zustand, in dem der Client Inventar-Aktionen
ablehnt.

## Befund 3 — „Grillen wenn Inventar voll" existiert nicht

Eine Voll-Erkennung gibt es im Code nicht (Suche über `inventory/` und `interface/`
ohne Treffer). Vorhanden ist nur der Zeitweg: `timer_action='cleanup'` →
`_start_timer_cleanup` (`interface/app/views_inventory.py:796`) → Scan → Grillen →
Wegwerfen → Auto-Neustart.

Zwei Gründe, warum das „nicht zu gehen scheint":

1. Der Ablauf hängt am **Lauf-Zeitlimit**, nicht an einem eigenen Grill-Intervall.
   Ohne gesetztes Zeitlimit *und* Aktion „Inventar-Cleanup" passiert gar nichts.
2. Er stoppt zwar den Lauf, prüft aber **nicht, ob der Charakter noch angelt**,
   bevor er Drags im Inventar ausführt — dieselbe Falle wie beim Köder.

---

## Was auf der Liste noch fehlt

- **Nachher-Prüfung für jede Aktion.** Der eigentliche Grund, warum alles „scheint
  nicht zu gehen" statt klar zu scheitern.
- **Falschtreffer R1C4** (gemessen am Screenshot vom 2026-08-05): ein bronzenes
  Abzeichen wird als `Worm` gelesen (Distanz 29,49 / Marge 13,86 → die
  margin-primary-Ausnahme greift). Solange der echte Stapel existiert, gewinnt er
  zeilenweise. Ist er alle, zieht das Nachlegen **das Abzeichen** in den Köderslot,
  statt ehrlich „kein Köder mehr" zu melden.
- **Phantom-Stapelzahlen** durch den Leuchtrand markierter Fische (717 statt leer).
  Rein kosmetisch — `stack_totals()` wird nur in `views_inventory.py:160` angezeigt.
- **Kein Verbrauchs-Zähler.** Der Quickslot zeigt die Stapelzahl des Köders (im
  Screenshot: 195). Sinkt sie bei einem Wurf nicht, wurde kein Köder angebracht.
  Dieser Sensor ist praktisch gratis und heute ungenutzt.

---

## Der Plan

### Stufe 0 — ERLEDIGT am 2026-08-06 (5 Screenshots, alle 802×632)

Gemessen an den Bildern: Köder 195 / leer / 199 („befestigt") / 197 („getauscht") /
195 („kannst diese Aktion nicht ausführen"). Ergebnis besser als erwartet — drei
der vier Sensoren funktionieren **ohne eine Zeile neuen Code**.

**Die Meldungszeile liegt in der Region, die der Bot ohnehin liest.**
Zeilenprojektion ergibt die unterste Chat-Zeile bei **y 582–589**, Text von
x≈111 bis max. 384. `CHAT_REGION = (115, 579, 405, 596)` deckt das ab. Bei zwei
Meldungen liegt die ältere bei y 567–574 (Zeilenabstand 15 px) — für uns irrelevant,
die relevante Meldung ist immer die unterste.

**Diskriminator-Scores an Wortposition 4** (`DISC_MIN_SCORE = 0.55`):

| Bild | Meldung | Wort[4] | `koeder` | bester anderer | Deutung |
|------|---------|---------|----------|----------------|---------|
| 10 | „Du hast Wurm als Köder am Haken befestigt." | Köder (26 px) | **1.000** | 0.323 | Erfolg |
| 11 | „Du tauschst den aktuellen Köder gegen Wurm." | Köder (26 px) | **1.000** | 0.323 | Erfolg |
| 12 | „Du kannst diese Aktion nicht ausführen, während du angelst." | nicht (21 px) | 0.137 | 0.324 | — |

→ **Der Erfolgs-Sensor existiert bereits**: beide Erfolgsmeldungen treffen den
vorhandenen `disc__koeder` mit Score 1,000. Der Bot verwirft das Ergebnis heute nur
als `NONE` („Köder dran, noch kein Biss"), statt es als Bestätigung zu verbuchen.
→ **Für die Blockade fehlt genau EIN Template**: das Wort „nicht" (8×21 px) aus
Bild 12. Bild 12 wird heute sauber abgelehnt (Höchstwert 0,324 < 0,55), es gibt also
keinen Fehlalarm — nur Blindheit.

**Korrektur meiner eigenen Annahme:** die fehlenden Glyphen `D`/`ü` sind hier
**gegenstandslos**. Der Diskriminator vergleicht ganze Wort-Bitmaps, keine
Einzelzeichen — der Atlas wird für diesen Sensor gar nicht angefasst.

**Härtung gegen Fehlalarm:** „nicht" an Position 4 kann auch in fremden
Chat-Meldungen vorkommen. Deshalb zweites Merkmal verlangen (Wortanzahl 9 und/oder
Wort[8] = „angelst.", 33 px), bevor „blockiert" gemeldet wird.

**Quickslot-Sensoren (Slot 2 = Client-Zentrum (364, 582)):**

| Bild | Zustand | `quickslot_is_empty` | mean / std / bright | `read_count` |
|------|---------|----------------------|---------------------|--------------|
| 8 | belegt 195 | False | 70,9 / 100,4 / 121 | **195** (Konf. 0,998) |
| 9 | **leer** | **True** | 9,8 / 15,9 / 2 | – (n_digits 0) |
| 10 | belegt 199 | False | 72,9 / 101,6 / 125 | **199** (0,998) |
| 11 | belegt 197 | False | 67,1 / 97,7 / 113 | **197** (0,998) |
| 12 | belegt 195 | False | 70,9 / 100,4 / 121 | **195** (0,998) |

→ Die Leer-Erkennung trennt mit riesigem Abstand (std 16 gegen 98, helle Pixel 2
gegen 113) — die gelockerten Schwellen (`FLAT_STD 30`, `MAX_BRIGHT_PX 20`) sind
damit **an echten Bildern belegt**, nicht mehr nur plausibel. Die offene Frage aus
dem Review-Panel vom 2026-07-22 („kann das False-Empty erzeugen?") ist beantwortet: nein.
→ Die Stapelzahl liest sich **unverändert mit der Inventar-Ziffern-Engine**
(`inventory/digits.read_count` auf einem 32×32-Ausschnitt um das Slot-Zentrum).
Achtung: bei leerem Slot liefert sie `value=1, n_digits=0` (der Ink-Fallback) —
die Zahl darf also nur gelesen werden, wenn der Slot als belegt gilt.

### Stufe 1 — Sensorik: der Bot merkt, dass er blockiert wurde

1. **Systemmeldungs-Leser** auf Basis des bestehenden Chat-OCR (`fishing_chat.py`) —
   erkennt die Ablehnung und macht sie zu einem Ereignis statt zu einem Rätsel.
2. **Köder-Verbrauchszähler**: Stapelzahl im Quickslot vor und nach dem Wurf lesen
   (die Ziffern-Engine `inventory/digits.py` kann das bereits). Keine Abnahme =
   der Wurf ging ins Leere. Unabhängig vom Chat, deshalb der verlässlichere Sensor.
3. **Aktions-Journal** als JSONL neben dem Textlog: pro Aktion eine Zeile mit
   Absicht, Messung vorher, Messung nachher, Urteil (`ok` / `blockiert` /
   `wirkungslos`) und Dauer. Damit ist eine Sitzung auswertbar statt nur lesbar —
   „von 300 Würfen sind 12 verpufft, alle 12 nach einem Whitelist-Abbruch" ist eine
   Antwort, „irgendwas stimmt nicht" ist keine.
4. **Screenshot-Dump bei jedem Urteil ≠ ok**, gedeckelt (z. B. 20 pro Lauf), damit
   ein Fehlschlag nachher ansehbar ist statt rekonstruiert werden zu müssen.

### Stufe 2 — Regelkreis: jede Aktion prüft ihr eigenes Ergebnis

- **Nachlegen**: Quickslot vorher/nachher vergleichen. Kein Köder im Slot →
  `'dragged'` wird zu `'failed'`, mit einem Wiederholungsversuch und einem klaren
  Log statt einer Erfolgsmeldung.
- **Grillen/Wegwerfen**: Slotzahl vorher/nachher. Kein Unterschied → melden statt
  „fertig" behaupten.
- **Angel-Zustand als Vorbedingung**: vor jeder Inventar-Aktion sicherstellen, dass
  der Char nicht mehr angelt (ESC + kurze Wartezeit + Nachweis über den Sensor aus
  Stufe 1), statt es zu hoffen.

### Stufe 3 — Die eigentlichen Fixes

- **Cooldown nach dem Abbruch**: `_abort_minigame` darf den Timer nicht auf „sofort"
  vordatieren. Die richtige Wartezeit messe ich in Stufe 1 (wie lange dauert es,
  bis Aktionen wieder angenommen werden), statt sie zu raten.
- **Grill-Auslöser „Inventar voll"**: freie Slots zählen (der Scanner liefert die
  Zahl bereits) und unter einer Schwelle den bestehenden Grill-Ablauf starten —
  plus ein eigenes Zeitintervall, unabhängig vom Lauf-Zeitlimit.
- **R1C4-Falschtreffer** entschärfen, ohne die Ausnahme zu töten, die die
  leuchtenden Fische korrekt erkennt.

### UMGESETZT in v1.6.6 (2026-08-06)

- `fishing_chat.read_action_feedback` — liest die Client-Antwort, liefert
  `(BAITED | BLOCKED | NONE, kennung)`. `read_hook` blieb unangetastet, damit der
  Whitelist-Pfad garantiert unverändert bleibt; verifiziert an allen 22
  Ground-Truth-Bildern.
- `fishing_chat_templates/disc__nicht.png` — die eine fehlende Wortvorlage.
- `FishingBot._check_bait_feedback` — wertet die Antwort aus: bestätigt → zählen;
  abgelehnt vor dem Wurf → warten und neu ködern; abgelehnt im laufenden
  Minispiel → nur protokollieren (ein Fang stirbt nie an einer Chat-Zeile).
- **Doppelwertungs-Sperre** (bei der Selbstprüfung gefunden): die Chat-Zeile
  bleibt stehen, ohne Fingerabdruck hätte derselbe Text endlos gezählt.
- `_ABORT_COOLDOWN_S = 1.0` — der Whitelist-Abbruch ködert nicht mehr in
  derselben Sekunde neu.
- Köder-Bilanz alle 25 Würfe im Log, ohne Schalter.
- `refill.find_first` fasst nur Treffer unter `MATCH_THRESHOLD` an (R1C4).
- `tests/test_bait_feedback.py` — 21 Tests; die Logik-Tests laufen auch ohne
  Screenshots, die Bildtests skippen sauber.
- Referenz-Screenshots nach `FischOCR/` gesichert (`aktion_*`, `quickslot_*`) —
  der Bild-Cache ist flüchtig, ein früherer Beleg war schon verloren.

### NICHT umgesetzt — bewusst offen

**Grillen bei vollem Inventar / nach eigenem Intervall.** Der Auslöser fehlt
weiterhin; heute hängt das Grillen am Lauf-Zeitlimit mit Aktion
„Inventar-Cleanup". Der Grund für die Vertagung: der Ablauf sitzt in der
GUI-Schicht (`interface/app/views_inventory.py`) und die ist unter WSL nicht
testbar (`customtkinter` gibt es nur unter Windows) — ein blind eingebauter
Auslöser, der ungefragt Fische verbrennt, ist das falsche Risiko für eine
Testversion. Braucht eine eigene Runde mit Live-Prüfung.

## Nachtrag 2026-08-09 — warum Fänge nach dem Nachlegen nicht mehr gelesen wurden

Live-Report nach v1.6.6: „Nach dem Nachlegen des Köders bleibt der Cursor an der
Stelle … dadurch wird die Chat-Erkennung der gefangenen Fische blockiert."
Am mitgelieferten Bild nachgemessen und bestätigt — die Ursache ist aber nicht
der Mauszeiger, sondern der **Item-Tooltip**, den der Client unter dem Zeiger
einblendet:

| Größe | Wert |
| --- | --- |
| Ablageort des Köder-Drags | `QUICKSLOT_XY[2] = (364, 582)` |
| Tooltip-Rahmen (gemessen) | y 514 – **592** |
| Chat-Lesezone | y 579 – 596 |
| Überlappung | **14 von 18 Zeilen**, inkl. der ganzen Textzeile 582–589 |

Der Tooltip wird nicht nur *darübergelegt*, sondern **mitgelesen**: Auf einem
LEEREN Chat fand `_chat_line_words` fünf „Wörter" — das war der Tooltip-Text
(„Beliebter Köder, der Fische …"). Damit war jede Namens- und Köder-Erkennung
unbrauchbar, solange der Zeiger dort stand.

`_maybe_refill_bait` war der einzige Pfad ohne Cursor-Park; `inventory_runner`,
`inventory_campfire_runner` und `inventory_discard_runner` parken längst, mit
exakt dieser Begründung im Kommentar („its glow/tooltip can occlude the slot").

**Zwei Verteidigungslinien gebaut:**

1. `refill.park_cursor` + `CURSOR_PARK_XY = (585, 372)` — nach JEDEM Ausgang des
   Nachlegens (auch `error`/`stopped`). Nur `moveTo`, nie ein Klick: ein
   Weltklick ließe die Figur loslaufen. Der Punkt liegt mit doppelter Reserve
   außerhalb der Lesezone (x 585 > 405 **und** y 372 ≪ 548) und auf keinem Slot.
2. `fishing_chat.zone_obstructed` — Wortbreite als Overlay-Merkmal. Über alle 13
   gelabelten Zeilen ist das breiteste echte Wort **66 px**
   („Spiegelkarpfen"/„Haarfärbemittel"), der Tooltip bildet einen **100 px**-Block;
   `MAX_WORD_WIDTH = 85` liegt in der Lücke. Verdeckte Frames liefern NONE
   **ohne** Fingerabdruck, damit ein späterer freier Frame dieselbe Zeile normal
   werten darf. Restfehler zeigt in die sichere Richtung: ein fälschlich
   verworfener Frame kostet eine Whitelist-Entscheidung, ein nicht erkanntes
   Overlay erzeugt einen falschen Namen.

Neu im Log: „Chat-Zeile von einem Spiel-Tooltip verdeckt …" (gedrosselt, 30 s) —
damit unterscheidet sich „nichts am Haken" künftig von „kann nicht lesen".

Beleg-Bild: `FischOCR/tooltip_verdeckt_chatzeile.png`.

### Reihenfolge

Stufe 0 und 1 zuerst, und zwar zusammen: erst wenn ein Fehlschlag sichtbar ist,
lässt sich ein Fix belegen statt behaupten. Stufe 3 ohne Stufe 1 wäre wieder
„fühlt sich besser an" — genau der Modus, der uns die zwei kaputten Releases
v1.1.1 und v1.1.2 eingebracht hat.
