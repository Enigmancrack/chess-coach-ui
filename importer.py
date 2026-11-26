"""Import games the chess bot recorded, without the browser.

Two shapes arrive from the bot:

* ``~/.chess_coach_games/*.json`` — a finished game in this app's own shape
  (``sans``/``ucis`` and optionally a stored ``review``),
* ``~/.chess_bot_journals/*.jsonl`` — one event per line (``game_start``,
  ``our_move``, ``opp_move``, ``game_end`` plus anything the bot adds later).

The journal is the richer source: every move event carries the bot's own
evaluation, so the review can be built from stored numbers and Stockfish is
never started.  Unknown event types are ignored, a malformed line is counted
and skipped, and a journal that begins mid-game (the bot attached after the
opening) is re-anchored on the ``fen`` that ``our_move`` carries — the moves
before it cannot be replayed, so the game simply starts where the journal does.

Nothing here writes outside ``COACH_DATA_DIR/imports``; reads from the bot's
directories are read-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import chess

import review
import rules

JOURNAL_DIR_ENV = "COACH_JOURNAL_DIR"
GAMES_DIR_ENV = "COACH_DATA_DIR"
SOURCE_SUFFIXES = (".json", ".jsonl")
EVAL_KEYS = ("eval_cp", "eval_cp_after", "eval", "cp", "score_cp")
PGN_RESULTS = ("1-0", "0-1", "1/2-1/2")


class ImportRejected(ValueError):
    """The requested path is outside the bot's data directories."""


# ── locations (read at call time so tests can point them at a tmp dir) ──────

def journal_dir() -> Path:
    return Path(os.environ.get(JOURNAL_DIR_ENV) or Path.home() / ".chess_bot_journals")


def games_dir() -> Path:
    return Path(os.environ.get(GAMES_DIR_ENV) or Path.home() / ".chess_coach_games")


def imports_dir() -> Path:
    return games_dir() / "imports"


def allowed_roots() -> tuple[Path, Path]:
    return (journal_dir().resolve(), games_dir().resolve())


def resolve_source(raw: str | Path) -> Path:
    """Resolve `raw` and insist it lives inside one of the bot's directories.

    Symlinks are followed before the check on purpose: a link placed inside an
    allowed directory must not become a way to read `/etc/shadow`.
    """
    text = str(raw or "").strip()
    if not text:
        raise ImportRejected("chybí cesta k partii")
    try:
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ImportRejected(f"cestu nelze přečíst: {exc}") from exc

    for root in allowed_roots():
        if resolved == root or root in resolved.parents:
            break
    else:
        raise ImportRejected(
            "cesta musí ležet v ~/.chess_bot_journals nebo ~/.chess_coach_games")
    if resolved.suffix.lower() not in SOURCE_SUFFIXES:
        raise ImportRejected("podporované jsou jen .json a .jsonl")
    if not resolved.is_file():
        raise FileNotFoundError(f"soubor neexistuje: {resolved}")
    return resolved


# ── small readers ──────────────────────────────────────────────────────────

def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _eval_of(event: dict[str, Any]) -> int | None:
    for key in EVAL_KEYS:
        value = event.get(key)
        if isinstance(value, dict):
            value = value.get("cp", value.get("score"))
        number = _int(value)
        if number is not None:
            return number
    return None


def _color_of(event_type: str, event: dict[str, Any],
              my_color: str | None) -> str | None:
    if event_type == "our_move":
        return my_color
    if event_type == "opp_move":
        if my_color == "white":
            return "black"
        if my_color == "black":
            return "white"
        return None
    side = str(event.get("color") or "").lower()
    return side if side in ("white", "black") else None


def _move_of(board: chess.Board, event: dict[str, Any]) -> chess.Move | None:
    """UCI first (``move``/``uci``), SAN second — the bot writes UCI."""
    for key in ("uci", "move", "san"):
        raw = event.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        move = rules.normalise_uci(board, raw)
        if move is not None:
            return move
        try:
            candidate = board.parse_san(raw.strip())
        except ValueError:
            continue
        if candidate in board.legal_moves:
            return candidate
    return None


def _resync(event: dict[str, Any], move: chess.Move | None,
            board: chess.Board) -> tuple[chess.Board, chess.Move] | None:
    """A journal that starts mid-game carries the position in ``fen``.

    Returns the anchor board and the move read from it, or None when the event
    cannot be trusted (no fen, invalid fen, or a move that is illegal even
    there — a half-written line must not move the game sideways).
    """
    fen = event.get("fen")
    if not isinstance(fen, str) or not fen.strip():
        return None
    try:
        candidate = chess.Board(fen)
    except ValueError:
        return None
    if not candidate.is_valid() or candidate.fen() == board.fen():
        return None
    anchored = move if move is not None and move in candidate.legal_moves \
        else _move_of(candidate, event)
    if anchored is None:
        return None
    return candidate, anchored


def _result_from_label(label: Any, my_color: str | None) -> str | None:
    text = str(label or "").strip().lower()
    if text in PGN_RESULTS:
        return text
    if text in ("draw", "drawn", "remiza", "remíza"):
        return "1/2-1/2"
    if text in ("win", "won", "vyhra", "výhra"):
        if my_color in ("white", "black"):
            return "1-0" if my_color == "white" else "0-1"
    if text in ("loss", "lost", "prohra"):
        if my_color in ("white", "black"):
            return "0-1" if my_color == "white" else "1-0"
    return None


def _result_from_board(board: chess.Board) -> str:
    if board.is_game_over(claim_draw=True):
        return board.result(claim_draw=True)
    return "*"


def _stamp(epoch: Any, path: Path) -> str:
    when = _int(epoch)
    if when is not None and when > 0:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(when))
        except (OverflowError, OSError, ValueError):
            pass
    try:
        return time.strftime("%Y-%m-%d %H:%M",
                             time.localtime(path.stat().st_mtime))
    except OSError:
        return time.strftime("%Y-%m-%d %H:%M")


def _source_id(resolved: Path) -> str:
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()
    return f"imp-{digest[:10]}"


# ── journal parsing ────────────────────────────────────────────────────────

def parse_journal(path: str | Path) -> dict[str, Any]:
    """Turn a JSONL journal into an import record; never raises on bad input."""
    resolved = Path(path)
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"deník nelze přečíst: {exc}") from exc

    start_fen = chess.STARTING_FEN
    my_color: str | None = None
    opponent = ""
    opponent_rating: int | None = None
    time_control = ""
    game_id = ""
    started_at: int | None = None
    termination = ""
    end_result: str | None = None
    final_eval: int | None = None
    our_clock: float | None = None
    their_clock: float | None = None
    lines = bad_lines = ignored = skipped = resets = 0
    truncated = False
    board = chess.Board(start_fen)
    moves: list[dict[str, Any]] = []
    evals_ours: list[int | None] = []
    prev_eval: int | None = None
    our_samples = 0
    repeats = 0
    seen_start = False

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        lines += 1
        try:
            event = json.loads(raw_line)
        except ValueError:
            bad_lines += 1
            continue
        if not isinstance(event, dict):
            bad_lines += 1
            continue
        kind = str(event.get("type") or event.get("event") or "").lower()
        if kind == "game_start":
            if not seen_start:
                seen_start = True
                side = str(event.get("my_color") or "").lower()
                if side in ("white", "black"):
                    my_color = side
                opponent = str(event.get("opp") or event.get("opponent") or "")[:64]
                opponent_rating = _int(event.get("opp_rating"))
                time_control = str(event.get("time_control") or "")[:20]
                game_id = str(event.get("game_id") or "")[:64]
                started_at = _int(event.get("t"))
                fen = event.get("initial_fen")
                if isinstance(fen, str):
                    try:
                        candidate = chess.Board(fen)
                    except ValueError:
                        candidate = None
                    if candidate is not None and candidate.is_valid():
                        board = candidate
                        start_fen = candidate.fen()
            continue
        if kind in ("our_move", "opp_move"):
            if my_color is None:
                # No game_start (or a journal that lost it): infer from the
                # first identifiable move so the side names stay right.
                inferred = _color_of(kind, event, "white") if kind == "our_move" else None
                my_color = inferred or my_color
            move = _move_of(board, event)
            if move is None or move not in board.legal_moves:
                anchored = _resync(event, move, board)
                if anchored is None:
                    skipped += 1
                    continue
                # The journal jumped (it was attached mid-game or a move went
                # missing): keep only the part that can be replayed.
                board, move = anchored
                start_fen = board.fen()
                moves.clear()
                evals_ours.clear()
                prev_eval = None
                resets += 1
            before = board.copy()
            side = _color_of(kind, event, my_color) or (
                "white" if before.turn == chess.WHITE else "black")
            san = before.san(move)
            flags = rules.move_flags(before, move)
            board.push(move)
            moves.append({
                "ply": len(moves) + 1,
                "san": san,
                "uci": move.uci(),
                "color": side,
                "flags": flags,
            })
            sample = _eval_of(event)
            if side == my_color and sample is not None and prev_eval is not None:
                # The bot samples its evaluation before its own move, so an
                # our_move sample repeats the one written by the opponent's
                # move. Counting the repeats tells us how the journal samples.
                our_samples += 1
                if sample == prev_eval:
                    repeats += 1
            if sample is not None:
                prev_eval = sample
            evals_ours.append(sample)
            clock = event.get("our_clock")
            if isinstance(clock, (int, float)) and not isinstance(clock, bool):
                our_clock = float(clock)
            clock = event.get("their_clock")
            if isinstance(clock, (int, float)) and not isinstance(clock, bool):
                their_clock = float(clock)
            if started_at is None:
                started_at = _int(event.get("t"))
            continue
        if kind == "game_end":
            end_result = _result_from_label(
                event.get("pgn_result"), my_color) or _result_from_label(
                event.get("result"), my_color)
            termination = str(event.get("termination") or "")[:24]
            final_eval = _int(event.get("final_eval_cp"))
            continue
        ignored += 1  # explanation/plan/... events are tolerated by design

    if not moves:
        raise ValueError("v deníku nejsou žádné použitelné tahy")

    if len(text) and not text.endswith("\n"):
        # A crash can leave the last line half-written; the counter above
        # already skipped it, this only records why the game may look short.
        truncated = bad_lines > 0 and text.rsplit("\n", 1)[-1].strip() != ""

    my_color = my_color or "white"
    sign = 1 if my_color == "white" else -1
    white_evals: list[int | None] = []
    for value in evals_ours:
        white_evals.append(None if value is None else rules.clamp_cp(value * sign, 10000))
    if final_eval is not None:
        white_evals[-1] = rules.clamp_cp(final_eval * sign, 10000)
    # Our-move samples repeating the previous sample means the journal only
    # measures the position before our own moves (decision points).
    pair_sampled = our_samples >= 1 and repeats >= max(1, int(our_samples * 0.8))

    result = end_result or _result_from_board(board)
    clocks: dict[str, float] = {}
    if our_clock is not None:
        clocks[my_color] = round(our_clock, 1)
    if their_clock is not None:
        clocks["black" if my_color == "white" else "white"] = round(their_clock, 1)
    record: dict[str, Any] = {
        "id": _source_id(resolved.resolve()),
        "source": "journal",
        "source_path": str(resolved.resolve()),
        "game_id": game_id,
        "player": "bot",
        "my_color": my_color,
        "opponent": opponent,
        "opponent_rating": opponent_rating,
        "time_control": time_control or "-",
        "result": result,
        "result_label": ("win" if result == ("1-0" if my_color == "white" else "0-1")
                         else "loss" if result in ("1-0", "0-1")
                         else "draw" if result == "1/2-1/2" else "*"),
        "termination": termination,
        "start_fen": start_fen,
        "moves": moves,
        "clocks": clocks,
        "ucis": [move["uci"] for move in moves],
        "sans": [move["san"] for move in moves],
        "evals_white": white_evals,
        "pair_sampled": pair_sampled,
        "date": _stamp(started_at, resolved),
        "parse": {
            "lines": lines,
            "bad_lines": bad_lines,
            "ignored": ignored,
            "skipped": skipped,
            "resets": resets,
            "truncated": truncated,
        },
    }
    with_report(record)
    return record


def with_report(record: dict[str, Any]) -> dict[str, Any]:
    """Fill `evals`/`report`/`accuracy` from the evals the bot already stored."""
    stored = record.get("evals_white")
    player_color = chess.BLACK if record.get("my_color") == "black" else chess.WHITE
    if not isinstance(stored, list) or not stored:
        record.setdefault("evals", None)
        record["eval_source"] = "none"
        record["report"] = None
        record["accuracy"] = None
        record["evals_filled"] = 0
        return record

    known = [value for value in stored if isinstance(value, int)]
    if not known:
        record["evals"] = None
        record["eval_source"] = "none"
        record["report"] = None
        record["accuracy"] = None
        record["evals_filled"] = 0
        return record

    # A missing sample keeps the last known evaluation (a hole in the journal,
    # not a new fact); the count is surfaced so the UI can say so.
    filled: list[int] = []
    last = known[0]
    missing = 0
    for value in stored:
        if isinstance(value, int):
            last = value
        else:
            missing += 1
        filled.append(last)
    evals = [filled[0], *filled]
    report = review.report_from_evals(record["start_fen"], record["ucis"],
                                      player_color, evals,
                                      pair_sampled=bool(record.get("pair_sampled")))
    report["eval_source"] = "journal"
    report["player"] = record.get("player") or "bot"
    report["result"] = record.get("result") or "*"
    report["time_control"] = record.get("time_control") or "-"
    report["opponent"] = record.get("opponent") or ""
    record["evals"] = evals
    record["eval_source"] = "journal"
    record["evals_filled"] = missing
    record["report"] = report
    record["accuracy"] = report.get("accuracy")
    return record


# ── game-JSON parsing ──────────────────────────────────────────────────────

def _ucis_from(data: dict[str, Any], start_fen: str) -> list[str]:
    raw: Sequence[Any] = ()
    for key in ("ucis", "moves"):
        value = data.get(key)
        if isinstance(value, list) and value:
            raw = value
            break
    else:
        value = data.get("sans")
        raw = value if isinstance(value, list) else ()
    board = chess.Board(start_fen)
    out: list[str] = []
    for item in raw:
        text = item.get("uci") if isinstance(item, dict) else item
        move = _move_of(board, {"uci": text, "san": text}) if text else None
        if move is None:
            break
        out.append(move.uci())
        board.push(move)
    return out


def parse_game_json(path: str | Path) -> dict[str, Any]:
    """Import one stored game JSON; reuse its review when it carries evals."""
    resolved = Path(path)
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"partii nelze přečíst: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("soubor neobsahuje objekt partie")

    start_fen = str(data.get("start_fen") or data.get("fen") or chess.STARTING_FEN)
    try:
        if not chess.Board(start_fen).is_valid():
            start_fen = chess.STARTING_FEN
    except ValueError:
        start_fen = chess.STARTING_FEN
    ucis = _ucis_from(data, start_fen)
    if not ucis:
        raise ValueError("v souboru nejsou žádné použitelné tahy")

    board = chess.Board(start_fen)
    moves: list[dict[str, Any]] = []
    for index, raw in enumerate(ucis):
        move = chess.Move.from_uci(raw)
        before = board.copy()
        flags = rules.move_flags(before, move)
        moves.append({
            "ply": index + 1,
            "san": before.san(move),
            "uci": raw,
            "color": "white" if before.turn == chess.WHITE else "black",
            "flags": flags,
        })
        board.push(move)
    sans = [move["san"] for move in moves]

    stored_raw = data.get("review")
    stored: dict[str, Any] | None = (dict(stored_raw)
                                     if isinstance(stored_raw, dict) else None)
    color = str(data.get("color") or "").lower()
    if color not in ("white", "black"):
        color = str(data.get("my_color") or "").lower()
    if color not in ("white", "black"):
        color = "white"
    base = _int(data.get("base"))
    time_control = data.get("time_control")
    if not isinstance(time_control, str) or not time_control:
        time_control = f"{base}+{_int(data.get('inc')) or 0}" if base else "-"

    record: dict[str, Any] = {
        "id": _source_id(resolved.resolve()),
        "source": "game",
        "source_path": str(resolved.resolve()),
        "game_id": "",
        "player": str(data.get("player") or "me")[:40],
        "my_color": color,
        "opponent": str(data.get("opponent") or "")[:64],
        "opponent_rating": _int(data.get("opponent_rating")),
        "time_control": time_control[:20],
        "result": _result_from_label(data.get("result"), color)
        or _result_from_board(board),
        "result_label": str(data.get("result") or "*")[:16],
        "termination": "",
        "start_fen": start_fen,
        "moves": moves,
        "ucis": ucis,
        "sans": sans,
        "evals_ours": None,
        "date": str(data.get("when") or _stamp(None, resolved))[:16],
        "parse": {"lines": 1, "bad_lines": 0, "ignored": 0, "skipped": 0,
                  "resets": 0, "truncated": False},
    }
    report: dict[str, Any] | None = None
    if (stored is not None
            and isinstance(stored.get("plies"), list)
            and isinstance(stored.get("evals"), list)
            and "accuracy" in stored):
        report = dict(stored)
    if report is not None:
        report.setdefault("player", record["player"])
        report.setdefault("result", record["result"])
        report.setdefault("time_control", record["time_control"])
        report.setdefault("eval_source", "review")
        record["report"] = report
        record["evals"] = list(report["evals"])
        record["eval_source"] = "review"
        record["accuracy"] = report.get("accuracy")
        record["evals_filled"] = 0
    else:
        record["evals"] = None
        record["eval_source"] = "none"
        record["report"] = None
        record["accuracy"] = None
        record["evals_filled"] = 0
    return record


# ── entry points ───────────────────────────────────────────────────────────

def parse(path: str | Path) -> dict[str, Any]:
    """Parse a journal or a game JSON; the suffix decides."""
    resolved = Path(path)
    if resolved.suffix.lower() == ".jsonl":
        return parse_journal(resolved)
    return parse_game_json(resolved)


def import_path(raw: str | Path) -> dict[str, Any]:
    """Guard the path, parse it, attach the read-only model insight, persist."""
    resolved = resolve_source(raw)
    record = parse(resolved)
    record["imported_at"] = time.strftime("%Y-%m-%d %H:%M")
    record["insight"] = review.opponent_insight(record.get("opponent") or "")
    save(record)
    return record


def save(record: dict[str, Any]) -> Path:
    directory = imports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def get(game_id: str) -> dict[str, Any] | None:
    if not game_id or "/" in game_id or "\\" in game_id or ".." in game_id:
        return None
    path = imports_dir() / f"{game_id}.json"
    if path.suffix != ".json" or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def summary(record: dict[str, Any]) -> dict[str, Any]:
    """The listing row: enough to render a game card, no move data."""
    report_raw = record.get("report")
    report: dict[str, Any] = report_raw if isinstance(report_raw, dict) else {}
    return {
        "id": record.get("id"),
        "source": record.get("source"),
        "source_path": record.get("source_path"),
        "player": record.get("player"),
        "my_color": record.get("my_color"),
        "opponent": record.get("opponent") or "",
        "opponent_rating": record.get("opponent_rating"),
        "result": record.get("result") or "*",
        "result_label": record.get("result_label") or "*",
        "date": record.get("date") or "",
        "imported_at": record.get("imported_at") or "",
        "time_control": record.get("time_control") or "-",
        "moves": len(record.get("ucis") or []),
        "accuracy": record.get("accuracy"),
        "eval_source": record.get("eval_source") or "none",
        "counts": report.get("counts") or {},
    }


def list_games() -> list[dict[str, Any]]:
    """Newest first; unreadable files are skipped, never fatal."""
    rows: list[dict[str, Any]] = []
    try:
        files: Iterable[Path] = sorted(imports_dir().glob("*.json"))
    except OSError:
        return rows
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("id"):
            rows.append(summary(data))
    rows.sort(key=lambda row: (row.get("date") or "", row.get("imported_at") or ""),
              reverse=True)
    return rows
