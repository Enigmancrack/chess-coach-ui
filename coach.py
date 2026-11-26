"""Terminal coach: play against Stockfish and get the review afterwards.

    python3 coach.py play --level 8 --player viktor
    python3 coach.py review            # poslední partie
    python3 coach.py review file.json  # konkrétní

Moves are typed as SAN (Nf3) or UCI (g1f3); `quit` ends the game early.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import chess

import review
import rules
from data import default_store
from engine import DEFAULT_STOCKFISH, StockfishEngine

STOCKFISH: str = os.environ.get("COACH_STOCKFISH") or DEFAULT_STOCKFISH

ICON = {"brilliant": "!!", "great": "!", "best": "*", "good": ".",
        "book": "B", "inaccuracy": "?!", "mistake": "?", "blunder": "??",
        "miss": "X"}
COLOR = {"brilliant": "\033[96m", "great": "\033[94m", "best": "\033[92m",
         "good": "\033[37m", "book": "\033[33m", "inaccuracy": "\033[93m",
         "mistake": "\033[38;5;208m", "blunder": "\033[91m", "miss": "\033[95m"}
OFF = "\033[0m"


def _paint(name: str, text: str) -> str:
    return f"{COLOR.get(name, '')}{text}{OFF}"


def _parse(board: chess.Board, text: str) -> chess.Move | None:
    raw = text.strip()
    if (len(raw) in (4, 5) and raw[0] in "abcdefgh" and raw[1] in "12345678"
            and raw[2] in "abcdefgh" and raw[3] in "12345678"):
        move = rules.normalise_uci(board, raw)
        if move is not None:
            return move
    try:
        return board.parse_san(raw)
    except ValueError:
        return None


def _is_quit(text: str) -> bool:
    return text.strip().lower() in ("quit", "q", "exit", "konec")


def play(level: int, player: str, human_color: chess.Color = chess.WHITE) -> int:
    engine = StockfishEngine(STOCKFISH)
    board = chess.Board()
    sans: list[str] = []
    ucis: list[str] = []
    play_depth = int(os.environ.get("COACH_DEPTH", "8"))
    review_depth = int(os.environ.get("COACH_REVIEW_DEPTH", "10"))
    try:
        if board.turn != human_color:
            reply = engine.play(board, level)
            if reply is not None:
                sans.append(board.san(reply))
                ucis.append(reply.uci())
                board.push(reply)
                print(f"  soupeř: {sans[-1]}")

        while not board.is_game_over(claim_draw=True):
            print()
            print(board.unicode(borders=True, orientation=human_color))
            print("\n  tvůj tah (SAN/UCI), 'quit' ukončí: ", end="", flush=True)
            line = sys.stdin.readline()
            if not line or _is_quit(line):
                print("  konec předčasně")
                break
            move = _parse(board, line)
            if move is None:
                print("  nerozumím / nelegální tah")
                continue
            rec = review.judge(board, move, engine, depth=play_depth,
                               ply=len(board.move_stack) + 1)
            sans.append(rec["san"])
            ucis.append(move.uci())
            board.push(move)
            print(f"  {_paint(rec['verdict'], ICON.get(rec['verdict'], '?') + ' '
                               + rec['verdict'])}  {rec['san']}"
                  + (f"  (−{rec['loss']} cp, lepší {rec['best']})"
                     if rec["loss"] else ""))
            if board.is_game_over(claim_draw=True):
                break
            reply = engine.play(board, level)
            if reply is None:
                break
            sans.append(board.san(reply))
            ucis.append(reply.uci())
            board.push(reply)
            print(f"  soupeř: {sans[-1]}")

        result = (board.result(claim_draw=True)
                  if board.is_game_over(claim_draw=True) else "*")
        print(f"\n  výsledek: {result}   ({len(ucis)} půltahů)")
        print("  analyzuji partii…", flush=True)
        report = review.analyse_game(chess.Board(), ucis, human_color,
                                     engine, depth=review_depth)
        report.update({"player": player, "level": level, "result": result,
                       "color": "white" if human_color else "black"})
        store = default_store()
        path = store.save({
            "player": player,
            "level": level,
            "color": "white" if human_color else "black",
            "result": result,
            "sans": sans,
            "ucis": ucis,
            "when": time.strftime("%Y-%m-%d %H:%M"),
            "review": report,
        })
        print(f"  uloženo: {path}")
        print_report(report, player, level, result)
        return 0
    finally:
        engine.close()


def _ucis_from_sans(sans: list[str]) -> list[str]:
    board = chess.Board()
    out: list[str] = []
    for san in sans:
        try:
            move = board.parse_san(san)
        except ValueError:
            break
        out.append(move.uci())
        board.push(move)
    return out


def print_report(report: dict[str, Any], player: str, level: int | str,
                 result: str) -> None:
    width = 40
    print("\n" + "=" * width)
    print(f"  REVIEW  {player}  vs  engine (lvl {level})")
    moves = int(report.get("moves") or 0)
    word = "tah" if moves == 1 else ("tahy" if 2 <= moves <= 4 else "tahů")
    print(f"  výsledek {result}  ·  {moves} {word}"
          f"  ·  průměrná ztráta {report.get('avg_loss', 0)} cp")
    print("=" * width)
    acc = float(report.get("accuracy") or 0)
    filled = int(round(acc / 100 * 30))
    bar_color = "\033[92m" if acc >= 85 else "\033[93m" if acc >= 70 else "\033[91m"
    print(f"  přesnost {acc} %  {bar_color}{'█' * filled}{OFF}{'░' * (30 - filled)}")
    print()
    counts = report.get("counts") or {}
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {_paint(name, (ICON.get(name, '') + ' ' + name).ljust(16))} {count}")
    worst = report.get("worst") or []
    if worst:
        print("\n  nejhorší momenty:")
        for w in worst:
            better = f" lepší: {w['best']}" if w.get("best") else ""
            print(f"   ply {w.get('ply', 0):>3}  {str(w.get('san')):<6}"
                  f" {str(w.get('verdict')):<11} −{w.get('loss', 0)} cp{better}")
    knowledge = review.opponent_insight(player)
    print("\n  " + review.verdict_sentence(knowledge, report))
    print("=" * width)
    review.profile_update(player or "me", report)


def review_file(path: Path) -> int:
    store = default_store()
    data = store.load(path)
    player = str(data.get("player") or "me")
    result = str(data.get("result") or "*")
    level = data.get("level", "?")
    report = data.get("review")
    if not isinstance(report, dict) or "accuracy" not in report:
        ucis = data.get("ucis")
        if not isinstance(ucis, list):
            sans = data.get("sans")
            ucis = _ucis_from_sans(sans) if isinstance(sans, list) else []
        if not Path(STOCKFISH).exists():
            print(f"Stockfish nenalezen: {STOCKFISH}")
            return 2
        engine = StockfishEngine(STOCKFISH)
        try:
            color = chess.BLACK if str(data.get("color")) == "black" else chess.WHITE
            report = review.analyse_game(chess.Board(), [str(u) for u in ucis],
                                         color, engine,
                                         depth=int(os.environ.get(
                                             "COACH_REVIEW_DEPTH", "10")))
        finally:
            engine.close()
    print_report(report, player, level, result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coach")
    sub = parser.add_subparsers(dest="cmd")
    play_cmd = sub.add_parser("play", help="hrát partii a dostat review")
    play_cmd.add_argument("--level", type=int, default=8)
    play_cmd.add_argument("--player", default="me")
    play_cmd.add_argument("--color", choices=("white", "black"), default="white")
    review_cmd = sub.add_parser("review", help="review uložené partie")
    review_cmd.add_argument("file", nargs="?")
    args = parser.parse_args(argv)

    if args.cmd == "review":
        if args.file:
            path = Path(args.file)
        else:
            path = default_store().latest()
        if path is None:
            print("žádná uložená partie")
            return 1
        if not path.exists():
            print(f"soubor neexistuje: {path}")
            return 1
        return review_file(path)

    if args.cmd == "play":
        if not Path(STOCKFISH).exists():
            print(f"Stockfish nenalezen: {STOCKFISH}\nNastav COACH_STOCKFISH.")
            return 2
        color = chess.BLACK if args.color == "black" else chess.WHITE
        return play(max(4, min(16, args.level)), args.player, color)

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n  ukončeno")
