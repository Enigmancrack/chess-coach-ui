# Chess Coach — first steps

A local chess coach: you play against Stockfish in the browser, the coach
grades every move, and afterwards you get a full review with an evaluation
graph and arrows. Everything runs on your machine; there is no account and no
internet connection.

## 1. Install and start

You need Python 3.11+ and a Stockfish binary. Check that Stockfish is
reachable:

```bash
command -v stockfish
```

If that prints nothing, set `COACH_STOCKFISH` to the full path of the binary
before starting anything (see step 3). Then, from the repository root:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

The last command runs the test suite — `96 passed` means the install is
healthy. Start the app in this terminal:

```bash
./run.sh 8770
```

It prints `chess-coach-ui na http://127.0.0.1:8770  (engine …)` and keeps
running until you press Ctrl+C. Open <http://127.0.0.1:8770> in your browser.
`./run.sh` refuses to start if the port is already taken.

To start the server by hand, with an English coach, use:

```bash
python3 server.py --port 8770 --lang en
```

## 2. Your first game

The "Nová partie" dialog opens on load. Pick:

- **Barva** — Bílá (White), Černá (Black) or Náhodně (Random). As Black the
  server immediately makes White's first move and the board is flipped so your
  pieces are at the bottom.
- **Tempo** — a preset (3|0 … 30|0) or your own base in minutes plus increment
  in seconds. Bullet is deliberately not offered.
- **Úroveň soupeře** — 4 (beginner) to 16 (strong club player).
- **Režim** — Trénink (advice after every move), Ostrá (no advice until the
  game ends) or Analýza (advice plus the evaluation bar).
- **Jméno** — the name stored with the game.

Press **Hrát**. The board appears in the middle, your clock at the bottom and
the opponent's at the top; the coach panel is on the right.

Play by clicking a piece and then a highlighted destination, or by dragging.
Legal destinations appear as small dots, captures as rings. Promotions open a
picker (queen, rook, bishop, knight). You cannot move while it is not your turn
or while the engine is thinking — the clock is owned by the server, not the
browser, so it stops at the moment your move arrives.

Moves you play are graded immediately in the coach panel. A badge appears next
to the move in the move list too.

## 3. What the badges mean

| Badge | English | Meaning |
|---|---|---|
| !! | Brilliant | a sacrifice that still keeps the position |
| ! | Great | the only move that holds |
| * | Best | the engine's own choice (or as good as it) |
| . | Good | a small loss, up to 30 centipawns |
| B | Book | opening theory, first ten plies |
| ?! | Inaccuracy | 30–90 centipawns lost |
| ? | Mistake | 90–220 centipawns lost |
| ?? | Blunder | more than 220 centipawns lost |
| X | Missed win | a forced win that was not played |

The id (`best`, `blunder`, …) is what the app stores and compares; the visible
word is only a translation. Switch the language with the **Jazyk** selector in
the top bar — the coach text, badges and new-game messages follow it, while
moves and results stay in standard notation.

## 4. The evaluation bar

The thin vertical bar left of the board shows who is better. The light part is
always the player whose pieces are at the bottom, the dark part the opponent;
the number above it is the evaluation in pawns from White's side (`+1.2` means
White is a pawn and a bit up). It slides smoothly instead of jumping, and it is
hidden in Sharp mode until the game is over. The **≈** button in the top bar
hides or shows it.

## 5. Hints and takeback

After each of your moves the coach card shows a badge and one sentence, e.g.
`Nf3 is a good move.` When the move cost something it also shows
`Loss 120 cp · best Nf3`. This is the hint system: it never suggests a move
before you play, it explains the move you just made.

**↶ Vzít tah zpět** takes back your last move *and* the bot's reply, so it is
your turn again. It is disabled while the engine is thinking and after the game
has ended. **Vzdát partii** resigns; the result is stored as a loss for you.

## 6. Reading the review

When the game is over, **Analyzovat partii** becomes active. Press it: a
progress bar counts the analysed plies, then the review panel opens.

- **Accuracy** — the big number on the left, 0–100 %. It is derived from the
  drop in winning probability, not from raw centipawns; 85+ is a clean game.
- **Subtitle** — accuracy, how many of your moves were graded, average loss in
  centipawns, where the evaluations came from (journal, stored game or
  Stockfish) and whether they were sampled before your moves.
- **Counts** — one pill per badge with how many times it occurred.
- **Graph** — the evaluation curve of the whole game. The upper, lighter half
  is White's side; a line above the middle means White is winning. Click the
  graph to jump to that moment.
- **Arrows** — on the board, green is the best move, red is the move actually
  played, blue-grey is a played move with no recorded alternative (typical for
  imported bot journals).
- **Worst moments** — the five most expensive mistakes. Click a row to jump to
  that ply.
- **← / →** step through the game; **PGN** downloads the game.

You can re-open the review at any time; the report is kept in memory for the
running session.

## 7. Importing a game

The coach can replay games recorded by the companion bot. Point the input in
the **Partie bota** panel at a `.jsonl` journal or a stored `.json` game and
press **Import**. Only files inside the bot's data directories are accepted
(`~/.chess_bot_journals` and `~/.chess_coach_games` by default). Imported
games appear in the list and open read-only: you cannot move, take back or
resign, but the board, move list, review and PGN export work normally. Stored
evaluations are used as they are; Stockfish is started only when the journal
carries none.

The same thing from the terminal:

```bash
COACH_JOURNAL_DIR=~/.chess_bot_journals COACH_DATA_DIR=~/.chess_coach_games \
  python3 coach.py import ~/.chess_bot_journals/demo.done.jsonl
python3 coach.py games
```

## 8. Playing and reviewing in the terminal

```bash
python3 coach.py play --level 4 --player demo          # Czech by default
python3 coach.py play --level 4 --player demo --lang en
COACH_LANG=en python3 coach.py review                  # persistent default
python3 coach.py review --lang cs
```

`play` prints the board, accepts SAN (`Nf3`) or UCI (`g1f3`) and ends on
`quit`; it then analyses and saves the game. `review` opens the latest saved
game (or the file you name). You can keep the language in `COACH_LANG` so you
do not have to repeat `--lang`.

## 9. Keyboard shortcuts

| Key | Where | Action |
|---|---|---|
| ← / → | review panel open | previous / next ply |
| Esc | review panel open | close the review |
| Esc | promotion picker open | cancel the promotion |
| Enter | import path field | start the import |

Pointing devices do the rest: click to select and move, drag to move, click a
graph point or a worst-moment row to jump.
