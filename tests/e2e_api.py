"""End-to-end API exercise for chess-coach-ui. Prints evidence, exits non-zero on failure."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def call(base: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                return response.status, json.loads(raw)
            return response.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode()


def wait_bot(base: str, gid: str, plies: int, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, state = call(base, f"/api/state?gid={gid}")
        assert status == 200, state
        if len(state["moves"]) >= plies and not state["thinking"]:
            return state
        time.sleep(0.15)
    raise AssertionError(f"bot did not reach {plies} plies")


def main() -> int:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                status, health = call(base, "/api/health")
                if status == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")
        print("HEALTH", health)
        status, themes = call(base, "/api/themes")
        print("THEMES", status, "boards", len(themes["boards"]),
              "pieces", len(themes["pieces"]), "sounds", themes["sounds"])
        assert len(themes["boards"]) >= 9 and len(themes["pieces"]) >= 8

        # ── white game, clock drain, move + bot reply, takeback ────────────
        status, state = call(base, "/api/new", {
            "color": "white", "base": 60, "inc": 1, "level": 4,
            "mode": "training", "player": "e2e",
        })
        assert status == 200, state
        gid = state["gid"]
        print("NEW WHITE", state["my_color"], state["time_control"],
              "legal origins", len(state["legal"]))
        assert state["my_color"] == "white" and "e2" in state["legal"]
        before = state["clocks"]["white"]
        time.sleep(1.2)
        status, state = call(base, f"/api/state?gid={gid}")
        after = state["clocks"]["white"]
        print(f"CLOCK white {before} -> {after} (drained {before - after:.2f}s)")
        assert before - after > 0.8

        status, out = call(base, "/api/move", {"gid": gid, "uci": "e2e4"})
        assert status == 200, out
        print("PLAYER e4", "note", out["note"]["verdict"], "-", out["note"]["text"][:70])
        assert out["moves"][0]["san"] == "e4"
        state = wait_bot(base, gid, 2)
        print("BOT REPLY", state["moves"][-1]["san"], "plies", len(state["moves"]))
        status, state = call(base, "/api/takeback", {"gid": gid})
        assert status == 200, state
        print("TAKEBACK plies", len(state["moves"]), "turn", state["turn"],
              "e2 legal", "e2" in state["legal"])
        assert state["moves"] == [] and state["turn"] == "white"

        # ── illegal move never a false illegal from our side ───────────────
        status, out = call(base, "/api/move", {"gid": gid, "uci": "e2e5"})
        print("ILLEGAL", status, out["error"], "has legal", "e2" in out.get("legal", {}))
        assert status == 400 and "e2" in out["legal"]

        # ── black game, bot opens, player replies ─────────────────────────
        status, state = call(base, "/api/new", {
            "color": "black", "base": 180, "inc": 2, "level": 4,
            "mode": "training", "player": "e2e",
        })
        gid_black = state["gid"]
        state = wait_bot(base, gid_black, 1)
        print("NEW BLACK", state["my_color"], "bot opened", state["moves"][0]["san"],
              "legal", len(state["legal"]))
        assert state["my_color"] == "black" and state["turn"] == "black"
        status, out = call(base, "/api/move", {"gid": gid_black, "uci": "a7a6"})
        assert status == 200, out
        state = wait_bot(base, gid_black, 3)
        print("BLACK PLAYED", state["moves"][-2]["san"], "bot", state["moves"][-1]["san"])

        # ── back-rank queen capture with a stray promotion letter ─────────
        fen = "3qk3/8/8/8/8/8/8/3QK3 w - - 0 1"
        status, state = call(base, "/api/new", {
            "color": "white", "base": 300, "inc": 0, "level": 4,
            "mode": "training", "player": "e2e", "fen": fen,
        })
        gid_cap = state["gid"]
        print("CUSTOM FEN", state["fen"], "legal d1", state["legal"].get("d1"))
        status, out = call(base, "/api/move", {"gid": gid_cap, "uci": "d1d8q"})
        assert status == 200, out
        print("BACK RANK", out["moves"][0]["uci"], out["moves"][0]["san"],
              "capture", out["moves"][0]["flags"]["capture"],
              "check", out["moves"][0]["flags"]["check"])
        assert out["moves"][0]["uci"] == "d1d8"
        state = wait_bot(base, gid_cap, 2)
        print("BACK RANK BOT", state["moves"][-1]["san"])

        # ── review on the capture game ─────────────────────────────────────
        status, payload = call(base, "/api/review", {"gid": gid_cap})
        print("REVIEW START", status, payload["status"])
        for _ in range(120):
            status, payload = call(base, f"/api/review?gid={gid_cap}")
            if payload["status"] != "running":
                break
            time.sleep(0.2)
        assert payload["status"] == "ready", payload
        report = payload["report"]
        print("REVIEW READY accuracy", report["accuracy"], "counts", report["counts"],
              "avg_loss", report["avg_loss"], "plies", len(report["plies"]),
              "evals", len(report["evals"]))
        assert report["moves"] >= 1 and report["plies"]
        assert report["plies"][0]["best_uci"]

        status, pgn = call(base, f"/api/pgn?gid={gid_cap}")
        assert status == 200 and "1. Qxd8" in pgn
        moves = [line for line in pgn.splitlines() if line.strip() and not line.startswith("[")]
        print("PGN", " ".join(moves)[:220])

        # ── resign ends a game ────────────────────────────────────────────
        status, out = call(base, "/api/resign", {"gid": gid_black})
        print("RESIGN", out["over"], out["result"])
        assert out["over"] and out["result"] == "1-0"

        print("E2E OK")
        return 0
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        print("SERVER LOG:", output.strip().splitlines()[:3])


if __name__ == "__main__":
    raise SystemExit(main())
