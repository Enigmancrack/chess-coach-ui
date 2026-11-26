"""Classification, accuracy, full-game analysis and PGN."""
from __future__ import annotations

import chess

import review


def test_classification_bands_and_special_cases():
    assert review.classify({"loss": 0, "uci": "e2e4", "best_uci": "e2e4"}) == "best"
    assert review.classify({"loss": 20, "uci": "e2e4", "best_uci": "d2d4"}) == "good"
    assert review.classify({"loss": 60, "uci": "e2e4", "best_uci": "d2d4"}) == "inaccuracy"
    assert review.classify({"loss": 150, "uci": "e2e4", "best_uci": "d2d4"}) == "mistake"
    assert review.classify({"loss": 400, "uci": "e2e4", "best_uci": "d2d4"}) == "blunder"
    assert review.classify({"loss": 0, "only_move": True,
                            "uci": "e2e4", "best_uci": "e2e4"}) == "great"
    assert review.classify({"loss": 0, "book": True, "ply": 3,
                            "uci": "e2e4", "best_uci": "e2e4"}) == "book"
    assert review.classify({"loss": 700, "missed_win": True}) == "miss"
    assert review.classify({"loss": 10, "sacrifice": True, "eval_after": 300,
                            "uci": "e2e4", "best_uci": "e2e4"}) == "brilliant"


def test_accuracy_is_100_for_zero_loss_and_falls_with_losses():
    assert review.move_accuracy(0, 0) == 100.0
    assert review.move_accuracy(0, 500) == 100.0
    assert review.move_accuracy(100, 0) < 80
    assert review.move_accuracy(1000, 0) < 10
    records = [{"loss": 0, "eval_before": 0}, {"loss": 0, "eval_before": 0}]
    assert review.accuracy(records) == 100.0
    assert review.accuracy([]) == 0.0


def test_loss_is_higher_in_a_quiet_position_than_in_a_won_one():
    quiet = review.move_accuracy(150, 0)
    winning = review.move_accuracy(150, 700)
    assert winning > quiet


def test_summarise_counts_and_worst_order():
    records = [
        {"ply": 1, "san": "e4", "verdict": "best", "loss": 0, "best": "e4"},
        {"ply": 3, "san": "Qh5", "verdict": "blunder", "loss": 500, "best": "Nf3"},
        {"ply": 5, "san": "Bc4", "verdict": "mistake", "loss": 120, "best": "d4"},
        {"ply": 7, "san": "Nf3", "verdict": "blunder", "loss": 800, "best": "e5"},
    ]
    summary = review.summarise(records)
    assert summary["moves"] == 4
    assert summary["counts"] == {"best": 1, "blunder": 2, "mistake": 1}
    assert summary["avg_loss"] == 355.0
    assert [w["ply"] for w in summary["worst"]] == [7, 3, 5]


def test_analyse_game_builds_plies_evals_and_player_only_records(fake_engine):
    board = chess.Board()
    report = review.analyse_game(board, ["e2e4", "a7a6"], chess.WHITE,
                                 fake_engine, depth=6)
    assert report["moves"] == 1
    assert report["accuracy"] == 100.0
    assert report["counts"] == {"book": 1}
    assert len(report["plies"]) == 2
    assert len(report["evals"]) == 3
    assert report["plies"][0]["verdict"] == "book"
    assert report["plies"][1]["verdict"] is None
    assert report["plies"][0]["best_uci"] is not None
    assert report["plies"][0]["fen_after"] != report["start_fen"]


def test_analyse_game_stops_on_an_unknown_uci(fake_engine):
    report = review.analyse_game(chess.Board(), ["e2e4", "zzzz"], chess.WHITE,
                                 fake_engine, depth=4)
    assert len(report["plies"]) == 1


def test_pgn_export_and_headers():
    pgn = review.build_pgn(chess.STARTING_FEN, ["e2e4", "e7e5"],
                           result="1-0", white="viktor", black="Stockfish",
                           time_control="300+0")
    assert "1. e4 e5" in pgn
    assert '[White "viktor"]' in pgn
    assert '[Result "1-0"]' in pgn
    assert '[TimeControl "300+0"]' in pgn
