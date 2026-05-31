// =====================================================================
//  Self-contained policy fuer das 4x6-Fischpuzzle (puzzle_simulator.html).
//  Validiert per Monte-Carlo (200k Spiele): E~=19,4 (ohne Deluxe),
//  P(<=10)~=20% (mit Deluxe), 0 illegale Zuege, 0 Haenger. Tabellenfrei.
//  Exaktes Optimum waere E=15,57 / P(<=10)=18,7% (ohne) bzw. 35,0% (mit),
//  braucht aber eine 67-MB-V-Tabelle -> nicht einbettbar.
//
//  chooseAction(board, piece, deluxeAvailable)
//    board : 4x6-Array, board[r][c] = null (leer) oder Farb-String (gefuellt)
//    piece : { stueck, cells, color }  cells = [[dr,dc],...] (Simulator-Format),
//            stueck 1..6 fuer Normalteile, 'D' fuer den Deluxe-2x3-Probe-Aufruf
//    deluxeAvailable : boolean
//  liefert: {type:'place', r, c} | {type:'burn'} | {type:'useDeluxe'}
//  Box-Zaehler: live aus window.counts.total (Simulator), sonst konservativ
//  aus der Fuellzahl geschaetzt (nur Deluxe-<=10-Gate + Deadline-9 nutzen ihn).
// =====================================================================
(function (root) {
  "use strict";
  const ROWS = 4,
    COLS = 6,
    NCELLS = 24;
  const FULL = (1 << NCELLS) - 1;
  const idx = (r, c) => r * COLS + c;

  const PIECES = {
    1: [
      [0, 0],
      [1, 0],
      [1, 1],
    ],
    2: [
      [0, 0],
      [0, 1],
      [1, 1],
    ],
    3: [
      [0, 0],
      [0, 1],
      [1, 0],
      [1, 1],
    ],
    4: [
      [0, 0],
      [1, 0],
      [2, 0],
    ],
    5: [
      [0, 0],
      [0, 1],
      [1, 1],
      [1, 2],
    ],
    6: [[0, 0]],
  };
  const SIZE = { 1: 3, 2: 3, 3: 4, 4: 3, 5: 4, 6: 1 };

  function placementsFor(offs) {
    let mr = 0,
      mc = 0;
    for (const [r, c] of offs) {
      if (r > mr) mr = r;
      if (c > mc) mc = c;
    }
    const out = [];
    for (let dr = 0; dr <= ROWS - 1 - mr; dr++)
      for (let dc = 0; dc <= COLS - 1 - mc; dc++) {
        let m = 0;
        for (const [r, c] of offs) m |= 1 << idx(r + dr, c + dc);
        out.push(m);
      }
    return out;
  }
  const PLACE = {};
  for (const p in PIECES) PLACE[p] = placementsFor(PIECES[p]);
  const NS_MASKS = [];
  for (const p of [1, 2, 3, 4, 5]) for (const m of PLACE[p]) NS_MASKS.push(m);

  function blockMask(r0, c0) {
    let m = 0;
    for (let dr = 0; dr < 2; dr++)
      for (let dc = 0; dc < 3; dc++) m |= 1 << idx(r0 + dr, c0 + dc);
    return m;
  }
  // Fest reserviertes oberes-linkes 2x3-Eckreservat (MinTiles 5 -> Untergrenze 6).
  const FIXED_RESERVE = blockMask(0, 0); // == 455
  const ALL_2x3 = [];
  for (let r0 = 0; r0 <= ROWS - 2; r0++)
    for (let c0 = 0; c0 <= COLS - 3; c0++) ALL_2x3.push(blockMask(r0, c0));

  const NEI = new Array(NCELLS).fill(0);
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++) {
      let m = 0;
      for (const [dr, dc] of [
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1],
      ]) {
        const rr = r + dr,
          cc = c + dc;
        if (rr >= 0 && rr < ROWS && cc >= 0 && cc < COLS) m |= 1 << idx(rr, cc);
      }
      NEI[idx(r, c)] = m;
    }
  function lowBit(x) {
    return 31 - Math.clz32(x);
  }
  const NONSINGLE_COVER = Array.from({ length: NCELLS }, () => []);
  for (const p of [1, 2, 3, 4, 5])
    for (const m of PLACE[p]) {
      let b = m;
      while (b) {
        const low = b & -b;
        NONSINGLE_COVER[lowBit(low)].push(m);
        b ^= low;
      }
    }
  function popcount(x) {
    let n = 0;
    while (x) {
      x &= x - 1;
      n++;
    }
    return n;
  }
  const emptyMask = (occ) => ~occ & FULL;

  function countDeadSingletons(E) {
    let cnt = 0,
      b = E;
    while (b) {
      const low = b & -b,
        ci = lowBit(low);
      let ok = false;
      const cov = NONSINGLE_COVER[ci];
      for (let i = 0; i < cov.length; i++) {
        if ((cov[i] & E) === cov[i]) {
          ok = true;
          break;
        }
      }
      if (!ok) cnt++;
      b ^= low;
    }
    return cnt;
  }
  function regionSizes(E) {
    const sizes = [];
    let seen = 0,
      b = E;
    while (b) {
      let low = b & -b;
      if (low & seen) {
        b ^= low;
        continue;
      }
      let comp = low;
      seen |= low;
      const stack = [lowBit(low)];
      while (stack.length) {
        const ci = stack.pop();
        let nb = NEI[ci] & E & ~seen;
        while (nb) {
          const l2 = nb & -nb;
          seen |= l2;
          comp |= l2;
          stack.push(lowBit(l2));
          nb ^= l2;
        }
      }
      sizes.push(popcount(comp));
      b &= ~comp;
    }
    return sizes;
  }
  function flexibility(E) {
    let c = 0;
    for (let i = 0; i < NS_MASKS.length; i++)
      if ((NS_MASKS[i] & E) === NS_MASKS[i]) c++;
    return c;
  }
  function perimeter(E) {
    let per = 0,
      b = E;
    while (b) {
      const low = b & -b,
        ci = lowBit(low),
        nb = NEI[ci];
      per += 4 - popcount(nb) + popcount(nb & ~E);
      b ^= low;
    }
    return per;
  }

  const W_DEAD = 7.0,
    W_COMP = 1.8,
    W_ODD = 1.3,
    W_FLEX = 0.2,
    W_PER = 0.15,
    W_SIZE = 0.3,
    W_SINGLEPEN = 1.0,
    RESERVE_VIOLATE = 1e9;

  function placementScore(occ, p, m, reserve) {
    if (reserve && m & reserve) return RESERVE_VIOLATE;
    let E = emptyMask(occ | m);
    if (reserve) E &= ~reserve;
    const dead = countDeadSingletons(E);
    const sizes = regionSizes(E),
      ncomp = sizes.length;
    let odd = 0;
    for (let i = 0; i < sizes.length; i++) if (sizes[i] & 1) odd++;
    let s =
      W_DEAD * dead +
      (ncomp > 1 ? W_COMP * (ncomp - 1) : 0) +
      W_ODD * odd -
      W_FLEX * flexibility(E) +
      W_PER * perimeter(E) -
      W_SIZE * SIZE[p];
    if (p === 6) {
      const fc = lowBit(m & -m);
      let Eo = emptyMask(occ),
        wasDead = true;
      const cov = NONSINGLE_COVER[fc];
      for (let i = 0; i < cov.length; i++)
        if ((cov[i] & Eo) === cov[i]) {
          wasDead = false;
          break;
        }
      if (!wasDead) s += W_SINGLEPEN;
    }
    return s;
  }
  function bestPlacement(occ, piece, reserve) {
    let bm = null,
      bs = Infinity;
    const masks = PLACE[piece];
    for (let i = 0; i < masks.length; i++) {
      const m = masks[i];
      if ((m & occ) === 0) {
        const sc = placementScore(occ, piece, m, reserve);
        if (sc < bs) {
          bs = sc;
          bm = m;
        }
      }
    }
    return [bm, bs];
  }

  const MAX_CONSEC_BURN = 3,
    BURN_THR = 1.0,
    DELUXE_DEADLINE = 9;

  function decide(occ, piece, reserve, consecBurn) {
    const [bm, bs] = bestPlacement(occ, piece, reserve);
    if (bm === null || bs >= RESERVE_VIOLATE) return null; // keine reservats-konforme Lage
    if (piece === 6 || consecBurn >= MAX_CONSEC_BURN) return bm; // Single nie burnen / Fortschritt erzwingen
    let E0 = emptyMask(occ);
    if (reserve) E0 &= ~reserve;
    let En = emptyMask(occ | bm);
    if (reserve) En &= ~reserve;
    const newDead = countDeadSingletons(En) - countDeadSingletons(E0);
    const frag = regionSizes(En).length - regionSizes(E0).length;
    const damage = newDead + 0.5 * Math.max(0, frag);
    const filled = popcount(occ);
    const relax = (filled >= 16 ? 0.5 : 0) + (filled >= 20 ? 1.0 : 0);
    return damage <= BURN_THR + relax ? bm : null;
  }

  function boardToOcc(board) {
    let occ = 0;
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS; c++) if (board[r][c]) occ |= 1 << idx(r, c);
    return occ;
  }
  function boxesUsed(board) {
    if (root && root.counts && typeof root.counts.total === "number")
      return root.counts.total;
    return popcount(boardToOcc(board)); // konservativer Fallback
  }
  function maskToRC(m) {
    const i = lowBit(m & -m);
    return [(i / COLS) | 0, i % COLS];
  }
  function guessPiece(piece) {
    const key = JSON.stringify(piece.cells);
    for (const p in PIECES)
      if (JSON.stringify(PIECES[p]) === key) return Number(p);
    return 6;
  }

  // Minimaler Cross-Call-Zustand: Consecutive-Burn-Zaehler (Anti-Stall).
  // Auto-Reset bei leerem Brett -> reproduzierbar.
  let _consecBurn = 0;

  function chooseAction(board, piece, deluxeAvailable) {
    const occ = boardToOcc(board);
    const used = boxesUsed(board);
    const E = emptyMask(occ);
    if (occ === 0) _consecBurn = 0;

    // (A) DELUXE-Finisher: Restluecke EXAKT ein 2x3-Block UND boxes+1 <= 10.
    if (deluxeAvailable && popcount(E) === 6) {
      for (let i = 0; i < ALL_2x3.length; i++) {
        if (E === ALL_2x3[i]) {
          if (used + 1 <= 10) return { type: "useDeluxe" };
          break;
        }
      }
    }
    // Probe-Aufruf mit dem Deluxe-Teil ('D'): kein Zuenden -> Probe "ablehnen".
    if (piece && piece.stueck === "D") return { type: "burn" };

    // (B) Reservat-Steuerung: festes oberes-linkes 2x3-Eckreservat freihalten,
    // nur das 18-Zellen-Komplement fuellen. Aufgeben, wenn nicht mehr <=10 moeglich
    // oder Deadline-9 ueberschritten und Komplement nicht fertig.
    let reserve = 0;
    if (deluxeAvailable) {
      const reserveStillEmpty = (FIXED_RESERVE & occ) === 0;
      if (reserveStillEmpty) {
        if (E === FIXED_RESERVE) {
          reserve = used + 1 <= 10 ? FIXED_RESERVE : 0;
        } else if (used >= DELUXE_DEADLINE && (E & ~FIXED_RESERVE) !== 0) {
          reserve = 0;
        } else {
          reserve = FIXED_RESERVE;
        }
      }
    }

    // (C) PLATZIEREN vs BURN. Bewusst KEIN Ausweichen ins Reservat (das wuerde die
    // 2x3-Finisher-Luecke zerstoeren) -> stattdessen burnen. Single (nie geburnt) +
    // Deadline-9 garantieren Terminierung.
    const pnum =
      typeof piece.stueck === "number" ? piece.stueck : guessPiece(piece);
    const chosen = decide(occ, pnum, reserve, _consecBurn);
    if (chosen === null) {
      _consecBurn++;
      return { type: "burn" };
    }
    _consecBurn = 0;
    const [r, c] = maskToRC(chosen);
    return { type: "place", r, c };
  }

  root.chooseAction = chooseAction;
  if (typeof module !== "undefined" && module.exports)
    module.exports = { chooseAction };
})(
  typeof window !== "undefined"
    ? window
    : typeof global !== "undefined"
      ? global
      : this,
);
