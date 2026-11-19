from pathlib import Path
import pytest

from app.domain.models import ReplayData
from app.parser.battles import UnitDeathRecord, detect_battles
from app.parser.replay_parser import ReplayParseError, parse_replay_async, parse_replay_file


FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def test_detect_battles_clusters_and_picks_winner():
    deaths = [
        UnitDeathRecord(time_sec=100, pid=1, unit_name="Zergling", x=50.0, y=50.0, minerals=25, vespene=0),
        UnitDeathRecord(time_sec=102, pid=1, unit_name="Roach", x=52.0, y=51.0, minerals=75, vespene=25),
        UnitDeathRecord(time_sec=104, pid=2, unit_name="Stalker", x=53.0, y=52.0, minerals=125, vespene=50),
        UnitDeathRecord(time_sec=105, pid=2, unit_name="Stalker", x=54.0, y=51.0, minerals=125, vespene=50),
        # Separate small skirmish too cheap to be a battle
        UnitDeathRecord(time_sec=200, pid=1, unit_name="Zergling", x=120.0, y=120.0, minerals=25, vespene=0),
    ]

    battles = detect_battles(deaths)
    assert len(battles) == 1
    b = battles[0]
    assert b.start_sec == 100
    assert b.end_sec == 105
    assert b.lost_minerals[1] == 100
    assert b.lost_minerals[2] == 250
    assert b.winner_pid == 1


def test_parse_missing_file_raises():
    with pytest.raises(ReplayParseError):
        parse_replay_file(Path("non_existent_file.SC2Replay"))


@pytest.mark.parametrize(
    "filename",
    [
        "Blackburn LE (9) ZergCheese.SC2Replay",
        "2000 атмосфер РВ (15).SC2Replay",
        "Беккетт Индастриз РВ (42).SC2Replay",
    ],
)
def test_parse_real_replays_compact_json(filename: str):
    replay_path = FILES_DIR / filename
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    bundle = parse_replay_file(replay_path)
    data = bundle.data

    assert isinstance(data, ReplayData)
    assert len(data.meta.replay_id) == 12
    assert len(data.players) == 2
    assert all(p.race in {"Zerg", "Terran", "Protoss"} for p in data.players)
    assert len(data.frames) > 10
    assert len(data.unit_dict) > 0
    assert len(data.deaths) > 0
    sample_death = data.deaths[0]
    assert len(sample_death) == 12
    assert isinstance(sample_death[0], (int, float))
    assert sample_death[3] in data.unit_dict
    for d in data.deaths:
        if d[10] is not None and d[11] is not None:
            dist = ((d[4] - d[10]) ** 2 + (d[5] - d[11]) ** 2) ** 0.5
            assert dist <= 20.0, f"Bogus killer tracer dist={dist}"
    assert len(data.ability_dict) > 0
    assert len(data.ability_casts) > 0
    sample_cast = data.ability_casts[0]
    assert len(sample_cast) == 5
    assert isinstance(sample_cast[0], (int, float))
    assert sample_cast[1] in {p.pid for p in data.players}
    assert sample_cast[2] in data.ability_dict
    assert (sample_cast[3] is None and sample_cast[4] is None) or (
        isinstance(sample_cast[3], (int, float)) and isinstance(sample_cast[4], (int, float))
    )
    assert all(
        data.ability_casts[i][0] <= data.ability_casts[i + 1][0]
        for i in range(len(data.ability_casts) - 1)
    )
    assert len(data.charts.times_sec) > 5
    assert bundle.minimap_png is not None and len(bundle.minimap_png) > 1000

    json_bytes = data.model_dump_json().encode("utf-8")
    assert len(json_bytes) < 500_000, f"JSON too large: {len(json_bytes)} bytes"


async def test_parse_replay_async():
    replay_path = FILES_DIR / "Blackburn LE (9) ZergCheese.SC2Replay"
    if not replay_path.is_file():
        pytest.skip("Sample replay missing")

    bundle = await parse_replay_async(replay_path)
    assert bundle.data.meta.map_name == "Blackburn LE"
