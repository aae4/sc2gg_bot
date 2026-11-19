from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import BufferedInputFile, FSInputFile
import pytest

from app.bot.handlers.replays import (
    build_mini_app_url,
    build_replay_keyboard,
    format_replay_caption,
    handle_replay_document,
)
from app.bot.handlers.start import cmd_start
from app.config import Settings
from app.db.repository import DatabaseRepository
from app.domain.models import ChartSeries, MatchMeta, PlayerInfo, ReplayData
from app.storage.base import ReplayStorage, StoredReplay

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


class FakeStorage(ReplayStorage):
    def __init__(self) -> None:
        self.saved_ids: list[str] = []

    async def save_replay(self, bundle, *, overwrite: bool = False) -> StoredReplay:
        rid = bundle.data.meta.replay_id
        self.saved_ids.append(rid)
        return StoredReplay(
            replay_id=rid,
            json_path=f"data/replays/{rid}.json",
            json_url=f"https://example.github.io/repo/data/replays/{rid}.json",
            json_uploaded=True,
        )

    async def exists(self, replay_id: str) -> bool:
        return replay_id in self.saved_ids


def test_build_mini_app_url_and_keyboard():
    s_direct = Settings(
        bot_token="123:test",
        mini_app_url="https://user.github.io/sc2gg/",
        mini_app_short_name="viewer",
    )
    assert (
        build_mini_app_url(s_direct, "abc123", bot_username="sc2gg_bot")
        == "https://t.me/sc2gg_bot/viewer?startapp=abc123"
    )
    kb = build_replay_keyboard(s_direct, "abc123", bot_username="sc2gg_bot")
    assert kb is not None
    assert kb.inline_keyboard[0][0].url == "https://t.me/sc2gg_bot/viewer?startapp=abc123"

    s_fallback = Settings(bot_token="123:test", mini_app_url="https://user.github.io/sc2gg/")
    assert (
        build_mini_app_url(s_fallback, "abc123", bot_username="sc2gg_bot")
        == "https://user.github.io/sc2gg?startapp=abc123"
    )

    s_empty = Settings(bot_token="123:test", mini_app_url="", mini_app_short_name="")
    assert build_replay_keyboard(s_empty, "abc123") is None


def test_format_replay_caption_escapes_html():
    data = ReplayData(
        meta=MatchMeta(
            replay_id="id1234567890",
            sha256="0" * 64,
            map_name="Map <Test> & Co",
            map_width=100,
            map_height=100,
            minimap_filename="map.png",
            duration_sec=125,
            version="5.0",
            played_at="",
        ),
        players=[
            PlayerInfo(pid=1, name="<Zerg&Pro>", race="Zerg", color_hex="#B4141E", result="Win", apm=100),
            PlayerInfo(pid=2, name="Terran", race="Terran", color_hex="#0042FF", result="Loss", apm=90),
        ],
        unit_dict={},
        frames=[],
        battles=[],
        build_order=[],
        charts=ChartSeries(),
    )
    caption = format_replay_caption(data)
    assert "Map &lt;Test&gt; &amp; Co" in caption
    assert "&lt;Zerg&amp;Pro&gt;" in caption
    assert "02:05" in caption


async def test_cmd_start_upserts_user(tmp_path: Path):
    async with DatabaseRepository(tmp_path / "bot.sqlite") as repo:
        msg = SimpleNamespace(
            from_user=SimpleNamespace(id=101, username="tester", first_name="Test"),
            answer=AsyncMock(),
        )
        await cmd_start(msg, repo)
        msg.answer.assert_awaited_once()
        user = await repo.get_user(101)
        assert user is not None
        assert user.username == "tester"


async def test_handle_replay_document_caches_by_sha256(tmp_path: Path):
    replay_path = FILES_DIR / "10000 Feet LE (4).SC2Replay"
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    app_settings = Settings(
        bot_token="123:test",
        data_dir=tmp_path / "data",
        mini_app_short_name="viewer",
    )
    storage = FakeStorage()
    cards_dir = tmp_path / "cards"

    async def fake_download(_document, destination: Path) -> None:
        shutil.copyfile(replay_path, destination)

    bot = SimpleNamespace(
        download=AsyncMock(side_effect=fake_download),
        get_me=AsyncMock(return_value=SimpleNamespace(username="sc2gg_test_bot")),
    )

    async with DatabaseRepository(tmp_path / "bot.sqlite") as repo:
        status_msg = SimpleNamespace(delete=AsyncMock())
        msg1 = SimpleNamespace(
            document=SimpleNamespace(file_name="10000 Feet LE (4).SC2Replay"),
            from_user=SimpleNamespace(id=777, username="papillon", first_name="Papillon"),
            reply=AsyncMock(return_value=status_msg),
            reply_photo=AsyncMock(),
        )

        # 1st call: cache miss -> parses, renders, uploads, saves to DB
        await handle_replay_document(
            msg1,
            bot=bot,
            repo=repo,
            settings=app_settings,
            storage=storage,
            cards_dir=cards_dir,
        )
        assert len(storage.saved_ids) == 1
        msg1.reply_photo.assert_awaited_once()
        photo_kw1 = msg1.reply_photo.call_args.kwargs
        assert isinstance(photo_kw1["photo"], BufferedInputFile)
        assert "10000 Feet LE" in photo_kw1["caption"]
        assert (
            photo_kw1["reply_markup"].inline_keyboard[0][0].url
            == f"https://t.me/sc2gg_test_bot/viewer?startapp={storage.saved_ids[0]}"
        )

        # 2nd call: cache hit -> no upload, serves cached FSInputFile
        msg2 = SimpleNamespace(
            document=SimpleNamespace(file_name="10000 Feet LE (4).SC2Replay"),
            from_user=SimpleNamespace(id=777, username="papillon", first_name="Papillon"),
            reply=AsyncMock(return_value=status_msg),
            reply_photo=AsyncMock(),
        )
        await handle_replay_document(
            msg2,
            bot=bot,
            repo=repo,
            settings=app_settings,
            storage=storage,
            cards_dir=cards_dir,
        )
        assert len(storage.saved_ids) == 1  # Not uploaded again!
        msg2.reply_photo.assert_awaited_once()
        photo_kw2 = msg2.reply_photo.call_args.kwargs
        assert isinstance(photo_kw2["photo"], FSInputFile)
        assert "10000 Feet LE" in photo_kw2["caption"]
