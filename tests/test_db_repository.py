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


async def test_repository_list_replays_and_uploads(tmp_path: Path):
    db_path = tmp_path / "test_list.sqlite"
    async with DatabaseRepository(db_path) as repo:
        for idx in range(3):
            await repo.save_replay(
                ReplayRecord(
                    sha256=f"{idx}" * 64,
                    replay_id=f"rep{idx:09d}",
                    map_name=f"Map {idx}",
                    duration_sec=300 + idx * 10,
                    summary_text=f"Summary {idx}",
                    match_title=f"P1 (Z) vs P2 (T) #{idx}",
                )
            )

        await repo.record_upload("rep000000000", user_id=1, chat_id=1)
        await repo.record_upload("rep000000001", user_id=1, chat_id=-100)
        await repo.record_upload("rep000000002", user_id=2, chat_id=-100)

        by_id = await repo.get_replay_by_id("rep000000001")
        assert by_id is not None
        assert by_id.match_title == "P1 (Z) vs P2 (T) #1"

        user1_items, user1_total = await repo.list_replays(user_id=1, limit=1, offset=0)
        assert user1_total == 2
        assert len(user1_items) == 1
        assert user1_items[0].replay_id == "rep000000001"

        user1_page2, _ = await repo.list_replays(user_id=1, limit=1, offset=1)
        assert len(user1_page2) == 1
        assert user1_page2[0].replay_id == "rep000000000"

        group_items, group_total = await repo.list_replays(chat_id=-100, limit=10, offset=0)
        assert group_total == 2
        assert [item.replay_id for item in group_items] == ["rep000000002", "rep000000001"]
