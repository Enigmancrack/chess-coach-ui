"""Move normalisation and legal-destination exposure."""
from __future__ import annotations

import chess

import rules
from game import Game


def test_stray_promotion_letter_on_queen_capture_is_stripped():
    board = chess.Board("3qk3/8/8/8/8/8/8/3QK3 w - - 0 1")
    move = rules.normalise_uci(board, "d1d8q")
    assert move is not None
    assert move.uci() == "d1d8"
    assert board.is_capture(move)


def test_queen_capture_on_eighth_rank_is_legal():
    board = chess.Board("3qk3/8/8/8/8/8/8/3QK3 w - - 0 1")
    move = rules.normalise_uci(board, "d1d8")
    assert move is not None
    assert move.uci() == "d1d8"
    flags = rules.move_flags(board, move)
    assert flags["capture"] is True
    assert flags["check"] is True


def test_pawn_promotion_requires_and_accepts_a_piece():
    board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    queen = rules.normalise_uci(board, "a7a8q")
    knight = rules.normalise_uci(board, "a7a8n")
    assert queen is not None and queen.uci() == "a7a8q"
    assert knight is not None and knight.uci() == "a7a8n"
    # A bare pawn move is completed with a queen, never sent as illegal.
    bare = rules.normalise_uci(board, "a7a8")
    assert bare is not None and bare.uci() == "a7a8q"


def test_illegal_and_malformed_moves():
    board = chess.Board()
    assert rules.normalise_uci(board, "e2e5") is None
    assert rules.normalise_uci(board, "xyz") is None
    assert rules.normalise_uci(board, "e2e4q") is not None   # stray letter stripped
    assert rules.normalise_uci(board, "") is None


def test_legal_map_exists_only_for_the_player_to_move(fake_engine):
    game = Game("moves", fake_engine, color="black")
    fake_engine.block = __import__("threading").Event()
    game.start()
    state = game.state()
    assert state["legal"] == {}
    assert state["thinking"] is True
    fake_engine.block.set()
    assert game.wait_bot()
    state = game.state()
    assert state["legal"], "player is black and should see black destinations"
    for origin in state["legal"]:
        piece = game.board.piece_at(chess.parse_square(origin))
        assert piece is not None and piece.color == chess.BLACK


def test_player_move_is_recorded_and_bot_replies(fake_engine):
    game = Game("play", fake_engine)
    game.start()
    state = game.play("e2e4")
    assert "error" not in state
    assert game.wait_bot()
    state = game.state()
    assert [m["san"] for m in state["moves"]][0] == "e4"
    assert len(state["moves"]) == 2
    assert state["last_move"]["from"] == state["moves"][-1]["uci"][:2]
    assert state["note"] is not None
    assert state["note"]["verdict"] in (
        "best", "good", "inaccuracy", "mistake", "blunder", "book",
    )


def test_illegal_player_move_returns_error_and_legal_map(fake_engine):
    game = Game("illegal", fake_engine)
    game.start()
    out = game.play("e2e5")
    assert "error" in out
    assert "e2" in out["legal"]
