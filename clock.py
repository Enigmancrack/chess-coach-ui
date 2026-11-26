"""Server-authoritative chess clock.

The clock owns the truth: it remembers when the side to move started thinking
and charges exactly that side when asked.  A polling client only interpolates
between snapshots and always re-syncs from the numbers returned here.

`now` is injectable so the tests can move time without sleeping.
"""
from __future__ import annotations

import time
from typing import Callable

WHITE = "white"
BLACK = "black"
SIDES = (WHITE, BLACK)


class Clock:
    def __init__(self, base: float, increment: float = 0.0,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.base = max(1.0, float(base))
        self.increment = max(0.0, float(increment))
        self.remaining: dict[str, float] = {WHITE: self.base, BLACK: self.base}
        self.running: str | None = None
        self.since: float = now()
        self.flagged: str | None = None
        self._now = now

    def _clock(self) -> float:
        return float(self._now())

    def settle(self) -> None:
        """Charge the running side up to *now* and detect a flag fall."""
        if self.running is None:
            return
        moment = self._clock()
        spent = max(0.0, moment - self.since)
        self.since = moment
        side = self.running
        self.remaining[side] = max(0.0, self.remaining[side] - spent)
        if self.remaining[side] <= 0.0:
            self.remaining[side] = 0.0
            self.flagged = side
            self.running = None

    def start(self, side: str) -> None:
        if side not in SIDES:
            raise ValueError(f"unknown side: {side}")
        self.settle()
        if self.flagged is not None:
            return
        self.running = side
        self.since = self._clock()

    def stop(self) -> None:
        self.settle()
        self.running = None

    def add_increment(self, side: str) -> None:
        if side not in SIDES:
            raise ValueError(f"unknown side: {side}")
        self.remaining[side] += self.increment

    def snapshot(self) -> dict[str, float]:
        self.settle()
        return {side: round(self.remaining[side], 3) for side in SIDES}

    def is_out(self, side: str) -> bool:
        self.settle()
        return self.remaining[side] <= 0.0

    @property
    def over(self) -> bool:
        return self.flagged is not None
