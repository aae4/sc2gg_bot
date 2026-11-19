from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from pydantic import BaseModel


class ReplayRecord(BaseModel):
    sha256: str
    replay_id: str
    map_name: str
    duration_sec: int = 0
    summary_text: str = ""
    created_at: str = ""


class UserRecord(BaseModel):
    user_id: int
    username: str | None = None
    first_name: str | None = None
    created_at: str = ""
    last_seen_at: str = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseRepository:
    """Async SQLite repository for replay deduplication (SHA-256) and users."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._init_schema()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "DatabaseRepository":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("DatabaseRepository is not connected. Call connect() first.")
        return self._conn

    async def _init_schema(self) -> None:
        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS replays (
                sha256 TEXT PRIMARY KEY,
                replay_id TEXT NOT NULL UNIQUE,
                map_name TEXT NOT NULL,
                duration_sec INTEGER NOT NULL DEFAULT 0,
                summary_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            """
        )
        await conn.commit()

    async def get_replay_by_sha256(self, sha256: str) -> ReplayRecord | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT sha256, replay_id, map_name, duration_sec, summary_text, created_at "
            "FROM replays WHERE sha256 = ?",
            (sha256,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return ReplayRecord(**dict(row))

    async def save_replay(self, record: ReplayRecord) -> None:
        conn = self._require_conn()
        created_at = record.created_at or _utc_now_iso()
        await conn.execute(
            """
            INSERT INTO replays (sha256, replay_id, map_name, duration_sec, summary_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                replay_id = excluded.replay_id,
                map_name = excluded.map_name,
                duration_sec = excluded.duration_sec,
                summary_text = excluded.summary_text
            """,
            (
                record.sha256,
                record.replay_id,
                record.map_name,
                record.duration_sec,
                record.summary_text,
                created_at,
            ),
        )
        await conn.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        conn = self._require_conn()
        now = _utc_now_iso()
        await conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen_at = excluded.last_seen_at
            """,
            (user_id, username, first_name, now, now),
        )
        await conn.commit()

    async def get_user(self, user_id: int) -> UserRecord | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT user_id, username, first_name, created_at, last_seen_at "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return UserRecord(**dict(row))
