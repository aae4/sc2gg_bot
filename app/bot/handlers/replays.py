import hashlib
import html
import logging
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import Settings
from app.db.repository import DatabaseRepository, ReplayRecord
from app.domain.models import ReplayData
from app.parser.replay_parser import ReplayParseError, parse_replay_async
from app.renderer.summary_card import render_summary_card_async
from app.storage.base import ReplayStorage, StorageError

logger = logging.getLogger(__name__)
router = Router(name="replays")

RACE_EMOJI = {
    "Zerg": "🟣",
    "Terran": "🔵",
    "Protoss": "🟡",
}


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_duration(seconds: int) -> str:
    mins, secs = divmod(max(0, seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def format_replay_caption(data: ReplayData) -> str:
    map_name = html.escape(data.meta.map_name)
    duration = _format_duration(data.meta.duration_sec)
    lines = [
        f"🗺 <b>{map_name}</b>  •  ⏱ <code>{duration}</code>",
        "",
    ]
    for player in data.players:
        emoji = RACE_EMOJI.get(player.race, "⚪")
        name = html.escape(player.name)
        result_tag = "🏆" if player.result.lower() == "win" else "💀"
        lines.append(
            f"{result_tag} {emoji} <b>{name}</b> ({player.race}) — "
            f"APM {player.apm}, раб. {player.workers_peak}, армия {player.army_value_peak:,}"
        )

    lines.append("")
    lines.append(f"⚔️ Сражений: <b>{len(data.battles)}</b>  •  <code>#{data.meta.replay_id}</code>")
    return "\n".join(lines)[:1024]


def build_mini_app_url(
    settings: Settings,
    replay_id: str,
    bot_username: str | None = None,
) -> str | None:
    if settings.mini_app_short_name and bot_username:
        return f"https://t.me/{bot_username}/{settings.mini_app_short_name}?startapp={replay_id}"
    if settings.mini_app_url:
        base = settings.mini_app_url.rstrip("/")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}startapp={replay_id}"
    return None


def build_replay_keyboard(
    settings: Settings,
    replay_id: str,
    bot_username: str | None = None,
) -> InlineKeyboardMarkup | None:
    url = build_mini_app_url(settings, replay_id, bot_username=bot_username)
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="▶ Смотреть реплей", url=url)]]
    )


async def _resolve_bot_username(bot: Bot, bot_username: str) -> str:
    if bot_username:
        return bot_username
    me = await bot.get_me()
    return me.username or ""


async def _safe_delete(msg: Message | None) -> None:
    if msg is None:
        return
    try:
        await msg.delete()
    except Exception:
        pass


@router.message(F.document)
async def handle_replay_document(
    message: Message,
    bot: Bot,
    repo: DatabaseRepository,
    settings: Settings,
    storage: ReplayStorage | None = None,
    cards_dir: Path | None = None,
    bot_username: str = "",
) -> None:
    document = message.document
    if document is None or not document.file_name:
        return
    if not document.file_name.lower().endswith(".sc2replay"):
        return

    if message.from_user is not None:
        await repo.upsert_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

    resolved_cards_dir = cards_dir or (settings.data_dir / "cards")
    resolved_cards_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_replays_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = settings.temp_replays_dir / f"{uuid4().hex}.SC2Replay"
    status_msg = await message.reply("⏳ Анализирую реплей...")

    try:
        await bot.download(document, destination=tmp_path)
        sha256 = compute_sha256(tmp_path)
        resolved_username = await _resolve_bot_username(bot, bot_username)

        cached = await repo.get_replay_by_sha256(sha256)
        if cached is not None:
            keyboard = build_replay_keyboard(settings, cached.replay_id, resolved_username)
            cached_card = resolved_cards_dir / f"{cached.replay_id}.png"
            caption = cached.summary_text or f"🗺 <b>{html.escape(cached.map_name)}</b>"
            if cached_card.is_file():
                await message.reply_photo(
                    photo=FSInputFile(cached_card),
                    caption=caption,
                    reply_markup=keyboard,
                )
            else:
                await message.reply(caption, reply_markup=keyboard)
            await _safe_delete(status_msg)
            return

        bundle = await parse_replay_async(tmp_path)
        png_bytes = await render_summary_card_async(bundle.data)

        card_path = resolved_cards_dir / f"{bundle.data.meta.replay_id}.png"
        card_path.write_bytes(png_bytes)

        if storage is not None:
            try:
                await storage.save_replay(bundle)
            except StorageError as exc:
                logger.warning("Failed to upload replay %s to storage: %s", bundle.data.meta.replay_id, exc)

        caption = format_replay_caption(bundle.data)
        await repo.save_replay(
            ReplayRecord(
                sha256=bundle.data.meta.sha256,
                replay_id=bundle.data.meta.replay_id,
                map_name=bundle.data.meta.map_name,
                duration_sec=bundle.data.meta.duration_sec,
                summary_text=caption,
            )
        )

        keyboard = build_replay_keyboard(settings, bundle.data.meta.replay_id, resolved_username)
        await message.reply_photo(
            photo=BufferedInputFile(png_bytes, filename=f"{bundle.data.meta.replay_id}.png"),
            caption=caption,
            reply_markup=keyboard,
        )
        await _safe_delete(status_msg)
    except ReplayParseError as exc:
        await _safe_delete(status_msg)
        await message.reply(f"⚠️ Не удалось разобрать реплей: {html.escape(str(exc))}")
    except Exception:
        logger.exception("Unexpected error processing replay %s", document.file_name)
        await _safe_delete(status_msg)
        await message.reply("❌ Произошла ошибка при обработке реплея.")
    finally:
        tmp_path.unlink(missing_ok=True)
