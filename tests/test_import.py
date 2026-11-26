"""Importing the bot's games: journals, path guard, stored review, listing."""
from __future__ import annotations

import json
import time
from pathlib import Path

import chess
import pytest

import game
import importer
import review


def _journal(path: Path, events: list[dict | str], *,
             trailing: bool = True) -> Path:
    lines = [event if isinstance(event, str) else json.dumps(event)
             for event in events]
    text = "\n".join(lines) + ("\n" if trailing else "")
    path.write_text(text, encoding="utf-8")
    return path


def _start(my_color: str = "white") -> dict:
    return {"type": "game_start", "game_id": "42", "my_color": my_color,
            "opp": "player_abc123", "opp_rating": 800, "time_control": "5|2",
            "initial_clock": 300.0, "initial_fen": chess.STARTING_FEN,
            "t": 1_700_000_000.0}


def _our(ply: int, uci: str | None, san: str | None, ev: int | None,
         fen: str | None = None) -> dict:
    event = {"type": "our_move", "ply": ply, "move": uci, "san": san,
             "eval_cp": ev, "our_clock": 290.0, "their_clock": 295.0}
    if fen:
        event["fen"] = fen
    return event


def _opp(ply: int, uci: str, san: str, ev: int | None) -> dict:
    return {"type": "opp_move", "ply": ply, "move": uci, "san": san,
            "eval_cp_after": ev, "our_clock": 288.0, "their_clock": 292.0}


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    journals = tmp_path / "journals"
    coach = tmp_path / "coach"
    journals.mkdir()
    coach.mkdir()
    monkeypatch.setenv("COACH_JOURNAL_DIR", str(journals))
    monkeypatch.setenv("COACH_DATA_DIR", str(coach))
    monkeypatch.setenv("COACH_MODEL_FILE", str(tmp_path / "model.json"))
    return journals, coach


def test_journal_happy_path_maps_moves_evals_and_result(dirs):
    journals, _ = dirs
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    fen_before_nf3 = board.fen()
    path = _journal(journals / "42.done.jsonl", [
        _start(),
        _our(1, "e2e4", "e4", 20, fen=chess.STARTING_FEN),
        _opp(1, "e7e5", "e5", 20),
        _our(2, "g1f3", "Nf3", 20, fen=fen_before_nf3),
        _opp(2, "b8c6", "Nc6", 10),
        {"type": "game_end", "result": "win", "pgn_result": "1-0",
         "final_eval_cp": 300, "termination": "checkmate",
         "move_count": 4},
    ])
    record = importer.parse_journal(path)

    assert record["my_color"] == "white"
    assert record["opponent"] == "player_abc123"
    assert record["opponent_rating"] == 800
    assert record["time_control"] == "5|2"
    assert record["result"] == "1-0"
    assert record["result_label"] == "win"
    assert record["termination"] == "checkmate"
    assert record["sans"] == ["e4", "e5", "Nf3", "Nc6"]
    assert record["moves"][0]["color"] == "white"
    assert record["moves"][1]["color"] == "black"
    assert record["moves"][2]["flags"]["check"] is False
    assert record["clocks"] == {"white": 288.0, "black": 292.0}
    assert record["evals_white"][0] == 20
    assert record["accuracy"] is not None
    assert record["report"]["plies"][2]["san"] == "Nf3"
    assert record["parse"]["bad_lines"] == 0


def test_journal_starting_mid_game_is_reanchored(dirs):
    journals, _ = dirs
    board = chess.Board()
    for san in ("e4", "e5", "Nf3", "Nc6"):
        board.push_san(san)
    path = _journal(journals / "mid.jsonl", [
        _start(),
        _our(3, "f1b5", "Bb5", 15, fen=board.fen()),
    ])
    record = importer.parse_journal(path)
    # Only the replayable tail is kept, anchored on the fen the journal gives.
    assert record["sans"] == ["Bb5"]
    assert record["start_fen"] == board.fen()
    assert record["parse"]["resets"] == 1


def test_journal_tolerates_unknown_events_and_bad_lines(dirs):
    journals, _ = dirs
    path = _journal(journals / "noise.jsonl", [
        _start("black"),
        {"type": "explanation", "text": "protože centrum"},
        {"type": "plan", "target": "rozvinout figur"},
        _opp(0, "e2e4", "e4", 12),
        _our(1, None, None, None),                 # move the bot could not read
        _our(1, "c7c5", "c5", 12),
        '{"type": "our_move", "ply": 2, "mov',     # truncated mid-write
    ], trailing=False)
    record = importer.parse_journal(path)
    assert record["parse"]["ignored"] == 2
    assert record["parse"]["bad_lines"] == 1
    assert record["parse"]["truncated"] is True
    assert record["parse"]["skipped"] >= 1
    assert record["sans"] == ["e4", "c5"]
    assert record["my_color"] == "black"
    assert record["moves"][1]["color"] == "black"


def test_journal_without_moves_is_rejected(dirs):
    journals, _ = dirs
    path = _journal(journals / "empty.jsonl", [_start()])
    with pytest.raises(ValueError):
        importer.parse_journal(path)


def test_import_path_guard_rejects_escape_and_foreign_suffix(dirs, tmp_path):
    journals, coach = dirs
    inside = _journal(journals / "ok.jsonl", [_start(),
                                             _our(0, "e2e4", "e4", 5)])
    assert importer.resolve_source(inside) == inside.resolve()
    assert importer.resolve_source(str(inside)) == inside.resolve()

    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source(outside)
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source("/etc/passwd")
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source(journals / ".." / "outside.jsonl")
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source("")

    text = journals / "note.txt"
    text.write_text("x", encoding="utf-8")
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source(text)

    link = journals / "link.jsonl"
    try:
        link.symlink_to(outside)
    except OSError:  # pragma: no cover - filesystem without symlinks
        return
    with pytest.raises(importer.ImportRejected):
        importer.resolve_source(link)

    # A game JSON under the coach directory is allowed too.
    stored = coach / "20260101-000000-abc.json"
    stored.write_text(json.dumps({"player": "me", "sans": ["e4"]}),
                      encoding="utf-8")
    assert importer.resolve_source(stored) == stored.resolve()


def test_review_from_stored_evals_needs_no_engine(dirs):
    journals, _ = dirs

    class ExplodingEngine:
        def analyse(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the engine must not be asked for an analysis")

        def play(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("no play in an imported game")

    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    fen_before = board.fen()
    path = _journal(journals / "evals.jsonl", [
        _start(), _our(1, "e2e4", "e4", 30, fen=chess.STARTING_FEN),
        _opp(1, "e7e5", "e5", 30), _our(2, "g1f3", "Nf3", 30,
                                        fen=fen_before),
        _opp(2, "b8c6", "Nc6", 0),
        {"type": "game_end", "result": "draw", "pgn_result": "1/2-1/2"},
    ])
    record = importer.import_path(path)
    imported = game.ImportedGame(record, ExplodingEngine())

    payload = imported.start_review()
    assert payload["status"] == "ready"
    report = payload["report"]
    assert report is not None
    assert report["eval_source"] == "journal"
    assert report["sampling"] == "our_turn"
    assert [ply["san"] for ply in report["plies"]] == ["e4", "e5", "Nf3", "Nc6"]
    assert report["plies"][2]["verdict"] is not None
    assert report["plies"][1]["verdict"] is None  # opponent moves stay blank
    assert report["evals"][0] == 30
    assert report["plies"][2]["best_uci"] is None

    state = imported.state()
    assert state["imported"] is True
    assert state["over"] is True
    assert state["result"] == "1/2-1/2"
    assert state["can_move"] is False
    assert len(state["moves"]) == 4
    assert "error" in imported.play("e2e4")
    assert "error" in imported.takeback()
    assert "error" in imported.resign()
    assert "e4" in imported.pgn()


def test_review_falls_back_to_the_engine_without_stored_evals(dirs, fake_engine):
    journals, _ = dirs
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    path = _journal(journals / "plain.jsonl", [
        _start(), _our(1, "e2e4", "e4", None, fen=chess.STARTING_FEN),
        _opp(1, "e7e5", "e5", None),
        _our(2, "g1f3", "Nf3", None, fen=board.fen()),
    ])
    record = importer.parse_journal(path)
    assert record["report"] is None
    assert record["eval_source"] == "none"
    imported = game.ImportedGame(record, fake_engine)
    assert imported.review_status == "idle"
    imported.start_review()
    deadline = time.time() + 5
    while imported.review_status == "running" and time.time() < deadline:
        time.sleep(0.01)
    assert imported.review_status == "ready"
    payload = imported.review_payload()
    assert payload["report"] is not None
    assert payload["report"]["eval_source"] == "engine"
    assert payload["report"]["moves"] == 2
    assert fake_engine.calls > 0


def test_import_then_list_games_with_summary(dirs):
    journals, _ = dirs
    path = _journal(journals / "list.jsonl", [
        _start(), _our(1, "e2e4", "e4", 10, fen=chess.STARTING_FEN),
        _opp(1, "e7e5", "e5", 10),
        {"type": "game_end", "result": "loss", "pgn_result": "0-1"},
    ])
    record = importer.import_path(path)
    saved = importer.imports_dir() / f"{record['id']}.json"
    assert saved.is_file()

    rows = importer.list_games()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == record["id"]
    assert row["source"] == "journal"
    assert row["result"] == "0-1"
    assert row["moves"] == 2
    assert row["opponent"] == "player_abc123"
    assert row["accuracy"] is not None
    assert row["eval_source"] == "journal"
    assert "plies" not in row  # the listing never ships move data
    stored_record = importer.get(record["id"])
    assert stored_record is not None
    assert stored_record["id"] == record["id"]
    assert importer.get("../etc/passwd") is None
    assert importer.get("nope") is None


def test_game_json_import_uses_the_stored_review(dirs):
    journals, coach = dirs
    board = chess.Board()
    ucis = []
    for san in ("e4", "e5"):
        board.push_san(san)
        ucis.append(board.peek().uci())
    stored = review.report_from_evals(chess.STARTING_FEN, ucis, chess.WHITE,
                                      [0, 20, 10])
    path = coach / "20260101-000000-abc.json"
    path.write_text(json.dumps({
        "player": "viktor", "level": 4, "result": "1-0",
        "sans": ["e4", "e5"], "ucis": ucis, "when": "2026-01-01 00:00",
        "review": stored,
    }), encoding="utf-8")
    record = importer.import_path(path)
    assert record["source"] == "game"
    assert record["result"] == "1-0"
    assert record["eval_source"] == "review"
    assert record["report"]["accuracy"] == stored["accuracy"]
    assert record["sans"] == ["e4", "e5"]
    assert importer.list_games()[0]["id"] == record["id"]


def test_opponent_insight_is_read_only_and_reduced(dirs, tmp_path):
    _, _ = dirs
    model = tmp_path / "model.json"
    model.write_text(json.dumps({"opponents": {"player_abc123": {
        "games": 7, "wins": 4, "losses": 2, "draws": 1,
        "elo_estimate": 910, "elo_variance": 80,
        "style_scores": {"aggressive": 0.0, "positional": 0.4},
        "weaknesses": {"blunders_under_pressure": 0, "weak_endgame": 3},
    }}}), encoding="utf-8")
    before = model.read_bytes()
    insight = review.opponent_insight("player_abc123")
    assert insight["read_only"] is True
    assert insight["games"] == 7
    assert insight["style"] == "positional"
    assert insight["weakness"] == "weak_endgame"
    assert insight["available"] is True
    assert model.read_bytes() == before          # never writes the bot's file
    assert review.opponent_insight("player_missing") == {}


def test_cli_import_and_games(dirs, capsys):
    journals, _ = dirs
    import coach

    path = _journal(journals / "cli.jsonl", [
        _start(), _opp(0, "e2e4", "e4", 10), _our(1, "g1f3", "Nf3", 10),
        {"type": "game_end", "result": "win", "pgn_result": "1-0"},
    ])
    assert coach.main(["import", str(path)]) == 0
    out = capsys.readouterr().out
    assert "IMPORT" in out
    assert "přesnost" in out
    assert "model si o soupeři" in out

    assert coach.main(["games"]) == 0
    out = capsys.readouterr().out
    assert "1-0" in out
    assert "player_abc123" in out

    assert coach.main(["import", "/etc/passwd"]) == 1
    assert "odmítnuto" in capsys.readouterr().out
