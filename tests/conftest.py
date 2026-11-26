"""Shared fixtures: a deterministic fake engine and a manual clock."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
import pytest

from engine import Line


class FakeEngine:
    """Legal moves, fixed evaluation, optional block for clock tests."""

    def __init__(self, cp: int = 0) -> None:
        self.cp = cp
        self.calls = 0
        self.block: threading.Event | None = None
        self.fail = False

    def analyse(self, board: chess.Board, depth: int = 10,
                multipv: int = 2) -> list[Line]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("engine down")
        if board.is_game_over(claim_draw=True):
            return []
        moves: Sequence[chess.Move] = sorted(board.legal_moves,
                                             key=lambda move: move.uci())
        return [Line(uci=m.uci(), san=board.san(m), cp=self.cp, mate=False,
                     pv=[m.uci()]) for m in moves[:max(1, multipv)]]

    def play(self, board: chess.Board, level: int = 8) -> chess.Move | None:
        if self.block is not None:
            self.block.wait(5)
        moves = sorted(board.legal_moves, key=lambda move: move.uci())
        return moves[0] if moves else None


class ManualClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def manual_clock() -> ManualClock:
    return ManualClock()
