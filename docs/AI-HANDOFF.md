# AI handoff — chess-coach-ui

## What this is

A local, single-user chess coach in the chess.com idiom: the browser is a thin
client over a stdlib Python HTTP server that owns the game (board, clocks, bot
replies, review worker), Stockfish answers through one adapter, and every move
the player makes is graded into one of nine categories with an explainable
centipawn-loss number; after the game the full evaluation curve, accuracy,
worst moments, arrows and PGN are available, and the same engine can replay
games recorded by the companion bot. No account, no network, no framework on
either side — `static/app.js` is hand-written DOM code and the server imports
nothing outside the standard library plus `python-chess`.

## Invariants (break these and the app is wrong, not just ugly)

1. **The server owns the clock.** The browser only interpolates between
   polls; every state refresh re-syncs from `server_ms`. Stop the player's
   clock at the moment the move is *received*, settle before flag checks, and
   add the increment only for the side that just moved.
2. **Legal moves are computed and exposed only for the player's turn.** The
   client never generates moves. `/api/state` returns `legal: {}` while the
   engine thinks, when the game is over, or when it is not the player's turn.
   Never send an illegal UCI — normalise promotions in `rules.normalise_uci`.
3. **Animation uses `transform`, never `left/top`.** `static/motion.js` is the
   pure motion layer (tweens, arrow geometry, sound choice); the layout is a
   grid and pieces move by `translate(...)` so a frame never reflows. CSS
   contracts are pinned by `tests/test_motion.py`.
4. **Arrows are SVG.** The `<svg class="arrows">` layer draws review arrows in
   board coordinates; green = best, red = played, blue-grey = played with no
   recorded alternative. Do not replace it with absolutely positioned divs or
   canvas — it must scale with the board and stay crisp.
5. **i18n keys are not machine values.** Verdict ids (`best`, `blunder`, …),
   UCI/SAN, result codes (`1-0`, `1/2-1/2`), JSON keys and `lang` codes are
   never translated. Display text lives only in `i18n.py`; the UI receives
   labels through `/api/settings` and per-move `label`/`text` fields.
6. **No Selenium, Playwright, Puppeteer or any online driver.** Verification
   is pytest + `node --check` + `tests/e2e_api.py` (real HTTP, real
   Stockfish). The UI is not driven by a browser automation tool and must not
   become dependent on one.

## File map and ownership

| Path | Owns | Must not |
|---|---|---|
| `server.py` | HTTP transport, JSON envelope, game registry (max 40), settings, static files, CLI flags | contain chess rules, grading text or clock maths |
| `game.py` | one `Game`/`ImportedGame`: board, clock, bot thread, takeback, review worker, state payload | do HTTP, print, or own translations |
| `rules.py` | legality, UCI normalisation, move flags, material, sacrifice detection | know about HTTP or text |
| `clock.py` | authoritative per-side time with injectable `now` | talk to the engine |
| `engine.py` | the single Stockfish process, `analyse`/`play`, level limits | grade moves or format output |
| `review.py` | classification, accuracy, whole-game analysis, eval curve, PGN headers, optional profile/model glue | do HTTP or hold game state |
| `i18n.py` | every user-facing string in cs/en + plurals; raises on a missing key | translate ids, SAN or JSON keys |
| `coach.py` | terminal client (`play`, `review`, `import`, `games`), `--lang` | duplicate grading logic |
| `importer.py` | read-only bot journals/stored games → record; writes only under `COACH_DATA_DIR/imports` | write into the bot's directories |
| `data/store.py` | JSON persistence seam (`COACH_DATA_DIR`) | assume a schema beyond `save/load/list/latest` |
| `static/index.html`, `style.css` | markup and the visual contract (eval bar, badges, review card) | compute positions |
| `static/app.js` | polling, rendering, input, review UI, language selector | decide legality or clock truth |
| `static/motion.js` | pure animation/geometry/sound helpers (Node-testable) | touch the DOM beyond the passed elements |
| `tests/` | pytest suite, motion suite, `e2e_api.py`, shared fake engine/clock | reach the network |
| `docs/` | tutorial (cs/en), this handoff | drift from the actual UI labels |

## Tests and what each gate proves

```bash
python3 -m pytest -q                 # 96 tests, stdlib + fake engine, no Stockfish needed
lsp-diag --no-daemon <file.py>       # pyright diagnostics on every touched module
node --check static/app.js           # the browser bundle parses
python3 tests/e2e_api.py             # real server + real Stockfish, both colours (~15 s)
```

- `pytest` covers move normalisation (including `d1d8q` onto a queen), legal
  destination exposure only on the player's turn, clock drain/increment/flag,
  takeback for both colours, classification/accuracy/PGN, import shapes and
  path guard, motion constants, catalog completeness, Czech plurals and the
  `lang=en` round trip.
- `lsp-diag` proves the Python type surface still matches (TypedDict catalogs,
  engine protocol, payload shapes). A new diagnostic in a touched file is
  blocking.
- `node --check` proves the single JS bundle parses; the motion suite inside
  pytest proves the numeric animation contract.
- `e2e_api.py` proves the whole loop over HTTP: clock drains, move accepted,
  bot replies, takeback, illegal move refused with a legal map, black game
  opens with a bot move, review reaches `ready`, PGN, resign.

## Three expensive bugs already fixed

1. **Orientation-rotated FEN map in black games.** The square→element map was
   built in visual order, so a flipped board looked up FEN squares in a
   mirrored map: pieces rendered on the wrong squares and drops resolved to
   the wrong target. *Lesson:* keep the position model in FEN coordinates and
   apply orientation only in `squareToGrid`/layout; orientation is a view
   transform, never a model transform.
2. **`x.index` vs `x.ply`.** One code path addressed moves by 0-based array
   index while the review, move list and takeback addressed them by 1-based
   ply, so jumps landed one move off (and got worse after a takeback).
   *Lesson:* exactly one identifier for a move in payloads — `ply`; array
   indices stay local to a loop.
3. **Review deadlock inside `start_review`.** The review was started while a
   lock was still held and the worker immediately tried to take the same lock:
   the request hung and the worker never ran. *Lesson:* mutate flags under the
   lock, release it, then start the thread; the worker takes `self.lock` only
   to attach result metadata. `start_review` in `game.py` shows the pattern.

## Open work and the seams left for it

- **`data/`** — `JsonStore` is deliberately tiny (`save/load/list/latest`);
  a SQLite store, or drills/spaced repetition, plugs in here without touching
  `game.py`. Today only the terminal coach persists games; the web keeps at
  most 40 games in memory.
- **Drills** — no puzzle/drill mode exists. Keys for it belong in `i18n.py`,
  not in new literals; review categories are already stable ids to build on.
- **Packaging (`apt`)** — there is no Debian package, service unit or
  installer; the app assumes a checkout plus Python + Stockfish. A future
  package should keep `COACH_*` env overrides and the loopback-only default.
- **UI chrome is Czech** — the coach output, errors, badges and API text are
  bilingual, but static labels in `index.html`/`app.js` are not translated
  yet. Extend `/api/settings` rather than hard-coding a second language.
- **Persistence of web games** — refreshing the tab loses the in-memory game;
  `data/` is the place to fix that.
- **Visual polish** — the UI has only been verified syntactically and through
  the API here, not by a human eye on a device.

## Do not

- Do not add an online driver (Selenium/Playwright/Puppeteer) or any headless
  browser dependency; e2e goes through `tests/e2e_api.py`.
- Do not localize enum values, verdict ids, UCI/SAN, result strings or JSON
  keys — only display text, and only through `i18n.py`.
- Do not re-download, re-encode or replace `static/vendor/` assets; they are
  vendored deliberately (chess.com artwork, personal local use) and tests pin
  their counts.
- Do not move clock authority or legal-move generation into the browser.
- Do not animate with `left`/`top` or `setTimeout` frame loops; use the
  transform tweens in `motion.js`.
- Do not silently fall back to another language when a key is missing — a
  `KeyError` is the intended failure.
- Do not widen the HTTP surface beyond loopback or add authentication-free
  file access outside `static/`.

## Current tree note

`git status` may show local edits to `engine.py` (portable Stockfish lookup
instead of one hard-coded path) and `run.sh` (foreground start instead of
`nohup`). They are intentional local improvements; do not revert them while
working on unrelated features.
