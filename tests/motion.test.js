/* Node test suite for static/motion.js (run through pytest or directly). */
'use strict';

const assert = require('node:assert/strict');
const M = require('../static/motion.js');

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';
const FILES = 'abcdefgh';

function fenMap(fen) {
  const map = new Map();
  const [placement] = fen.split(' ');
  placement.split('/').forEach((row, index) => {
    let file = 0;
    for (const token of row) {
      if (token >= '1' && token <= '8') { file += Number(token); continue; }
      const color = token === token.toUpperCase() ? 'w' : 'b';
      map.set(FILES[file] + (8 - index), color + token.toLowerCase());
      file += 1;
    }
  });
  return map;
}

function moveOn(map, from, to, code) {
  const next = new Map(map);
  next.delete(from);
  next.set(to, code || map.get(from));
  return next;
}

let passed = 0;
let total = 0;

function test(name, fn) {
  total += 1;
  try {
    fn();
    passed += 1;
  } catch (error) {
    console.error(`FAIL ${name}: ${error.message}`);
    process.exitCode = 1;
  }
}

test('easeInOutCubic endpoints and midpoint', () => {
  assert.equal(M.easeInOutCubic(0), 0);
  assert.equal(M.easeInOutCubic(0.5), 0.5);
  assert.equal(M.easeInOutCubic(1), 1);
  assert.equal(M.easeInOutCubic(0.25), 4 * 0.25 ** 3);
  assert.ok(M.easeInOutCubic(0.75) > 0.5);
  assert.equal(M.easeInOutCubic(2), 1);
  assert.equal(M.easeInOutCubic(-1), 0);
});

test('animation speed map matches the researched values', () => {
  assert.equal(M.animationMs('default'), 200);
  assert.equal(M.animationMs('none'), 0);
  assert.equal(M.animationMs('fast'), 120);
  assert.equal(M.animationMs('normal'), 250);
  assert.equal(M.animationMs('slow'), 500);
  assert.equal(M.animationMs('nonsense'), M.DEFAULT_ANIMATION_MS);
  assert.equal(M.DEFAULT_ANIMATION_MS, 200);
});

test('drag centre uses half a square and no scale', () => {
  const rect = { left: 10, top: 20, width: 800, height: 800 };
  assert.deepEqual(M.dragCentre(110, 120, rect), { x: 50, y: 50 });
  assert.deepEqual(M.dragCentre(790, 20, rect), { x: 730, y: -50 });
});

test('squareFromPoint respects orientation and bounds', () => {
  const rect = { left: 0, top: 0, width: 800, height: 800 };
  assert.equal(M.squareFromPoint(50, 50, rect, 'white'), 'a8');
  assert.equal(M.squareFromPoint(50, 750, rect, 'white'), 'a1');
  assert.equal(M.squareFromPoint(750, 750, rect, 'white'), 'h1');
  assert.equal(M.squareFromPoint(50, 50, rect, 'black'), 'h1');
  assert.equal(M.squareFromPoint(750, 750, rect, 'black'), 'a8');
  assert.equal(M.squareFromPoint(-1, 50, rect, 'white'), null);
  assert.equal(M.squareFromPoint(900, 50, rect, 'white'), null);
});

test('grid distance is Chebyshev', () => {
  assert.equal(M.gridDistance('e2', 'e4'), 2);
  assert.equal(M.gridDistance('a1', 'c3'), 2);
  assert.equal(M.gridDistance('a1', 'a1'), 0);
});

test('eval bar fill inverts for white at the bottom', () => {
  assert.equal(M.evalFillPercent(70, 'white'), 30);
  assert.equal(M.evalFillPercent(70, 'black'), 70);
  assert.equal(M.evalFillPercent(0, 'white'), 100);
  assert.equal(M.evalFillPercent(100, 'white'), 0);
  assert.equal(M.evalFillPercent(120, 'black'), 100);
  assert.equal(M.winPercent(0), 50);
});

test('arrow geometry and shared-destination shortening', () => {
  const plain = M.arrowGeometry('a1', 'a8');
  assert.equal(plain.x1, 0.5);
  assert.equal(plain.y1, 7.5);
  assert.equal(plain.x2, 0.5);
  assert.ok(Math.abs(plain.y2 - 0.66) < 1e-9);
  const shifted = M.arrowGeometry('a1', 'a8', { shorten: M.ARROW_DEST_SHIFT });
  assert.ok(Math.abs(shifted.y2 - 0.9725) < 1e-9);
  assert.equal(M.arrowGeometry('e4', 'e4'), null);
});

test('fenToMap uses absolute squares (orientation independent)', () => {
  const map = M.fenToMap('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  assert.equal(map.get('a8'), 'br');
  assert.equal(map.get('e1'), 'wk');
  assert.equal(map.get('d1'), 'wq');
  assert.equal(map.get('c7'), 'bp');
  assert.equal(map.get('h2'), 'wp');
  assert.equal(map.size, 32);
});

test('diffPosition reports the played move as a slide', () => {
  const start = fenMap(START);
  const after = moveOn(start, 'e2', 'e4');
  const diff = M.diffPosition([...start].map(([square, code]) => ({ square, code })),
    after, { from: 'e2', to: 'e4' });
  assert.equal(diff.slides.length, 1);
  assert.deepEqual(diff.slides[0], { from: 'e2', to: 'e4', code: 'wp' });
  assert.equal(diff.stays.length, 31);
  assert.equal(diff.added.length, 0);
  assert.equal(diff.removed.length, 0);
});

test('diffPosition pairs a captured piece for the fade', () => {
  const oldMap = new Map([['a1', 'wr'], ['a8', 'br']]);
  const newMap = new Map([['a8', 'wr']]);
  const diff = M.diffPosition([...oldMap].map(([square, code]) => ({ square, code })),
    newMap, { from: 'a1', to: 'a8' });
  assert.deepEqual(diff.slides, [{ from: 'a1', to: 'a8', code: 'wr' }]);
  assert.deepEqual(diff.removed, [{ square: 'a8', code: 'br', captureAt: 'a8' }]);
});

test('diffPosition handles castling as two slides', () => {
  const oldMap = new Map([['e1', 'wk'], ['h1', 'wr']]);
  const newMap = new Map([['g1', 'wk'], ['f1', 'wr']]);
  const diff = M.diffPosition([...oldMap].map(([square, code]) => ({ square, code })),
    newMap, { from: 'e1', to: 'g1' });
  assert.equal(diff.slides.length, 2);
  assert.deepEqual(diff.slides.find((s) => s.code === 'wr'), { from: 'h1', to: 'f1', code: 'wr' });
  assert.equal(diff.removed.length, 0);
});

test('diffPosition slides a promoting pawn from its square', () => {
  const diff = M.diffPosition([{ square: 'a7', code: 'wp' }],
    new Map([['a8', 'wq']]), { from: 'a7', to: 'a8' });
  assert.deepEqual(diff.slides, [{ from: 'a7', to: 'a8', code: 'wq' }]);
  assert.equal(diff.removed.length, 0);
});

test('diffPosition picks the nearest vanished same-role piece', () => {
  const old = [{ square: 'a1', code: 'wr' }, { square: 'h1', code: 'wr' }];
  const diff = M.diffPosition(old, new Map([['b1', 'wr']]), null);
  assert.deepEqual(diff.slides, [{ from: 'a1', to: 'b1', code: 'wr' }]);
});

test('diffPosition adds pieces with no same-role origin', () => {
  const diff = M.diffPosition([], new Map([['d4', 'wq']]), null);
  assert.deepEqual(diff.added, [{ square: 'd4', code: 'wq' }]);
  assert.equal(diff.slides.length, 0);
});

test('premoveUci only emits legal, present, properly promoted moves', () => {
  const legal = { e2: ['e4'], a7: ['a8'] };
  assert.equal(M.premoveUci({ from: 'e2', to: 'e4' }, legal, { e2: 'wp' }), 'e2e4');
  assert.equal(M.premoveUci({ from: 'e2', to: 'e5' }, legal, { e2: 'wp' }), null);
  assert.equal(M.premoveUci({ from: 'd2', to: 'd4' }, legal, { e2: 'wp' }), null);
  assert.equal(M.premoveUci({ from: 'a7', to: 'a8', promo: 'n' }, legal, { a7: 'wp' }), 'a7a8n');
  assert.equal(M.premoveUci({ from: 'a7', to: 'a8' }, legal, { a7: 'wp' }), 'a7a8q');
  assert.equal(M.premoveUci({ from: 'h1', to: 'h2', promo: 'q' },
    { h1: ['h2'] }, { h1: 'wr' }), 'h1h2');
  assert.equal(M.premoveUci(null, legal, { e2: 'wp' }), null);
});

test('soundForMove follows san priority', () => {
  assert.equal(M.soundForMove({ san: 'Qxd8#', flags: { capture: true } }, 'white'), 'checkmate');
  assert.equal(M.soundForMove({ san: 'Qxd8+', flags: { capture: true } }, 'white'), 'move-check');
  assert.equal(M.soundForMove({ san: 'Qxd8', flags: { capture: true } }, 'white'), 'capture');
  assert.equal(M.soundForMove({ san: 'e8=Q+', flags: { promotion: true } }, 'white'), 'promote');
  assert.equal(M.soundForMove({ san: 'O-O', flags: { castle: true } }, 'white'), 'castle');
  assert.equal(M.soundForMove({ san: 'e4', color: 'white' }, 'white'), 'move-self');
  assert.equal(M.soundForMove({ san: 'e5', color: 'black' }, 'white'), 'move-opponent');
  assert.equal(M.soundFallback('checkmate'), 'move-check');
  assert.equal(M.soundFallback('victory'), 'game-end');
  assert.equal(M.soundFallback('defeat'), 'game-end');
  assert.equal(M.soundFallback('capture'), 'capture');
});

console.log(`motion: ${passed}/${total} ok`);
if (process.exitCode) {
  console.error('motion tests failed');
  process.exit(1);
}
