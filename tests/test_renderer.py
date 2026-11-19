from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from app.domain.models import (
    BattleEvent,
    ChartSeries,
    MatchMeta,
    PlayerInfo,
    ReplayData,
)
from app.parser.replay_parser import parse_replay_file
from app.renderer.summary_card import (
    CARD_HEIGHT,
    CARD_WIDTH,
    render_summary_card,
    render_summary_card_async,
)

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def test_render_summary_card_synthetic_cyrillic_and_missing_icons(tmp_path: Path):
    data = ReplayData(
        meta=MatchMeta(
            replay_id="deadbeef1234",
            sha256="deadbeef1234" + "0" * 52,
            map_name="2000 атмосфер РВ",
            map_width=176,
            map_height=184,
            minimap_filename="2000_atmosfer.png",
            duration_sec=542,
            version="5.0.17.98310",
            played_at="2026-11-19T10:00:00+00:00",
        ),
        players=[
            PlayerInfo(
                pid=1,
                name="ИгрокПервыйОченьДлинныйНикнейм",
                race="Protoss",
                color_hex="#0042FF",
                result="Win",
                apm=145,
                workers_peak=72,
                army_value_peak=4200,
                minerals_lost=1200,
                vespene_lost=600,
            ),
            PlayerInfo(
                pid=2,
                name="ИгрокВторой",
                race="Terran",
                color_hex="#B4141E",
                result="Loss",
                apm=118,
                workers_peak=61,
                army_value_peak=3100,
                minerals_lost=2800,
                vespene_lost=950,
            ),
        ],
        unit_dict={},
        frames=[],
        battles=[
            BattleEvent(start_sec=240, end_sec=265, x=80.0, y=90.0, winner_pid=1),
        ],
        build_order=[],
        charts=ChartSeries(
            times_sec=[0, 120, 240, 360, 480],
            army_value={1: [0, 400, 1800, 3200, 4200], 2: [0, 500, 1600, 2100, 1500]},
            workers={1: [12, 28, 48, 66, 72], 2: [12, 26, 44, 58, 61]},
        ),
    )

    png_bytes = render_summary_card(data, icons_dir=tmp_path)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)


async def test_render_summary_card_real_replay():
    replay_path = FILES_DIR / "10000 Feet LE (4).SC2Replay"
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    bundle = parse_replay_file(replay_path)
    png_bytes = await render_summary_card_async(bundle.data)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 20_000
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)
