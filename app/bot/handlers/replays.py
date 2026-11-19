import hashlib
import html
import logging
import math
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
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

RACE_SHORT = {
    "Zerg": "Z",
    "Terran": "T",
    "Protoss": "P",
}

REPLAYS_PAGE_SIZE = 6


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
        arch = f" • {html.escape(player.build_archetype)}" if player.build_archetype else ""
        lines.append(
            f"{result_tag} {emoji} <b>{name}</b> ({player.race}{arch})\n"
            f"   APM {player.apm} • SQ {player.spending_quotient} • "
            f"блок {_format_duration(player.supply_block_sec)} • "
            f"раб. {player.workers_peak} (уб. {player.workers_killed}/пот. {player.workers_lost})"
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


def format_match_title(data: ReplayData) -> str:
    parts = [f"{p.name} ({RACE_SHORT.get(p.race, p.race[:1])})" for p in data.players]
    return " vs ".join(parts)


def _resolve_scope(chat: object | None, user: object | None) -> tuple[int | None, int | None]:
    chat_type = getattr(chat, "type", None) if chat is not None else None
    if chat_type in ("group", "supergroup"):
        return None, getattr(chat, "id", None)
    user_id = getattr(user, "id", None) if user is not None else None
    return user_id, None


def _truncate_label(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_replays_list_view(
    items: list[ReplayRecord],
    total: int,
    page: int,
    page_size: int = REPLAYS_PAGE_SIZE,
) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = max(1, math.ceil(total / page_size))
    current_page = max(0, min(page, total_pages - 1))

    rows: list[list[InlineKeyboardButton]] = []
    for rec in items:
        duration = _format_duration(rec.duration_sec)
        label = f"{rec.map_name} • {duration}"
        if rec.match_title:
            label = f"{label} • {rec.match_title}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=_truncate_label(f"🗺 {label}"),
                    callback_data=f"replay:{rec.replay_id}",
                )
            ]
        )

    if total_pages > 1:
        prev_btn = (
            InlineKeyboardButton(text="⬅️", callback_data=f"replays_page:{current_page - 1}")
            if current_page > 0
            else InlineKeyboardButton(text="·", callback_data="replays_noop")
        )
        page_btn = InlineKeyboardButton(
            text=f"{current_page + 1}/{total_pages}",
            callback_data="replays_noop",
        )
        next_btn = (
            InlineKeyboardButton(text="➡️", callback_data=f"replays_page:{current_page + 1}")
            if current_page + 1 < total_pages
            else InlineKeyboardButton(text="·", callback_data="replays_noop")
        )
        rows.append([prev_btn, page_btn, next_btn])

    header = f"📚 <b>Загруженные реплеи</b> (всего: {total})\nВыберите матч, чтобы открыть карточку и 2D-плеер:"
    return header, InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_cached_replay(
    target_message: Message,
    record: ReplayRecord,
    settings: Settings,
    cards_dir: Path,
    bot_username: str,
    *,
    use_reply: bool = True,
) -> None:
    keyboard = build_replay_keyboard(settings, record.replay_id, bot_username)
    cached_card = cards_dir / f"{record.replay_id}.png"
    caption = record.summary_text or f"🗺 <b>{html.escape(record.map_name)}</b>"
    if cached_card.is_file():
        send_photo = target_message.reply_photo if use_reply else target_message.answer_photo
        await send_photo(
            photo=FSInputFile(cached_card),
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        send_text = target_message.reply if use_reply else target_message.answer
        await send_text(caption, reply_markup=keyboard)


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

    user_id = message.from_user.id if message.from_user is not None else None
    chat_obj = getattr(message, "chat", None)
    chat_id = getattr(chat_obj, "id", None) if chat_obj is not None else None

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
            await repo.record_upload(cached.replay_id, user_id=user_id, chat_id=chat_id)
            await _send_cached_replay(
                message,
                cached,
                settings,
                resolved_cards_dir,
                resolved_username,
                use_reply=True,
            )
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
                match_title=format_match_title(bundle.data),
            )
        )
        await repo.record_upload(bundle.data.meta.replay_id, user_id=user_id, chat_id=chat_id)

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


@router.message(Command("replays"))
async def cmd_replays(message: Message, repo: DatabaseRepository) -> None:
    user_id, chat_id = _resolve_scope(getattr(message, "chat", None), message.from_user)
    items, total = await repo.list_replays(
        user_id=user_id,
        chat_id=chat_id,
        limit=REPLAYS_PAGE_SIZE,
        offset=0,
    )
    if total == 0:
        await message.answer(
            "📭 Пока нет загруженных реплеев.\n"
            "Отправьте файл <code>.SC2Replay</code>, чтобы добавить первый!"
        )
        return

    text, keyboard = build_replays_list_view(items, total, page=0)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "replays_noop")
async def cb_replays_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("replays_page:"))
async def cb_replays_page(callback: CallbackQuery, repo: DatabaseRepository) -> None:
    if not callback.data or callback.message is None:
        await callback.answer()
        return
    try:
        page = max(0, int(callback.data.split(":", 1)[1]))
    except ValueError:
        await callback.answer()
        return

    user_id, chat_id = _resolve_scope(getattr(callback.message, "chat", None), callback.from_user)
    items, total = await repo.list_replays(
        user_id=user_id,
        chat_id=chat_id,
        limit=REPLAYS_PAGE_SIZE,
        offset=page * REPLAYS_PAGE_SIZE,
    )
    if total == 0:
        await callback.message.edit_text("📭 Список реплеев пуст.")
        await callback.answer()
        return

    if not items:
        last_page = max(0, math.ceil(total / REPLAYS_PAGE_SIZE) - 1)
        page = last_page
        items, total = await repo.list_replays(
            user_id=user_id,
            chat_id=chat_id,
            limit=REPLAYS_PAGE_SIZE,
            offset=page * REPLAYS_PAGE_SIZE,
        )

    text, keyboard = build_replays_list_view(items, total, page=page)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("replay:"))
async def cb_replay_select(
    callback: CallbackQuery,
    bot: Bot,
    repo: DatabaseRepository,
    settings: Settings,
    cards_dir: Path | None = None,
    bot_username: str = "",
) -> None:
    if not callback.data or callback.message is None:
        await callback.answer()
        return

    replay_id = callback.data.split(":", 1)[1]
    record = await repo.get_replay_by_id(replay_id)
    if record is None:
        await callback.answer("Реплей не найден.", show_alert=True)
        return

    resolved_cards_dir = cards_dir or (settings.data_dir / "cards")
    resolved_username = await _resolve_bot_username(bot, bot_username)
    await _send_cached_replay(
        callback.message,
        record,
        settings,
        resolved_cards_dir,
        resolved_username,
        use_reply=False,
    )
    await callback.answer()
