/* Pure motion / geometry / sound logic for the board.
 *
 * Kept free of DOM access so it can be exercised by node (tests/motion.test.js)
 * and reused by app.js.  Numbers come from the researched chess.com/lichess
 * behaviour: rAF tweens with easeInOutCubic, 3 px drag threshold, arrow
 * geometry on an 8x8 viewBox, san-driven sound selection.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ChessMotion = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const FILES = 'abcdefgh';
  const PROMO_LETTERS = 'qrbn';

  /** Animation speed preferences (ms). 200 ms is the historical default. */
  const ANIMATION_MS = Object.freeze({
    default: 200, none: 0, fast: 120, normal: 250, slow: 500
  });
  const DEFAULT_ANIMATION_MS = 200;

  /** Arrow layer geometry on the 0..8 viewBox. */
  const ARROW_HEAD_CLEARANCE = 0.16; // room for the marker tip at the target centre
  const ARROW_DEST_SHIFT = 20 / 64; // second arrow sharing a destination is shortened

  /** Sounds the vendored themes do not ship fall back to a sibling event. */
  const SOUND_FALLBACK = Object.freeze({
    checkmate: 'move-check',
    victory: 'game-end',
    defeat: 'game-end'
  });

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function easeInOutCubic(t) {
    const x = clamp(Number(t) || 0, 0, 1);
    return x < 0.5 ? 4 * x * x * x : (x - 1) * (2 * x - 2) * (2 * x - 2) + 1;
  }

  function animationMs(speed) {
    return Object.prototype.hasOwnProperty.call(ANIMATION_MS, String(speed))
      ? ANIMATION_MS[String(speed)]
      : DEFAULT_ANIMATION_MS;
  }

  function winPercent(cp) {
    const value = clamp(Number(cp) || 0, -2000, 2000);
    return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * value)) - 1);
  }

  /**
   * Gradient stop used by the eval bar.  The CSS gradient paints dark from the
   * top down to `--eval-percent`, so white-at-bottom needs 100 - whitePct.
   */
  function evalFillPercent(whitePct, orientation) {
    const p = clamp(Number(whitePct) || 0, 0, 100);
    return orientation === 'black' ? p : 100 - p;
  }

  function fileOf(square) {
    return FILES.indexOf(String(square || '')[0]);
  }

  function gridOf(square) {
    const text = String(square || '');
    return { fx: FILES.indexOf(text[0]), ry: 8 - Number(text[1]) };
  }

  function squareAtGrid(fx, ry, orientation) {
    if (!(fx >= 0 && fx < 8 && ry >= 0 && ry < 8)) return null;
    const file = orientation === 'white' ? fx : 7 - fx;
    const rank = orientation === 'white' ? 7 - ry : ry;
    return FILES[file] + String(rank + 1);
  }

  /**
   * FEN placement -> Map(absolute square -> code).  Absolute squares never
   * depend on board orientation; flipping belongs to the display layer only.
   */
  function fenToMap(fen) {
    const map = new Map();
    const rows = String(fen || '').split(' ')[0].split('/');
    rows.forEach((row, ry) => {
      let fx = 0;
      for (const ch of row) {
        if (ch >= '1' && ch <= '8') { fx += Number(ch); continue; }
        map.set(squareAtGrid(fx, ry, 'white'),
          (ch === ch.toUpperCase() ? 'w' : 'b') + ch.toLowerCase());
        fx += 1;
      }
    });
    return map;
  }

  /** Square under a pointer, or null outside the board rect. */
  function squareFromPoint(clientX, clientY, rect, orientation) {
    if (!rect || !rect.width || !rect.height) return null;
    const fx = Math.floor(((clientX - rect.left) / rect.width) * 8);
    const ry = Math.floor(((clientY - rect.top) / rect.height) * 8);
    return squareAtGrid(fx, ry, orientation || 'white');
  }

  /** Piece translate origin so the cursor sits in the middle of the piece. */
  function dragCentre(clientX, clientY, rect) {
    return {
      x: clientX - rect.left - rect.width / 16,
      y: clientY - rect.top - rect.height / 16
    };
  }

  function gridDistance(a, b) {
    const ga = gridOf(a);
    const gb = gridOf(b);
    return Math.max(Math.abs(ga.fx - gb.fx), Math.abs(ga.ry - gb.ry));
  }

  function entriesOf(map) {
    if (!map) return [];
    if (typeof map.entries === 'function') return [...map.entries()];
    return Object.entries(map);
  }

  function slideCompatible(oldCode, newCode) {
    if (!oldCode || !newCode) return false;
    if (oldCode === newCode) return true;
    // pawn -> queen/rook/bishop/knight on the last rank
    return oldCode[0] === newCode[0] && oldCode[1] === 'p' && newCode[1] !== 'p';
  }

  /**
   * Diff two positions into the minimal set of slides/stays/added/removed.
   *
   * Order of preference:
   *  1. the move actually played (so castling rooks and promotions look right),
   *  2. pieces that did not move (same square, same code),
   *  3. the nearest vanished same-role piece (this is what makes a capture look
   *     like the capturing piece sliding from its real origin),
   *  4. anything else is added or removed.
   *
   * @param {Array<{square:string, code:string}>} oldPieces
   * @param {Map|Object} newMap square -> code
   * @param {{from:string, to:string}|null} lastMove
   */
  function diffPosition(oldPieces, newMap, lastMove) {
    const olds = (oldPieces || []).map((piece) => ({
      square: String(piece.square), code: String(piece.code), used: false
    }));
    const news = entriesOf(newMap)
      .map(([square, code]) => ({ square: String(square), code: String(code) }))
      .sort((a, b) => (a.square < b.square ? -1 : a.square > b.square ? 1 : 0));
    const matched = new Set();
    const slides = [];
    const stays = [];
    const added = [];

    const newsCode = (square) => {
      const hit = news.find((entry) => entry.square === square);
      return hit ? hit.code : null;
    };
    const freeOld = (square) => olds.find((entry) => !entry.used && entry.square === square);
    const take = (oldEntry, square, code) => {
      oldEntry.used = true;
      matched.add(square);
      return { from: oldEntry.square, to: square, code };
    };

    if (lastMove && lastMove.from && lastMove.to) {
      const source = freeOld(String(lastMove.from));
      const code = newsCode(String(lastMove.to));
      if (source && code && slideCompatible(source.code, code)) {
        slides.push(take(source, String(lastMove.to), code));
      }
    }

    for (const entry of news) {
      if (matched.has(entry.square)) continue;
      const source = freeOld(entry.square);
      if (source && source.code === entry.code) {
        take(source, entry.square, entry.code);
        stays.push({ square: entry.square, code: entry.code });
      }
    }

    for (const entry of news) {
      if (matched.has(entry.square)) continue;
      let best = null;
      let bestDistance = Infinity;
      for (const candidate of olds) {
        if (candidate.used) continue;
        if (candidate.code[1] !== entry.code[1]) continue;
        const distance = gridDistance(candidate.square, entry.square);
        if (distance < bestDistance
          || (distance === bestDistance && best && candidate.square < best.square)) {
          best = candidate;
          bestDistance = distance;
        }
      }
      if (best) {
        slides.push(take(best, entry.square, entry.code));
      } else {
        matched.add(entry.square);
        added.push({ square: entry.square, code: entry.code });
      }
    }

    const removed = olds.filter((entry) => !entry.used).map((entry) => ({
      square: entry.square,
      code: entry.code,
      captureAt: slides.some((slide) => slide.to === entry.square) ? entry.square : null
    }));

    return { slides, stays, added, removed };
  }

  /**
   * Arrow line endpoints in viewBox units (the SVG uses viewBox 0 0 8 8).
   * `shorten` is in squares and used when two arrows share a destination.
   */
  function arrowGeometry(from, to, options = {}) {
    const a = typeof from === 'string' ? gridOf(from) : from;
    const b = typeof to === 'string' ? gridOf(to) : to;
    const x1 = a.fx + 0.5;
    const y1 = a.ry + 0.5;
    const x2 = b.fx + 0.5;
    const y2 = b.ry + 0.5;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy);
    if (length < 0.01) return null;
    const ux = dx / length;
    const uy = dy / length;
    const clearance = options.clearance === undefined
      ? ARROW_HEAD_CLEARANCE : Number(options.clearance) || 0;
    const shorten = Number(options.shorten) || 0;
    const end = length - clearance - shorten;
    if (end <= 0.05) return null;
    return {
      x1,
      y1,
      x2: x1 + ux * end,
      y2: y1 + uy * end,
      ux,
      uy,
      length,
      angle: Math.atan2(dy, dx) * 180 / Math.PI
    };
  }

  /**
   * Sound event for a move, derived from san first (x = capture, # = mate,
   * + = check) and the server flags as a safety net.
   */
  function soundForMove(move, myColor) {
    const item = move || {};
    const san = String(item.san || '');
    const flags = item.flags || {};
    if (flags.promotion || /=[QRBN]/.test(san)) return 'promote';
    if (flags.castle || san === 'O-O' || san === 'O-O-O') return 'castle';
    if (san.includes('#')) return 'checkmate';
    if (san.includes('+')) return 'move-check';
    if (flags.capture || san.includes('x')) return 'capture';
    return item.color && item.color === myColor ? 'move-self' : 'move-opponent';
  }

  function soundFallback(event) {
    return SOUND_FALLBACK[String(event)] || String(event);
  }

  /**
   * UCI to send for a queued premove, or null when it must never leave the
   * browser: the piece has to still be there, the target has to be legal in
   * the current state, and a promotion letter is only allowed for a pawn that
   * reaches the last rank.
   */
  function premoveUci(premove, legal, boardCodes) {
    if (!premove || !premove.from || !premove.to) return null;
    const from = String(premove.from);
    const to = String(premove.to);
    if (fileOf(from) < 0 || fileOf(to) < 0) return null;
    const code = boardCodes && typeof boardCodes.get === 'function'
      ? boardCodes.get(from) : (boardCodes || {})[from];
    if (!code) return null;
    const targets = legal && typeof legal.get === 'function'
      ? legal.get(from) : (legal || {})[from];
    if (!Array.isArray(targets) || !targets.includes(to)) return null;
    if (code[1] === 'p' && (to[1] === '1' || to[1] === '8')) {
      const promo = String(premove.promo || '');
      const letter = promo.length === 1 && PROMO_LETTERS.includes(promo) ? promo : 'q';
      return from + to + letter;
    }
    return from + to;
  }

  return {
    FILES,
    ANIMATION_MS,
    DEFAULT_ANIMATION_MS,
    ARROW_HEAD_CLEARANCE,
    ARROW_DEST_SHIFT,
    SOUND_FALLBACK,
    clamp,
    easeInOutCubic,
    animationMs,
    winPercent,
    evalFillPercent,
    gridOf,
    squareAtGrid,
    fenToMap,
    squareFromPoint,
    dragCentre,
    gridDistance,
    diffPosition,
    arrowGeometry,
    soundForMove,
    soundFallback,
    premoveUci
  };
}));
