"""Local HTTP API + static file server for the chess coach.

Standard library only.  The server owns the game (board, clocks, bot replies)
and the browser is a thin, forgiving client.  Bind to loopback by default;
there is no authentication and no network exposure intended.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import chess

import game as game_mod
import importer
from engine import DEFAULT_STOCKFISH, StockfishEngine

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
STOCKFISH: str = os.environ.get("COACH_STOCKFISH") or DEFAULT_STOCKFISH
MAX_BODY = 64 * 1024
MAX_GAMES = 40

ENGINE = StockfishEngine(STOCKFISH)
GAMES: dict[str, Any] = {}
GAMES_LOCK = threading.Lock()


def get_game(gid: str) -> Any | None:
    with GAMES_LOCK:
        cached = GAMES.get(gid)
    if cached is not None:
        return cached
    # An imported game lives on disk: reopening it after a restart must work
    # from the listing alone, without importing it again.
    record = importer.get(gid)
    if record is None:
        return None
    game = game_mod.ImportedGame(record, ENGINE)
    put_game(gid, game)
    return game


def put_game(gid: str, game: Any) -> None:
    with GAMES_LOCK:
        GAMES[gid] = game
        while len(GAMES) > MAX_GAMES:
            oldest = next(iter(GAMES))
            if oldest == gid:
                break
            GAMES.pop(oldest, None)


def themes() -> dict[str, Any]:
    base = STATIC / "vendor" / "chesscom"
    boards = sorted(p.stem for p in (base / "boards").glob("*.png"))
    pieces_dir = base / "pieces"
    pieces = sorted(d.name for d in pieces_dir.iterdir()
                    if d.is_dir()) if pieces_dir.is_dir() else []
    sound_dir = STATIC / "vendor" / "sounds"
    sounds = sorted({p.name.split("-", 1)[0] for p in sound_dir.glob("*.mp3")})
    return {"boards": boards, "pieces": pieces, "sounds": sounds}


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def new_game(body: dict[str, Any]) -> dict[str, Any]:
    color = str(body.get("color") or "white").lower()
    if color not in ("white", "black", "random"):
        color = "white"
    if color == "random":
        color = random.choice(("white", "black"))
    fen = body.get("fen")
    if fen is not None and not isinstance(fen, str):
        fen = None
    if isinstance(fen, str):
        try:
            board = chess.Board(fen)
            if not board.is_valid():
                raise ValueError("invalid fen")
        except ValueError as exc:
            raise ValueError(f"neplatná FEN: {exc}") from exc
    gid = uuid.uuid4().hex[:10]
    game = game_mod.Game(
        gid,
        ENGINE,
        level=_int(body.get("level"), 8, 4, 16),
        player=str(body.get("player") or "me")[:40],
        color=color,
        base=_int(body.get("base"), 600, 10, 10800),
        inc=_int(body.get("inc"), 0, 0, 180),
        mode=str(body.get("mode") or "training"),
        fen=fen if isinstance(fen, str) else None,
    )
    put_game(gid, game)
    game.start()
    return game.state()


class Handler(SimpleHTTPRequestHandler):
    server_version = "ChessCoach/2.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if os.environ.get("COACH_HTTP_LOG"):
            super().log_message(format, *args)

    # ── plumbing ───────────────────────────────────────────────────────────
    def _json(self, payload: dict[str, Any],
              status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text: str, content_type: str = "text/plain; charset=utf-8",
              status: int = HTTPStatus.OK,
              extra: dict[str, str] | None = None) -> None:
        body = text.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw or b"{}")
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _query(self, name: str) -> str:
        values = parse_qs(urlparse(self.path).query).get(name)
        return values[0] if values else ""

    # ── GET ────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({
                "ok": True,
                "stockfish": STOCKFISH,
                "engine_present": Path(STOCKFISH).exists(),
            })
            return
        if path == "/api/themes":
            self._json(themes())
            return
        if path == "/api/games":
            self._json({
                "games": importer.list_games(),
                "imports": str(importer.imports_dir()),
                "journals": str(importer.journal_dir()),
                "games_dir": str(importer.games_dir()),
            })
            return
        if path == "/api/state":
            game = get_game(self._query("gid"))
            if game is None:
                self._json({"error": "neznámá partie"}, HTTPStatus.NOT_FOUND)
                return
            self._json(game.state())
            return
        if path == "/api/review":
            game = get_game(self._query("gid"))
            if game is None:
                self._json({"error": "neznámá partie"}, HTTPStatus.NOT_FOUND)
                return
            self._json(game.review_payload())
            return
        if path == "/api/pgn":
            game = get_game(self._query("gid"))
            if game is None:
                self._json({"error": "neznámá partie"}, HTTPStatus.NOT_FOUND)
                return
            self._text(game.pgn(), "application/x-chess-pgn; charset=utf-8",
                       extra={"Content-Disposition":
                              f'attachment; filename="chess-coach-{game.gid}.pgn"'})
            return
        if path.startswith("/api/"):
            self._json({"error": "neznámý endpoint"}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    # ── POST ───────────────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/new":
            try:
                self._json(new_game(body))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path in ("/api/move", "/api/takeback", "/api/resign",
                    "/api/review"):
            game = get_game(str(body.get("gid") or ""))
            if game is None:
                self._json({"error": "neznámá partie"}, HTTPStatus.NOT_FOUND)
                return
            if path == "/api/move":
                out = game.play(str(body.get("uci") or ""))
                if "error" in out and "state" not in out:
                    out["state"] = game.state()
                self._json(out, HTTPStatus.BAD_REQUEST if "error" in out
                           else HTTPStatus.OK)
                return
            if path == "/api/takeback":
                out = game.takeback()
                self._json(out, HTTPStatus.CONFLICT if "error" in out
                           else HTTPStatus.OK)
                return
            if path == "/api/resign":
                self._json(game.resign())
                return
            self._json(game.start_review())
            return
        if path == "/api/import":
            raw = body.get("path")
            if not isinstance(raw, str) or not raw.strip():
                self._json({"error": "chybí cesta k partii"},
                           HTTPStatus.BAD_REQUEST)
                return
            try:
                record = importer.import_path(raw)
            except importer.ImportRejected as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except FileNotFoundError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            imported = game_mod.ImportedGame(record, ENGINE)
            put_game(imported.gid, imported)
            self._json({
                "ok": True,
                "gid": imported.gid,
                "game": importer.summary(record),
                "state": imported.state(),
            })
            return
        self._json({"error": "neznámý endpoint"}, HTTPStatus.NOT_FOUND)


def main(argv: list[str] | None = None) -> int:
    global ENGINE, STOCKFISH
    parser = argparse.ArgumentParser(description="Lokální šachový kouč")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--stockfish", default=STOCKFISH)
    args = parser.parse_args(argv)

    STOCKFISH = args.stockfish
    ENGINE = StockfishEngine(STOCKFISH)
    if not Path(STOCKFISH).exists():
        print(f"Stockfish nenalezen: {STOCKFISH}\nNastav COACH_STOCKFISH.")
        return 2

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    host, port = server.server_address[:2]
    print(f"chess-coach-ui na http://{host}:{port}  (engine {STOCKFISH})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        ENGINE.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
