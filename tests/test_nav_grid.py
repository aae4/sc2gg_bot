from __future__ import annotations

from pathlib import Path
import struct
import time
from types import SimpleNamespace
import urllib.error

import numpy as np
import pytest
import sc2reader

from app.parser.nav_grid import NavGrid

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def _assert_path_is_walkable(grid: NavGrid, path: list[tuple[float, float]]) -> None:
    assert len(path) >= 1
    for x, y in path:
        assert grid.is_walkable(x, y), f"Waypoint ({x}, {y}) is not walkable"
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        gx0, gy0 = grid.world_to_grid(x0, y0)
        gx1, gy1 = grid.world_to_grid(x1, y1)
        assert grid._has_line_of_sight(gx0, gy0, gx1, gy1), (
            f"Segment ({gx0}, {gy0}) -> ({gx1}, {gy1}) crosses unwalkable cell or corner"
        )


def test_l_shaped_wall_avoidance_and_smoothing():
    walkable = np.ones((20, 20), dtype=bool)
    # L-shaped wall blocking direct diagonal from (2, 2) to (16, 16)
    walkable[4:14, 10] = False
    walkable[13, 4:11] = False

    grid = NavGrid(walkable, cell_size=1)
    path = grid.find_path(2.5, 2.5, 16.5, 16.5)

    _assert_path_is_walkable(grid, path)
    assert path[0] == (2.5, 2.5)
    assert path[-1] == (16.5, 16.5)
    # Smoothed path should only need a few corner waypoints, far fewer than ~28 grid steps
    assert 3 <= len(path) <= 6


def test_u_shaped_wall_avoidance():
    walkable = np.ones((24, 24), dtype=bool)
    # U-shaped trap facing left; start is inside the U at (10, 12), goal is to the right at (18, 12)
    walkable[6:19, 14] = False  # back wall
    walkable[6, 7:15] = False   # bottom arm
    walkable[18, 7:15] = False  # top arm

    grid = NavGrid(walkable, cell_size=1)
    path = grid.find_path(10.5, 12.5, 18.5, 12.5)

    _assert_path_is_walkable(grid, path)
    assert path[0] == (10.5, 12.5)
    assert path[-1] == (18.5, 12.5)
    # Must exit to the left (x < 7) before wrapping around
    assert any(x < 7.0 for x, _ in path)


def test_diagonal_no_corner_cutting():
    walkable = np.ones((6, 6), dtype=bool)
    # Diagonal barrier from (2, 3) to (3, 2):
    # A unit at (2, 2) must NOT cut diagonally to (3, 3)
    walkable[3, 2] = False
    walkable[2, 3] = False

    grid = NavGrid(walkable, cell_size=1)
    path = grid.find_path(2.5, 2.5, 3.5, 3.5)

    # Cannot reach (3, 3) directly; must go around via (1, 2)->(1, 3)->(1, 4)->(2, 4)->(3, 4)->(3, 3) or similar
    _assert_path_is_walkable(grid, path)
    assert path[0] == (2.5, 2.5)
    assert path[-1] == (3.5, 3.5)
    assert len(path) >= 3

    # Also test single-corner clipping: blocked at (2, 3) only
    walkable2 = np.ones((6, 6), dtype=bool)
    walkable2[3, 2] = False
    grid2 = NavGrid(walkable2, cell_size=1)
    path2 = grid2.find_path(2.5, 2.5, 3.5, 3.5)
    _assert_path_is_walkable(grid2, path2)
    # Direct 2-point diagonal from (2,2) to (3,3) is forbidden because (2,3) is blocked
    assert len(path2) >= 3


def test_smoothing_open_grid_collapses_to_two_points():
    walkable = np.ones((30, 30), dtype=bool)
    grid = NavGrid(walkable, cell_size=1)
    path = grid.find_path(1.2, 2.3, 27.8, 24.6)
    assert path == [(1.2, 2.3), (27.8, 24.6)]


def test_lru_cache_hits_and_eviction():
    walkable = np.ones((20, 20), dtype=bool)
    walkable[5:15, 10] = False
    grid = NavGrid(walkable, cell_size=2, cache_size=2)

    p1 = grid.find_path(2.2, 10.1, 18.4, 10.2)
    assert grid.cache_misses == 1
    assert grid.cache_hits == 0

    # Different exact float coordinates inside the same 2x2 cells -> cache hit!
    p2 = grid.find_path(2.8, 10.9, 18.9, 10.7)
    assert grid.cache_misses == 1
    assert grid.cache_hits == 1
    assert p2[0] == (2.8, 10.9)
    assert p2[-1] == (18.9, 10.7)
    assert p1 is not p2

    # Fill cache beyond cache_size=2 to verify LRU eviction
    grid.find_path(0.5, 0.5, 18.5, 18.5)
    grid.find_path(0.5, 2.5, 18.5, 16.5)
    assert len(grid._cache) == 2

    grid.clear_cache()
    assert grid.cache_hits == 0
    assert grid.cache_misses == 0
    assert len(grid._cache) == 0


def test_is_walkable_and_find_nearest_walkable():
    walkable = np.ones((10, 10), dtype=bool)
    walkable[3:7, 3:7] = False
    grid = NavGrid(walkable, cell_size=1)

    assert grid.is_walkable(0.5, 0.5) is True
    assert grid.is_walkable(5.0, 5.0) is False
    assert grid.is_walkable(-1.0, 5.0) is False
    assert grid.is_walkable(10.0, 5.0) is False

    nx, ny = grid.find_nearest_walkable(4.5, 3.2)
    assert grid.is_walkable(nx, ny) is True
    assert ny < 3.0  # nearest edge of the 3..6 block is y=2.5


def test_unreachable_goal_returns_nearest_reachable_within_limit():
    walkable = np.ones((30, 30), dtype=bool)
    # Completely enclose (25, 25) in a box
    walkable[20:29, 20] = False
    walkable[20:29, 28] = False
    walkable[20, 20:29] = False
    walkable[28, 20:29] = False

    grid = NavGrid(walkable, cell_size=1, max_iterations=500)
    path = grid.find_path(2.5, 2.5, 25.5, 25.5)

    _assert_path_is_walkable(grid, path)
    assert path[0] == (2.5, 2.5)
    # Should stop near the outside of the box rather than inside it
    end_gx, end_gy = grid.world_to_grid(*path[-1])
    assert not (20 < end_gx < 28 and 20 < end_gy < 28)


def test_from_replay_synthetic_cliffs_ramps_and_bounds():
    w, h = 128, 128
    # High ground island in center (cliff=128) surrounded by low ground (cliff=64)
    cliff_vals = [128 if (40 <= x < 88 and 40 <= y < 88) else 64 for y in range(h) for x in range(w)]
    # Ramp on the left edge of the high ground at x=39..40, y=64..67
    for ry in range(64, 68):
        cliff_vals[ry * w + 39] = 96
        cliff_vals[ry * w + 40] = 96

    clif_bytes = b"CLIF" + b"\x00" * 28 + struct.pack(f"<{w * h}H", *cliff_vals)
    flag_vals = [2] * (w * h)
    lfct_bytes = b"LFCT" + b"\x00" * 28 + struct.pack(f"<{w * h}B", *flag_vals)

    archive = SimpleNamespace(read_file=lambda name: {"t3SyncCliffLevel": clif_bytes, "t3CellFlags": lfct_bytes}.get(name))
    map_info = SimpleNamespace(
        width=w,
        height=h,
        camera_left=16,
        camera_bottom=16,
        camera_right=112,
        camera_top=112,
    )
    replay = SimpleNamespace(map=SimpleNamespace(archive=archive, map_info=map_info))

    grid = NavGrid.from_replay(replay)
    assert grid.is_fallback is False
    assert grid.cell_size == 2
    assert grid.is_walkable(4.0, 4.0) is False  # outside camera bounds
    assert grid.is_walkable(64.0, 64.0) is True

    # Path from low ground (30, 64) to high ground (64, 64) goes through the ramp,
    # whereas direct crossing at y=50 is blocked by cliff edge.
    path = grid.find_path(30.0, 50.0, 64.0, 50.0)
    _assert_path_is_walkable(grid, path)
    assert any(60.0 <= y <= 70.0 for _, y in path)


def test_from_replay_offline_fallback():
    def _raise_offline():
        raise urllib.error.URLError("offline")

    replay = SimpleNamespace(map=None, map_width=160, map_height=160, load_map=_raise_offline)
    grid = NavGrid.from_replay(replay)

    assert grid.is_fallback is True
    assert grid.cell_size == 2
    assert grid.is_walkable(80.0, 80.0) is True
    assert grid.find_path(10.0, 10.0, 140.0, 140.0) == [(10.0, 10.0), (140.0, 140.0)]


def test_real_replays_nav_grid_and_latency():
    replays = sorted(FILES_DIR.glob("*.SC2Replay"))[:3]
    if not replays:
        pytest.skip("No sample replays in files/")

    for replay_path in replays:
        replay = sc2reader.load_replay(str(replay_path), load_level=2)
        grid = NavGrid.from_replay(replay)
        assert grid.grid_width > 0 and grid.grid_height > 0

        # Measure uncached pathfinding latency across 10 diagonal queries
        grid.clear_cache()
        t0 = time.perf_counter()
        for i in range(10):
            sx = 30.0 + i * 2.0
            sy = 30.0 + i * 2.0
            gx = min(grid.world_width - 10.0, 140.0 + i)
            gy = min(grid.world_height - 10.0, 140.0 + i)
            path = grid.find_path(sx, sy, gx, gy)
            assert len(path) >= 1
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        avg_ms = elapsed_ms / 10.0
        assert avg_ms < 5.0, f"Pathfinding too slow on {replay_path.name}: {avg_ms:.2f} ms/query"
