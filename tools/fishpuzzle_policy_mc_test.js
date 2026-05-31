// MC harness driving the SHIPPED chooseAction through full games, replicating
// puzzle_simulator.html mechanics exactly (random 1/6 piece; place/burn/useDeluxe).
const mod = require("/tmp/policy.js");
const { chooseAction } = mod;

const ROWS = 4,
  COLS = 6;
const PIECES = {
  1: {
    color: "#36C93C",
    cells: [
      [0, 0],
      [1, 0],
      [1, 1],
    ],
  },
  2: {
    color: "#F2CE1B",
    cells: [
      [0, 0],
      [0, 1],
      [1, 1],
    ],
  },
  3: {
    color: "#2FC6CE",
    cells: [
      [0, 0],
      [0, 1],
      [1, 0],
      [1, 1],
    ],
  },
  4: {
    color: "#2E7BEF",
    cells: [
      [0, 0],
      [1, 0],
      [2, 0],
    ],
  },
  5: {
    color: "#E5402F",
    cells: [
      [0, 0],
      [0, 1],
      [1, 1],
      [1, 2],
    ],
  },
  6: { color: "#F39A21", cells: [[0, 0]] },
};
const DELUXE_CELLS = [
  [0, 0],
  [0, 1],
  [0, 2],
  [1, 0],
  [1, 1],
  [1, 2],
];

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function fits(board, cells, r, c) {
  for (const [dr, dc] of cells) {
    const rr = r + dr,
      cc = c + dc;
    if (rr < 0 || rr >= ROWS || cc < 0 || cc >= COLS || board[rr][cc])
      return false;
  }
  return true;
}
const full = (b) => b.every((row) => row.every(Boolean));

function game(rng, deluxeAvailable) {
  const board = Array.from({ length: ROWS }, () => Array(COLS).fill(null));
  global.counts = { normal: 0, deluxe: 0, placed: 0, burned: 0, total: 0 };
  const counts = global.counts;
  let guard = 0;
  while (!full(board)) {
    if (++guard > 5000) return { boxes: 9999, stalled: true };
    // Probe whether the agent wants a deluxe finisher right now (board state only).
    let wantsDeluxe = false;
    if (deluxeAvailable) {
      const probe = chooseAction(
        board,
        { stueck: "D", cells: DELUXE_CELLS, color: "#C24DE0" },
        true,
      );
      if (probe && probe.type === "useDeluxe") wantsDeluxe = true;
    }
    if (wantsDeluxe) {
      counts.deluxe++;
      counts.total = counts.normal + counts.deluxe;
      let placed = false;
      for (let r = 0; r <= ROWS - 2 && !placed; r++)
        for (let c = 0; c <= COLS - 3 && !placed; c++)
          if (fits(board, DELUXE_CELLS, r, c)) {
            for (const [dr, dc] of DELUXE_CELLS)
              board[r + dr][c + dc] = "#C24DE0";
            counts.placed++;
            placed = true;
          }
      if (!placed) return { boxes: 9999, stalled: true };
      continue;
    }
    counts.normal++;
    counts.total = counts.normal + counts.deluxe;
    const t = 1 + Math.floor(rng() * 6);
    const p = PIECES[t];
    const piece = {
      stueck: t,
      color: p.color,
      cells: p.cells.map((x) => x.slice()),
    };
    const act = chooseAction(board, piece, deluxeAvailable);
    if (act.type === "place") {
      if (!fits(board, piece.cells, act.r, act.c))
        return { boxes: 9999, illegal: true, t, act };
      for (const [dr, dc] of piece.cells)
        board[act.r + dr][act.c + dc] = piece.color;
      counts.placed++;
    } else if (act.type === "burn") {
      counts.burned++;
    } else if (act.type === "useDeluxe") {
      counts.burned++; // shouldn't happen on a normal draw (we probe first)
    }
  }
  return {
    boxes: counts.total,
    normal: counts.normal,
    deluxe: counts.deluxe,
    burned: counts.burned,
  };
}

function run(deluxe, sims, seed) {
  const rng = mulberry32(seed);
  const hist = new Array(2000).fill(0);
  let illegal = 0,
    stalled = 0,
    sum = 0,
    maxb = 0;
  for (let i = 0; i < sims; i++) {
    const g = game(rng, deluxe);
    if (g.illegal) {
      illegal++;
      continue;
    }
    if (g.stalled) {
      stalled++;
      continue;
    }
    hist[g.boxes]++;
    sum += g.boxes;
    if (g.boxes > maxb) maxb = g.boxes;
  }
  const n = sims - illegal - stalled;
  const cum = [];
  let acc = 0;
  for (let i = 0; i < 30; i++) {
    acc += hist[i];
    cum[i] = acc / n;
  }
  let med = 0;
  for (let i = 0; i < 30; i++)
    if (cum[i] >= 0.5) {
      med = i;
      break;
    }
  return {
    E: sum / n,
    P10: cum[10],
    P12: cum[12],
    P9: cum[9],
    P8: cum[8],
    illegal,
    stalled,
    n,
    maxb,
    med,
  };
}

const SIMS = parseInt(process.argv[2] || "100000", 10);
let r = run(false, SIMS, 12345);
console.log(
  "NO DELUXE :",
  `n=${r.n} illegal=${r.illegal} stalled=${r.stalled} maxB=${r.maxb}`,
  `| E=${r.E.toFixed(3)} median=${r.med} P(<=8)=${(r.P8 * 100).toFixed(2)}% P(<=9)=${(r.P9 * 100).toFixed(2)}% P(<=10)=${(r.P10 * 100).toFixed(2)}% P(<=12)=${(r.P12 * 100).toFixed(2)}%`,
);
let r2 = run(true, SIMS, 67890);
console.log(
  "DELUXE    :",
  `n=${r2.n} illegal=${r2.illegal} stalled=${r2.stalled} maxB=${r2.maxb}`,
  `| E=${r2.E.toFixed(3)} median=${r2.med} P(<=8)=${(r2.P8 * 100).toFixed(2)}% P(<=9)=${(r2.P9 * 100).toFixed(2)}% P(<=10)=${(r2.P10 * 100).toFixed(2)}% P(<=12)=${(r2.P12 * 100).toFixed(2)}%`,
);
