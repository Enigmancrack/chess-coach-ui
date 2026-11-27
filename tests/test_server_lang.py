"""`/api/settings` and per-request language: same numbers, different words."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

import pytest

import review
import server


def call(base: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.fixture
def base(monkeypatch, fake_engine):
    monkeypatch.setattr(server, "ENGINE", fake_engine)
    monkeypatch.setattr(server, "SETTINGS", {"lang": "cs"})
    with server.GAMES_LOCK:
        server.GAMES.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def new_move(base: str, lang: str) -> dict[str, Any]:
    status, state = call(base, "/api/new", {
        "color": "white", "base": 60, "inc": 0, "level": 4,
        "player": "lang-test", "lang": lang,
    })
    assert status == 200, state
    assert state["lang"] == lang
    status, out = call(base, "/api/move",
                       {"gid": state["gid"], "uci": "e2e4", "lang": lang})
    assert status == 200, out
    return out


def test_settings_speak_both_languages_and_reject_others(base):
    status, out = call(base, "/api/settings")
    assert status == 200
    assert out["lang"] == "cs"
    assert out["langs"] == ["cs", "en"]
    assert out["labels"]["blunder"] == "Hrubka"

    status, out = call(base, "/api/settings", {"lang": "en"})
    assert status == 200 and out["lang"] == "en"
    assert out["labels"]["blunder"] == "Blunder"
    status, out = call(base, "/api/settings")
    assert out["lang"] == "en"

    status, out = call(base, "/api/settings", {"lang": "de"})
    assert status == 400 and "de" in out["error"]
    status, out = call(base, "/api/settings")
    assert out["lang"] == "en"          # a bad request changes nothing


def test_english_request_has_english_text_and_identical_numbers(base):
    cs = new_move(base, "cs")
    en = new_move(base, "en")

    assert set(cs) == set(en)
    assert cs["note"]["verdict"] == en["note"]["verdict"] in review.CATEGORIES
    assert cs["note"]["label"] == "Teorie" and en["note"]["label"] == "Book"
    assert cs["note"]["loss"] == en["note"]["loss"] == 0
    assert cs["eval_cp"] == en["eval_cp"]
    assert cs["moves"][0]["uci"] == en["moves"][0]["uci"] == "e2e4"
    assert cs["moves"][0]["san"] == en["moves"][0]["san"] == "e4"
    assert "teorie" in cs["note"]["text"]
    assert "book" in en["note"]["text"]


def test_server_default_language_applies_to_new_games(base):
    call(base, "/api/settings", {"lang": "en"})
    status, state = call(base, "/api/new", {
        "color": "black", "base": 60, "level": 4, "player": "t",
    })
    assert status == 200 and state["lang"] == "en"


def test_http_and_game_errors_follow_the_language(base):
    status, out = call(base, "/api/state?gid=nope&lang=en")
    assert status == 404 and out["error"] == "unknown game"

    game = new_move(base, "en")
    status, out = call(base, "/api/move", {"gid": game["gid"], "uci": "e2e5"})
    assert status == 400 and out["error"] == "illegal move"

    status, out = call(base, "/api/new", {
        "color": "white", "lang": "en", "fen": "not a fen"})
    assert status == 400 and out["error"].startswith("invalid FEN")

    status, out = call(base, "/api/new", {
        "color": "white", "lang": "cs", "fen": "not a fen"})
    assert status == 400 and out["error"].startswith("neplatná FEN")


def test_review_payload_is_localized_too(base):
    game = new_move(base, "en")
    status, payload = call(base, "/api/review", {"gid": game["gid"]})
    assert status == 200
    for _ in range(100):
        status, payload = call(base, f"/api/review?gid={game['gid']}")
        if payload["status"] != "running":
            break
        time.sleep(0.05)
    assert payload["status"] == "ready", payload
    report = payload["report"]
    assert report["moves"] == 1
    assert report["labels"]["book"] == "Book"
    assert report["plies"][0]["label"] == "Book"
    assert "book" in report["plies"][0]["text"]
    assert report["plies"][0]["verdict"] == "book"
