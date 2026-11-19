from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """12-Factor application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = False

    # Telegram Bot
    bot_token: str
    mini_app_url: str = ""
    mini_app_short_name: str = ""

    # GitHub REST API Storage (for replay JSONs)
    github_token: str = ""
    github_repo: str = ""      # e.g. "owner/repo"
    github_branch: str = "gh-pages"
    github_data_prefix: str = "data"

    # Local runtime directory (SQLite cache, temp files)
    data_dir: Path = BASE_DIR / "data"

    # Optional external APIs
    blizzard_client_id: str = ""
    blizzard_client_secret: str = ""
    youtube_api_key: str = ""

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "bot.sqlite"

    @property
    def temp_replays_dir(self) -> Path:
        return self.data_dir / "tmp"


settings = Settings()
