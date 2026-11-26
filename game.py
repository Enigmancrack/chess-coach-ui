"""One game: board, server-side clock, bot replies and the review worker.

All mutations go through `Game.lock`; engine calls happen while the lock is
held for the player's own move (so the clock stops at the exact moment of the
move), and in the background for the bot and the review.  The HTTP layer only
reads `state()`.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

import chess

import review
import rules
from clock import BLACK, WHITE, Clock
from engine import EngineLike, Line

MODES = ("training", "sharp", "analysis")
MATE_CP = rules.MATE_CP


class Game:
    def __init__(self, gid: str, engine: EngineLike, *, level: int = 8,
                 player: str = "me", color: str = "white", base: int = 600,
                 inc: int = 0, mode: str = "training", fen: str | None = None,
                 now: Callable[[], float] = time.monotonic,
                 play_depth: int | None = None,
                 review_depth: int | None = None) -> None:
        self.gid = gid
        self.engine = engine
        self.player = (player or "me").strip()[:40] or "me"
        self.player_color = chess.BLACK if str(color).lower().startswith("b") else chess.WHITE
        self.my_color = "black" if self.player_color == chess.BLACK else "white"
        self.bot_color = "white" if self.my_color == "black" else "black"
        self.mode = mode if mode in MODES else "training"
        self.level = max(4, min(16, int(level)))
        self.base = max(10, int(base))
        self.inc = max(0, int(inc))
        self.play_depth = play_depth or int(os.environ.get("COACH_DEPTH", "10"))
        self.review_depth = review_depth or int(os.environ.get("COACH_REVIEW_DEPTH", "12"))

        self.board = chess.Board(fen or chess.STARTING_FEN)
        if not self.board.is_valid():
            raise ValueError("neplatná FEN")
        self.start_fen = self.board.fen()
        self.clock = Clock(self.base, self.inc, now=now)
        self.moves: list[dict[str, Any]] = []
        self.records: dict[int, dict[str, Any]] = {}
        self.last_note: dict[str, Any] | None = None
        self.eval_cp = 0
        self.thinking = False
        self.resigned_by: str | None = None
        self.engine_error: str | None = None
        self.created = time.time()
        self.lock = threading.RLock()
        self._bot_thread: threading.Thread | None = None

        self.review_status = "idle"
        self.review_progress = 0
        self.review_total = max(1, len(self.moves))
        self.report: dict[str, Any] | None = None
        self.review_error: str | None = None
        self._review_lock = threading.Lock()

    # ── helpers ────────────────────────────────────────────────────────────
    def _side(self, color: chess.Color) -> str:
        return "white" if color == chess.WHITE else "black"

    def _is_player_turn_locked(self) -> bool:
        return self.board.turn == self.player_color

    def _is_over_locked(self) -> bool:
        if self.resigned_by is not None or self.clock.flagged is not None:
            return True
        return self.board.is_game_over(claim_draw=True)

    def _result_locked(self) -> str | None:
        if self.resigned_by is not None:
            return "0-1" if self.resigned_by == "white" else "1-0"
        if self.clock.flagged is not None:
            return "0-1" if self.clock.flagged == "white" else "1-0"
        if self.board.is_game_over(claim_draw=True):
            return self.board.result(claim_draw=True)
        return None

    def _analyse(self, board: chess.Board, depth: int, multipv: int) -> list[Line]:
        if board.is_game_over(claim_draw=True):
            return []
        try:
            return self.engine.analyse(board, depth=depth, multipv=multipv)
        except Exception as exc:  # engine crash must not kill the game
            self.engine_error = str(exc)
            return []

    def _legal_locked(self) -> dict[str, list[str]]:
        if (self._is_over_locked() or self.thinking
                or not self._is_player_turn_locked()):
            return {}
        return rules.legal_destinations(self.board, self.player_color)

    def _refresh_eval(self) -> None:
        fen = self.board.fen()
        turn = self.board.turn
        lines = self._analyse(self.board.copy(),
                              max(4, min(10, self.play_depth)), 1)
        with self.lock:
            if self.board.fen() != fen:
                return
            cp = lines[0].cp if lines else (-MATE_CP if self.board.is_checkmate() else 0)
            self.eval_cp = rules.white_cp(cp, turn)

    # ── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        # Warm the engine before the clock starts so a cold Stockfish does not
        # eat the first player's time.
        self._refresh_eval()
        with self.lock:
            if self._is_over_locked():
                return
            self.clock.start("white" if self.board.turn == chess.WHITE else "black")
            if self.board.turn != self.player_color:
                self._start_bot_locked()

    def _start_bot_locked(self) -> None:
        if self.thinking or self._is_over_locked():
            return
        self.thinking = True
        self._bot_thread = threading.Thread(target=self._bot_turn, daemon=True,
                                            name=f"bot-{self.gid}")
        self._bot_thread.start()

    def _bot_turn(self) -> None:
        try:
            move = self.engine.play(self.board.copy(), self.level)
        except Exception as exc:
            self.engine_error = str(exc)
            move = None
        with self.lock:
            self.clock.settle()
            if self.clock.flagged is not None or self._is_over_locked():
                self.thinking = False
                self.clock.stop()
                return
            if move is None or move not in self.board.legal_moves:
                move = next(iter(self.board.legal_moves), None)
            if move is None:
                self.thinking = False
                return
            flags = rules.move_flags(self.board, move)
            san = self.board.san(move)
            self.clock.add_increment(self.bot_color)
            self.board.push(move)
            self.moves.append({
                "ply": len(self.board.move_stack),
                "san": san,
                "uci": move.uci(),
                "color": self.bot_color,
                "flags": flags,
            })
            self.thinking = False
            if self._is_over_locked():
                self.clock.stop()
            else:
                self.clock.start(self.my_color)
        self._refresh_eval()

    def wait_bot(self, timeout: float = 10.0) -> bool:
        thread = self._bot_thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    # ── player actions ─────────────────────────────────────────────────────
    def play(self, uci: str) -> dict[str, Any]:
        with self.lock:
            if self._is_over_locked():
                return {"error": "partie už skončila"}
            if self.thinking:
                return {"error": "engine právě přemýšlí"}
            if not self._is_player_turn_locked():
                return {"error": "nejsi na tahu",
                        "turn": self._side(self.board.turn)}
            move = rules.normalise_uci(self.board, uci)
            if move is None:
                return {"error": "nelegální tah", "legal": self._legal_locked()}

            # Stop the player's clock at the moment the move was received.
            self.clock.settle()
            if self.clock.flagged is not None:
                self.clock.stop()
                return {"error": "vypršel čas", "state": self.state()}

            before_board = self.board.copy()
            before_lines = self._analyse(self.board, self.play_depth, 2)
            flags = rules.move_flags(self.board, move)
            san = self.board.san(move)
            self.clock.add_increment(self.my_color)
            self.board.push(move)
            after_lines = self._analyse(self.board, self.play_depth, 1)
            rec = review.evaluate_move(before_board, move, before_lines,
                                       after_lines, len(self.board.move_stack))
            self.moves.append({
                "ply": len(self.board.move_stack),
                "san": san,
                "uci": move.uci(),
                "color": self.my_color,
                "flags": flags,
            })
            self.records[len(self.board.move_stack)] = rec
            self.last_note = rec
            cp = after_lines[0].cp if after_lines else (
                -MATE_CP if self.board.is_checkmate() else 0)
            self.eval_cp = rules.white_cp(cp, self.board.turn)
            if self._is_over_locked():
                self.clock.stop()
            else:
                self.clock.start(self.bot_color)
                self._start_bot_locked()
            return self.state()

    def takeback(self) -> dict[str, Any]:
        with self.lock:
            if self.thinking:
                return {"error": "počkej, engine přemýšlí"}
            if self._is_over_locked():
                return {"error": "partie už skončila"}
            if not any(m["color"] == self.my_color for m in self.moves):
                return {"error": "není co vracet"}

            removed_player = False
            while self.board.move_stack:
                entry = self.moves.pop()
                self.board.pop()
                self.records.pop(entry["ply"], None)
                if entry["color"] == self.my_color:
                    removed_player = True
                if removed_player and self.board.turn == self.player_color:
                    break

            remaining = [self.records[ply] for ply in sorted(self.records)]
            self.last_note = remaining[-1] if remaining else None
            self.resigned_by = None
            self.thinking = False
            self.clock.stop()
            self.clock.start(self.my_color)
        self._refresh_eval()
        return self.state()

    def resign(self) -> dict[str, Any]:
        with self.lock:
            if not self._is_over_locked():
                self.resigned_by = self.my_color
                self.clock.stop()
                self.thinking = False
            return self.state()

    # ── read model ─────────────────────────────────────────────────────────
    def state(self) -> dict[str, Any]:
        with self.lock:
            self.clock.settle()
            over = self._is_over_locked()
            if over:
                self.clock.stop()
            reveal = self.mode != "sharp" or over
            moves: list[dict[str, Any]] = []
            for entry in self.moves:
                item = dict(entry)
                rec = self.records.get(entry["ply"])
                if rec is not None and reveal:
                    item["verdict"] = rec.get("verdict")
                    item["loss"] = rec.get("loss")
                    item["best"] = rec.get("best")
                moves.append(item)

            last_uci = self.moves[-1]["uci"] if self.moves else None
            check = self.board.is_check()
            check_square = None
            if check:
                square = rules.king_square(self.board, self.board.turn)
                if square is not None:
                    check_square = chess.square_name(square)

            return {
                "gid": self.gid,
                "player": self.player,
                "my_color": self.my_color,
                "mode": self.mode,
                "level": self.level,
                "base": self.base,
                "inc": self.inc,
                "time_control": f"{self.base}+{self.inc}",
                "fen": self.board.fen(),
                "start_fen": self.start_fen,
                "turn": self._side(self.board.turn),
                "moves": moves,
                "last_uci": last_uci,
                "last_move": ({"from": last_uci[:2], "to": last_uci[2:4]}
                              if last_uci else None),
                "legal": self._legal_locked(),
                "can_move": bool(self._legal_locked()),
                "thinking": self.thinking,
                "clocks": self.clock.snapshot(),
                "flagged": self.clock.flagged,
                "over": over,
                "result": self._result_locked(),
                "resigned": self.resigned_by,
                "check": check,
                "check_square": check_square,
                "eval_cp": int(self.eval_cp),
                "note": (dict(self.last_note)
                         if reveal and self.last_note is not None else None),
                "engine_error": self.engine_error,
                "review_status": self.review_status,
                "review_progress": self.review_progress,
                "review_total": self.review_total,
                "server_ms": int(time.time() * 1000),
            }

    # ── review / PGN ───────────────────────────────────────────────────────
    def _review_progress(self, done: int, total: int) -> None:
        with self._review_lock:
            self.review_progress = done
            self.review_total = max(1, total)

    def start_review(self) -> dict[str, Any]:
        with self._review_lock:
            if self.review_status == "running":
                return self.review_payload()
            self.review_status = "running"
            self.review_progress = 0
            self.review_total = max(1, len(self.moves))
            self.report = None
            self.review_error = None
            fen = self.start_fen
            ucis = [m["uci"] for m in self.moves]
            color = self.player_color
            depth = self.review_depth
        threading.Thread(target=self._review_worker,
                         args=(fen, ucis, color, depth),
                         daemon=True, name=f"review-{self.gid}").start()
        return self.review_payload()

    def _review_worker(self, fen: str, ucis: list[str],
                       color: chess.Color, depth: int) -> None:
        try:
            report = review.analyse_game(chess.Board(fen), ucis, color,
                                         self.engine, depth=depth,
                                         progress=self._review_progress)
            with self.lock:
                report["player"] = self.player
                report["level"] = self.level
                report["mode"] = self.mode
                report["result"] = self._result_locked() or "*"
                report["time_control"] = f"{self.base}+{self.inc}"
            with self._review_lock:
                self.report = report
                self.review_status = "ready"
                self.review_progress = max(1, len(ucis))
        except Exception as exc:  # pragma: no cover - defensive
            with self._review_lock:
                self.review_status = "error"
                self.review_error = str(exc)

    def review_payload(self) -> dict[str, Any]:
        with self._review_lock:
            total = max(1, self.review_total)
            return {
                "status": self.review_status,
                "progress": round(min(1.0, self.review_progress / total), 3),
                "report": self.report,
                "error": self.review_error,
            }

    def pgn(self) -> str:
        with self.lock:
            result = self._result_locked() or "*"
            white = self.player if self.my_color == "white" else f"Stockfish lvl {self.level}"
            black = self.player if self.my_color == "black" else f"Stockfish lvl {self.level}"
            return review.build_pgn(
                self.start_fen,
                [m["uci"] for m in self.moves],
                result=result,
                white=white,
                black=black,
                time_control=f"{self.base}+{self.inc}",
                mode=self.mode,
            )
