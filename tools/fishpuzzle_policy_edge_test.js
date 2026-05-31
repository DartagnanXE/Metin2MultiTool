const { chooseAction, _internal } = require("/tmp/policy.js");
const ROWS = 4,
  COLS = 6;
const DC = [
  [0, 0],
  [0, 1],
  [0, 2],
  [1, 0],
  [1, 1],
  [1, 2],
];
function fits(b, c, r, cc) {
  for (const [dr, dc] of c) {
    const rr = r + dr,
      k = cc + dc;
    if (rr < 0 || rr >= ROWS || k < 0 || k >= COLS || b[rr][k]) return false;
  }
  return true;
}
let pass = 0,
  fail = 0;
function ok(cond, msg) {
  if (cond) {
    pass++;
  } else {
    fail++;
    console.log("FAIL:", msg);
  }
}

// 1) Empty board, single piece -> must place (never burn early)
global.counts = { total: 0 };
let b = Array.from({ length: 4 }, () => Array(6).fill(null));
let a = chooseAction(
  b,
  { stueck: 6, color: "#F39A21", cells: [[0, 0]] },
  false,
);
ok(a.type === "place", "empty board single should place");

// 2) Any returned place is always legal, across many random boards/pieces
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
let illegal = 0,
  tested = 0;
for (let it = 0; it < 20000; it++) {
  const board = Array.from({ length: 4 }, () => Array(6).fill(null));
  // random partial fill
  const k = Math.floor(Math.random() * 20);
  for (let f = 0; f < k; f++) {
    const r = Math.floor(Math.random() * 4),
      c = Math.floor(Math.random() * 6);
    board[r][c] = "#fff";
  }
  if (board.every((row) => row.every(Boolean))) continue;
  global.counts = { total: Math.floor(Math.random() * 12) };
  const t = 1 + Math.floor(Math.random() * 6);
  const dl = Math.random() < 0.5;
  const act = chooseAction(
    board,
    { stueck: t, color: "#abc", cells: PIECES[t].map((x) => x.slice()) },
    dl,
  );
  tested++;
  if (act.type === "place") {
    if (!fits(board, PIECES[t], act.r, act.c)) illegal++;
  } else if (act.type === "useDeluxe") {
    /* only valid if exactly a 2x3 gap & a fit exists */
    let okfit = false;
    for (let r = 0; r <= 2; r++)
      for (let c = 0; c <= 3; c++) if (fits(board, DC, r, c)) okfit = true;
    if (!okfit) illegal++;
  }
}
ok(illegal === 0, `illegal actions across ${tested} random boards: ${illegal}`);

// 3) Board full except a 2x3 hole, deluxe available, used+1<=10 -> useDeluxe
b = Array.from({ length: 4 }, () => Array(6).fill("#fff"));
for (const [dr, dc] of DC) b[0 + dr][0 + dc] = null; // top-left 2x3 empty
global.counts = { total: 5 };
a = chooseAction(b, { stueck: "D", cells: DC, color: "#C24DE0" }, true);
ok(a.type === "useDeluxe", "2x3 gap + used=5 + deluxe -> useDeluxe");

// 4) Same hole but used+1>10 -> NOT useDeluxe (must not fire)
global.counts = { total: 10 };
a = chooseAction(b, { stueck: "D", cells: DC, color: "#C24DE0" }, true);
ok(a.type !== "useDeluxe", "2x3 gap but used=10 -> must NOT fire deluxe");

// 5) deluxe gap but deluxeAvailable=false -> never useDeluxe
global.counts = { total: 5 };
a = chooseAction(b, { stueck: "D", cells: DC, color: "#C24DE0" }, false);
ok(a.type !== "useDeluxe", "deluxe unavailable -> never useDeluxe");

// 6) Non-2x3 single-cell gap, deluxe avail -> must NOT fire (gap != 2x3)
b = Array.from({ length: 4 }, () => Array(6).fill("#fff"));
b[3][5] = null;
global.counts = { total: 5 };
a = chooseAction(b, { stueck: 6, cells: [[0, 0]], color: "#F39A21" }, true);
ok(
  a.type === "place" && a.r === 3 && a.c === 5,
  "single fills the last lone cell",
);

console.log(`\nEdge-case tests: ${pass} passed, ${fail} failed.`);
process.exit(fail ? 1 : 0);
