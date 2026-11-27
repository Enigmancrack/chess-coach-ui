# chess-coach-ui

**English** · [Čeština](README.cs.md) · [Deutsch](README.de.md) · [Español](README.es.md)

Local chess board, coach and post-game review in the style of chess.com, backed
by Stockfish. Everything runs on `127.0.0.1`: there is no account, no cloud and
no network request at runtime. Boards, pieces and sounds are vendored under
`static/vendor/` (chess.com artwork, personal local use only). The same code
also imports games recorded by the Python bot and reviews them from the bot's
own evaluations, without replaying them through an engine.

## Features

| Feature | What it does |
|---|---|
| Board and input | drag & drop and click–click, including capture by clicking the enemy piece; switching the selection by clicking another own piece; promotion always opens a Q/R/B/N picker; illegal UCI is never sent |
| Board state | selection, legal-move dots, capture rings, last move highlighted for both sides, red king in check, 200 ms move animation, no full repaint during a game |
| Themes | 9 boards, 8 piece sets, 2 sound themes (`default`, `beat`), sounds for move, capture, castle, check, promotion, start/end, ten seconds and illegal move |
| Modes | `training` (live badges and advice), `sharp` (no advice until the game ends), `analysis` (eval always visible), plus read-only `import` |
| Clock | server-authoritative for both sides: the side to move is drained (including Stockfish while it thinks), increment after the move, flag detection and result |
| Live coach | instant badge (brilliant / great / best / good / book / inaccuracy / mistake / blunder / miss) and one sentence on what was better and by how many centipawns |
| Review | accuracy, category counts, average loss, worst moments with the best alternative, canvas eval graph, best/played arrows, keyboard navigation, PGN export |
| Bot game import | reads `~/.chess_bot_journals/*.jsonl` and `~/.chess_coach_games/*.json`; reuses stored evaluations instead of re-running Stockfish; journals that start mid-game are re-anchored on the recorded FEN |
| Terminal coach | `coach.py play|review|import|games` for a game, a saved review, a journal import or a listing |

## Quick start

```bash
cd ~/projekty/chess-coach-ui

# PEP 668 systems (Kali, Debian) refuse a system-wide pip install; use a venv.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Start the server (blocks; Ctrl+C stops it). `./run.sh` does the same
# with the system python3.
.venv/bin/python server.py --port 8770
curl -s http://127.0.0.1:8770/api/health
# {"ok": true, "stockfish": "...", "engine_present": true}
```

Open `http://127.0.0.1:8770`. Another host or port, or another Stockfish:

```bash
.venv/bin/python server.py --host 127.0.0.1 --port 9000
COACH_STOCKFISH=/path/to/stockfish .venv/bin/python server.py
```

Checks:

```bash
.venv/bin/python -m pytest -q
node --check static/app.js
node --check static/motion.js
.venv/bin/python tests/e2e_api.py     # full API pass, needs Stockfish (~15 s)
```

Terminal coach:

```bash
.venv/bin/python coach.py games
.venv/bin/python coach.py review
.venv/bin/python coach.py import ~/.chess_bot_journals/<game>.done.jsonl
.venv/bin/python coach.py play --level 8 --player viktor
```

The server refuses to start when the Stockfish path does not exist. Static files
are served from `static/`, the API lives under `/api/*`, and there is no
authentication because everything is loopback-only.

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `COACH_STOCKFISH` | path to the Stockfish binary | first `stockfish` in `PATH`, else a known install path, else the author's build |
| `COACH_DEPTH` | analysis depth while playing | `10` |
| `COACH_REVIEW_DEPTH` | analysis depth for reviews | `12` |
| `COACH_DATA_DIR` | where game JSON is stored | `~/.chess_coach_games` |
| `COACH_JOURNAL_DIR` | bot journal directory | `~/.chess_bot_journals` |
| `COACH_MODEL_FILE` | opponent model, read-only | `~/.chess_opponent_model.json` |
| `COACH_LANG` | UI language (`cs`, `en`) | `cs` |
| `COACH_HTTP_LOG` | `1` enables the HTTP log | off |

## Architecture

| File | Role |
|---|---|
| `server.py` | stdlib HTTP server, JSON API, static files, game lifecycle, import allowlist |
| `game.py` | one game: board, clock, bot, takeback, review worker, imported-game view |
| `rules.py` | legality, UCI normalisation, move flags, material, sacrifice detection |
| `clock.py` | server clock with injectable time for tests |
| `engine.py` | Stockfish adapter (`analyse`, `play`, levels 4–16) |
| `review.py` | classification, accuracy, whole-game analysis, PGN, player profile |
| `importer.py` | journal and saved-game parsing, mid-game anchoring, stored-eval reuse |
| `coach.py` | terminal client |
| `i18n.py` | Czech and English display strings |
| `data/store.py` | JSON game store (seam for a later SQLite backend) |
| `static/` | `index.html`, `style.css`, `app.js`, `motion.js`, vendored assets |

API: `GET /api/health|themes|settings|state|review|pgn|games`,
`POST /api/new|move|takeback|resign|review|import|settings`. Errors are JSON with
status 400/404/409. `state` returns FEN, moves, legal targets (only when the
human is to move), clocks, result, eval and the coach note.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **96 passed** |
| `node --check static/app.js`, `static/motion.js` | both clean |
| `python3 tests/e2e_api.py` | passes end to end against a real Stockfish |

The E2E run exercises health, themes (9 boards, 8 piece sets, sounds
`beat`/`default`), a new white game, clock drain (59.997 → 58.793), a player
move and the bot reply, takeback, an illegal move returning 400, a black game
with the bot opening, a custom FEN, back-rank promotion with capture and check,
review (accuracy 87.6 %, average loss 32.0 cp), PGN and resignation.

## Limitations

- **Web games are not persisted.** The server keeps at most 40 games in memory;
  only the terminal coach and the importer write JSON to disk.
- **One Stockfish process behind a lock.** A review and a bot move serialise;
  a long review delays the next bot reply.
- **No opponent adaptation from imported data, no drills or spaced repetition.**
  `data/` has a seam for them, but they are not implemented.
- **Visual polish is only verified syntactically and through the API.** No
  browser ran in the build environment, so layout on small screens and exact
  colours are unchecked.
- **Import paths are restricted.** Reads are allowed only under
  `~/.chess_bot_journals` and `~/.chess_coach_games`; anything else is rejected
  with 400.

## Licence

The repository contains no `LICENSE` file. `python-chess` and Stockfish are
GPL-3.0-or-later, so a distributed bundle that includes them falls under GPLv3.
The vendored chess.com artwork and sounds are not licensed for redistribution
and are included for personal local use only.
