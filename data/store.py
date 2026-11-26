"""JSON game store (the out-of-scope SQLite migration plugs in here)."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, directory: str | Path | None = None) -> None:
        env = os.environ.get("COACH_DATA_DIR")
        self.directory = Path(directory or env or (Path.home() / ".chess_coach_games"))

    def save(self, record: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.directory / f"{stamp}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return path

    def load(self, path: str | Path) -> dict[str, Any]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def list(self) -> list[Path]:
        try:
            return sorted(self.directory.glob("*.json"))
        except OSError:
            return []

    def latest(self) -> Path | None:
        files = self.list()
        return files[-1] if files else None


def default_store() -> JsonStore:
    return JsonStore()
