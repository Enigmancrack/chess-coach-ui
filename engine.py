"""Stockfish adapter.

The UI and the terminal coach talk to this small interface instead of driving
UCI themselves.  One process, one lock: the app is single-user and a second
engine process would only fight for CPU.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Protocol

import chess
import chess.engine

DEFAULT_STOCKFISH = "/home/enigma/projekty/_externi/Stockfish/src/stockfish"
MATE_CP = 10000


@dataclass(slots=True)
class Line:
    uci: str | None
    san: str | None
    cp: int          # from the point of view of the side to move
    mate: bool
    pv: list[str]


class EngineLike(Protocol):
    def analyse(self, board: chess.Board, depth: int = 10,
                multipv: int = 2) -> list[Line]: ...

    def play(self, board: chess.Board, level: int = 8) -> chess.Move | None: ...


def level_limits(level: int) -> tuple[int, chess.engine.Limit]:
    """Level 4-16 -> a weak-but-sane opponent, never bullet-fast."""
    lvl = max(4, min(16, int(level)))
    skill = round((lvl - 4) * 20 / 12)
    depth = max(3, min(12, 2 + lvl // 2))
    return skill, chess.engine.Limit(depth=depth, time=0.35)


class StockfishEngine:
    def __init__(self, path: str | None = None, threads: int = 2,
                 hash_mb: int = 256) -> None:
        self.path = path or os.environ.get("COACH_STOCKFISH") or DEFAULT_STOCKFISH
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.RLock()

    def _get(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            if not os.path.exists(self.path):
                raise FileNotFoundError(f"Stockfish nenalezen: {self.path}")
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        return self._engine

    def analyse(self, board: chess.Board, depth: int = 10,
                multipv: int = 2) -> list[Line]:
        with self._lock:
            engine = self._get()
            try:
                infos = engine.analysis(
                    board,
                    chess.engine.Limit(depth=max(1, int(depth))),
                    multipv=max(1, int(multipv)),
                )
            except chess.engine.EngineTerminatedError:
                self._engine = None
                raise
            lines: list[Line] = []
            for info in infos:
                score = info.get("score")
                if score is None:
                    continue
                pov = score.pov(board.turn)
                cp = int(pov.score(mate_score=MATE_CP) or 0)
                pv = [move.uci() for move in (info.get("pv") or [])]
                san: str | None = None
                if pv:
                    try:
                        san = board.san(chess.Move.from_uci(pv[0]))
                    except ValueError:
                        san = None
                lines.append(Line(uci=pv[0] if pv else None, san=san, cp=cp,
                                  mate=pov.is_mate(), pv=pv))
            return lines

    def play(self, board: chess.Board, level: int = 8) -> chess.Move | None:
        skill, limit = level_limits(level)
        with self._lock:
            engine = self._get()
            engine.configure({"Skill Level": skill, "UCI_LimitStrength": False})
            try:
                result = engine.play(board, limit, info=chess.engine.INFO_NONE)
            except chess.engine.EngineTerminatedError:
                self._engine = None
                raise
            return result.move

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                finally:
                    self._engine = None
