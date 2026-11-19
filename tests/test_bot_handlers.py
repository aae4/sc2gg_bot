from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import BufferedInputFile, FSInputFile
import pytest

from app.bot.handlers.replays import (
    build_mini_app_url,
    build_replay_keyboard,
    cb_replay_select,
    cb_replays_page,
    cmd_replays,
    format_replay_caption,
    handle_replay_document,
)
from app.bot.handlers.start import cmd_start
from app.config import Settings
from app.db.repository import DatabaseRepository, ReplayRecord
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


async def test_cmd_replays_empty_and_paginated(tmp_path: Path):
    async with DatabaseRepository(tmp_path / "bot.sqlite") as repo:
        empty_msg = SimpleNamespace(
            chat=SimpleNamespace(id=555, type="private"),
            from_user=SimpleNamespace(id=555, username="u", first_name="U"),
            answer=AsyncMock(),
        )
        await cmd_replays(empty_msg, repo)
        empty_msg.answer.assert_awaited_once()
        assert "Пока нет загруженных реплеев" in empty_msg.answer.call_args.args[0]

        for idx in range(8):
            rid = f"rep{idx:09d}"
            await repo.save_replay(
                ReplayRecord(
                    sha256=f"{idx}" * 64,
                    replay_id=rid,
                    map_name=f"Map {idx}",
                    duration_sec=600 + idx,
                    summary_text=f"Summary {idx}",
                    match_title=f"Alice (Z) vs Bob (T)",
                )
            )
            await repo.record_upload(rid, user_id=555, chat_id=555)

        list_msg = SimpleNamespace(
            chat=SimpleNamespace(id=555, type="private"),
            from_user=SimpleNamespace(id=555, username="u", first_name="U"),
            answer=AsyncMock(),
        )
        await cmd_replays(list_msg, repo)
        list_msg.answer.assert_awaited_once()
        kb_page0 = list_msg.answer.call_args.kwargs["reply_markup"]
        # 6 replay buttons + 1 pagination row
        assert len(kb_page0.inline_keyboard) == 7
        assert kb_page0.inline_keyboard[-1][1].text == "1/2"
        assert kb_page0.inline_keyboard[-1][2].callback_data == "replays_page:1"

        cb_msg = SimpleNamespace(
            chat=SimpleNamespace(id=555, type="private"),
            edit_text=AsyncMock(),
        )
        cb_page = SimpleNamespace(
            data="replays_page:1",
            from_user=SimpleNamespace(id=555),
            message=cb_msg,
            answer=AsyncMock(),
        )
        await cb_replays_page(cb_page, repo)
        cb_msg.edit_text.assert_awaited_once()
        kb_page1 = cb_msg.edit_text.call_args.kwargs["reply_markup"]
        # 2 remaining replay buttons + 1 pagination row
        assert len(kb_page1.inline_keyboard) == 3
        assert kb_page1.inline_keyboard[-1][1].text == "2/2"
        cb_page.answer.assert_awaited_once()


async def test_cb_replay_select_sends_cached_card_and_handles_missing(tmp_path: Path):
    app_settings = Settings(
        bot_token="123:test",
        data_dir=tmp_path / "data",
        mini_app_short_name="viewer",
    )
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    (cards_dir / "rep000000000.png").write_bytes(b"PNGDATA")

    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(username="sc2gg_test_bot")),
    )

    async with DatabaseRepository(tmp_path / "bot.sqlite") as repo:
        await repo.save_replay(
            ReplayRecord(
                sha256="a" * 64,
                replay_id="rep000000000",
                map_name="Blackburn LE",
                duration_sec=500,
                summary_text="<b>Blackburn LE</b>",
                match_title="Serral (Z) vs Maru (T)",
            )
        )

        cb_msg = SimpleNamespace(answer_photo=AsyncMock(), answer=AsyncMock())
        cb_ok = SimpleNamespace(
            data="replay:rep000000000",
            message=cb_msg,
            answer=AsyncMock(),
        )
        await cb_replay_select(
            cb_ok,
            bot=bot,
            repo=repo,
            settings=app_settings,
            cards_dir=cards_dir,
        )
        cb_msg.answer_photo.assert_awaited_once()
        photo_kw = cb_msg.answer_photo.call_args.kwargs
        assert isinstance(photo_kw["photo"], FSInputFile)
        assert photo_kw["caption"] == "<b>Blackburn LE</b>"
        assert (
            photo_kw["reply_markup"].inline_keyboard[0][0].url
            == "https://t.me/sc2gg_test_bot/viewer?startapp=rep000000000"
        )
        cb_ok.answer.assert_awaited_once()

        cb_missing = SimpleNamespace(
            data="replay:doesnotexist",
            message=cb_msg,
            answer=AsyncMock(),
        )
        await cb_replay_select(
            cb_missing,
            bot=bot,
            repo=repo,
            settings=app_settings,
            cards_dir=cards_dir,
        )
        cb_missing.answer.assert_awaited_once_with("Реплей не найден.", show_alert=True)
