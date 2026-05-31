// =====================================================================
//  Self-contained policy for the 4x6 fish puzzle (puzzle_simulator.html).
//  Faithful JS port of the calibrated "Ansatz B" heuristic, validated in
//  Monte-Carlo to E[boxes] ~= 19.4 (no deluxe) and P(<=10) ~= 20% (deluxe).
//  The exact DP optimum is E=15.57 / P(<=10)=18.7% (no deluxe), 35.0% with
//  deluxe; this heuristic is table-free (no 67MB V-table) and explainable.
//
//  chooseAction(board, piece, deluxeAvailable)
//    board : 4x6 array, board[r][c] = null (empty) or a color string (filled)
//    piece : { stueck, cells, color }  cells = [[dr,dc],...] (simulator format)
//            stueck in 1..6 for normal pieces, 'D' for the deluxe 2x3 probe.
//    deluxeAvailable : boolean
//  returns: {type:'place', r, c} | {type:'burn'} | {type:'useDeluxe'}
//
//  Box counter: read live from window.counts.total (the simulator's counter)
//  when present; otherwise estimated. Only the deluxe <=10 gate and the
//  deadline-9 reserve-abandon use the counter.
// =====================================================================
(function (root) {
  "use strict";
  const ROWS = 4,
    COLS = 6,
    NCELLS = 24;
  const FULL = (1 << NCELLS) - 1;
  const idx = (r, c) => r * COLS + c;

  // ---- piece geometry (fixed orientation, NO rotation) ----
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

  // corner 2x3 reserves (min-tiles 5 -> lower bound 6 boxes)
  function blockMask(r0, c0) {
    let m = 0;
    for (let dr = 0; dr < 2; dr++)
      for (let dc = 0; dc < 3; dc++) m |= 1 << idx(r0 + dr, c0 + dc);
    return m;
  }
  const CORNER_RESERVES = [
    blockMask(0, 0),
    blockMask(0, 3),
    blockMask(2, 0),
    blockMask(2, 3),
  ];
  // Fixed reserve target chosen once at the empty board (least-occupied corner = top-left).
  // Held constant for the whole game so the 2x3 finisher gap reliably materializes.
  const FIXED_RESERVE = blockMask(0, 0); // == 455
  // the 12 possible 2x3 positions (for deluxe gap detection)
  const ALL_2x3 = [];
  for (let r0 = 0; r0 <= ROWS - 2; r0++)
    for (let c0 = 0; c0 <= COLS - 3; c0++) ALL_2x3.push(blockMask(r0, c0));

  // neighbour masks + per-cell non-single cover
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
  function lowBit(x) {
    return 31 - Math.clz32(x);
  } // index of single set bit

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

  // ---- placement score (penalty; lower = better) — B's calibrated weights ----
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

  // ---- PLACE vs BURN (economic) — B's calibrated burn rule, thr=1.0 ----
  const MAX_CONSEC_BURN = 3,
    BURN_THR = 1.0,
    DELUXE_DEADLINE = 9;

  function decide(occ, piece, reserve, consecBurn) {
    const [bm, bs] = bestPlacement(occ, piece, reserve);
    if (bm === null || bs >= RESERVE_VIOLATE) return null; // no reserve-legal spot
    if (piece === 6 || consecBurn >= MAX_CONSEC_BURN) return bm; // never burn single / force progress
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

  // ---- board <-> occ bitmask ----
  function boardToOcc(board) {
    let occ = 0;
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS; c++) if (board[r][c]) occ |= 1 << idx(r, c);
    return occ;
  }
  function boxesUsed(board) {
    if (root && root.counts && typeof root.counts.total === "number")
      return root.counts.total;
    return popcount(boardToOcc(board)); // conservative fallback
  }
  function maskToRC(m) {
    const i = lowBit(m & -m);
    return [(i / COLS) | 0, i % COLS];
  }

  // pick the corner reserve with the fewest already-occupied cells
  function pickReserve(occ) {
    let best = null,
      bestFilled = 99;
    for (const r of CORNER_RESERVES) {
      const f = popcount(r & occ);
      if (f < bestFilled) {
        bestFilled = f;
        best = r;
      }
    }
    return best;
  }

  // ---- minimal cross-call state: consecutive-burn counter (anti-stall) ----
  // B's policy forces a placement after MAX_CONSEC_BURN burns in a row to finish
  // the complement before the deadline. The simulator is sequential & single-
  // threaded, so a module-level counter faithfully reproduces this. It auto-resets
  // whenever the board is empty (new game) so behaviour stays reproducible.
  let _consecBurn = 0;
  function chooseAction(board, piece, deluxeAvailable) {
    const occ = boardToOcc(board);
    const used = boxesUsed(board);
    const E = emptyMask(occ);

    // reset the consec-burn counter at the start of a fresh game (empty board)
    if (occ === 0) _consecBurn = 0;

    // (A) DELUXE finisher probe: gap is EXACTLY a 2x3 block AND boxes+1<=10.
    if (deluxeAvailable && popcount(E) === 6) {
      for (let i = 0; i < ALL_2x3.length; i++) {
        if (E === ALL_2x3[i]) {
          // remaining empties == one full 2x3 position
          if (used + 1 <= 10) return { type: "useDeluxe" };
          break;
        }
      }
    }
    // If the probe piece itself is the deluxe ('D') and we got here, no fire:
    if (piece && piece.stueck === "D") {
      // deluxe not warranted now -> signal "don't open deluxe" by burning the probe
      return { type: "burn" };
    }

    // (B) Reserve steering. Mirrors B's simulate(): a FIXED top-left 2x3 reserve is
    // kept empty; we fill only the 18-cell complement. The reserve is abandoned when
    //  - it can no longer fire within 10 boxes (used+1>10 once it is the sole gap), or
    //  - the deadline passed and the complement is not yet finished.
    let reserve = 0;
    if (deluxeAvailable) {
      const reserveStillEmpty = (FIXED_RESERVE & occ) === 0;
      if (reserveStillEmpty) {
        if (E === FIXED_RESERVE) {
          // reserve is the sole remaining gap -> (A) fires if used+1<=10; else drop it.
          reserve = used + 1 <= 10 ? FIXED_RESERVE : 0;
        } else if (used >= DELUXE_DEADLINE && (E & ~FIXED_RESERVE) !== 0) {
          reserve = 0; // deadline: complement not finished in time -> give up reserve
        } else {
          reserve = FIXED_RESERVE; // keep steering toward the 2x3 finisher gap
        }
      }
    }

    // (C) PLACE vs BURN via the calibrated rule (with anti-stall consec-burn).
    // NOTE: we deliberately do NOT relax into the reserve when it blocks all spots
    // (that would pollute the 2x3 finisher gap). Like B, we burn instead. The single
    // (never burned) plus the deadline-9 reserve-abandon guarantee termination.
    const pnum =
      typeof piece.stueck === "number" ? piece.stueck : guessPiece(piece);
    const chosen = decide(occ, pnum, reserve, _consecBurn);

    if (chosen === null) {
      _consecBurn++; // burning -> bump the anti-stall counter
      return { type: "burn" };
    }
    _consecBurn = 0; // placed -> reset
    const [r, c] = maskToRC(chosen);
    return { type: "place", r, c };
  }

  // map an arbitrary piece (by cells) to its number, if possible
  function guessPiece(piece) {
    const key = JSON.stringify(piece.cells);
    for (const p in PIECES)
      if (JSON.stringify(PIECES[p]) === key) return Number(p);
    return 6;
  }

  root.chooseAction = chooseAction;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      chooseAction,
      _internal: {
        decide,
        bestPlacement,
        boardToOcc,
        PLACE,
        pickReserve,
        CORNER_RESERVES,
        ALL_2x3,
        MAX_CONSEC_BURN,
      },
    };
  }
})(
  typeof window !== "undefined"
    ? window
    : typeof global !== "undefined"
      ? global
      : this,
);
