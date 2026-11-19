import base64
from urllib.parse import quote

import httpx

from app.config import Settings
from app.domain.models import ParsedReplayBundle
from app.storage.base import ReplayStorage, StorageError, StoredReplay


class GitHubApiStorage(ReplayStorage):
    """Publishes replay JSON and minimap PNGs to a GitHub branch via Contents REST API."""

    API_BASE_URL = "https://api.github.com"

    def __init__(
        self,
        *,
        token: str,
        repo: str,
        branch: str = "gh-pages",
        data_prefix: str = "data",
        pages_base_url: str = "",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not token:
            raise StorageError("GITHUB_TOKEN is required for GitHubApiStorage")
        if "/" not in repo or not all(part.strip() for part in repo.split("/", 1)):
            raise StorageError(f"Invalid GITHUB_REPO format '{repo}'; expected 'owner/repo'")

        self.token = token
        self.repo = repo.strip("/")
        self.branch = branch
        self.data_prefix = data_prefix.strip("/")
        self.pages_base_url = pages_base_url.rstrip("/")

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.API_BASE_URL,
            timeout=timeout,
            headers=self._build_headers(),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "GitHubApiStorage":
        return cls(
            token=settings.github_token,
            repo=settings.github_repo,
            branch=settings.github_branch,
            data_prefix=settings.github_data_prefix,
            pages_base_url=settings.mini_app_url,
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def __aenter__(self) -> "GitHubApiStorage":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _join_prefix(self, *parts: str) -> str:
        clean_parts = [p.strip("/") for p in parts if p and p.strip("/")]
        if self.data_prefix:
            return "/".join([self.data_prefix, *clean_parts])
        return "/".join(clean_parts)

    def replay_json_path(self, replay_id: str) -> str:
        return self._join_prefix("replays", f"{replay_id}.json")

    def minimap_path(self, minimap_filename: str) -> str:
        return self._join_prefix("minimaps", minimap_filename)

    def public_url(self, repo_path: str) -> str:
        clean_path = repo_path.lstrip("/")
        if self.pages_base_url:
            return f"{self.pages_base_url}/{clean_path}"
        return f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{clean_path}"

    def _contents_endpoint(self, repo_path: str) -> str:
        encoded_path = quote(repo_path.lstrip("/"), safe="/")
        return f"/repos/{self.repo}/contents/{encoded_path}"

    async def _get_file_sha(self, repo_path: str) -> str | None:
        endpoint = self._contents_endpoint(repo_path)
        try:
            response = await self._client.get(
                endpoint,
                params={"ref": self.branch},
                headers=self._build_headers(),
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"GitHub GET failed for {repo_path}: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise StorageError(
                f"GitHub GET {repo_path} returned {response.status_code}: {response.text}"
            )

        payload = response.json()
        sha = payload.get("sha")
        if not isinstance(sha, str) or not sha:
            raise StorageError(f"Unexpected GitHub GET response for {repo_path}: missing sha")
        return sha

    async def _put_file(
        self,
        repo_path: str,
        content: bytes,
        *,
        message: str,
        sha: str | None = None,
    ) -> None:
        endpoint = self._contents_endpoint(repo_path)
        body: dict[str, str] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        if sha is not None:
            body["sha"] = sha

        try:
            response = await self._client.put(
                endpoint,
                json=body,
                headers=self._build_headers(),
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"GitHub PUT failed for {repo_path}: {exc}") from exc

        if response.status_code not in (200, 201):
            raise StorageError(
                f"GitHub PUT {repo_path} returned {response.status_code}: {response.text}"
            )

    async def exists(self, replay_id: str) -> bool:
        path = self.replay_json_path(replay_id)
        return (await self._get_file_sha(path)) is not None

    async def save_replay(
        self,
        bundle: ParsedReplayBundle,
        *,
        overwrite: bool = False,
    ) -> StoredReplay:
        meta = bundle.data.meta
        json_repo_path = self.replay_json_path(meta.replay_id)

        # Sequential PUTs prevent 409 branch-head conflicts on GitHub Contents API.
        json_sha = await self._get_file_sha(json_repo_path)
        json_uploaded = False
        if json_sha is None or overwrite:
            json_bytes = bundle.data.model_dump_json().encode("utf-8")
            await self._put_file(
                json_repo_path,
                json_bytes,
                message=f"chore(replays): add {meta.replay_id} ({meta.map_name})",
                sha=json_sha,
            )
            json_uploaded = True

        minimap_repo_path: str | None = None
        minimap_public_url: str | None = None
        minimap_uploaded = False

        if bundle.minimap_png:
            minimap_repo_path = self.minimap_path(meta.minimap_filename)
            minimap_public_url = self.public_url(minimap_repo_path)
            minimap_sha = await self._get_file_sha(minimap_repo_path)
            if minimap_sha is None:
                await self._put_file(
                    minimap_repo_path,
                    bundle.minimap_png,
                    message=f"chore(minimaps): add {meta.minimap_filename}",
                )
                minimap_uploaded = True

        return StoredReplay(
            replay_id=meta.replay_id,
            json_path=json_repo_path,
            json_url=self.public_url(json_repo_path),
            minimap_path=minimap_repo_path,
            minimap_url=minimap_public_url,
            json_uploaded=json_uploaded,
            minimap_uploaded=minimap_uploaded,
        )
