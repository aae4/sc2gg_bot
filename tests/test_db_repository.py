from pathlib import Path

from app.db.repository import DatabaseRepository, ReplayRecord


async def test_repository_replays_and_users(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    async with DatabaseRepository(db_path) as repo:
        assert await repo.get_replay_by_sha256("missing") is None

        rec = ReplayRecord(
            sha256="a" * 64,
            replay_id="a" * 12,
            map_name="10000 Feet LE",
            duration_sec=716,
            summary_text="Summary",
        )
        await repo.save_replay(rec)

        loaded = await repo.get_replay_by_sha256("a" * 64)
        assert loaded is not None
        assert loaded.replay_id == "a" * 12
        assert loaded.map_name == "10000 Feet LE"
        assert loaded.duration_sec == 716
        assert loaded.summary_text == "Summary"
        assert loaded.created_at != ""

        await repo.upsert_user(user_id=42, username="alice", first_name="Alice")
        user = await repo.get_user(42)
        assert user is not None
        assert user.username == "alice"
        assert user.first_name == "Alice"

        await repo.upsert_user(user_id=42, username="alice_new", first_name="Alice M")
        updated = await repo.get_user(42)
        assert updated is not None
        assert updated.username == "alice_new"
        assert updated.first_name == "Alice M"
