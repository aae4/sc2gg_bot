from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.domain.models import ParsedReplayBundle


class StorageError(Exception):
    """Raised when storing or checking replay artifacts fails."""


class StoredReplay(BaseModel):
    replay_id: str
    json_path: str
    json_url: str
    minimap_path: str | None = None
    minimap_url: str | None = None
    json_uploaded: bool = False
    minimap_uploaded: bool = False


class ReplayStorage(ABC):
    """Abstract storage interface for publishing parsed replay JSON and minimaps."""

    @abstractmethod
    async def save_replay(
        self,
        bundle: ParsedReplayBundle,
        *,
        overwrite: bool = False,
    ) -> StoredReplay:
        """Persist replay JSON and minimap (if present), returning public metadata."""

    @abstractmethod
    async def exists(self, replay_id: str) -> bool:
        """Check whether the replay JSON already exists in storage."""
