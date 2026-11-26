(() => {
'use strict';

const $ = (id) => document.getElementById(id);
const FILES = 'abcdefgh';
const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const CATEGORIES = ['brilliant', 'great', 'best', 'good', 'book',
  'inaccuracy', 'mistake', 'blunder', 'miss'];
const LABEL = {
  brilliant: 'Brilliant', great: 'Great', best: 'Best', good: 'Good',
  book: 'Book', inaccuracy: 'Inaccuracy', mistake: 'Mistake',
  blunder: 'Blunder', miss: 'Miss'
};
const MODE_LABEL = { training: 'Trénink', sharp: 'Ostrá', analysis: 'Analýza' };
const PRESETS = [
  [180, 0], [180, 2], [300, 0], [300, 5],
  [600, 0], [600, 5], [900, 10], [1800, 0]
];

const S = {
  gid: null,
  st: null,
  boardMap: new Map(),
  pieceEls: new Map(),
  orientation: 'white',
  selected: null,
  legal: {},
  lastMove: null,
  drag: null,
  premove: null,
  pendingPromo: null,
  busy: false,
  sq: 0,
  pollTimer: null,
  polling: false,
  clocks: { white: 600, black: 600 },
  lastStateAt: 0,
  ten: { white: false, black: false },
  soundOn: true,
  soundTheme: 'default',
  animSpeed: 'default',
  boardTheme: 'brown',
  pieceTheme: 'classic',
  evalVisible: true,
  playedUci: new Set(),
  moveSig: '',
  review: null,
  reviewPly: 0,
  reviewActive: false,
  reviewBusy: false,
  setup: {
    color: 'white', base: 300, inc: 0, level: 8,
    mode: 'training', player: 'me'
  }
};

const MOTION = window.ChessMotion;
const BOARD_TINT = {
  brown: '#b58863', blue: '#8ca2ad', bubblegum: '#e4a0b7',
  burled_wood: '#9c6b3f', dark_wood: '#5b3a1e', checkers: '#4f6b3a',
  marble: '#c9c2b6', walnut: '#7b5a3a', '8_bit': '#b0b0b0'
};

/* ── small helpers ─────────────────────────────────────────────────────── */

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function winPercent(cp) {
  return MOTION.winPercent(cp);
}

function fmtEval(cp) {
  const value = Number(cp) || 0;
  if (Math.abs(value) >= 9000) return value > 0 ? 'M' : '−M';
  return `${value >= 0 ? '+' : ''}${(value / 100).toFixed(1)}`;
}

function fmtClock(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value >= 10) {
    const total = Math.floor(value);
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
  }
  return value.toFixed(1);
}

function formatTc(base, inc) {
  const minutes = base % 60 === 0 ? String(base / 60) : (base / 60).toFixed(1);
  return `${minutes}|${inc}`;
}

function humanize(name) {
  return name.replace(/_/g, ' ').replace(/\b3d\b/i, '3D')
    .replace(/\b8 bit\b/i, '8-bit')
    .replace(/^\w/, (c) => c.toUpperCase());
}

function fenToMap(fen) {
  return MOTION.fenToMap(fen);
}

function squareToGrid(square) {
  const file = FILES.indexOf(square[0]);
  const rank = Number(square[1]) - 1;
  return {
    fx: S.orientation === 'white' ? file : 7 - file,
    ry: S.orientation === 'white' ? 7 - rank : rank
  };
}

function myPieceColor() {
  return S.st && S.st.my_color === 'black' ? 'b' : 'w';
}

function pieceSrc(code) {
  return `vendor/chesscom/pieces/${S.pieceTheme}/${code}.png`;
}

function currentEval() {
  if (S.reviewActive && S.review && S.review.evals) {
    return S.review.evals[clamp(S.reviewPly, 0, S.review.evals.length - 1)] || 0;
  }
  return S.st ? S.st.eval_cp : 0;
}

function reviewFen() {
  if (!S.review) return START_FEN;
  if (S.reviewPly <= 0) return S.review.start_fen;
  const ply = S.review.plies[S.reviewPly - 1];
  return ply ? ply.fen_after : S.review.start_fen;
}

/* ── API ───────────────────────────────────────────────────────────────── */

async function api(path, options = {}) {
  const method = options.method || 'GET';
  const body = options.body === undefined ? null : options.body;
  const response = await fetch(path, {
    method,
    cache: 'no-store',
    headers: body === null ? undefined : { 'Content-Type': 'application/json' },
    body: body === null ? undefined : JSON.stringify(body)
  });
  const type = response.headers.get('content-type') || '';
  let data;
  if (type.includes('json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }
  if (!response.ok) {
    const error = new Error((data && data.error) || response.statusText);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function showToast(text, ms = 4000) {
  const toast = $('toast');
  toast.textContent = text;
  toast.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add('hidden'), ms);
}

/* ── board rendering ───────────────────────────────────────────────────── */

function buildSquares() {
  const host = $('squares');
  const fragment = document.createDocumentFragment();
  for (let ry = 0; ry < 8; ry += 1) {
    for (let fx = 0; fx < 8; fx += 1) {
      // Cells always carry the ABSOLUTE square; orientation only moves them
      // inside the grid, so highlights and legal moves stay readable.
      const square = `${FILES[fx]}${8 - ry}`;
      const cell = document.createElement('div');
      cell.className = 'sq';
      cell.dataset.square = square;
      const grid = squareToGrid(square);
      cell.style.order = String(grid.ry * 8 + grid.fx);
      fragment.appendChild(cell);
    }
  }
  host.replaceChildren(fragment);
}

/* ── transform tweens (requestAnimationFrame, never left/top) ─────────── */

const TWEENS = new Map();
let rafId = null;

function animMs() {
  return MOTION.animationMs(S.animSpeed);
}

/** Re-read the board box; pieces are placed in pixels so 12.5% stays exact. */
function measure() {
  const rect = $('boardWrap').getBoundingClientRect();
  if (rect.width) S.sq = rect.width / 8;
  return rect;
}

function gridPx(square) {
  const { fx, ry } = squareToGrid(square);
  return { x: fx * S.sq, y: ry * S.sq };
}

function setXY(el, x, y) {
  el._x = x;
  el._y = y;
  el.style.transform = `translate(${x}px, ${y}px)`;
}

function placeEl(el, square) {
  const { x, y } = gridPx(square);
  setXY(el, x, y);
}

function tick(now) {
  rafId = null;
  for (const [el, tw] of TWEENS) {
    const t = tw.dur > 0 ? Math.min(1, (now - tw.t0) / tw.dur) : 1;
    const eased = MOTION.easeInOutCubic(t);
    setXY(el, tw.x0 + (tw.x1 - tw.x0) * eased,
      tw.y0 + (tw.y1 - tw.y0) * eased);
    if (t >= 1) {
      TWEENS.delete(el);
      el.classList.remove('sliding');
      if (tw.done) tw.done();
    }
  }
  if (TWEENS.size && rafId === null) rafId = requestAnimationFrame(tick);
}

function tweenTo(el, x, y, dur, done) {
  if (dur <= 0) {
    TWEENS.delete(el);
    setXY(el, x, y);
    el.classList.remove('sliding');
    if (done) done();
    return;
  }
  const x0 = typeof el._x === 'number' ? el._x : x;
  const y0 = typeof el._y === 'number' ? el._y : y;
  el.classList.add('sliding');
  TWEENS.set(el, { x0, y0, x1: x, y1: y, t0: performance.now(), dur, done });
  if (rafId === null) rafId = requestAnimationFrame(tick);
}

function cancelTweens() {
  if (rafId !== null) cancelAnimationFrame(rafId);
  rafId = null;
  const pending = [...TWEENS.values()];
  for (const el of TWEENS.keys()) el.classList.remove('sliding');
  TWEENS.clear();
  // Let fade batches finish so interrupted captures do not leak elements.
  for (const tw of pending) if (tw.done) tw.done();
}

function updateEl(el, square, code) {
  el.dataset.square = square;
  if (el.dataset.code !== code) {
    el.dataset.code = code;
    el.style.backgroundImage = `url("${pieceSrc(code)}")`;
  }
}

function createPiece(square, code) {
  const el = document.createElement('div');
  el.className = 'piece';
  el.dataset.square = square;
  el.dataset.code = code;
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', code);
  el.style.backgroundImage = `url("${pieceSrc(code)}")`;
  placeEl(el, square);
  $('pieces').appendChild(el);
  return el;
}

function addPiece(square, code) {
  S.pieceEls.set(square, { el: createPiece(square, code), code });
}

function cancelDrag() {
  if (S.drag && S.drag.cancel) S.drag.cancel();
  S.drag = null;
}

function layoutPieces() {
  cancelDrag();
  cancelTweens();
  measure();
  for (const [square, entry] of S.pieceEls) {
    updateEl(entry.el, square, entry.code);
    placeEl(entry.el, square);
  }
}

function renderPosition(fen, options = {}) {
  const newMap = fenToMap(fen);
  const host = $('pieces');
  cancelDrag();
  measure();
  const dur = options.instant ? 0 : animMs();

  if (dur === 0) {
    cancelTweens();
    host.replaceChildren();
    S.pieceEls.clear();
    for (const [square, code] of newMap) addPiece(square, code);
    return;
  }

  const oldEls = new Map(S.pieceEls);
  const oldList = [...oldEls].map(([square, entry]) => ({ square, code: entry.code }));
  const diff = MOTION.diffPosition(oldList, newMap, options.lastMove || null);
  S.pieceEls.clear();

  // Captured pieces stay visible (z-index 1, opacity .5) until the slide ends.
  const batch = { left: 0, els: [] };
  const finish = () => {
    if (batch.left > 0) return;
    for (const el of batch.els) el.remove();
    batch.els.length = 0;
  };

  for (const stay of diff.stays) {
    const entry = oldEls.get(stay.square);
    if (!entry) { addPiece(stay.square, stay.code); continue; }
    updateEl(entry.el, stay.square, stay.code);
    S.pieceEls.set(stay.square, { el: entry.el, code: stay.code });
  }

  for (const slide of diff.slides) {
    const entry = oldEls.get(slide.from);
    if (!entry) { addPiece(slide.to, slide.code); continue; }
    updateEl(entry.el, slide.to, slide.code);
    S.pieceEls.set(slide.to, { el: entry.el, code: slide.code });
    const goal = gridPx(slide.to);
    batch.left += 1;
    tweenTo(entry.el, goal.x, goal.y, dur, () => {
      batch.left -= 1;
      finish();
    });
  }

  for (const added of diff.added) addPiece(added.square, added.code);

  for (const gone of diff.removed) {
    const entry = oldEls.get(gone.square);
    if (!entry) continue;
    if (gone.captureAt) {
      entry.el.classList.add('fading');
      batch.els.push(entry.el);
    } else {
      entry.el.remove();
    }
  }
  finish();
}

function renderHighlights() {
  const last = S.lastMove;
  const selected = S.selected;
  const targets = selected ? new Set(S.legal[selected] || []) : new Set();
  const selectedPiece = selected ? S.boardMap.get(selected) : null;
  const premove = S.premove;
  const premovePiece = premove ? S.boardMap.get(premove.from) : null;
  const premoveCapture = premove
    ? Boolean(S.boardMap.get(premove.to))
      || (Boolean(premovePiece) && premovePiece[1] === 'p'
        && premove.from[0] !== premove.to[0])
    : false;

  for (const cell of $('squares').children) {
    const square = cell.dataset.square;
    const occupant = S.boardMap.get(square);
    const isTarget = targets.has(square);
    let dot = false;
    let cap = false;
    if (isTarget) {
      const enemy = occupant && occupant[0] !== myPieceColor();
      dot = !enemy;
      cap = Boolean(enemy);
      if (!occupant && selectedPiece && selectedPiece[1] === 'p'
        && square[0] !== selected[0]) {
        cap = true; // en passant ring (a pawn only moves diagonally to an empty square)
      }
    }
    const isPremove = Boolean(premove && square === premove.to);
    cell.classList.toggle('last', Boolean(last && (square === last.from || square === last.to)));
    cell.classList.toggle('sel', square === selected);
    cell.classList.toggle('dot', dot);
    cell.classList.toggle('cap', cap);
    cell.classList.toggle('check', !S.reviewActive && S.st
      && square === S.st.check_square);
    cell.classList.toggle('pm-from', Boolean(premove && square === premove.from));
    cell.classList.toggle('pm-to', isPremove);
    cell.classList.toggle('pdot', isPremove && !premoveCapture);
    cell.classList.toggle('pcap', isPremove && premoveCapture);
  }
}

/* ── state application ─────────────────────────────────────────────────── */

function applyState(st) {
  if (!st || st.error) return;
  if (st.engine_error && (!S.st || S.st.engine_error !== st.engine_error)) {
    showToast(`Engine: ${st.engine_error}`);
  }
  const prev = S.st;
  const sameGame = prev && prev.gid === st.gid;
  const fenChanged = !sameGame || !prev || prev.fen !== st.fen;
  const forceRender = Boolean(S.forceRender);
  S.forceRender = false;
  S.st = st;
  S.gid = st.gid || S.gid;
  S.clocks = { ...st.clocks };
  S.legal = st.legal || {};
  S.lastStateAt = performance.now();

  if (!S.reviewActive) {
    const takeback = sameGame && prev.moves.length > st.moves.length;
    S.boardMap = fenToMap(st.fen);
    if (fenChanged || forceRender) {
      renderPosition(st.fen, {
        instant: !sameGame || takeback || forceRender,
        lastMove: st.last_move
      });
      S.lastMove = st.last_move || null;
      S.selected = null;
    }
    renderHighlights();
  }

  if (!sameGame) {
    S.ten = { white: false, black: false };
  }

  updateSideLabels(st);
  renderEvalBar();
  renderMoves(st.moves || []);
  renderCoach(st);
  updateStatus(st);
  updateButtons(st);
  playMoveSounds(sameGame ? prev : null, st);

  if (st.over) {
    S.premove = null;
    if (!sameGame || !prev.over) {
      // Victory/defeat lands 600 ms after the final move, never mid-slide.
      setTimeout(() => playResultSound(st), 600);
    }
  } else {
    tryPremove(st);
  }
}

function renderMoves(moves) {
  const signature = `${S.st ? S.st.mode : ''}|${S.st && S.st.over}|${moves.length}|`
    + moves.map((m) => `${m.ply}${m.uci}${m.verdict || ''}`).join(',');
  if (signature === S.moveSig) {
    if (S.reviewActive) markActiveMove(S.reviewPly);
    return;
  }
  S.moveSig = signature;
  $('moveCount').textContent = moves.length ? `${moves.length} půltahů` : '';
  const host = $('moveList');
  host.replaceChildren();
  if (!moves.length) {
    const empty = document.createElement('div');
    empty.className = 'muted small';
    empty.textContent = 'Zatím žádné tahy.';
    host.appendChild(empty);
    return;
  }

  for (let i = 0; i < moves.length; i += 2) {
    const row = document.createElement('div');
    row.className = 'move-row';
    const number = document.createElement('div');
    number.className = 'move-no';
    number.textContent = `${Math.floor(i / 2) + 1}.`;
    row.appendChild(number);
    for (const move of moves.slice(i, i + 2)) {
      const span = document.createElement('span');
      span.className = 'move-san';
      span.dataset.ply = String(move.ply);
      if (S.reviewActive) span.classList.add('clickable');
      const san = document.createElement('span');
      san.textContent = move.san;
      span.appendChild(san);
      if (move.verdict) {
        const badge = document.createElement('span');
        badge.className = `badge v-${move.verdict}`;
        badge.textContent = LABEL[move.verdict] || move.verdict;
        badge.title = move.loss !== undefined && move.loss !== null
          ? `ztráta ${move.loss} cp` : '';
        span.appendChild(badge);
      }
      row.appendChild(span);
    }
    host.appendChild(row);
  }
  if (S.reviewActive) markActiveMove(S.reviewPly);
  else host.scrollTop = host.scrollHeight;
}

function renderCoach(st) {
  $('modeTag').textContent = MODE_LABEL[st.mode] || st.mode;
  const host = $('coachBody');
  host.replaceChildren();
  if (st.engine_error) {
    const err = document.createElement('div');
    err.className = 'coach-line';
    err.textContent = `Engine hlásí problém: ${st.engine_error}`;
    host.appendChild(err);
    return;
  }
  if (st.mode === 'sharp' && !st.over) {
    const line = document.createElement('div');
    line.className = 'coach-empty';
    line.textContent = 'Ostrá partie — bez rad do konce.';
    const sub = document.createElement('div');
    sub.className = 'coach-line';
    sub.textContent = 'Vše uvidíš v review po partii.';
    host.append(line, sub);
    return;
  }
  const note = st.note;
  if (note) {
    const badge = document.createElement('span');
    badge.className = `coach-badge v-${note.verdict}`;
    badge.textContent = LABEL[note.verdict] || note.verdict;
    host.appendChild(badge);
    const text = document.createElement('span');
    text.textContent = note.text;
    host.appendChild(text);
    if (note.loss) {
      const loss = document.createElement('div');
      loss.className = 'coach-line muted';
      loss.textContent = note.best && note.best !== note.san
        ? `Ztráta ${note.loss} cp · nejlepší ${note.best}`
        : `Ztráta ${note.loss} cp`;
      host.appendChild(loss);
    }
    return;
  }
  const line = document.createElement('div');
  line.className = 'coach-empty';
  if (st.over) {
    line.textContent = 'Partie skončila. Spusť review.';
  } else if (st.thinking) {
    line.textContent = 'Stockfish přemýšlí…';
  } else if (st.turn === st.my_color) {
    line.textContent = 'Jsi na tahu. Vyber figuru a cíl.';
  } else {
    line.textContent = 'Na tahu je soupeř.';
  }
  host.appendChild(line);
}

function updateStatus(st) {
  const line = $('statusLine');
  const thinking = $('thinking');
  thinking.classList.toggle('hidden', !st.thinking || st.over || S.reviewActive);
  if (S.reviewActive) {
    line.textContent = `Review · půltah ${S.reviewPly}`;
    return;
  }
  if (st.over) {
    const result = st.result === '1-0' ? '1–0 (bílý)'
      : st.result === '0-1' ? '0–1 (černý)'
        : st.result === '1/2-1/2' ? '½–½' : (st.result || 'konec');
    let reason = '';
    if (st.flagged) reason = ` · čas vypršel (${st.flagged === 'white' ? 'bílý' : 'černý'})`;
    else if (st.resigned) reason = ' · vzdání';
    else if (st.result === '1/2-1/2') reason = ' · remíza';
    else reason = ' · mat';
    line.textContent = `Konec: ${result}${reason}`;
    return;
  }
  if (st.thinking) {
    line.textContent = 'Stockfish přemýšlí…';
  } else if (st.turn === st.my_color) {
    line.textContent = 'Jsi na tahu.';
  } else {
    line.textContent = 'Na tahu je soupeř.';
  }
}

function updateButtons(st) {
  if (!st) return;
  const hasPlayerMove = (st.moves || []).some((m) => m.color === st.my_color);
  $('takebackBtn').disabled = Boolean(st.thinking || st.over || !hasPlayerMove);
  $('resignBtn').disabled = Boolean(st.over);
  $('reviewBtn').disabled = !st.over || st.review_status === 'running'
    || Boolean(S.reviewBusy);
  $('reviewBtn').textContent = S.reviewActive ? 'Zavřít review'
    : (S.review ? 'Zobrazit review' : 'Analyzovat partii');
}

function updateSideLabels(st) {
  if (!st) return;
  const topColor = S.orientation === 'white' ? 'black' : 'white';
  const bottomColor = S.orientation;
  const name = (color) => (color === st.my_color
    ? st.player
    : `Stockfish (lvl ${st.level})`);
  $('nameTop').textContent = name(topColor);
  $('nameBottom').textContent = name(bottomColor);
  $('clockTop').classList.toggle('active', !st.over && st.turn === topColor);
  $('clockBottom').classList.toggle('active', !st.over && st.turn === bottomColor);
}

/* ── clocks / eval ─────────────────────────────────────────────────────── */

function tickClocks() {
  const st = S.st;
  if (!st) return;
  const elapsed = (performance.now() - S.lastStateAt) / 1000;
  const topColor = S.orientation === 'white' ? 'black' : 'white';
  const bottomColor = S.orientation;
  const running = !st.over && !S.reviewActive;
  const values = {};
  for (const side of ['white', 'black']) {
    let value = S.clocks[side] ?? 0;
    if (running && st.turn === side) value = Math.max(0, value - elapsed);
    values[side] = value;
    if (!st.over && !S.reviewActive && value > 0 && value < 10 && !S.ten[side]) {
      S.ten[side] = true;
      playSound('tenseconds');
    }
  }
  $('timeTop').textContent = fmtClock(values[topColor]);
  $('timeBottom').textContent = fmtClock(values[bottomColor]);
  for (const [id, color] of [['clockTop', topColor], ['clockBottom', bottomColor]]) {
    const el = $(id);
    el.classList.toggle('active', !st.over && st.turn === color);
    el.classList.toggle('low', values[color] < 20);
  }
}

function renderEvalBar() {
  const liveMode = S.st ? S.st.mode : 'training';
  const show = S.reviewActive
    || (S.st && liveMode === 'analysis')
    || (S.st && liveMode !== 'sharp' && S.evalVisible);
  $('evalWrap').classList.toggle('hidden', !show);
  if (!show) return;
  const cp = currentEval();
  const percent = clamp(winPercent(cp), 3, 97);
  $('evalBar').style.setProperty('--eval-percent',
    `${MOTION.evalFillPercent(percent, S.orientation)}%`);
  $('evalLabel').textContent = fmtEval(cp);
}

/* ── sounds (WebAudio, decoded buffers, 100 ms throttle) ───────────────── */

let audioCtx = null;
const audioBuffers = new Map();
let lastSoundAt = -1000;

function audioContext() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window['webkitAudioContext'];
    if (!Ctx) return null;
    audioCtx = new Ctx();
  }
  if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
}

function loadSound(event) {
  const url = `vendor/sounds/${S.soundTheme}-${event}.mp3`;
  if (!audioBuffers.has(url)) {
    audioBuffers.set(url, fetch(url)
      .then((response) => (response.ok ? response.arrayBuffer() : null))
      .then((data) => {
        if (!data) return null;
        const ctx = audioContext();
        return ctx ? ctx.decodeAudioData(data) : null;
      })
      .catch(() => null));
  }
  return audioBuffers.get(url);
}

function playSound(event, options = {}) {
  if (!S.soundOn) return;
  const ctx = audioContext();
  if (!ctx) return;
  const now = performance.now();
  if (!options.force && now - lastSoundAt < 100) return;
  lastSoundAt = now;
  loadSound(event).then((buffer) => {
    if (!buffer) {
      const fallback = MOTION.soundFallback(event);
      if (fallback !== event) playSound(fallback, { force: true });
      return;
    }
    if (!S.soundOn || !audioCtx) return;
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    const gain = audioCtx.createGain();
    gain.gain.value = 0.7;
    source.connect(gain).connect(audioCtx.destination);
    source.start(0);
  }).catch(() => {});
}

function playMoveEvent(event) {
  playSound(event);
}

function playResultSound(st) {
  if (!st || !st.over || S.reviewActive) return;
  if (st.result === '1/2-1/2') playSound('game-end');
  else playSound(st.result === (st.my_color === 'white' ? '1-0' : '0-1')
    ? 'victory' : 'defeat');
}

function playMoveSounds(prev, st) {
  if (S.reviewActive) return;
  const oldCount = prev ? prev.moves.length : 0;
  for (let i = oldCount; i < st.moves.length; i += 1) {
    const move = st.moves[i];
    const key = String(move.uci || '').slice(0, 4);
    if (S.playedUci.has(key)) continue;
    S.playedUci.add(key);
    playMoveEvent(MOTION.soundForMove(move, st.my_color));
  }
}

/* ── selection and moves ───────────────────────────────────────────────── */

function isLegal(from, to) {
  return Boolean(S.legal[from] && S.legal[from].includes(to));
}

function select(square) {
  S.selected = square;
  renderHighlights();
}

function clearSelection() {
  S.selected = null;
  renderHighlights();
}

function clearPremove() {
  if (!S.premove) return;
  S.premove = null;
  renderHighlights();
}

function canPremove() {
  return Boolean(S.st && !S.st.over && !S.reviewActive && !S.busy
    && S.st.turn !== S.st.my_color);
}

function onSquareDown(square, event) {
  if (S.pendingPromo) { closePromo(); return; }
  if (S.reviewActive || !S.st || S.st.over || S.busy) return;
  const occupant = S.boardMap.get(square);

  if (S.selected) {
    if (isLegal(S.selected, square)) { attemptMove(S.selected, square); return; }
    if (occupant && occupant[0] === myPieceColor()) {
      beginInteraction(square, event);
      return;
    }
    if (canPremove() && square !== S.selected) {
      queuePremove(S.selected, square);
      return;
    }
    clearSelection();
    return;
  }
  if (occupant && occupant[0] === myPieceColor()) beginInteraction(square, event);
}

function beginInteraction(square, event) {
  const wasSelected = S.selected === square;
  select(square);
  startDrag(square, wasSelected, event);
}

function startDrag(square, wasSelected, downEvent) {
  const entry = S.pieceEls.get(square);
  if (!entry) return;
  const drag = {
    el: entry.el, square, wasSelected, moved: false,
    startX: downEvent.clientX, startY: downEvent.clientY,
    target: null, ghost: null, cancel: null
  };
  S.drag = drag;

  function cleanup() {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    if (S.drag === drag) S.drag = null;
    drag.el.classList.remove('dragging');
    $('boardWrap').classList.remove('dragging');
    for (const cell of $('squares').children) cell.classList.remove('hover');
    if (drag.ghost) { drag.ghost.remove(); drag.ghost = null; }
  }

  function beginVisual(event) {
    drag.moved = true;
    clearPremove(); // a new drag cancels a queued premove
    drag.el.classList.add('dragging');
    $('boardWrap').classList.add('dragging');
    drag.ghost = createPiece(drag.square, entry.code);
    drag.ghost.classList.add('ghost');
    updateVisual(event);
  }

  function updateVisual(event) {
    const rect = $('boardWrap').getBoundingClientRect();
    const pos = MOTION.dragCentre(event.clientX, event.clientY, rect);
    setXY(drag.el, pos.x, pos.y);
    const target = MOTION.squareFromPoint(event.clientX, event.clientY, rect, S.orientation);
    if (target !== drag.target) {
      drag.target = target;
      for (const cell of $('squares').children) {
        cell.classList.toggle('hover', cell.dataset.square === target);
      }
    }
  }

  function resolveDrop(event) {
    if (!drag.moved) {
      placeEl(drag.el, drag.square);
      if (drag.wasSelected) clearSelection();
      return;
    }
    const rect = $('boardWrap').getBoundingClientRect();
    const target = MOTION.squareFromPoint(event.clientX, event.clientY, rect, S.orientation);
    if (target && target !== drag.square) {
      if (S.st && S.st.turn === S.st.my_color && isLegal(drag.square, target)) {
        attemptMove(drag.square, target);
        return;
      }
      if (canPremove()) {
        queuePremove(drag.square, target);
        placeEl(drag.el, drag.square);
        return;
      }
    }
    // Illegal drop snaps home immediately (no transition).
    placeEl(drag.el, drag.square);
  }

  function onMove(event) {
    if (S.drag !== drag) return;
    if (!drag.moved) {
      if (Math.hypot(event.clientX - drag.startX,
        event.clientY - drag.startY) < 3) return;
      beginVisual(event);
      return;
    }
    updateVisual(event);
  }

  function onUp(event) {
    if (S.drag !== drag) return;
    cleanup();
    resolveDrop(event);
  }

  function onCancel() {
    if (S.drag !== drag) return;
    cleanup();
    placeEl(drag.el, drag.square);
  }

  drag.cancel = onCancel;
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onCancel);
}

function queuePremove(from, to) {
  const code = S.boardMap.get(from);
  if (!code || code[0] !== myPieceColor() || from === to) return;
  if (code[1] === 'p' && (to[1] === '1' || to[1] === '8')) {
    openPromo(from, to, code[0], { premove: true });
    return;
  }
  S.premove = { from, to, promo: '' };
  S.selected = null;
  renderHighlights();
}

function tryPremove(st) {
  const pre = S.premove;
  if (!pre || !st || st.over || S.reviewActive) return;
  if (st.turn !== st.my_color || st.thinking) return;
  const uci = MOTION.premoveUci(pre, st.legal || {}, S.boardMap);
  S.premove = null;
  renderHighlights();
  if (!uci) return;
  // Execute 1 ms after the opponent's move; the normal animation path takes over.
  setTimeout(() => {
    if (!S.st || S.st.turn !== S.st.my_color || S.busy) return;
    attemptMove(pre.from, pre.to, pre.promo);
  }, 1);
}

function attemptMove(from, to, promo) {
  if (!isLegal(from, to) || S.busy) return;
  const code = S.boardMap.get(from);
  if (!code) return;
  const lastRank = to[1] === '8' || to[1] === '1';
  if (code[1] === 'p' && lastRank) {
    if (promo && 'qrbn'.includes(promo)) { sendMove(from + to + promo); return; }
    openPromo(from, to, code[0]);
    return;
  }
  sendMove(from + to);
}

function openPromo(from, to, color, options = {}) {
  S.pendingPromo = { from, to, premove: Boolean(options.premove) };
  const host = $('promo');
  host.replaceChildren();
  const { fx, ry } = squareToGrid(to);
  const column = document.createElement('div');
  column.className = 'promo-col';
  column.style.left = `${fx * 12.5}%`;
  column.style.top = ry === 0 ? '0%' : '50%';
  for (const piece of ['q', 'r', 'b', 'n']) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.piece = piece;
    button.title = { q: 'Dáma', r: 'Věž', b: 'Střelec', n: 'Jezdec' }[piece];
    const img = document.createElement('img');
    img.src = pieceSrc(color + piece);
    img.alt = piece;
    button.appendChild(img);
    column.appendChild(button);
  }
  host.appendChild(column);
  host.classList.remove('hidden');
}

function closePromo() {
  S.pendingPromo = null;
  $('promo').classList.add('hidden');
  $('promo').replaceChildren();
}

function onPromoClick(event) {
  const button = event.target.closest('button[data-piece]');
  if (!button || !S.pendingPromo) return;
  const { from, to, premove } = S.pendingPromo;
  if (premove) {
    S.premove = { from, to, promo: button.dataset.piece };
    closePromo();
    S.selected = null;
    renderHighlights();
    return;
  }
  sendMove(from + to + button.dataset.piece);
}

function optimisticMove(uci) {
  if (!S.st) return;
  const from = uci.slice(0, 2);
  const to = uci.slice(2, 4);
  const promo = uci.slice(4, 5);
  const entry = S.pieceEls.get(from);
  if (!entry) return;
  measure();

  const target = S.pieceEls.get(to);
  const capturedSquare = target ? null
    : (entry.code[1] === 'p' && from[0] !== to[0] ? to[0] + from[1] : null);
  const captured = capturedSquare ? S.pieceEls.get(capturedSquare) : null;
  const code = entry.code;
  const newCode = promo ? code[0] + promo : code;
  const dur = animMs();
  const batch = { left: 1, els: [] };
  const fade = (el) => {
    if (!el) return;
    el.classList.add('fading');
    batch.els.push(el);
  };

  fade(target && target.el);
  fade(captured && captured.el);

  S.pieceEls.delete(from);
  S.pieceEls.delete(to);
  if (capturedSquare) S.pieceEls.delete(capturedSquare);
  updateEl(entry.el, to, newCode);
  S.pieceEls.set(to, { el: entry.el, code: newCode });

  const goal = gridPx(to);
  tweenTo(entry.el, goal.x, goal.y, dur, () => {
    batch.left -= 1;
    if (batch.left <= 0) for (const el of batch.els) el.remove();
  });

  S.boardMap.delete(from);
  S.boardMap.set(to, newCode);
  if (capturedSquare) S.boardMap.delete(capturedSquare);
  S.lastMove = { from, to };
  S.selected = null;
  S.legal = {};
  S.playedUci.add(uci.slice(0, 4));
  const castle = code[1] === 'k'
    && Math.abs(FILES.indexOf(from[0]) - FILES.indexOf(to[0])) === 2;
  playMoveEvent(promo ? 'promote'
    : castle ? 'castle' : (target || captured) ? 'capture' : 'move-self');
  renderHighlights();
}

async function sendMove(uci) {
  if (!S.gid || S.busy) return;
  S.busy = true;
  closePromo();
  clearSelection();
  S.premove = null;
  optimisticMove(uci);
  // The server stops the clock when the move arrives; mirror that at once so
  // the interpolated clock does not over-drain during the engine analysis.
  if (S.st) {
    S.st.turn = S.st.my_color === 'white' ? 'black' : 'white';
    S.lastStateAt = performance.now();
  }
  try {
    const st = await api('api/move', {
      method: 'POST', body: { gid: S.gid, uci }
    });
    applyState(st);
  } catch (error) {
    playSound('illegal');
    showToast((error.data && error.data.error) || error.message || 'Tah se nepovedl');
    if (error.data && error.data.state) {
      S.forceRender = true;
      applyState(error.data.state);
    }
    poll();
  } finally {
    S.busy = false;
  }
}

/* ── polling ───────────────────────────────────────────────────────────── */

function startPolling() {
  if (S.pollTimer) return;
  S.pollTimer = setInterval(poll, 400);
  poll();
}

function stopPolling() {
  if (S.pollTimer) clearInterval(S.pollTimer);
  S.pollTimer = null;
}

async function poll() {
  if (!S.gid || S.polling || S.busy) return;
  S.polling = true;
  try {
    const st = await api(`api/state?gid=${encodeURIComponent(S.gid)}`);
    applyState(st);
  } catch (error) {
    if (error.status === 404) stopPolling();
  } finally {
    S.polling = false;
  }
}

/* ── review ────────────────────────────────────────────────────────────── */

async function openReview() {
  if (!S.gid || !S.st || S.reviewBusy) return;
  $('reviewPanel').classList.remove('hidden');
  if (S.review) {
    renderReview(S.review);
    enterReview(0);
    return;
  }
  S.reviewBusy = true;
  $('rvAcc').textContent = '—';
  $('rvSub').textContent = 'Analyzuji partii…';
  $('rvCounts').replaceChildren();
  $('rvWorst').replaceChildren();
  $('rvProgress').classList.remove('hidden');
  $('rvProgressBar').style.width = '0%';
  try {
    await api('api/review', { method: 'POST', body: { gid: S.gid } });
    setTimeout(pollReview, 250);
  } catch (error) {
    S.reviewBusy = false;
    showToast((error.data && error.data.error) || 'Review se nepovedl');
    $('rvProgress').classList.add('hidden');
    $('reviewPanel').classList.add('hidden');
  }
}

async function pollReview() {
  if (!S.gid || !S.reviewBusy) return;
  try {
    const data = await api(`api/review?gid=${encodeURIComponent(S.gid)}`);
    if (!S.reviewBusy) return; // the panel was closed while the request ran
    const pct = Math.round((data.progress || 0) * 100);
    $('rvProgressBar').style.width = `${pct}%`;
    $('rvProgressText').textContent = `Analyzuji… ${pct} %`;
    if (data.status === 'running') {
      setTimeout(pollReview, 450);
      return;
    }
    if (data.status === 'error') {
      S.reviewBusy = false;
      $('rvProgress').classList.add('hidden');
      showToast(data.error || 'Review selhal');
      return;
    }
    if (data.report) {
      S.review = data.report;
      S.reviewBusy = false;
      renderReview(data.report);
      enterReview(0);
    }
  } catch (error) {
    S.reviewBusy = false;
    $('rvProgress').classList.add('hidden');
    showToast((error.data && error.data.error) || 'Review selhal');
  }
}

function renderReview(report) {
  $('reviewPanel').classList.remove('hidden');
  $('rvProgress').classList.add('hidden');
  $('rvAcc').textContent = `${Number(report.accuracy || 0).toFixed(1)} %`;
  $('rvSub').textContent = `Přesnost · ${report.moves || 0} tvých tahů`
    + ` · průměrná ztráta ${report.avg_loss || 0} cp`;

  const counts = report.counts || {};
  const host = $('rvCounts');
  host.replaceChildren();
  for (const name of CATEGORIES) {
    const count = counts[name] || 0;
    if (!count) continue;
    const pill = document.createElement('div');
    pill.className = 'count-pill';
    const label = document.createElement('span');
    label.textContent = LABEL[name] || name;
    const value = document.createElement('b');
    value.className = `badge v-${name}`;
    value.textContent = String(count);
    pill.append(label, value);
    host.appendChild(pill);
  }

  const worst = $('rvWorst');
  worst.replaceChildren();
  if (!(report.worst || []).length) {
    const none = document.createElement('div');
    none.className = 'muted small';
    none.textContent = 'Žádné chyby — čistá partie.';
    worst.appendChild(none);
  } else {
    for (const item of report.worst) {
      const row = document.createElement('div');
      row.className = 'worst-row';
      row.dataset.ply = String(item.ply);
      const main = document.createElement('div');
      main.className = 'wmain';
      const badge = document.createElement('span');
      badge.className = `badge v-${item.verdict}`;
      badge.textContent = LABEL[item.verdict] || item.verdict;
      const text = document.createElement('span');
      text.textContent = `${item.ply}. ${item.san} · −${item.loss} cp`;
      main.append(badge, text);
      const sub = document.createElement('div');
      sub.className = 'wsub';
      sub.textContent = item.best ? `Lepší: ${item.best}` : 'Bez alternativy';
      row.append(main, sub);
      worst.appendChild(row);
    }
  }

  $('pgnLink').href = `api/pgn?gid=${encodeURIComponent(S.gid)}`;
  drawGraph();
}

function enterReview(ply) {
  S.reviewActive = true;
  S.reviewBusy = false;
  updateButtons(S.st);
  S.selected = null;
  S.legal = {};
  S.premove = null;
  closePromo();
  $('reviewPanel').classList.remove('hidden');
  $('rvProgress').classList.add('hidden');
  $('takebackBtn').disabled = true;
  jumpToPly(ply || 0);
}

function closeReview() {
  S.reviewActive = false;
  S.reviewBusy = false;
  $('reviewPanel').classList.add('hidden');
  $('rvProgress').classList.add('hidden');
  $('arrows').replaceChildren();
  S.selected = null;
  S.premove = null;
  markActiveMove(null);
  if (S.st) {
    S.boardMap = fenToMap(S.st.fen);
    renderPosition(S.st.fen, { instant: true });
    S.lastMove = S.st.last_move;
    S.legal = S.st.legal || {};
    renderHighlights();
    renderEvalBar();
    updateStatus(S.st);
    updateButtons(S.st);
  }
}

function jumpToPly(ply) {
  if (!S.review) return;
  const total = S.review.plies.length;
  const target = clamp(Number(ply) || 0, 0, total);
  S.reviewPly = target;
  const fen = target === 0 ? S.review.start_fen : S.review.plies[target - 1].fen_after;
  S.boardMap = fenToMap(fen);
  renderPosition(fen, { instant: true });
  S.selected = null;
  const last = target > 0 ? S.review.plies[target - 1] : null;
  S.lastMove = last ? { from: last.uci.slice(0, 2), to: last.uci.slice(2, 4) } : null;
  S.legal = {};
  renderHighlights();
  renderEvalBar();
  drawArrows(last);
  drawGraph();
  markActiveMove(target);
  $('rvPrev').disabled = target <= 0;
  $('rvNext').disabled = target >= total;

  let where = `${target} / ${total}`;
  if (!last) {
    where += ' · výchozí pozice';
  } else {
    where += ` · ${last.san}`;
    if (last.verdict) where += ` · ${LABEL[last.verdict] || last.verdict}`;
    if (last.loss) where += ` · −${last.loss} cp`;
  }
  $('rvWhere').textContent = where;

  if (S.st) updateStatus(S.st);
}

function markActiveMove(ply) {
  for (const el of $('moveList').querySelectorAll('.move-san.active')) {
    el.classList.remove('active');
  }
  if (ply === null || ply === undefined) return;
  const el = $('moveList').querySelector(`.move-san[data-ply="${ply}"]`);
  if (el) {
    el.classList.add('active');
    el.scrollIntoView({ block: 'nearest' });
  }
}

function ensureArrowDefs() {
  const host = $('arrows');
  if (host.querySelector('defs')) return;
  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns, 'defs');
  for (const [id, color] of [['arrow-best', '#15781B'], ['arrow-played', '#882020']]) {
    const marker = document.createElementNS(ns, 'marker');
    marker.setAttribute('id', id);
    marker.setAttribute('markerWidth', '4');
    marker.setAttribute('markerHeight', '4');
    marker.setAttribute('markerUnits', 'strokeWidth');
    marker.setAttribute('viewBox', '0 0 4 4');
    marker.setAttribute('refX', '2.05');
    marker.setAttribute('refY', '2');
    marker.setAttribute('orient', 'auto');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', 'M0,0 V4 L3,2 Z');
    path.setAttribute('fill', color);
    path.setAttribute('fill-opacity', '.4');
    marker.appendChild(path);
    defs.appendChild(marker);
  }
  host.appendChild(defs);
}

function drawArrows(ply) {
  const host = $('arrows');
  host.replaceChildren();
  if (!ply || !ply.uci) return;
  ensureArrowDefs();
  const best = ply.best_uci && ply.best_uci !== ply.uci ? ply.best_uci : null;
  const shared = Boolean(best && best.slice(2, 4) === ply.uci.slice(2, 4));
  if (best) {
    drawArrow(best, '#15781B', shared ? MOTION.ARROW_DEST_SHIFT : 0);
  }
  if (ply.uci !== ply.best_uci) {
    drawArrow(ply.uci, '#882020', 0);
  }
}

function drawArrow(uci, color, shorten) {
  const from = squareToGrid(uci.slice(0, 2));
  const to = squareToGrid(uci.slice(2, 4));
  const geo = MOTION.arrowGeometry(from, to, {
    shorten: shorten || 0, clearance: 0.12
  });
  if (!geo) return;
  const ns = 'http://www.w3.org/2000/svg';
  const line = document.createElementNS(ns, 'line');
  line.setAttribute('x1', String(geo.x1));
  line.setAttribute('y1', String(geo.y1));
  line.setAttribute('x2', String(geo.x2));
  line.setAttribute('y2', String(geo.y2));
  line.setAttribute('stroke', color);
  line.setAttribute('stroke-width', '0.156');
  line.setAttribute('stroke-linecap', 'round');
  line.setAttribute('stroke-opacity', '.4');
  line.setAttribute('marker-end',
    `url(#${color === '#15781B' ? 'arrow-best' : 'arrow-played'})`);
  $('arrows').appendChild(line);
}

function drawGraph() {
  const canvas = $('rvGraph');
  if (!S.review || !canvas) return;
  const width = canvas.clientWidth || 320;
  const height = 148;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = 'rgba(255,255,255,.055)';
  ctx.fillRect(0, 0, width, height / 2);
  ctx.fillStyle = 'rgba(0,0,0,.20)';
  ctx.fillRect(0, height / 2, width, height / 2);

  const evals = S.review.evals || [0];
  const n = Math.max(1, evals.length - 1);
  const xFor = (index) => 8 + index * (width - 16) / n;
  const yFor = (cp) => 8 + (1 - winPercent(cp) / 100) * (height - 16);

  ctx.beginPath();
  evals.forEach((cp, index) => {
    const x = xFor(index);
    const y = yFor(cp);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#e9e6e2';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,255,255,.18)';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();
  ctx.setLineDash([]);

  const x = xFor(clamp(S.reviewPly, 0, n));
  const y = yFor(evals[clamp(S.reviewPly, 0, evals.length - 1)] || 0);
  ctx.strokeStyle = '#81b64c';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, height);
  ctx.stroke();
  ctx.fillStyle = '#81b64c';
  ctx.beginPath();
  ctx.arc(x, y, 3.2, 0, Math.PI * 2);
  ctx.fill();
}

function onGraphClick(event) {
  if (!S.review) return;
  const rect = $('rvGraph').getBoundingClientRect();
  const relative = clamp(event.clientX - rect.left - 8, 0, rect.width - 16);
  const total = S.review.plies.length;
  const index = total === 0 ? 0 : Math.round(relative / (rect.width - 16) * total);
  jumpToPly(index);
}

/* ── game start / setup ────────────────────────────────────────────────── */

function resetGameView() {
  stopPolling();
  S.st = null;
  S.gid = null;
  S.selected = null;
  S.legal = {};
  S.lastMove = null;
  S.premove = null;
  S.drag = null;
  S.playedUci.clear();
  cancelTweens();
  S.boardMap = new Map();
  S.pieceEls.clear();
  $('pieces').replaceChildren();
  $('arrows').replaceChildren();
  closePromo();
  $('moveList').replaceChildren();
  $('moveCount').textContent = '';
  S.moveSig = '';
  S.review = null;
  S.reviewActive = false;
  S.reviewPly = 0;
  S.reviewBusy = false;
  $('reviewPanel').classList.add('hidden');
  $('rvProgress').classList.add('hidden');
  $('coachBody').replaceChildren();
  S.ten = { white: false, black: false };
  S.clocks = { white: S.setup.base, black: S.setup.base };
  S.lastStateAt = performance.now();
  $('statusLine').textContent = '';
  $('nameTop').textContent = 'Stockfish';
  $('nameBottom').textContent = S.setup.player || 'Ty';
}

async function startGame() {
  if (!S.gid) resetGameView();
  const base = Math.round(Number($('baseMin').value) * 60);
  const inc = Math.round(Number($('incSec').value));
  if (!Number.isFinite(base) || base < 10 || base > 10800) {
    showToast('Základ musí být 10 s – 180 min.');
    return;
  }
  if (!Number.isFinite(inc) || inc < 0 || inc > 180) {
    showToast('Přírůstek musí být 0–180 s.');
    return;
  }
  S.setup.base = base;
  S.setup.inc = inc;
  S.setup.level = clamp(Number($('levelRange').value) || 8, 4, 16);
  S.setup.player = ($('playerName').value || 'me').trim().slice(0, 40) || 'me';
  savePrefs();

  resetGameView();
  playSound('game-start');
  try {
    const st = await api('api/new', {
      method: 'POST',
      body: {
        color: S.setup.color,
        base,
        inc,
        level: S.setup.level,
        mode: S.setup.mode,
        player: S.setup.player
      }
    });
    S.orientation = st.my_color;
    S.gid = st.gid;
    buildSquares();
    applyState(st);
    hideSetup();
    startPolling();
    tickClocks();
  } catch (error) {
    showToast((error.data && error.data.error) || error.message || 'Start selhal');
  }
}

function showSetup() {
  $('colorChips').querySelectorAll('.chip').forEach((chip) => {
    chip.classList.toggle('on', chip.dataset.color === S.setup.color);
  });
  markPreset(S.setup.base, S.setup.inc);
  $('baseMin').value = String(Math.round((S.setup.base / 60) * 10) / 10);
  $('incSec').value = String(S.setup.inc);
  $('levelRange').value = String(S.setup.level);
  $('levelOut').textContent = String(S.setup.level);
  $('modeChips').querySelectorAll('.chip').forEach((chip) => {
    chip.classList.toggle('on', chip.dataset.mode === S.setup.mode);
  });
  $('playerName').value = S.setup.player;
  $('setupCancel').classList.toggle('hidden', !S.gid);
  $('setupOverlay').classList.remove('hidden');
}

function hideSetup() {
  $('setupOverlay').classList.add('hidden');
}

function markPreset(base, inc) {
  let matched = false;
  $('timeChips').querySelectorAll('.chip').forEach((chip) => {
    const on = Number(chip.dataset.base) === base && Number(chip.dataset.inc) === inc;
    chip.classList.toggle('on', on);
    if (on) matched = true;
  });
  return matched;
}

function savePrefs() {
  try {
    localStorage.setItem('coach.prefs', JSON.stringify({
      boardTheme: S.boardTheme,
      pieceTheme: S.pieceTheme,
      soundTheme: S.soundTheme,
      soundOn: S.soundOn,
      animSpeed: S.animSpeed,
      evalVisible: S.evalVisible,
      setup: S.setup
    }));
  } catch (error) { /* private mode */ }
}

function loadPrefs() {
  try {
    const prefs = JSON.parse(localStorage.getItem('coach.prefs') || '{}');
    if (prefs.boardTheme) S.boardTheme = prefs.boardTheme;
    if (prefs.pieceTheme) S.pieceTheme = prefs.pieceTheme;
    if (prefs.soundTheme) S.soundTheme = prefs.soundTheme;
    if (typeof prefs.soundOn === 'boolean') S.soundOn = prefs.soundOn;
    if (prefs.animSpeed
      && Object.prototype.hasOwnProperty.call(MOTION.ANIMATION_MS, prefs.animSpeed)) {
      S.animSpeed = prefs.animSpeed;
    }
    if (typeof prefs.evalVisible === 'boolean') S.evalVisible = prefs.evalVisible;
    if (prefs.setup && typeof prefs.setup === 'object') {
      S.setup = { ...S.setup, ...prefs.setup };
    }
  } catch (error) { /* ignore */ }
}

/* ── themes ────────────────────────────────────────────────────────────── */

async function loadThemes() {
  let data;
  try {
    data = await api('api/themes');
  } catch (error) {
    data = { boards: ['brown'], pieces: ['classic'], sounds: ['default', 'beat'] };
  }
  const boards = data.boards || [];
  const pieces = data.pieces || [];
  const boardSelect = $('boardTheme');
  const pieceSelect = $('pieceTheme');
  boardSelect.replaceChildren();
  pieceSelect.replaceChildren();
  for (const name of boards) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = humanize(name);
    boardSelect.appendChild(option);
  }
  for (const name of pieces) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = humanize(name);
    pieceSelect.appendChild(option);
  }
  if (!boards.includes(S.boardTheme)) S.boardTheme = boards[0] || 'brown';
  if (!pieces.includes(S.pieceTheme)) S.pieceTheme = pieces.includes('classic') ? 'classic' : (pieces[0] || 'classic');
  boardSelect.value = S.boardTheme;
  pieceSelect.value = S.pieceTheme;
  applyBoardTheme();
}

function applyBoardTheme() {
  $('boardImg').style.backgroundImage = `url("vendor/chesscom/boards/${S.boardTheme}.png")`;
  $('boardWrap').style.setProperty('--board-tint', BOARD_TINT[S.boardTheme] || '#b58863');
}

function rerenderBoard() {
  if (S.reviewActive) {
    renderPosition(reviewFen(), { instant: true });
  } else if (S.st) {
    renderPosition(S.st.fen, { instant: true });
  } else {
    renderPosition(START_FEN, { instant: true });
  }
  S.boardMap = fenToMap(S.reviewActive ? reviewFen() : (S.st ? S.st.fen : START_FEN));
  renderHighlights();
}

/* ── wiring ────────────────────────────────────────────────────────────── */

function wire() {
  $('squares').addEventListener('pointerdown', (event) => {
    const cell = event.target.closest('.sq');
    if (cell) onSquareDown(cell.dataset.square, event);
  });
  $('promo').addEventListener('click', (event) => {
    if (event.target === $('promo')) { closePromo(); return; }
    onPromoClick(event);
  });

  $('startBtn').addEventListener('click', startGame);
  $('newBtn').addEventListener('click', showSetup);
  $('setupCancel').addEventListener('click', hideSetup);

  $('colorChips').addEventListener('click', (event) => {
    const chip = event.target.closest('.chip');
    if (!chip) return;
    S.setup.color = chip.dataset.color;
    $('colorChips').querySelectorAll('.chip').forEach((c) => c.classList.toggle('on', c === chip));
    savePrefs();
  });

  $('timeChips').addEventListener('click', (event) => {
    const chip = event.target.closest('.chip');
    if (!chip) return;
    S.setup.base = Number(chip.dataset.base);
    S.setup.inc = Number(chip.dataset.inc);
    $('baseMin').value = String(S.setup.base / 60);
    $('incSec').value = String(S.setup.inc);
    markPreset(S.setup.base, S.setup.inc);
    savePrefs();
  });

  const customTime = () => {
    const minutes = Number($('baseMin').value);
    const inc = Number($('incSec').value);
    if (!Number.isFinite(minutes) || minutes <= 0) return;
    S.setup.base = Math.round(minutes * 60);
    S.setup.inc = Math.max(0, Math.round(inc) || 0);
    markPreset(S.setup.base, S.setup.inc);
    savePrefs();
  };
  $('baseMin').addEventListener('input', customTime);
  $('incSec').addEventListener('input', customTime);

  $('levelRange').addEventListener('input', () => {
    S.setup.level = Number($('levelRange').value);
    $('levelOut').textContent = String(S.setup.level);
    savePrefs();
  });

  $('modeChips').addEventListener('click', (event) => {
    const chip = event.target.closest('.chip');
    if (!chip) return;
    S.setup.mode = chip.dataset.mode;
    $('modeChips').querySelectorAll('.chip').forEach((c) => c.classList.toggle('on', c === chip));
    savePrefs();
  });

  $('playerName').addEventListener('input', () => {
    S.setup.player = $('playerName').value.slice(0, 40);
    savePrefs();
  });

  $('boardTheme').addEventListener('change', () => {
    S.boardTheme = $('boardTheme').value;
    applyBoardTheme();
    savePrefs();
  });
  $('pieceTheme').addEventListener('change', () => {
    S.pieceTheme = $('pieceTheme').value;
    rerenderBoard();
    savePrefs();
  });
  $('soundTheme').addEventListener('change', () => {
    S.soundTheme = $('soundTheme').value;
    savePrefs();
  });
  $('animSpeed').addEventListener('change', () => {
    S.animSpeed = $('animSpeed').value;
    savePrefs();
  });
  $('soundBtn').addEventListener('click', () => {
    S.soundOn = !S.soundOn;
    $('soundBtn').textContent = S.soundOn ? '🔊' : '🔇';
    savePrefs();
  });
  $('evalBtn').addEventListener('click', () => {
    S.evalVisible = !S.evalVisible;
    renderEvalBar();
    savePrefs();
  });

  $('flipBtn').addEventListener('click', () => {
    S.orientation = S.orientation === 'white' ? 'black' : 'white';
    buildSquares();
    if (S.reviewActive) jumpToPly(S.reviewPly);
    else rerenderBoard();
    renderEvalBar();
    if (S.st) updateSideLabels(S.st);
  });

  $('takebackBtn').addEventListener('click', async () => {
    if (!S.gid || S.busy) return;
    S.busy = true;
    try {
      const st = await api('api/takeback', { method: 'POST', body: { gid: S.gid } });
      applyState(st);
    } catch (error) {
      showToast((error.data && error.data.error) || 'Vzetí tahu zpět selhalo');
    } finally {
      S.busy = false;
      updateButtons(S.st);
    }
  });

  $('resignBtn').addEventListener('click', async () => {
    if (!S.gid || S.busy) return;
    if (!window.confirm('Vzdát partii?')) return;
    S.busy = true;
    try {
      const st = await api('api/resign', { method: 'POST', body: { gid: S.gid } });
      applyState(st);
    } catch (error) {
      showToast((error.data && error.data.error) || 'Vzdání selhalo');
    } finally {
      S.busy = false;
    }
  });

  $('reviewBtn').addEventListener('click', () => {
    if (S.reviewActive) closeReview();
    else openReview();
  });
  $('rvClose').addEventListener('click', closeReview);
  $('rvPrev').addEventListener('click', () => jumpToPly(S.reviewPly - 1));
  $('rvNext').addEventListener('click', () => jumpToPly(S.reviewPly + 1));
  $('rvGraph').addEventListener('click', onGraphClick);
  $('rvWorst').addEventListener('click', (event) => {
    const row = event.target.closest('.worst-row');
    if (row) jumpToPly(Number(row.dataset.ply));
  });
  $('moveList').addEventListener('click', (event) => {
    if (!S.reviewActive) return;
    const span = event.target.closest('.move-san');
    if (span) jumpToPly(Number(span.dataset.ply));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && S.pendingPromo) {
      closePromo();
      return;
    }
    if (!S.reviewActive) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      jumpToPly(S.reviewPly - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      jumpToPly(S.reviewPly + 1);
    } else if (event.key === 'Escape') {
      closeReview();
    }
  });

  window.addEventListener('resize', () => {
    layoutPieces();
    if (S.reviewActive) drawGraph();
  });
}

/* ── boot ──────────────────────────────────────────────────────────────── */

async function init() {
  loadPrefs();
  buildSquares();
  wire();
  renderPosition(START_FEN, { instant: true });
  S.boardMap = fenToMap(START_FEN);
  S.clocks = { white: S.setup.base, black: S.setup.base };
  $('soundBtn').textContent = S.soundOn ? '🔊' : '🔇';
  $('soundTheme').value = S.soundTheme;
  $('animSpeed').value = S.animSpeed;
  $('levelRange').value = String(S.setup.level);
  $('levelOut').textContent = String(S.setup.level);
  $('playerName').value = S.setup.player;
  $('nameBottom').textContent = S.setup.player;
  renderEvalBar();
  updateSideLabels({
    my_color: 'white', player: S.setup.player, level: S.setup.level,
    turn: 'white', over: true
  });
  tickClocks();
  showSetup();
  await loadThemes();
  try {
    const health = await api('api/health');
    if (!health.engine_present) showToast('Stockfish nenalezen — nastav COACH_STOCKFISH.', 8000);
  } catch (error) { /* server still shows its own error */ }
  setInterval(tickClocks, 100);
}

document.addEventListener('DOMContentLoaded', init);
})();
