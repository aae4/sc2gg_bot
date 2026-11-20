"""Fast 2D navigation grid and group pathfinding for StarCraft II ground units."""

from __future__ import annotations

from collections import OrderedDict, deque
import heapq
import logging
import math
from typing import Any

import numpy as np

from app.parser.tactical_map import (
    _read_cell_flags,
    _read_cliff_grid,
    get_camera_bounds,
)

logger = logging.getLogger(__name__)

_SQRT2 = math.sqrt(2.0)
_INF = 1e18

# 8-connected neighbor offsets: (dx, dy, step_cost)
_NEIGHBORS: tuple[tuple[int, int, float], ...] = (
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, _SQRT2),
    (1, -1, _SQRT2),
    (-1, 1, _SQRT2),
    (-1, -1, _SQRT2),
)


class NavGrid:
    """2D walkability grid with cached A* pathfinding and string-pulling smoothing.

    Coordinates are in StarCraft II world units where ``x`` runs left-to-right
    and ``y`` runs bottom-to-top (matching ``t3SyncCliffLevel`` / ``t3CellFlags``).
    """

    def __init__(
        self,
        walkable: np.ndarray,
        cell_size: int = 1,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        max_iterations: int = 12_000,
        cache_size: int = 4096,
        is_fallback: bool = False,
    ) -> None:
        grid = np.asarray(walkable, dtype=bool)
        if grid.ndim != 2 or grid.shape[0] == 0 or grid.shape[1] == 0:
            raise ValueError(f"walkable must be a non-empty 2D array, got shape {grid.shape}")
        if cell_size <= 0:
            raise ValueError(f"cell_size must be positive, got {cell_size}")

        self.grid: np.ndarray = grid
        self.grid_height: int = int(grid.shape[0])
        self.grid_width: int = int(grid.shape[1])
        self.cell_size: int = int(cell_size)
        self.origin_x: float = float(origin_x)
        self.origin_y: float = float(origin_y)
        self.world_width: float = self.grid_width * self.cell_size
        self.world_height: float = self.grid_height * self.cell_size
        self.max_iterations: int = max(1, int(max_iterations))
        self.cache_size: int = max(0, int(cache_size))
        self.is_fallback: bool = bool(is_fallback)

        # Flat Python list for fast O(1) indexing inside A* inner loop
        self._flat: list[bool] = grid.ravel().tolist()
        self._cache: OrderedDict[tuple[int, int, int, int], tuple[tuple[int, int], ...]] = OrderedDict()
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    @classmethod
    def from_replay(
        cls,
        replay: Any,
        cell_size: int | None = None,
        max_iterations: int = 12_000,
        cache_size: int = 4096,
    ) -> NavGrid:
        """Build a NavGrid from a ``sc2reader`` replay using ``tactical_map`` readers.

        Falls back to a fully walkable grid if ``.SC2Map`` data is unavailable
        (for example when running offline without a cached map).
        """
        sc2_map = getattr(replay, "map", None)
        if sc2_map is None and hasattr(replay, "load_map"):
            try:
                replay.load_map()
                sc2_map = getattr(replay, "map", None)
            except Exception as exc:
                logger.debug("NavGrid fallback: failed to load map from replay: %s", exc)
                sc2_map = None

        archive = getattr(sc2_map, "archive", None) if sc2_map is not None else None
        mi = getattr(sc2_map, "map_info", None) if sc2_map is not None else None

        width = int(getattr(mi, "width", 0) or 0) if mi is not None else 0
        height = int(getattr(mi, "height", 0) or 0) if mi is not None else 0

        if width <= 0 or height <= 0:
            # Try fallback dimensions from replay metadata if available, else 200x200
            width = int(getattr(replay, "map_width", 0) or 0) or 200
            height = int(getattr(replay, "map_height", 0) or 0) or 200

        resolved_cell_size = cell_size if cell_size is not None else (1 if max(width, height) <= 96 else 2)

        if archive is None or mi is None:
            return cls._make_fallback(width, height, resolved_cell_size, max_iterations, cache_size)

        cliff = _read_cliff_grid(archive, width, height)
        flags = _read_cell_flags(archive, width, height)
        if cliff is None or flags is None:
            return cls._make_fallback(width, height, resolved_cell_size, max_iterations, cache_size)

        walkable = (flags & 1) == 0

        # Block sharp cliff edges where neither adjacent cell is a ramp
        cliff_lvl = np.clip(np.round(cliff / 64.0).astype(np.int32), 0, 3)
        non_ramp = (cliff % 64) == 0
        edge_h = np.zeros((height, width), dtype=bool)
        edge_v = np.zeros((height, width), dtype=bool)
        edge_h[1:, :] = (cliff_lvl[1:, :] != cliff_lvl[:-1, :]) & non_ramp[1:, :] & non_ramp[:-1, :]
        edge_v[:, 1:] = (cliff_lvl[:, 1:] != cliff_lvl[:, :-1]) & non_ramp[:, 1:] & non_ramp[:, :-1]
        walkable &= ~(edge_h | edge_v)

        bounds = get_camera_bounds(replay)
        if bounds is not None:
            left, bottom, right, top = bounds
            in_bounds = np.zeros((height, width), dtype=bool)
            in_bounds[bottom:top, left:right] = True
            walkable &= in_bounds

        downsampled = _downsample_walkable(walkable, resolved_cell_size)
        return cls(
            walkable=downsampled,
            cell_size=resolved_cell_size,
            origin_x=0.0,
            origin_y=0.0,
            max_iterations=max_iterations,
            cache_size=cache_size,
            is_fallback=False,
        )

    @classmethod
    def _make_fallback(
        cls,
        width: int,
        height: int,
        cell_size: int,
        max_iterations: int,
        cache_size: int,
    ) -> NavGrid:
        gw = max(1, (width + cell_size - 1) // cell_size)
        gh = max(1, (height + cell_size - 1) // cell_size)
        return cls(
            walkable=np.ones((gh, gw), dtype=bool),
            cell_size=cell_size,
            origin_x=0.0,
            origin_y=0.0,
            max_iterations=max_iterations,
            cache_size=cache_size,
            is_fallback=True,
        )

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates ``(x, y)`` to grid cell indices ``(gx, gy)``."""
        gx = int(math.floor((x - self.origin_x) / self.cell_size))
        gy = int(math.floor((y - self.origin_y) / self.cell_size))
        return gx, gy

    def grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        """Convert grid cell indices ``(gx, gy)`` to world coordinates at cell center."""
        return (
            self.origin_x + (gx + 0.5) * self.cell_size,
            self.origin_y + (gy + 0.5) * self.cell_size,
        )

    def _in_bounds(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self.grid_width and 0 <= gy < self.grid_height

    def is_walkable(self, x: float, y: float) -> bool:
        """Return True if the cell containing world point ``(x, y)`` is walkable."""
        gx, gy = self.world_to_grid(x, y)
        if not self._in_bounds(gx, gy):
            return False
        return self._flat[gy * self.grid_width + gx]

    def find_nearest_walkable(self, x: float, y: float) -> tuple[float, float]:
        """Return ``(x, y)`` if walkable, else the center of the nearest walkable cell."""
        if self.is_walkable(x, y):
            return (float(x), float(y))

        gx, gy = self.world_to_grid(x, y)
        cx = max(0, min(self.grid_width - 1, gx))
        cy = max(0, min(self.grid_height - 1, gy))

        w = self.grid_width
        h = self.grid_height
        flat = self._flat

        if flat[cy * w + cx]:
            return self.grid_to_world(cx, cy)

        visited = bytearray(w * h)
        start_idx = cy * w + cx
        visited[start_idx] = 1
        queue: deque[tuple[int, int]] = deque([(cx, cy)])

        best_cell: tuple[int, int] | None = None
        best_dist_sq = _INF

        while queue:
            cur_x, cur_y = queue.popleft()
            if best_cell is not None:
                # Prune once BFS Manhattan/ring distance exceeds current best Euclidean radius
                min_possible = max(0, abs(cur_x - cx) - 1) ** 2 + max(0, abs(cur_y - cy) - 1) ** 2
                if min_possible > best_dist_sq:
                    continue

            for dx, dy, _ in _NEIGHBORS:
                nx = cur_x + dx
                ny = cur_y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                nidx = ny * w + nx
                if visited[nidx]:
                    continue
                visited[nidx] = 1
                if flat[nidx]:
                    wx, wy = self.grid_to_world(nx, ny)
                    d_sq = (wx - x) ** 2 + (wy - y) ** 2
                    if d_sq < best_dist_sq:
                        best_dist_sq = d_sq
                        best_cell = (nx, ny)
                else:
                    queue.append((nx, ny))

        if best_cell is not None:
            return self.grid_to_world(best_cell[0], best_cell[1])
        return (float(x), float(y))

    def clear_cache(self) -> None:
        """Clear cached paths and reset hit/miss counters."""
        self._cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0

    def find_path(
        self,
        start_x: float,
        start_y: float,
        goal_x: float,
        goal_y: float,
    ) -> list[tuple[float, float]]:
        """Find a smoothed ground path from ``(start_x, start_y)`` to ``(goal_x, goal_y)``.

        Uses 8-connected A* without corner cutting, string-pulling LOS smoothing,
        an iteration limit with nearest-reachable fallback, and an LRU cache keyed
        by quantized cell coordinates ``(sx, sy, gx, gy)``.
        """
        start_walkable = self.is_walkable(start_x, start_y)
        if not start_walkable:
            sx_w, sy_w = self.find_nearest_walkable(start_x, start_y)
            sx, sy = self.world_to_grid(sx_w, sy_w)
        else:
            sx_w, sy_w = float(start_x), float(start_y)
            sx, sy = self.world_to_grid(start_x, start_y)

        goal_walkable = self.is_walkable(goal_x, goal_y)
        if not goal_walkable:
            gx_w, gy_w = self.find_nearest_walkable(goal_x, goal_y)
            gx, gy = self.world_to_grid(gx_w, gy_w)
        else:
            gx_w, gy_w = float(goal_x), float(goal_y)
            gx, gy = self.world_to_grid(goal_x, goal_y)

        if not (self._in_bounds(sx, sy) and self._in_bounds(gx, gy)):
            return [(sx_w, sy_w), (gx_w, gy_w)]

        if sx == gx and sy == gy:
            if abs(sx_w - gx_w) < 1e-6 and abs(sy_w - gy_w) < 1e-6:
                return [(gx_w, gy_w)]
            return [(sx_w, sy_w), (gx_w, gy_w)]

        cache_key = (sx, sy, gx, gy)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(cache_key)
            return self._cells_to_world_path(cached, sx_w, sy_w, gx_w, gy_w, gx, gy)

        self.cache_misses += 1
        if self._has_line_of_sight(sx, sy, gx, gy):
            smoothed_cells = ((sx, sy), (gx, gy))
        else:
            cell_path = self._astar(sx, sy, gx, gy)
            smoothed_cells = self._smooth_cells(cell_path)

        if self.cache_size > 0:
            self._cache[cache_key] = smoothed_cells
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

        return self._cells_to_world_path(smoothed_cells, sx_w, sy_w, gx_w, gy_w, gx, gy)

    def _cells_to_world_path(
        self,
        cells: tuple[tuple[int, int], ...],
        sx_w: float,
        sy_w: float,
        gx_w: float,
        gy_w: float,
        gx: int,
        gy: int,
    ) -> list[tuple[float, float]]:
        if not cells:
            return [(sx_w, sy_w)]
        if len(cells) == 1:
            return [(sx_w, sy_w)]

        result: list[tuple[float, float]] = [(sx_w, sy_w)]
        for cx, cy in cells[1:-1]:
            result.append(self.grid_to_world(cx, cy))

        last_cx, last_cy = cells[-1]
        if last_cx == gx and last_cy == gy:
            result.append((gx_w, gy_w))
        else:
            result.append(self.grid_to_world(last_cx, last_cy))
        return result

    def _astar(self, sx: int, sy: int, gx: int, gy: int) -> list[tuple[int, int]]:
        w = self.grid_width
        h = self.grid_height
        total = w * h
        flat = self._flat

        start_idx = sy * w + sx
        goal_idx = gy * w + gx
        if not flat[start_idx]:
            return [(sx, sy)]

        g_score = [_INF] * total
        came_from = [-1] * total
        closed = bytearray(total)

        g_score[start_idx] = 0.0
        start_h = _octile(sx, sy, gx, gy)
        heap: list[tuple[float, int]] = [(start_h * 1.001, start_idx)]

        best_idx = start_idx
        best_h = start_h
        iterations = 0
        max_iter = self.max_iterations
        diag_delta = _SQRT2 - 2.0

        while heap and iterations < max_iter:
            _, cur_idx = heapq.heappop(heap)
            if closed[cur_idx]:
                continue
            closed[cur_idx] = 1
            iterations += 1

            if cur_idx == goal_idx:
                best_idx = goal_idx
                break

            cx = cur_idx % w
            cy = cur_idx // w
            adx = gx - cx if gx >= cx else cx - gx
            ady = gy - cy if gy >= cy else cy - gy
            cur_h = adx + ady + diag_delta * (adx if adx < ady else ady)
            if cur_h < best_h:
                best_h = cur_h
                best_idx = cur_idx

            cur_g = g_score[cur_idx]

            # Cardinal neighbors
            if cx + 1 < w:
                right_idx = cur_idx + 1
                right_ok = flat[right_idx]
                if right_ok and not closed[right_idx]:
                    ng = cur_g + 1.0
                    if ng < g_score[right_idx]:
                        g_score[right_idx] = ng
                        came_from[right_idx] = cur_idx
                        nx = cx + 1
                        dx = gx - nx if gx >= nx else nx - gx
                        h_val = dx + ady + diag_delta * (dx if dx < ady else ady)
                        heapq.heappush(heap, (ng + h_val * 1.001, right_idx))
            else:
                right_ok = False

            if cx - 1 >= 0:
                left_idx = cur_idx - 1
                left_ok = flat[left_idx]
                if left_ok and not closed[left_idx]:
                    ng = cur_g + 1.0
                    if ng < g_score[left_idx]:
                        g_score[left_idx] = ng
                        came_from[left_idx] = cur_idx
                        nx = cx - 1
                        dx = gx - nx if gx >= nx else nx - gx
                        h_val = dx + ady + diag_delta * (dx if dx < ady else ady)
                        heapq.heappush(heap, (ng + h_val * 1.001, left_idx))
            else:
                left_ok = False

            if cy + 1 < h:
                up_idx = cur_idx + w
                up_ok = flat[up_idx]
                if up_ok and not closed[up_idx]:
                    ng = cur_g + 1.0
                    if ng < g_score[up_idx]:
                        g_score[up_idx] = ng
                        came_from[up_idx] = cur_idx
                        ny = cy + 1
                        dy = gy - ny if gy >= ny else ny - gy
                        h_val = adx + dy + diag_delta * (adx if adx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, up_idx))
            else:
                up_ok = False

            if cy - 1 >= 0:
                down_idx = cur_idx - w
                down_ok = flat[down_idx]
                if down_ok and not closed[down_idx]:
                    ng = cur_g + 1.0
                    if ng < g_score[down_idx]:
                        g_score[down_idx] = ng
                        came_from[down_idx] = cur_idx
                        ny = cy - 1
                        dy = gy - ny if gy >= ny else ny - gy
                        h_val = adx + dy + diag_delta * (adx if adx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, down_idx))
            else:
                down_ok = False

            # Diagonal neighbors (strictly no corner cutting)
            if right_ok and up_ok:
                nidx = cur_idx + w + 1
                if flat[nidx] and not closed[nidx]:
                    ng = cur_g + _SQRT2
                    if ng < g_score[nidx]:
                        g_score[nidx] = ng
                        came_from[nidx] = cur_idx
                        nx = cx + 1
                        ny = cy + 1
                        dx = gx - nx if gx >= nx else nx - gx
                        dy = gy - ny if gy >= ny else ny - ny
                        h_val = dx + dy + diag_delta * (dx if dx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, nidx))

            if left_ok and up_ok:
                nidx = cur_idx + w - 1
                if flat[nidx] and not closed[nidx]:
                    ng = cur_g + _SQRT2
                    if ng < g_score[nidx]:
                        g_score[nidx] = ng
                        came_from[nidx] = cur_idx
                        nx = cx - 1
                        ny = cy + 1
                        dx = gx - nx if gx >= nx else nx - gx
                        dy = gy - ny if gy >= ny else ny - ny
                        h_val = dx + dy + diag_delta * (dx if dx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, nidx))

            if right_ok and down_ok:
                nidx = cur_idx - w + 1
                if flat[nidx] and not closed[nidx]:
                    ng = cur_g + _SQRT2
                    if ng < g_score[nidx]:
                        g_score[nidx] = ng
                        came_from[nidx] = cur_idx
                        nx = cx + 1
                        ny = cy - 1
                        dx = gx - nx if gx >= nx else nx - gx
                        dy = gy - ny if gy >= ny else ny - ny
                        h_val = dx + dy + diag_delta * (dx if dx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, nidx))

            if left_ok and down_ok:
                nidx = cur_idx - w - 1
                if flat[nidx] and not closed[nidx]:
                    ng = cur_g + _SQRT2
                    if ng < g_score[nidx]:
                        g_score[nidx] = ng
                        came_from[nidx] = cur_idx
                        nx = cx - 1
                        ny = cy - 1
                        dx = gx - nx if gx >= nx else nx - gx
                        dy = gy - ny if gy >= ny else ny - ny
                        h_val = dx + dy + diag_delta * (dx if dx < dy else dy)
                        heapq.heappush(heap, (ng + h_val * 1.001, nidx))

        # Reconstruct path from start_idx to best_idx
        path: list[tuple[int, int]] = []
        curr = best_idx
        while curr != -1:
            path.append((curr % w, curr // w))
            curr = came_from[curr]
        path.reverse()
        return path

    def _has_line_of_sight(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        """Supercover Bresenham line-of-sight check that forbids corner cutting."""
        w = self.grid_width
        flat = self._flat

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x1 > x0 else -1
        sy = 1 if y1 > y0 else -1

        x = x0
        y = y0
        err = dx - dy

        while x != x1 or y != y1:
            e2 = 2 * err
            step_x = e2 > -dy
            step_y = e2 < dx

            if step_x and step_y:
                # Crossing diagonally: both adjacent cardinal cells must be walkable
                if not flat[y * w + (x + sx)] or not flat[(y + sy) * w + x]:
                    return False
                err -= dy
                err += dx
                x += sx
                y += sy
            elif step_x:
                err -= dy
                x += sx
            elif step_y:
                err += dx
                y += sy

            if not flat[y * w + x]:
                return False

        return True

    def _smooth_cells(self, path: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
        """Simplify a grid path using greedy line-of-sight string pulling."""
        n = len(path)
        if n <= 2:
            return tuple(path)

        smoothed: list[tuple[int, int]] = [path[0]]
        anchor = 0
        while anchor < n - 1:
            ax, ay = path[anchor]
            furthest = anchor + 1
            for j in range(n - 1, anchor + 1, -1):
                if self._has_line_of_sight(ax, ay, path[j][0], path[j][1]):
                    furthest = j
                    break
            smoothed.append(path[furthest])
            anchor = furthest
        return tuple(smoothed)


def _octile(x: int, y: int, gx: int, gy: int) -> float:
    dx = abs(x - gx)
    dy = abs(y - gy)
    if dx < dy:
        return dx * _SQRT2 + (dy - dx)
    return dy * _SQRT2 + (dx - dy)


def _downsample_walkable(walkable: np.ndarray, cell_size: int) -> np.ndarray:
    """Downsample a boolean walkability mask using conservative AND pooling."""
    if cell_size <= 1:
        return walkable.copy()

    h, w = walkable.shape
    gh = (h + cell_size - 1) // cell_size
    gw = (w + cell_size - 1) // cell_size
    pad_h = gh * cell_size - h
    pad_w = gw * cell_size - w
    if pad_h > 0 or pad_w > 0:
        padded = np.pad(walkable, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=False)
    else:
        padded = walkable

    return padded.reshape(gh, cell_size, gw, cell_size).all(axis=(1, 3))
