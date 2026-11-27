"""Terminal coach: play against Stockfish and get the review afterwards.

    python3 coach.py play --level 8 --player viktor
    python3 coach.py review            # poslední partie
    python3 coach.py review file.json  # konkrétní
    python3 coach.py import ~/.chess_bot_journals/123.jsonl
    python3 coach.py games             # importované partie

Moves are typed as SAN (Nf3) or UCI (g1f3); `quit` ends the game early.
Every printed line comes from `i18n`; `--lang {cs,en}` or `COACH_LANG` picks
the language (Czech by default).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import chess

import i18n
import importer
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


def _label(verdict: str, lang: str) -> str:
    """Localized display word for a category id (the id itself never changes)."""
    try:
        return i18n.category_label(verdict, lang)
    except KeyError:
        return verdict


def play(level: int, player: str, human_color: chess.Color = chess.WHITE,
         lang: str | None = None) -> int:
    lang = i18n.resolve(lang)
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
                print(i18n.t("cli.opponent_move", lang, san=sans[-1]))

        while not board.is_game_over(claim_draw=True):
            print()
            print(board.unicode(borders=True, orientation=human_color))
            print(i18n.t("cli.prompt", lang), end="", flush=True)
            line = sys.stdin.readline()
            if not line or _is_quit(line):
                print(i18n.t("cli.ended_early", lang))
                break
            move = _parse(board, line)
            if move is None:
                print(i18n.t("cli.unclear", lang))
                continue
            rec = review.judge(board, move, engine, depth=play_depth,
                               ply=len(board.move_stack) + 1, lang=lang)
            sans.append(rec["san"])
            ucis.append(move.uci())
            board.push(move)
            detail = (i18n.t("cli.move_loss", lang, loss=rec["loss"],
                            best=rec["best"]) if rec["loss"] else "")
            print(f"  {_paint(rec['verdict'], ICON.get(rec['verdict'], '?') + ' ' + _label(rec['verdict'], lang))}"
                  f"  {rec['san']}{detail}")
            if board.is_game_over(claim_draw=True):
                break
            reply = engine.play(board, level)
            if reply is None:
                break
            sans.append(board.san(reply))
            ucis.append(reply.uci())
            board.push(reply)
            print(i18n.t("cli.opponent_move", lang, san=sans[-1]))

        result = (board.result(claim_draw=True)
                  if board.is_game_over(claim_draw=True) else "*")
        print(i18n.t("cli.result", lang, result=result, plies=len(ucis),
                     plies_word=i18n.plural("plies", len(ucis), lang)))
        print(i18n.t("cli.analysing", lang), flush=True)
        report = review.analyse_game(chess.Board(), ucis, human_color,
                                     engine, depth=review_depth, lang=lang)
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
        print(i18n.t("cli.saved", lang, path=path))
        print_report(report, player, level, result, lang)
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
                 result: str, lang: str | None = None) -> None:
    lang = i18n.resolve(lang)
    width = 40
    print("\n" + "=" * width)
    print(i18n.t("cli.review_head", lang, player=player, level=level))
    moves = int(report.get("moves") or 0)
    print(i18n.t("cli.review_line", lang, result=result, moves=moves,
                 moves_word=i18n.plural("moves", moves, lang),
                 avg=report.get("avg_loss", 0)))
    print("=" * width)
    acc = float(report.get("accuracy") or 0)
    filled = int(round(acc / 100 * 30))
    bar_color = "\033[92m" if acc >= 85 else "\033[93m" if acc >= 70 else "\033[91m"
    bar = f"{bar_color}{'█' * filled}{OFF}{'░' * (30 - filled)}"
    print(i18n.t("cli.accuracy_bar", lang, accuracy=acc, bar=bar))
    print()
    counts = report.get("counts") or {}
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {_paint(name, (ICON.get(name, '') + ' ' + _label(name, lang)).ljust(16))} {count}")
    worst = report.get("worst") or []
    if worst:
        print(i18n.t("cli.worst_head", lang))
        for w in worst:
            better = (i18n.t("cli.better", lang, best=w["best"])
                      if w.get("best") else "")
            print(i18n.t("cli.worst_line", lang, ply=w.get("ply", 0),
                         san=str(w.get("san")), loss=w.get("loss", 0),
                         verdict=_label(str(w.get("verdict")), lang),
                         better=better))
    knowledge = review.opponent_insight(player)
    print("\n  " + review.verdict_sentence(knowledge, report, lang))
    print("=" * width)
    review.profile_update(player or "me", report)


def review_file(path: Path, lang: str | None = None) -> int:
    lang = i18n.resolve(lang)
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
            print(i18n.t("errors.stockfish_missing", lang, path=STOCKFISH))
            return 2
        engine = StockfishEngine(STOCKFISH)
        try:
            color = chess.BLACK if str(data.get("color")) == "black" else chess.WHITE
            report = review.analyse_game(chess.Board(), [str(u) for u in ucis],
                                         color, engine,
                                         depth=int(os.environ.get(
                                             "COACH_REVIEW_DEPTH", "10")),
                                         lang=lang)
        finally:
            engine.close()
    print_report(report, player, level, result, lang)
    return 0


def _insight_line(insight: dict[str, Any], lang: str | None = None) -> str:
    """One readable line from the bot's (read-only) opponent model entry."""
    if not insight or not insight.get("available"):
        return i18n.t("insight.empty", lang)
    bits: list[str] = []
    elo = insight.get("elo_estimate")
    if elo:
        variance = insight.get("elo_variance")
        bits.append(i18n.t("insight.elo", lang, elo=elo)
                    + (i18n.t("insight.variance", lang, variance=variance)
                       if variance else ""))
    if insight.get("style"):
        bits.append(i18n.t("insight.style", lang, style=insight["style"]))
    if insight.get("weakness"):
        bits.append(i18n.t("insight.weakness", lang,
                           weakness=insight["weakness"]))
    games = insight.get("games")
    if games:
        bits.append(i18n.t("insight.games", lang, count=games,
                           games=i18n.plural("games", games, lang),
                           wins=insight.get("wins", 0),
                           losses=insight.get("losses", 0),
                           draws=insight.get("draws", 0)))
    elif elo:
        bits.append(i18n.t("insight.estimate_only", lang))
    body = ", ".join(bits) if bits else i18n.t("insight.blank", lang)
    return i18n.t("insight.line", lang, body=body)


def print_import(record: dict[str, Any], lang: str | None = None) -> None:
    lang = i18n.resolve(lang)
    width = 46
    report = record.get("report") if isinstance(record.get("report"), dict) else {}
    print("\n" + "=" * width)
    print(i18n.t("cli.import_title", lang,
                 name=Path(str(record.get("source_path") or "?")).name))
    print("=" * width)
    rating = record.get("opponent_rating")
    who = f"{record.get('player')} ({record.get('my_color')})"
    other = record.get("opponent") or i18n.t("common.opponent", lang)
    if rating:
        other = f"{other} ({rating})"
    print(i18n.t("cli.import_who", lang, who=who, other=other))
    print(i18n.t("cli.import_date", lang, date=record.get("date"),
                 time_control=record.get("time_control")))
    moves = len(record.get("ucis") or [])
    line = i18n.t("cli.import_result", lang, result=record.get("result"),
                  label=record.get("result_label"), moves=moves,
                  moves_word=i18n.plural("moves", moves, lang))
    if record.get("termination"):
        line += i18n.t("cli.import_termination", lang,
                       termination=record["termination"])
    print(line)
    if report:
        source = {"journal": i18n.t("cli.source_journal", lang),
                  "review": i18n.t("cli.source_stored", lang),
                  "engine": i18n.t("cli.source_engine", lang)}.get(
                      str(record.get("eval_source")), "?")
        note = (i18n.t("cli.eval_note", lang)
                if report.get("sampling") == "our_turn" else "")
        print(i18n.t("cli.import_review", lang, source=source, note=note,
                     accuracy=float(report.get("accuracy") or 0),
                     avg=report.get("avg_loss", 0)))
        counts = report.get("counts") or {}
        if counts:
            pills = "  ".join(
                f"{_paint(name, ICON.get(name, '') + ' ' + _label(name, lang))} {count}"
                for name, count in sorted(counts.items(), key=lambda kv: -kv[1]))
            print(f"  {pills}")
        for worst in (report.get("worst") or [])[:3]:
            better = (i18n.t("cli.better", lang, best=worst["best"])
                      if worst.get("best") else "")
            print(i18n.t("cli.worst_line", lang, ply=worst.get("ply", 0),
                         san=str(worst.get("san")), loss=worst.get("loss", 0),
                         verdict=_label(str(worst.get("verdict")), lang),
                         better=better))
    else:
        print(i18n.t("cli.import_no_review", lang))
    print(_insight_line(record.get("insight") or {}, lang))
    print("=" * width)


def import_game(raw: str, lang: str | None = None) -> int:
    lang = i18n.resolve(lang)
    try:
        record = importer.import_path(raw)
    except importer.ImportRejected as exc:
        print(i18n.t("cli.rejected", lang, error=exc))
        return 1
    except FileNotFoundError as exc:
        print(i18n.t("cli.error_line", lang, error=exc))
        return 1
    except ValueError as exc:
        print(i18n.t("cli.import_failed", lang, error=exc))
        return 1
    print_import(record, lang)
    print(i18n.t("cli.saved", lang,
                 path=importer.imports_dir() / (str(record["id"]) + ".json")))
    return 0


def list_imports(lang: str | None = None) -> int:
    lang = i18n.resolve(lang)
    rows = importer.list_games()
    if not rows:
        print(i18n.t("cli.no_imports", lang, dir=importer.imports_dir()))
        print(i18n.t("cli.import_hint", lang))
        return 0
    header = (f"  {i18n.t('cli.list_date', lang):<16} "
              f"{i18n.t('cli.list_result', lang):<9} "
              f"{i18n.t('cli.list_moves', lang):>4} "
              f"{i18n.t('cli.list_accuracy', lang):>8}  "
              f"{i18n.t('cli.list_opponent', lang)}")
    print("\n" + header)
    print("  " + "-" * (len(header) - 2))
    for row in rows:
        accuracy = row.get("accuracy")
        acc = f"{float(accuracy):.1f} %" if isinstance(accuracy, (int, float)) else "—"
        other = (row.get("opponent") or "—")[:24]
        print(f"  {str(row.get('date') or '')[:16]:<16} "
              f"{str(row.get('result') or '*'):<9} "
              f"{int(row.get('moves') or 0):>4} {acc:>8}  {other}")
    print(i18n.t("cli.list_footer", lang, count=len(rows),
                 games_word=i18n.plural("games", len(rows), lang),
                 dir=importer.imports_dir()))
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", choices=i18n.LANGS, default=None,
                        help=i18n.t("cli.help_lang"))
    parser = argparse.ArgumentParser(prog="coach", parents=[common])
    sub = parser.add_subparsers(dest="cmd")
    play_cmd = sub.add_parser("play", parents=[common],
                              help=i18n.t("cli.help_play"))
    play_cmd.add_argument("--level", type=int, default=8)
    play_cmd.add_argument("--player", default="me")
    play_cmd.add_argument("--color", choices=("white", "black"), default="white")
    review_cmd = sub.add_parser("review", parents=[common],
                                help=i18n.t("cli.help_review"))
    review_cmd.add_argument("file", nargs="?")
    import_cmd = sub.add_parser("import", parents=[common],
                                help=i18n.t("cli.help_import"))
    import_cmd.add_argument("file", help=i18n.t("cli.help_import_file"))
    sub.add_parser("games", parents=[common], help=i18n.t("cli.help_games"))
    args = parser.parse_args(argv)
    lang = i18n.resolve(args.lang)

    if args.cmd == "review":
        if args.file:
            path = Path(args.file)
        else:
            path = default_store().latest()
        if path is None:
            print(i18n.t("cli.no_saved_game", lang))
            return 1
        if not path.exists():
            print(i18n.t("cli.file_missing", lang, path=path))
            return 1
        return review_file(path, lang)

    if args.cmd == "import":
        return import_game(args.file, lang)

    if args.cmd == "games":
        return list_imports(lang)

    if args.cmd == "play":
        if not Path(STOCKFISH).exists():
            print(i18n.t("errors.stockfish_missing", lang, path=STOCKFISH)
                  + "\n" + i18n.t("errors.env_hint", lang))
            return 2
        color = chess.BLACK if args.color == "black" else chess.WHITE
        return play(max(4, min(16, args.level)), args.player, color, lang)

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(i18n.t("cli.stopped"))
