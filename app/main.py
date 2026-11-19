import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import replays, start
from app.config import Settings, settings
from app.db.repository import DatabaseRepository
from app.storage.base import ReplayStorage
from app.storage.github_api import GitHubApiStorage

logger = logging.getLogger(__name__)


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def create_dispatcher(
    *,
    repo: DatabaseRepository,
    app_settings: Settings,
    storage: ReplayStorage | None = None,
    cards_dir: Path | None = None,
    bot_username: str = "",
) -> Dispatcher:
    dp = Dispatcher()
    dp["repo"] = repo
    dp["settings"] = app_settings
    dp["storage"] = storage
    dp["cards_dir"] = cards_dir or (app_settings.data_dir / "cards")
    dp["bot_username"] = bot_username

    dp.include_router(start.router)
    dp.include_router(replays.router)
    return dp


async def run_bot(app_settings: Settings = settings) -> None:
    configure_logging(app_settings.debug)

    repo = DatabaseRepository(app_settings.sqlite_path)
    await repo.connect()

    storage: GitHubApiStorage | None = None
    if app_settings.github_token and app_settings.github_repo:
        storage = GitHubApiStorage.from_settings(app_settings)
        logger.info("GitHubApiStorage enabled for %s (%s)", app_settings.github_repo, app_settings.github_branch)
    else:
        logger.warning("GITHUB_TOKEN or GITHUB_REPO is empty; replay JSON upload is disabled.")

    bot = Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        me = await bot.get_me()
        bot_username = me.username or ""
        logger.info("Starting polling as @%s", bot_username)

        dp = create_dispatcher(
            repo=repo,
            app_settings=app_settings,
            storage=storage,
            bot_username=bot_username,
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Shutting down bot resources...")
        if storage is not None:
            await storage.aclose()
        await repo.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
