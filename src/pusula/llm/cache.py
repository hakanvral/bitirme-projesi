"""SQLite response cache keyed by (provider, model, prompt_version, input hash)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path


def cache_key(provider: str, model: str, prompt_version: str, *parts: str) -> str:
    h = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{provider}|{model}|{prompt_version}|{h}"


class ResponseCache:
    def __init__(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            self._con.commit()

    def get(self, key: str) -> dict | None:
        with self._lock:
            row = self._con.execute("SELECT value FROM responses WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row[0])

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO responses (key, value) VALUES (?, ?)",
                              (key, json.dumps(value, ensure_ascii=False)))  # fmt: skip
            self._con.commit()

    def __len__(self) -> int:
        with self._lock:
            return self._con.execute("SELECT count(*) FROM responses").fetchone()[0]
