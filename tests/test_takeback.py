"""Takeback removes the player's move and the reply that followed it."""
from __future__ import annotations

import threading

from game import Game


def test_takeback_white_removes_both_plies(fake_engine):
    game = Game("tb-white", fake_engine)
    game.start()
    game.play("e2e4")
    assert game.wait_bot()
    assert len(game.state()["moves"]) == 2

    state = game.takeback()
    assert "error" not in state
    assert state["moves"] == []
    assert state["turn"] == "white"
    assert "e2" in state["legal"]
    assert state["note"] is None
    assert game.records == {}


def test_takeback_black_keeps_the_bot_opening_move(fake_engine):
    game = Game("tb-black", fake_engine, color="black")
    game.start()
    assert game.wait_bot()
    assert len(game.state()["moves"]) == 1

    game.play("a7a6")
    assert game.wait_bot()
    assert len(game.state()["moves"]) == 3

    state = game.takeback()
    assert len(state["moves"]) == 1
    assert state["turn"] == "black"
    assert "a7" in state["legal"]


def test_takeback_is_refused_while_the_bot_thinks(fake_engine):
    gate = threading.Event()
    fake_engine.block = gate
    game = Game("tb-busy", fake_engine)
    game.start()
    game.play("e2e4")
    out = game.takeback()
    assert "error" in out
    gate.set()
    assert game.wait_bot()


def test_takeback_without_a_player_move(fake_engine):
    game = Game("tb-empty", fake_engine)
    game.start()
    out = game.takeback()
    assert "error" in out
