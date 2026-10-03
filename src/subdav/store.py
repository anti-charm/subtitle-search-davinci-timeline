from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class PairingStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.db_path.touch(mode=0o600, exist_ok=True)
            self.db_path.chmod(0o600)
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS pairings ("
                "srt_path TEXT PRIMARY KEY, video_path TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.db_path)
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def _canon(path: Path) -> str:
        return str(Path(path).expanduser().resolve())

    def get_pair(self, srt_path: Path) -> Path | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT video_path FROM pairings WHERE srt_path = ?",
                (self._canon(srt_path),),
            ).fetchone()
        return Path(row[0]) if row else None

    def set_pair(self, srt_path: Path, video_path: Path) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO pairings(srt_path, video_path) VALUES(?, ?) "
                "ON CONFLICT(srt_path) DO UPDATE SET video_path = excluded.video_path",
                (self._canon(srt_path), self._canon(video_path)),
            )

    def remove_pair(self, srt_path: Path) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM pairings WHERE srt_path = ?", (self._canon(srt_path),))

    def get_setting(self, key: str) -> str | None:
        with self._connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
