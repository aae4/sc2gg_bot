from pathlib import Path

import pytest
import sc2reader

from app.parser.replay_parser import IGNORED_UNIT_NAMES
from app.parser.unit_specs import (
    UNIT_SPECS,
    can_load_into,
    get_effective_max_hp,
    get_effective_range,
    get_effective_speed,
    get_unit_spec,
)

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def test_basic_unit_lookup_and_aliases():
    marine = get_unit_spec("Marine")
    assert marine is not None
    assert marine.speed == pytest.approx(3.15)
    assert marine.is_flying is False
    assert marine.cargo_size == 1

    viking = get_unit_spec("VikingFighter")
    assert viking is not None
    assert viking.name == "Viking"
    assert viking.is_flying is True

    sieged = get_unit_spec("SiegeTankSieged")
    assert sieged is not None
    assert sieged.speed == 0.0
    assert sieged.attack_range == 13.0

    assert get_unit_spec("NonExistentUnit") is None


def test_effective_speed_upgrades_stim_and_creep():
    # Zergling with sc2reader upgrade alias
    assert get_effective_speed("Zergling") == pytest.approx(4.13)
    assert get_effective_speed("Zergling", {"zerglingmovementspeed"}) == pytest.approx(6.58)
    assert get_effective_speed("Zergling", {"zerglingmovementspeed"}, on_creep=True) == pytest.approx(
        6.58 * 1.3, rel=1e-3
    )

    # Queen on vs off creep
    assert get_effective_speed("Queen", on_creep=False) == pytest.approx(1.31)
    assert get_effective_speed("Queen", on_creep=True) == pytest.approx(1.31 * 2.67, rel=1e-2)

    # Marine stimmed
    assert get_effective_speed("Marine", is_stimmed=True) == pytest.approx(3.15 * 1.5, rel=1e-3)
    # Stim does not boost SiegeTank
    assert get_effective_speed("SiegeTank", is_stimmed=True) == pytest.approx(3.15)

    # Medivac boost
    assert get_effective_speed("Medivac") == pytest.approx(3.50)
    assert get_effective_speed("Medivac", is_medivac_boosted=True) == pytest.approx(5.94)

    # Sieged tank cannot move even on creep
    assert get_effective_speed("SiegeTankSieged", on_creep=True) == 0.0


def test_effective_range_and_hp():
    assert get_effective_range("Colossus") == pytest.approx(7.0)
    assert get_effective_range("Colossus", {"ExtendedThermalLance"}) == pytest.approx(9.0)
    assert get_effective_range("Phoenix", {"PhoenixRangeUpgrade"}) == pytest.approx(7.0)

    assert get_effective_max_hp("Marine") == pytest.approx(45.0)
    assert get_effective_max_hp("Marine", {"ShieldWall"}) == pytest.approx(55.0)


def test_transport_compatibility():
    assert can_load_into("Marine", "Medivac") is True
    assert can_load_into("SiegeTank", "Medivac") is True
    assert can_load_into("Marine", "Bunker") is True
    assert can_load_into("SiegeTank", "Bunker") is False
    assert can_load_into("Marine", "WarpPrism") is False
    assert can_load_into("Immortal", "WarpPrism") is True
    assert can_load_into("Colossus", "WarpPrism") is False
    assert can_load_into("Zergling", "OverlordTransport") is True
    assert can_load_into("Zergling", "Overlord") is False


@pytest.mark.parametrize(
    "filename",
    [
        "Blackburn LE (9) ZergCheese.SC2Replay",
        "2000 атмосфер РВ (15).SC2Replay",
        "Беккетт Индастриз РВ (42).SC2Replay",
    ],
)
def test_all_replay_army_and_worker_units_have_specs(filename: str):
    replay_path = FILES_DIR / filename
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    replay = sc2reader.load_replay(str(replay_path), load_level=3)
    missing: set[str] = set()
    for unit in replay.objects.values():
        if not (getattr(unit, "is_army", False) or getattr(unit, "is_worker", False)):
            continue
        if unit.name in IGNORED_UNIT_NAMES or unit.name == "Locust":
            continue
        if get_unit_spec(unit.name) is None:
            missing.add(unit.name)

    assert not missing, f"Missing UnitSpec entries for: {sorted(missing)}"
    assert len(UNIT_SPECS) > 50
