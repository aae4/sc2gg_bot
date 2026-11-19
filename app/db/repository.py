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
    match_title: str = ""
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
                match_title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS replay_uploads (
                replay_id TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                chat_id INTEGER NOT NULL DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                PRIMARY KEY (replay_id, user_id, chat_id)
            );

            CREATE INDEX IF NOT EXISTS idx_replay_uploads_user
                ON replay_uploads (user_id, uploaded_at DESC);
            CREATE INDEX IF NOT EXISTS idx_replay_uploads_chat
                ON replay_uploads (chat_id, uploaded_at DESC);
            """
        )
        async with conn.execute("PRAGMA table_info(replays)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}
        if "match_title" not in columns:
            await conn.execute("ALTER TABLE replays ADD COLUMN match_title TEXT NOT NULL DEFAULT ''")
        await conn.commit()

    async def get_replay_by_sha256(self, sha256: str) -> ReplayRecord | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT sha256, replay_id, map_name, duration_sec, summary_text, match_title, created_at "
            "FROM replays WHERE sha256 = ?",
            (sha256,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return ReplayRecord(**dict(row))

    async def get_replay_by_id(self, replay_id: str) -> ReplayRecord | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT sha256, replay_id, map_name, duration_sec, summary_text, match_title, created_at "
            "FROM replays WHERE replay_id = ?",
            (replay_id,),
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
            INSERT INTO replays (sha256, replay_id, map_name, duration_sec, summary_text, match_title, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                replay_id = excluded.replay_id,
                map_name = excluded.map_name,
                duration_sec = excluded.duration_sec,
                summary_text = excluded.summary_text,
                match_title = CASE
                    WHEN excluded.match_title != '' THEN excluded.match_title
                    ELSE replays.match_title
                END
            """,
            (
                record.sha256,
                record.replay_id,
                record.map_name,
                record.duration_sec,
                record.summary_text,
                record.match_title,
                created_at,
            ),
        )
        await conn.commit()

    async def record_upload(
        self,
        replay_id: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
    ) -> None:
        conn = self._require_conn()
        now = _utc_now_iso()
        await conn.execute(
            """
            INSERT INTO replay_uploads (replay_id, user_id, chat_id, uploaded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(replay_id, user_id, chat_id) DO UPDATE SET
                uploaded_at = excluded.uploaded_at
            """,
            (replay_id, user_id or 0, chat_id or 0, now),
        )
        await conn.commit()

    async def list_replays(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        limit: int = 6,
        offset: int = 0,
    ) -> tuple[list[ReplayRecord], int]:
        conn = self._require_conn()
        filters: list[str] = []
        params: list[int] = []
        if user_id is not None:
            filters.append("u.user_id = ?")
            params.append(user_id)
        if chat_id is not None:
            filters.append("u.chat_id = ?")
            params.append(chat_id)

        if filters:
            where_clause = "WHERE " + " AND ".join(filters)
            count_sql = (
                f"SELECT COUNT(DISTINCT r.replay_id) AS cnt "
                f"FROM replays r JOIN replay_uploads u ON u.replay_id = r.replay_id "
                f"{where_clause}"
            )
            list_sql = (
                f"SELECT r.sha256, r.replay_id, r.map_name, r.duration_sec, "
                f"r.summary_text, r.match_title, r.created_at, "
                f"MAX(u.uploaded_at) AS last_uploaded "
                f"FROM replays r JOIN replay_uploads u ON u.replay_id = r.replay_id "
                f"{where_clause} "
                f"GROUP BY r.replay_id "
                f"ORDER BY last_uploaded DESC, r.created_at DESC "
                f"LIMIT ? OFFSET ?"
            )
        else:
            count_sql = "SELECT COUNT(*) AS cnt FROM replays"
            list_sql = (
                "SELECT sha256, replay_id, map_name, duration_sec, summary_text, match_title, created_at "
                "FROM replays ORDER BY created_at DESC LIMIT ? OFFSET ?"
            )

        async with conn.execute(count_sql, tuple(params)) as cursor:
            count_row = await cursor.fetchone()
        total = int(count_row["cnt"]) if count_row is not None else 0

        async with conn.execute(list_sql, tuple([*params, limit, offset])) as cursor:
            rows = await cursor.fetchall()

        items = [
            ReplayRecord(
                sha256=row["sha256"],
                replay_id=row["replay_id"],
                map_name=row["map_name"],
                duration_sec=row["duration_sec"],
                summary_text=row["summary_text"],
                match_title=row["match_title"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return items, total

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
