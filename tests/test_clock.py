"""Server-authoritative clock: settlement, increment and flag fall."""
from __future__ import annotations

import threading

from game import Game


def test_clock_charges_the_side_to_move(fake_engine, manual_clock):
    game = Game("clock", fake_engine, base=60, now=manual_clock)
    game.start()
    manual_clock.advance(5)
    state = game.state()
    assert abs(state["clocks"]["white"] - 55) < 0.01
    assert state["clocks"]["black"] == 60


def test_increment_is_added_to_the_mover_and_the_bot_clock_drains(fake_engine,
                                                                 manual_clock):
    gate = threading.Event()
    fake_engine.block = gate
    game = Game("increment", fake_engine, base=60, inc=2, now=manual_clock)
    game.start()
    manual_clock.advance(5)

    state = game.play("e2e4")
    assert "error" not in state
    # 60 - 5 spent + 2 increment
    assert abs(state["clocks"]["white"] - 57) < 0.01
    assert state["thinking"] is True

    manual_clock.advance(4)
    gate.set()
    assert game.wait_bot()
    state = game.state()
    # Bot spent 4 of its own time and got the increment.
    assert abs(state["clocks"]["black"] - 58) < 0.01
    assert abs(state["clocks"]["white"] - 57) < 0.01


def test_flag_fall_ends_the_game_and_reports_the_winner(fake_engine, manual_clock):
    game = Game("flag", fake_engine, base=10, now=manual_clock)
    game.start()
    manual_clock.advance(11)
    state = game.state()
    assert state["over"] is True
    assert state["flagged"] == "white"
    assert state["result"] == "0-1"
    assert state["clocks"]["white"] == 0
    assert state["legal"] == {}


def test_bot_can_flag_while_thinking(fake_engine, manual_clock):
    gate = threading.Event()
    fake_engine.block = gate
    game = Game("botflag", fake_engine, base=10, now=manual_clock)
    game.start()
    game.play("e2e4")
    manual_clock.advance(11)
    gate.set()
    assert game.wait_bot()
    state = game.state()
    assert state["over"] is True
    assert state["flagged"] == "black"
    assert state["result"] == "1-0"
    assert len(state["moves"]) == 1, "the bot's late move must be discarded"
