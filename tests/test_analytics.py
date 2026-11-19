from pathlib import Path

from app.bot.handlers.replays import format_replay_caption
from app.domain.models import BuildOrderItem
from app.parser.analytics import (
    compute_spending_quotient,
    compute_supply_block_sec,
    detect_build_archetype,
    extract_key_timings,
)
from app.parser.replay_parser import parse_replay_file
from app.renderer.summary_card import render_summary_card


def test_compute_spending_quotient():
    assert compute_spending_quotient(avg_unspent=500, avg_income=0) == 0
    sq_good = compute_spending_quotient(avg_unspent=200, avg_income=2000)
    sq_poor = compute_spending_quotient(avg_unspent=2000, avg_income=2000)
    assert sq_good > sq_poor
    assert sq_good > 80


def test_compute_supply_block_sec():
    samples = [
        (10, 12, 12),   # ignored (<30s)
        (40, 22, 22),   # blocked for 10s (40->50)
        (50, 22, 30),   # unblocked
        (100, 46, 46),  # blocked for 10s (100->110)
        (110, 46, 54),  # unblocked
        (600, 200, 200),  # ignored (max supply)
        (610, 200, 200),
    ]
    assert compute_supply_block_sec(samples) == 20


def test_extract_key_timings_and_archetype():
    bo_zerg = [
        BuildOrderItem(time_sec=50, pid=1, name="Hatchery", kind="building"),
        BuildOrderItem(time_sec=75, pid=1, name="SpawningPool", kind="building"),
        BuildOrderItem(time_sec=210, pid=1, name="Hatchery", kind="building"),
    ]
    timings = extract_key_timings(bo_zerg, pid=1, race="Zerg")
    assert timings["natural"] == 50
    assert timings["third"] == 210
    assert timings["pool"] == 75
    assert detect_build_archetype(bo_zerg, pid=1, race="Zerg", key_timings=timings) == "3-Base Macro"

    bo_terran = [
        BuildOrderItem(time_sec=45, pid=2, name="Barracks", kind="building"),
        BuildOrderItem(time_sec=110, pid=2, name="CommandCenter", kind="building"),
        BuildOrderItem(time_sec=150, pid=2, name="Barracks", kind="building"),
        BuildOrderItem(time_sec=210, pid=2, name="Starport", kind="building"),
    ]
    t_timings = extract_key_timings(bo_terran, pid=2, race="Terran")
    assert t_timings["natural"] == 110
    assert t_timings["starport"] == 210
    assert detect_build_archetype(bo_terran, pid=2, race="Terran", key_timings=t_timings) == "2-1-1 Bio"


def test_real_replay_analytics_and_card():
    replay_path = next(Path("files").glob("*.SC2Replay"))
    bundle = parse_replay_file(replay_path)
    for p in bundle.data.players:
        assert p.spending_quotient > 0
        assert p.supply_block_sec >= 0
        assert p.workers_killed >= 0
        assert p.workers_lost >= 0
        assert p.avg_unspent >= 0
        assert p.build_archetype != ""

    card_bytes = render_summary_card(bundle.data)
    assert card_bytes.startswith(b"\x89PNG")

    caption = format_replay_caption(bundle.data)
    assert "SQ" in caption
    assert "блок" in caption
