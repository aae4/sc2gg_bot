from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.db.repository import DatabaseRepository

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, repo: DatabaseRepository) -> None:
    if message.from_user is not None:
        await repo.upsert_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

    await message.answer(
        "👋 <b>SC2GG Bot</b>\n\n"
        "Отправьте файл реплея <code>.SC2Replay</code> (в личные сообщения или в группу), "
        "и я сформирую карточку матча со статистикой, графиками и ссылкой на 2D-плеер.\n\n"
        "Команды:\n"
        "• /start — приветствие\n"
        "• /help — справка",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Как пользоваться:</b>\n"
        "1. Прикрепите файл формата <code>.SC2Replay</code> (поддерживаются матчи 1v1).\n"
        "2. Дождитесь обработки — бот пришлёт PNG-карточку и кнопку для просмотра в Mini App.\n"
        "3. Повторно отправленные реплеи загружаются мгновенно из кэша.",
    )
