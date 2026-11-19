import base64
import json

import httpx
import pytest

from app.domain.models import (
    ChartSeries,
    MatchMeta,
    ParsedReplayBundle,
    PlayerInfo,
    ReplayData,
)
from app.storage.base import StorageError
from app.storage.github_api import GitHubApiStorage


def _sample_bundle() -> ParsedReplayBundle:
    data = ReplayData(
        meta=MatchMeta(
            replay_id="abc123def456",
            sha256="abc123def456" + "0" * 52,
            map_name="10000 Feet LE",
            map_width=176,
            map_height=184,
            minimap_filename="10000_Feet_LE.png",
            duration_sec=716,
            version="5.0.17.98310",
            played_at="2026-11-19T05:26:12+00:00",
        ),
        players=[
            PlayerInfo(pid=1, name="Papillon", race="Zerg", color_hex="#B4141E", result="Win"),
            PlayerInfo(pid=2, name="Opponent", race="Terran", color_hex="#0042FF", result="Loss"),
        ],
        unit_dict={1: "Drone"},
        frames=[],
        battles=[],
        build_order=[],
        charts=ChartSeries(times_sec=[0, 10], army_value={1: [0, 100], 2: [0, 50]}, workers={1: [12, 14], 2: [12, 13]}),
    )
    return ParsedReplayBundle(data=data, minimap_png=b"\x89PNG\r\n\x1a\nFAKE_MINIMAP")


def test_github_storage_validates_config():
    with pytest.raises(StorageError, match="GITHUB_TOKEN"):
        GitHubApiStorage(token="", repo="owner/repo")

    with pytest.raises(StorageError, match="GITHUB_REPO"):
        GitHubApiStorage(token="tok", repo="invalid_repo")


async def test_save_replay_uploads_json_and_minimap_when_missing():
    requests_log: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        requests_log.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "PUT":
            return httpx.Response(201, json={"content": {"sha": "newsha"}})
        return httpx.Response(405)

    client = httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    storage = GitHubApiStorage(
        token="secret-token",
        repo="user/sc2gg",
        branch="gh-pages",
        data_prefix="data",
        pages_base_url="https://user.github.io/sc2gg/",
        client=client,
    )

    bundle = _sample_bundle()
    result = await storage.save_replay(bundle)

    assert result.replay_id == "abc123def456"
    assert result.json_path == "data/replays/abc123def456.json"
    assert result.json_url == "https://user.github.io/sc2gg/data/replays/abc123def456.json"
    assert result.minimap_path == "data/minimaps/10000_Feet_LE.png"
    assert result.minimap_url == "https://user.github.io/sc2gg/data/minimaps/10000_Feet_LE.png"
    assert result.json_uploaded is True
    assert result.minimap_uploaded is True

    assert [m for m, _, _ in requests_log] == ["GET", "PUT", "GET", "PUT"]
    json_put_body = requests_log[1][2]
    assert json_put_body["branch"] == "gh-pages"
    assert "sha" not in json_put_body
    decoded_json = base64.b64decode(json_put_body["content"]).decode("utf-8")
    assert '"replay_id":"abc123def456"' in decoded_json

    minimap_put_body = requests_log[3][2]
    assert base64.b64decode(minimap_put_body["content"]) == bundle.minimap_png
    await client.aclose()


async def test_save_replay_skips_existing_minimap_and_respects_overwrite():
    requests_log: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        requests_log.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"sha": "existing_sha_123"})
        if request.method == "PUT":
            return httpx.Response(200, json={"content": {"sha": "updated_sha"}})
        return httpx.Response(405)

    client = httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    storage = GitHubApiStorage(token="tok", repo="user/sc2gg", client=client)

    bundle = _sample_bundle()
    # overwrite=False: both exist -> no PUTs at all
    res_skip = await storage.save_replay(bundle, overwrite=False)
    assert res_skip.json_uploaded is False
    assert res_skip.minimap_uploaded is False
    assert res_skip.json_url == "https://raw.githubusercontent.com/user/sc2gg/gh-pages/data/replays/abc123def456.json"
    assert [m for m, _, _ in requests_log] == ["GET", "GET"]

    requests_log.clear()
    # overwrite=True: JSON is updated with sha, minimap is still skipped
    res_overwrite = await storage.save_replay(bundle, overwrite=True)
    assert res_overwrite.json_uploaded is True
    assert res_overwrite.minimap_uploaded is False
    assert [m for m, _, _ in requests_log] == ["GET", "PUT", "GET"]
    assert requests_log[1][2]["sha"] == "existing_sha_123"
    await client.aclose()


async def test_exists_and_http_error_handling():
    def handler(request: httpx.Request) -> httpx.Response:
        if "missing" in request.url.path:
            return httpx.Response(404, json={"message": "Not Found"})
        if "boom" in request.url.path:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"sha": "abc"})

    client = httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    storage = GitHubApiStorage(token="tok", repo="user/sc2gg", client=client)

    assert await storage.exists("abc123def456") is True
    assert await storage.exists("missing") is False
    with pytest.raises(StorageError, match="500"):
        await storage.exists("boom")
    await client.aclose()
