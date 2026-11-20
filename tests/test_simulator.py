import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest
import sc2reader

from app.domain.models import ReplayData
from app.parser.command_tracker import UnitCommand
from app.parser.nav_grid import NavGrid
from app.parser.replay_parser import parse_replay_file
from app.parser.simulator import FRAMES_PER_REAL_SEC, simulate_match, simulate_replay

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


@dataclass
class _DummyOwner:
    pid: int


@dataclass
class _DummyUnit:
    id: int
    name: str
    owner: _DummyOwner
    location: tuple[float, float]

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class UnitBornEvent:
    frame: int
    unit: _DummyUnit
    location: tuple[float, float]


@dataclass
class UnitPositionsEvent:
    frame: int
    units: dict[_DummyUnit, tuple[float, float]] = field(default_factory=dict)


@dataclass
class UnitDiedEvent:
    frame: int
    unit: _DummyUnit
    location: tuple[float, float]


def test_simulator_wall_avoidance_and_smooth_anchor_convergence():
    walkable = np.ones((40, 40), dtype=bool)
    # Vertical wall at x = 20 from y = 0..27, leaving a gap at y = 28..39
    walkable[0:28, 20] = False
    nav_grid = NavGrid(walkable, cell_size=1)

    p1 = _DummyOwner(pid=1)
    marine = _DummyUnit(id=101, name="Marine", owner=p1, location=(10.0, 10.0))

    anchor_frame = int(round(15.0 * FRAMES_PER_REAL_SEC))
    events = [
        UnitBornEvent(frame=0, unit=marine, location=(10.0, 10.0)),
        UnitPositionsEvent(frame=anchor_frame, units={marine: (30.5, 10.5)}),
    ]
    commands = [
        UnitCommand(
            frame=int(round(0.5 * FRAMES_PER_REAL_SEC)),
            pid=1,
            unit_ids=(101,),
            action="move",
            target_x=30.0,
            target_y=10.0,
        )
    ]

    sim = simulate_match(
        duration_sec=16,
        tracker_events=events,
        commands=commands,
        nav_grid=nav_grid,
        map_width=40.0,
        map_height=40.0,
        dt=0.5,
    )

    positions: list[tuple[float, float]] = []
    for sec_half in range(0, 31):  # t = 0.0 .. 15.0s in 0.5s steps
        frame = int(round((sec_half * 0.5) * FRAMES_PER_REAL_SEC))
        pos = sim.get_unit_pos(101, frame)
        assert pos is not None
        positions.append(pos)

    # Marine must go around the wall (y >= 27.5) rather than clipping through x=20, y=10
    assert max(p[1] for p in positions) >= 27.0

    # Smoothness: no 10.7s teleport; max step displacement is bounded
    step_dists = [
        math.hypot(positions[i + 1][0] - positions[i][0], positions[i + 1][1] - positions[i][1])
        for i in range(len(positions) - 1)
    ]
    assert max(step_dists) < 4.0

    # Arrives smoothly at the anchor at t = 12.0s
    end_pos = sim.get_unit_pos(101, anchor_frame)
    assert end_pos is not None
    assert math.hypot(end_pos[0] - 30.5, end_pos[1] - 10.5) < 0.2


def test_simulator_medivac_load_boost_and_unload():
    walkable = np.ones((50, 50), dtype=bool)
    nav_grid = NavGrid(walkable, cell_size=1)

    p1 = _DummyOwner(pid=1)
    marine = _DummyUnit(id=201, name="Marine", owner=p1, location=(10.0, 10.0))
    medivac = _DummyUnit(id=202, name="Medivac", owner=p1, location=(11.0, 10.0))

    events = [
        UnitBornEvent(frame=0, unit=marine, location=(10.0, 10.0)),
        UnitBornEvent(frame=0, unit=medivac, location=(11.0, 10.0)),
    ]
    commands = [
        UnitCommand(
            frame=int(round(0.5 * FRAMES_PER_REAL_SEC)),
            pid=1,
            unit_ids=(201,),
            action="load",
            target_uid=202,
        ),
        UnitCommand(
            frame=int(round(1.0 * FRAMES_PER_REAL_SEC)),
            pid=1,
            unit_ids=(202,),
            action="medivac_boost",
        ),
        UnitCommand(
            frame=int(round(1.0 * FRAMES_PER_REAL_SEC)),
            pid=1,
            unit_ids=(202,),
            action="unload_at",
            target_x=30.0,
            target_y=10.0,
        ),
    ]

    sim = simulate_match(
        duration_sec=8,
        tracker_events=events,
        commands=commands,
        nav_grid=nav_grid,
        map_width=50.0,
        map_height=50.0,
        dt=0.5,
    )

    mid_frame = int(round(2.5 * FRAMES_PER_REAL_SEC))
    assert sim.is_in_cargo(201, mid_frame)
    m_pos = sim.get_unit_pos(201, mid_frame)
    med_pos = sim.get_unit_pos(202, mid_frame)
    assert m_pos is not None and med_pos is not None
    assert math.hypot(m_pos[0] - med_pos[0], m_pos[1] - med_pos[1]) < 0.01

    end_frame = int(round(7.0 * FRAMES_PER_REAL_SEC))
    assert not sim.is_in_cargo(201, end_frame)
    drop_pos = sim.get_unit_pos(201, end_frame)
    assert drop_pos is not None
    assert math.hypot(drop_pos[0] - 30.0, drop_pos[1] - 10.0) <= 2.5


def test_simulator_blink_teleport():
    walkable = np.ones((40, 40), dtype=bool)
    nav_grid = NavGrid(walkable, cell_size=1)
    p1 = _DummyOwner(pid=1)
    stalker = _DummyUnit(id=301, name="Stalker", owner=p1, location=(5.0, 5.0))

    events = [UnitBornEvent(frame=0, unit=stalker, location=(5.0, 5.0))]
    commands = [
        UnitCommand(
            frame=int(round(2.0 * FRAMES_PER_REAL_SEC)),
            pid=1,
            unit_ids=(301,),
            action="blink",
            target_x=13.0,
            target_y=5.0,
        )
    ]

    sim = simulate_match(
        duration_sec=4,
        tracker_events=events,
        commands=commands,
        nav_grid=nav_grid,
        map_width=40.0,
        map_height=40.0,
        dt=0.5,
    )

    before = sim.get_unit_pos(301, int(round(1.0 * FRAMES_PER_REAL_SEC)))
    after = sim.get_unit_pos(301, int(round(2.5 * FRAMES_PER_REAL_SEC)))
    assert before == pytest.approx((5.0, 5.0), abs=0.1)
    assert after == pytest.approx((13.0, 5.0), abs=0.1)


def test_simulator_attack_move_stops_at_range_and_resumes_after_kill():
    walkable = np.ones((40, 40), dtype=bool)
    nav_grid = NavGrid(walkable, cell_size=1)
    p1 = _DummyOwner(pid=1)
    p2 = _DummyOwner(pid=2)

    def _run(action: str) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        marine = _DummyUnit(id=401, name="Marine", owner=p1, location=(10.0, 10.0))
        enemy = _DummyUnit(id=402, name="Roach", owner=p2, location=(20.0, 10.0))
        events = [
            UnitBornEvent(frame=0, unit=marine, location=(10.0, 10.0)),
            UnitBornEvent(frame=0, unit=enemy, location=(20.0, 10.0)),
            UnitDiedEvent(
                frame=int(round(4.0 * FRAMES_PER_REAL_SEC)),
                unit=enemy,
                location=(20.0, 10.0),
            ),
        ]
        commands = [
            UnitCommand(
                frame=int(round(0.5 * FRAMES_PER_REAL_SEC)),
                pid=1,
                unit_ids=(401,),
                action=action,
                target_x=30.0,
                target_y=10.0,
            )
        ]
        sim = simulate_match(
            duration_sec=10,
            tracker_events=events,
            commands=commands,
            nav_grid=nav_grid,
            map_width=40.0,
            map_height=40.0,
            dt=0.5,
        )
        mid = sim.get_unit_pos(401, int(round(4.0 * FRAMES_PER_REAL_SEC)))
        end = sim.get_unit_pos(401, int(round(9.0 * FRAMES_PER_REAL_SEC)))
        return mid, end

    move_mid, _ = _run("move")
    atk_mid, atk_end = _run("attack_move")

    assert move_mid is not None and atk_mid is not None and atk_end is not None
    # On "move", Marine ignores enemy at x=20 and walks past it by t=4.0s
    assert move_mid[0] > 20.0
    # On "attack_move", Marine stops around attack range (5.0 tiles from x=20 -> x ~ 15)
    assert 13.5 <= atk_mid[0] <= 17.0
    # After enemy dies at t=4.0s, attack_move Marine resumes toward x=30
    assert atk_end[0] > 22.0


@pytest.mark.parametrize(
    "filename",
    [
        "Blackburn LE (9) ZergCheese.SC2Replay",
        "2000 атмосфер РВ (15).SC2Replay",
        "Беккетт Индастриз РВ (42).SC2Replay",
    ],
)
def test_simulator_real_replays_performance_and_bounds(filename: str):
    replay_path = FILES_DIR / filename
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    replay = sc2reader.load_replay(str(replay_path), load_level=4)
    map_info = getattr(getattr(replay, "map", None), "map_info", None)
    map_w = float(getattr(map_info, "width", 200) or 200)
    map_h = float(getattr(map_info, "height", 200) or 200)

    t0 = time.perf_counter()
    sim = simulate_replay(replay, dt=0.5)
    elapsed = time.perf_counter() - t0

    assert elapsed < 2.0, f"Simulation took too long: {elapsed:.2f}s"
    assert len(sim.tracks) > 0

    for track in sim.tracks.values():
        assert len(track.xs) == len(track.ys)
        for x, y in zip(track.xs, track.ys):
            assert math.isfinite(x) and math.isfinite(y)
            assert 0.0 <= x <= map_w
            assert 0.0 <= y <= map_h

    # Verify full parse_replay_file integration preserves ReplayData
    bundle = parse_replay_file(replay_path)
    data = bundle.data
    assert isinstance(data, ReplayData)
    assert len(data.frames) > 10
    assert len(data.deaths) > 0
    for d in data.deaths:
        if d[10] is not None and d[11] is not None:
            dist = math.hypot(d[4] - d[10], d[5] - d[11])
            assert dist <= 20.0
