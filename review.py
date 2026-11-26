"""Move classification, accuracy and the post-game review.

The category set follows chess.com: brilliant, great, best, good, book,
inaccuracy, mistake, blunder, miss.  The numbers are deliberately explainable:
a category comes from centipawn loss (clamped, mate-aware), accuracy from the
drop in win probability, and the review stores the full evaluation curve so the
UI can draw it and jump to any ply.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Iterable, List, Sequence

import chess
import chess.pgn

import rules
from engine import EngineLike, Line

MATE_CP = rules.MATE_CP
CATEGORIES = ("brilliant", "great", "best", "good", "book",
              "inaccuracy", "mistake", "blunder", "miss")
CATEGORY_CZ = {
    "brilliant": "brilantní",
    "great": "skvělý",
    "best": "nejlepší",
    "good": "dobrý",
    "book": "teorie",
    "inaccuracy": "nepřesnost",
    "mistake": "chyba",
    "blunder": "hrubka",
    "miss": "promarněná výhra",
}

MODEL_FILE = Path.home() / ".chess_opponent_model.json"
PROFILE_FILE = Path.home() / ".chess_coach_profile.json"
GAMES_DIR = Path.home() / ".chess_coach_games"


def clamp_cp(cp: int, limit: int = 2000) -> int:
    return max(-limit, min(limit, int(cp)))


def win_prob(cp: int) -> float:
    """Logistic win probability for a centipawn advantage (0-1)."""
    return 1.0 / (1.0 + 10 ** (-clamp_cp(cp) / 400.0))


def win_percent(cp: int) -> float:
    """Lichess-style win percentage (0-100), used for accuracy."""
    value = clamp_cp(cp, 2000)
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * value)) - 1.0)


def move_accuracy(loss: int, cp_before: int = 0) -> float:
    """Accuracy of one move from the drop in win probability."""
    if loss <= 0:
        return 100.0
    drop = max(0.0, win_percent(cp_before) - win_percent(cp_before - max(0, loss)))
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))


def accuracy(records: Iterable[dict[str, Any]]) -> float:
    values = [move_accuracy(int(r.get("loss") or 0), int(r.get("eval_before") or 0))
              for r in records]
    return round(sum(values) / len(values), 1) if values else 0.0


def classify(rec: dict[str, Any]) -> str:
    """One label for a played move. Explicit flags win over the loss bands."""
    loss = int(rec.get("loss") or 0)
    if rec.get("brilliant") or (rec.get("sacrifice") and loss <= 25
                                and int(rec.get("eval_after") or 0) >= 150):
        return "brilliant"
    if rec.get("missed_win"):
        return "miss"
    if rec.get("great") or (rec.get("only_move") and loss <= 25):
        return "great"
    if rec.get("book") and loss <= 25:
        return "book"
    if rec.get("uci") and rec.get("uci") == rec.get("best_uci"):
        return "best"
    if loss <= 5:
        return "best"
    if loss <= 30:
        return "good"
    if loss <= 90:
        return "inaccuracy"
    if loss <= 220:
        return "mistake"
    return "blunder"


def coach_sentence(rec: dict[str, Any]) -> str:
    """The one-liner under the badge."""
    san = str(rec.get("san") or "?")
    best = rec.get("best")
    loss = int(rec.get("loss") or 0)
    verdict = rec.get("verdict") or classify(rec)
    better = (f" Lepší bylo {best} (−{loss} cp)."
              if best and best != san and loss > 0 else "")
    if verdict == "brilliant":
        return f"{san} je brilantní oběť — pozice drží."
    if verdict == "great":
        return f"{san} je jediný tah, který drží."
    if verdict == "miss":
        return f"Promarněná výhra: {san}.{better}"
    if verdict == "book":
        return f"{san} je teorie."
    if verdict == "best":
        if best and best != san:
            return f"{san} — stejně dobré jako {best}."
        return f"{san} — přesně podle enginu."
    if verdict == "good":
        return f"{san} je dobrý tah.{better}"
    return f"{san} je {CATEGORY_CZ.get(verdict, verdict)}.{better}"


def evaluate_move(board_before: chess.Board, move: chess.Move,
                  before_lines: Sequence[Line], after_lines: Sequence[Line],
                  ply: int) -> dict[str, Any]:
    """Full record for one move. `after_lines` may be empty on a terminal move."""
    best = before_lines[0] if before_lines else None
    best_cp = int(best.cp) if best else 0
    after_board = board_before.copy()
    after_board.push(move)
    if after_lines:
        after_cp = -int(after_lines[0].cp)
    elif after_board.is_checkmate():
        after_cp = MATE_CP
    else:
        after_cp = 0

    if best and best.uci == move.uci():
        loss = 0
    else:
        loss = max(0, rules.clamp_cp(best_cp) - rules.clamp_cp(after_cp))
    loss = min(2000, loss)
    flags = rules.move_flags(board_before, move)
    only_move = board_before.legal_moves.count() == 1
    missed_win = bool(best and best.mate and best_cp > 0 and after_cp < 800)
    sacrifice = rules.is_sacrifice(after_board, move.to_square,
                                   chess.WHITE if board_before.turn == chess.WHITE
                                   else chess.BLACK)
    rec: dict[str, Any] = {
        "ply": ply,
        "san": board_before.san(move),
        "uci": move.uci(),
        "color": "white" if board_before.turn == chess.WHITE else "black",
        "loss": loss,
        "eval_before": best_cp,
        "eval_after": after_cp,
        "best": best.san if best else None,
        "best_uci": best.uci if best else None,
        "only_move": only_move,
        "book": ply <= 10 and loss <= 20,
        "sacrifice": sacrifice,
        "missed_win": missed_win,
        "capture": flags["capture"],
        "flags": flags,
    }
    rec["verdict"] = classify(rec)
    rec["text"] = coach_sentence(rec)
    return rec


def judge(board: chess.Board, move: chess.Move, engine: EngineLike,
          depth: int = 10, ply: int = 0) -> dict[str, Any]:
    """Classify one move using two engine calls (handy for the terminal)."""
    before = engine.analyse(board, depth=depth, multipv=2)
    after_board = board.copy()
    after_board.push(move)
    after = engine.analyse(after_board, depth=depth, multipv=1)
    return evaluate_move(board, move, before, after, ply)


def _terminal_cp(board: chess.Board) -> int:
    if board.is_checkmate():
        return -MATE_CP          # the side to move is mated
    return 0


def _safe_analyse(board: chess.Board, engine: EngineLike, depth: int,
                  multipv: int) -> list[Line]:
    if board.is_game_over(claim_draw=True):
        return []
    return engine.analyse(board, depth=depth, multipv=multipv)


def analyse_game(start_board: chess.Board, ucis: Sequence[str],
                 player_color: chess.Color, engine: EngineLike,
                 depth: int = 12,
                 progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Analyse a whole game once; n+1 engine calls for n plies.

    The evaluation after move i is the evaluation before move i+1, so each
    position is analysed exactly once.  `evals` is white-perspective.
    """
    board = start_board.copy()
    lines = _safe_analyse(board, engine, depth, 3)
    first_cp = lines[0].cp if lines else _terminal_cp(board)
    evals = [rules.white_cp(first_cp, board.turn)]
    plies: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    total = len(ucis)

    for index, raw in enumerate(ucis):
        try:
            move = chess.Move.from_uci(str(raw))
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        before_board = board.copy()
        san = board.san(move)
        before_lines = lines
        board.push(move)
        after_lines = _safe_analyse(board, engine, depth, 3)
        after_cp = (after_lines[0].cp if after_lines
                    else _terminal_cp(board))
        evals.append(rules.white_cp(after_cp, board.turn))
        rec = evaluate_move(before_board, move, before_lines, after_lines,
                            index + 1)
        is_player = before_board.turn == player_color
        plies.append({
            "ply": index + 1,
            "san": san,
            "uci": move.uci(),
            "color": rec["color"],
            "fen_before": before_board.fen(),
            "fen_after": board.fen(),
            "eval_before": evals[index],
            "eval_after": evals[index + 1],
            "flags": rec["flags"],
            "best": rec["best"],
            "best_uci": rec["best_uci"],
            "verdict": rec["verdict"] if is_player else None,
            "loss": rec["loss"] if is_player else None,
            "text": rec["text"] if is_player else None,
        })
        if is_player:
            records.append(rec)
        lines = after_lines
        if progress is not None:
            progress(index + 1, total)

    report = summarise(records)
    report.update({
        "start_fen": start_board.fen(),
        "player_color": "white" if player_color == chess.WHITE else "black",
        "plies": plies,
        "evals": evals,
        "avg_loss": report["avg_loss"],
    })
    return report


def summarise(records: List[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for rec in records:
        name = rec.get("verdict") or classify(rec)
        counts[name] = counts.get(name, 0) + 1
    worst = sorted(
        (r for r in records if (r.get("verdict") or classify(r))
         in ("mistake", "blunder", "miss")),
        key=lambda r: -int(r.get("loss") or 0),
    )[:5]
    return {
        "moves": len(records),
        "accuracy": accuracy(records),
        "counts": counts,
        "worst": [{
            "ply": r.get("ply"),
            "san": r.get("san"),
            "verdict": r.get("verdict") or classify(r),
            "loss": int(r.get("loss") or 0),
            "best": r.get("best"),
            "best_uci": r.get("best_uci"),
            "uci": r.get("uci"),
        } for r in worst],
        "avg_loss": round(sum(int(r.get("loss") or 0) for r in records)
                          / max(1, len(records)), 1),
    }


def build_pgn(start_fen: str, ucis: Sequence[str], *, result: str = "*",
              white: str = "?", black: str = "?", time_control: str = "-",
              mode: str = "training", date: str | None = None) -> str:
    game = chess.pgn.Game()
    game.setup(chess.Board(start_fen))
    node = game
    for raw in ucis:
        try:
            move = chess.Move.from_uci(str(raw))
        except ValueError:
            break
        if move not in node.board().legal_moves:
            break
        node = node.add_variation(move)
    game.headers["Event"] = "Chess Coach"
    game.headers["Site"] = "local"
    game.headers["Date"] = date or time.strftime("%Y.%m.%d")
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Result"] = result
    game.headers["TimeControl"] = time_control
    game.headers["Mode"] = mode
    return str(game)


# ── optional profile / model glue (kept for the terminal coach) ─────────────

def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def opponent_insight(name: str) -> dict[str, Any]:
    data = _load(MODEL_FILE)
    players = data.get("opponents") if isinstance(data.get("opponents"), dict) else data
    entry = players.get(name) if isinstance(players, dict) else None
    if not isinstance(entry, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("games", "wins", "losses", "draws", "style", "weakness",
                "elo_estimate", "elo_variance"):
        if key in entry:
            out[key] = entry[key]
    return out


def profile_update(name: str, review: dict[str, Any]) -> dict[str, Any]:
    data = _load(PROFILE_FILE)
    profiles = data.setdefault("players", {})
    entry = profiles.setdefault(name, {"games": 0, "accuracy_sum": 0.0,
                                       "blunders": 0, "mistakes": 0})
    entry["games"] = int(entry.get("games", 0)) + 1
    entry["accuracy_sum"] = float(entry.get("accuracy_sum", 0.0)) + review["accuracy"]
    entry["blunders"] = int(entry.get("blunders", 0)) + review["counts"].get("blunder", 0)
    entry["mistakes"] = int(entry.get("mistakes", 0)) + review["counts"].get("mistake", 0)
    entry["last_accuracy"] = review["accuracy"]
    entry["avg_accuracy"] = round(entry["accuracy_sum"] / entry["games"], 1)
    try:
        PROFILE_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass
    return entry


def verdict_sentence(knowledge: dict[str, Any], review: dict[str, Any]) -> str:
    acc = review["accuracy"]
    band = "čistá" if acc >= 85 else "solidní" if acc >= 70 else "volnější"
    parts = [f"Přesnost {acc} % ({band})."]
    est = knowledge.get("elo_estimate")
    if est:
        parts.append(f"Model tě odhaduje na {int(est)} Elo.")
    weak = knowledge.get("weakness")
    if isinstance(weak, str) and weak and weak not in ("unknown", "none"):
        parts.append(f"Známá slabina: {weak.replace('_', ' ')}.")
    if review["counts"].get("blunder", 0) >= 3:
        parts.append("Tři a více hrubek — příště taktika.")
    return " ".join(parts)


def load_games(player: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        files = sorted(GAMES_DIR.glob("*.json"))
    except OSError:
        return out
    for path in files:
        game = _load(path)
        if not game or not isinstance(game.get("moves") or game.get("sans"), list):
            continue
        if player and str(game.get("player") or "") != player:
            continue
        game["_file"] = str(path)
        out.append(game)
    return out


def trends(games: list[dict[str, Any]], window: int = 5) -> dict[str, Any]:
    if not games:
        return {}
    accs = [float((g.get("review") or {}).get("accuracy", 0) or 0) for g in games]
    blunders = [int(((g.get("review") or {}).get("counts") or {}).get("blunder", 0))
                for g in games]
    now_acc = accs[-window:]
    prev_acc = accs[-2 * window:-window]
    out: dict[str, Any] = {
        "games": len(games),
        "accuracy_now": round(sum(now_acc) / len(now_acc), 1),
        "blunders_now": round(sum(blunders[-window:]) / len(blunders[-window:]), 2),
        "best": max(accs), "worst": min(accs),
    }
    if prev_acc:
        out["accuracy_before"] = round(sum(prev_acc) / len(prev_acc), 1)
        out["accuracy_delta"] = round(out["accuracy_now"] - out["accuracy_before"], 1)
    return out


def advice(review: dict[str, Any], window: dict[str, Any] | None = None) -> list[str]:
    tips: list[str] = []
    counts = review.get("counts") or {}
    blunders = int(counts.get("blunder", 0))
    mistakes = int(counts.get("mistake", 0))
    misses = int(counts.get("miss", 0))
    worst = (review.get("worst") or [{}])[0]
    if blunders:
        tips.append(f"{blunders} hrubek: před každým braním nebo šachem si "
                    f"řekni, co soupeř bere. Začni tou nejhorší (tah "
                    f"{worst.get('ply')}, {worst.get('san')} — "
                    f"{worst.get('best')} bylo lepší).")
    if misses:
        tips.append("Měl jsi vynucenou výhru a pustil ji — trénuj matové obrazy.")
    if mistakes >= 2:
        tips.append(f"{mistakes} chyb: zpomal ve střední hře, jeden kandidát.")
    if counts.get("inaccuracy", 0) >= 4:
        tips.append("Hodně malých nepřesností: kontroluj celou desku každý tah.")
    if not tips:
        tips.append("Čistá partie. Zvedni úroveň o jedna a hraj stejně.")
    return tips
