"""Hybrid StarCraft II match simulator for replay unit movement reconstruction.

Combines discrete-time forward simulation (tracker lifecycle events, player
commands from ``command_tracker``, ``NavGrid`` group A* pathfinding, abilities,
and transport cargo) with two-pass forward/backward residual smoothing against
``UnitPositionsEvent`` anchors so units move smoothly around terrain without
10.7-second teleports.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from app.parser.command_tracker import UnitCommand, extract_unit_commands
from app.parser.nav_grid import NavGrid
from app.parser.unit_specs import (
    IGNORED_UNIT_NAMES,
    UPGRADE_ALIASES,
    can_load_into,
    get_effective_range,
    get_effective_speed,
    get_unit_spec,
    resolve_unit_name,
)

logger = logging.getLogger(__name__)

FRAMES_PER_REAL_SEC = 22.4

_IMMOBILE_MORPH_TYPES = frozenset(
    {
        "SiegeTankSieged",
        "LiberatorAG",
        "WarpPrismPhasing",
        "LurkerBurrowed",
        "SpineCrawler",
        "SporeCrawler",
        "WidowMineBurrowed",
        "SwarmHostBurrowed",
        "RoachBurrowed",
        "ZerglingBurrowed",
        "BanelingBurrowed",
        "HydraliskBurrowed",
        "InfestorBurrowed",
        "UltraliskBurrowed",
        "QueenBurrowed",
        "DroneBurrowed",
    }
)

STIM_DURATION_SEC = 11.0
MEDIVAC_BOOST_DURATION_SEC = 6.0
LOAD_RANGE_TILES = 2.5
UNLOAD_RANGE_TILES = 2.0


@dataclass(slots=True)
class _SimUnit:
    """Mutable per-unit simulation state during the forward pass."""

    uid: int
    pid: int
    type_name: str
    x: float
    y: float
    born_step: int
    end_step: int | None = None
    is_alive: bool = True
    is_static: bool = False
    is_attack_move: bool = False
    attack_range: float = 0.0
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    stim_until: float = -1.0
    boost_until: float = -1.0
    in_cargo_of: int | None = None
    cargo: list[int] = field(default_factory=list)
    load_target_uid: int | None = None
    load_passenger_uid: int | None = None
    unload_target: tuple[float, float] | None = None
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)
    anchors: list[tuple[int, float, float]] = field(default_factory=list)
    cargo_steps: list[tuple[int, int]] = field(default_factory=list)  # (step_k, transport_uid)
    commanded_in_window: bool = False
    window_commanded: dict[int, bool] = field(default_factory=dict)


@dataclass(slots=True)
class SimulatedUnitTrack:
    """Smoothed discrete-time position track for a single unit."""

    uid: int
    born_step: int
    end_step: int
    xs: list[float]
    ys: list[float]
    cargo_step_set: frozenset[int] = frozenset()
    is_static: bool = False


class SimulatedMatch:
    """Query interface over simulated unit tracks compatible with ``replay_parser``."""

    def __init__(
        self,
        tracks: dict[int, SimulatedUnitTrack],
        dt: float,
        duration_sec: int,
    ) -> None:
        self.tracks = tracks
        self.dt = dt
        self.duration_sec = duration_sec

    def get_unit_pos(
        self,
        uid: int,
        frame: int,
        max_outside_sec: float = 4.0,
    ) -> tuple[float, float] | None:
        """Return interpolated ``(x, y)`` for ``uid`` at ``frame``, or ``None``."""
        track = self.tracks.get(uid)
        if track is None or not track.xs:
            return None

        t = max(0.0, frame / FRAMES_PER_REAL_SEC)
        born_t = track.born_step * self.dt
        end_t = track.end_step * self.dt
        if t < born_t - max_outside_sec or t > end_t + max_outside_sec:
            return None

        if track.is_static:
            return track.xs[0], track.ys[0]

        k_float = t / self.dt - track.born_step
        n = len(track.xs)
        if k_float <= 0.0:
            return track.xs[0], track.ys[0]
        if k_float >= n - 1:
            return track.xs[-1], track.ys[-1]

        k0 = int(k_float)
        frac = k_float - k0
        x0, y0 = track.xs[k0], track.ys[k0]
        x1, y1 = track.xs[k0 + 1], track.ys[k0 + 1]
        return x0 + (x1 - x0) * frac, y0 + (y1 - y0) * frac

    def is_in_cargo(self, uid: int, frame: int) -> bool:
        """Return True if ``uid`` is inside a transport at ``frame``."""
        track = self.tracks.get(uid)
        if track is None or not track.cargo_step_set:
            return False
        step = int(round((max(0.0, frame / FRAMES_PER_REAL_SEC)) / self.dt))
        return step in track.cargo_step_set


def _clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def _is_ignored(name: str, ignored_names: frozenset[str] | set[str]) -> bool:
    return name in ignored_names or name.startswith("Beacon")


def _is_static_building(type_name: str, unit_obj: Any = None) -> bool:
    if type_name.endswith("Flying") or "Uprooted" in type_name:
        return False
    spec = get_unit_spec(type_name)
    if spec is not None:
        return spec.is_building and spec.speed == 0.0 and not spec.is_flying
    return bool(getattr(unit_obj, "is_building", False))


def _compute_load_waypoints(
    ux: float,
    uy: float,
    tx: float,
    ty: float,
    nav_grid: NavGrid | None,
) -> list[tuple[float, float]]:
    if nav_grid is not None and not nav_grid.is_fallback:
        path = nav_grid.find_path(ux, uy, tx, ty)
        if len(path) > 1:
            return path[1:]
    return [(tx, ty)]


def _advance_along_waypoints(
    x: float,
    y: float,
    waypoints: list[tuple[float, float]],
    max_dist: float,
) -> tuple[float, float]:
    """Advance ``(x, y)`` along ``waypoints`` by up to ``max_dist`` tiles."""
    remaining = max_dist
    while waypoints and remaining > 1e-6:
        tx, ty = waypoints[0]
        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)
        if dist <= remaining:
            x, y = tx, ty
            remaining -= dist
            waypoints.pop(0)
        else:
            ratio = remaining / dist
            x += dx * ratio
            y += dy * ratio
            remaining = 0.0
    return x, y


def _interpolate_along_path(
    path: list[tuple[float, float]],
    alpha: float,
) -> tuple[float, float]:
    """Sample a point at normalized progress ``alpha`` in ``[0, 1]`` along ``path``."""
    if not path:
        return 0.0, 0.0
    if len(path) == 1 or alpha <= 0.0:
        return path[0]
    if alpha >= 1.0:
        return path[-1]

    seg_lens: list[float] = []
    total_len = 0.0
    for i in range(len(path) - 1):
        d = math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
        seg_lens.append(d)
        total_len += d

    if total_len <= 1e-6:
        return path[-1]

    target_d = alpha * total_len
    acc = 0.0
    for i, d in enumerate(seg_lens):
        if acc + d >= target_d or i == len(seg_lens) - 1:
            if d <= 1e-6:
                return path[i + 1]
            t = (target_d - acc) / d
            x0, y0 = path[i]
            x1, y1 = path[i + 1]
            return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        acc += d
    return path[-1]


def _used_cargo_size(transport: _SimUnit, units: dict[int, _SimUnit]) -> int:
    total = 0
    for p_uid in transport.cargo:
        p = units.get(p_uid)
        if p is not None:
            p_spec = get_unit_spec(p.type_name)
            total += p_spec.cargo_size if p_spec is not None else 1
    return total


def _try_load_unit(
    passenger: _SimUnit,
    transport: _SimUnit,
    units: dict[int, _SimUnit],
) -> bool:
    """Load ``passenger`` into ``transport`` if compatible and capacity permits."""
    if not passenger.is_alive or not transport.is_alive:
        return False
    if passenger.in_cargo_of is not None:
        return False
    if not can_load_into(passenger.type_name, transport.type_name):
        return False

    t_spec = get_unit_spec(transport.type_name)
    p_spec = get_unit_spec(passenger.type_name)
    if t_spec is None or p_spec is None:
        return False
    if _used_cargo_size(transport, units) + p_spec.cargo_size > t_spec.cargo_capacity:
        return False

    transport.cargo.append(passenger.uid)
    passenger.in_cargo_of = transport.uid
    passenger.waypoints.clear()
    passenger.load_target_uid = None
    passenger.x = transport.x
    passenger.y = transport.y
    return True


def _unload_passenger(
    passenger: _SimUnit,
    transport: _SimUnit,
    nav_grid: NavGrid | None,
    map_width: float,
    map_height: float,
) -> None:
    """Unload ``passenger`` at ``transport`` position (snapped to walkable if needed)."""
    ux = _clamp(transport.x, 0.0, map_width)
    uy = _clamp(transport.y, 0.0, map_height)
    p_spec = get_unit_spec(passenger.type_name)
    if (
        nav_grid is not None
        and not nav_grid.is_fallback
        and (p_spec is None or not p_spec.is_flying)
    ):
        if not nav_grid.is_walkable(ux, uy):
            ux, uy = nav_grid.find_nearest_walkable(ux, uy)
    passenger.in_cargo_of = None
    passenger.x = _clamp(ux, 0.0, map_width)
    passenger.y = _clamp(uy, 0.0, map_height)
    passenger.waypoints.clear()


def _unload_all(
    transport: _SimUnit,
    units: dict[int, _SimUnit],
    nav_grid: NavGrid | None,
    map_width: float,
    map_height: float,
) -> None:
    for p_uid in list(transport.cargo):
        p = units.get(p_uid)
        if p is not None and p.in_cargo_of == transport.uid:
            _unload_passenger(p, transport, nav_grid, map_width, map_height)
    transport.cargo.clear()
    transport.unload_target = None


def _apply_command(
    cmd: UnitCommand,
    t: float,
    units: dict[int, _SimUnit],
    nav_grid: NavGrid | None,
    map_width: float,
    map_height: float,
    moving_uids: set[int],
) -> None:
    """Apply a single ``UnitCommand`` to active simulation units."""
    action = cmd.action
    alive_units = [u for uid in cmd.unit_ids if (u := units.get(uid)) is not None and u.is_alive]
    if not alive_units:
        return

    use_nav = nav_grid is not None and not nav_grid.is_fallback

    if action in {"move", "attack_move"}:
        if cmd.target_x is None or cmd.target_y is None:
            return
        tx = _clamp(float(cmd.target_x), 0.0, map_width)
        ty = _clamp(float(cmd.target_y), 0.0, map_height)
        is_atk = action == "attack_move"

        ground_units: list[_SimUnit] = []
        flying_units: list[_SimUnit] = []
        for u in alive_units:
            if u.in_cargo_of is not None or u.is_static:
                continue
            spec = get_unit_spec(u.type_name)
            if spec is not None and spec.speed <= 0.0:
                continue
            if resolve_unit_name(u.type_name) in _IMMOBILE_MORPH_TYPES:
                continue
            u.load_target_uid = None
            u.load_passenger_uid = None
            u.unload_target = None
            u.is_attack_move = is_atk
            u.commanded_in_window = True
            if spec is not None and spec.is_flying:
                flying_units.append(u)
            else:
                ground_units.append(u)

        if ground_units:
            if use_nav:
                cx = sum(u.x for u in ground_units) / len(ground_units)
                cy = sum(u.y for u in ground_units) / len(ground_units)
                path = nav_grid.find_path(cx, cy, tx, ty)  # type: ignore[union-attr]
                if len(path) > 1:
                    path = path[1:]
            else:
                path = [(tx, ty)]
            for u in ground_units:
                if cmd.is_queued and u.waypoints:
                    u.waypoints.extend(path)
                else:
                    u.waypoints = list(path)
                moving_uids.add(u.uid)

        if flying_units:
            for u in flying_units:
                if cmd.is_queued and u.waypoints:
                    u.waypoints.append((tx, ty))
                else:
                    u.waypoints = [(tx, ty)]
                moving_uids.add(u.uid)
        return

    if action in {"blink", "tactical_jump"}:
        if cmd.target_x is None or cmd.target_y is None:
            return
        tx = _clamp(float(cmd.target_x), 0.0, map_width)
        ty = _clamp(float(cmd.target_y), 0.0, map_height)
        for u in alive_units:
            if u.in_cargo_of is not None or u.is_static:
                continue
            spec = get_unit_spec(u.type_name)
            ux, uy = tx, ty
            if action == "blink" and use_nav and (spec is None or not spec.is_flying):
                if not nav_grid.is_walkable(ux, uy):  # type: ignore[union-attr]
                    ux, uy = nav_grid.find_nearest_walkable(ux, uy)  # type: ignore[union-attr]
            u.x = _clamp(ux, 0.0, map_width)
            u.y = _clamp(uy, 0.0, map_height)
            u.waypoints.clear()
            u.is_attack_move = False
            u.commanded_in_window = True
        return

    if action == "stim":
        for u in alive_units:
            u.stim_until = t + STIM_DURATION_SEC
        return

    if action == "medivac_boost":
        for u in alive_units:
            if resolve_unit_name(u.type_name) == "Medivac":
                u.boost_until = t + MEDIVAC_BOOST_DURATION_SEC
        return

    if action in {"stop", "hold", "siege", "burrow", "phasing"}:
        for u in alive_units:
            u.waypoints.clear()
            u.is_attack_move = False
            u.load_target_uid = None
            u.load_passenger_uid = None
            u.unload_target = None
            moving_uids.discard(u.uid)
        return

    if action == "load":
        target = units.get(cmd.target_uid) if cmd.target_uid is not None else None
        if target is None or not target.is_alive:
            return
        for u in alive_units:
            if u.uid == target.uid:
                continue
            if can_load_into(u.type_name, target.type_name):
                u.load_target_uid = target.uid
                u.is_attack_move = False
                u.commanded_in_window = True
                if math.hypot(target.x - u.x, target.y - u.y) <= LOAD_RANGE_TILES:
                    _try_load_unit(u, target, units)
                else:
                    u.waypoints = _compute_load_waypoints(u.x, u.y, target.x, target.y, nav_grid)
                    moving_uids.add(u.uid)
            elif can_load_into(target.type_name, u.type_name):
                u.load_passenger_uid = target.uid
                u.is_attack_move = False
                u.commanded_in_window = True
                if math.hypot(target.x - u.x, target.y - u.y) <= LOAD_RANGE_TILES:
                    _try_load_unit(target, u, units)
                else:
                    u.waypoints = [(target.x, target.y)]
                    moving_uids.add(u.uid)
        return

    if action == "unload_all":
        for u in alive_units:
            if u.cargo:
                _unload_all(u, units, nav_grid, map_width, map_height)
        return

    if action == "unload_at":
        for u in alive_units:
            if not u.cargo:
                continue
            if cmd.target_x is not None and cmd.target_y is not None:
                tx = _clamp(float(cmd.target_x), 0.0, map_width)
                ty = _clamp(float(cmd.target_y), 0.0, map_height)
                t_spec = get_unit_spec(u.type_name)
                if math.hypot(tx - u.x, ty - u.y) <= UNLOAD_RANGE_TILES or (
                    t_spec is not None and t_spec.speed <= 0.0
                ):
                    _unload_all(u, units, nav_grid, map_width, map_height)
                else:
                    u.unload_target = (tx, ty)
                    u.waypoints = [(tx, ty)]
                    u.is_attack_move = False
                    u.commanded_in_window = True
                    moving_uids.add(u.uid)
            elif cmd.target_uid is not None and cmd.target_uid in u.cargo:
                p = units.get(cmd.target_uid)
                if p is not None and p.in_cargo_of == u.uid:
                    _unload_passenger(p, u, nav_grid, map_width, map_height)
                u.cargo = [cid for cid in u.cargo if cid != cmd.target_uid]
            else:
                _unload_all(u, units, nav_grid, map_width, map_height)


def _has_enemy_in_range(
    u: _SimUnit,
    enemy_grid: dict[tuple[int, int], list[tuple[float, float]]],
    inv_bucket: float,
) -> bool:
    """Return True if an enemy unit/building or recent enemy death is within attack range."""
    eff_range = u.attack_range if u.attack_range > 2.0 else 2.0
    r_sq = eff_range * eff_range
    ux = u.x
    uy = u.y
    cx0 = int((ux - eff_range) * inv_bucket)
    cx1 = int((ux + eff_range) * inv_bucket)
    cy0 = int((uy - eff_range) * inv_bucket)
    cy1 = int((uy + eff_range) * inv_bucket)
    for cx in range(cx0, cx1 + 1):
        for cy in range(cy0, cy1 + 1):
            bucket = enemy_grid.get((cx, cy))
            if not bucket:
                continue
            for ex, ey in bucket:
                dx = ex - ux
                dy = ey - uy
                if dx * dx + dy * dy <= r_sq:
                    return True
    return False


def simulate_match(
    duration_sec: int,
    tracker_events: list[Any],
    commands: list[UnitCommand],
    nav_grid: NavGrid | None = None,
    *,
    map_width: float = 200.0,
    map_height: float = 200.0,
    dt: float = 0.5,
    ignored_unit_names: frozenset[str] | set[str] = IGNORED_UNIT_NAMES,
) -> SimulatedMatch:
    """Run two-pass hybrid simulation over tracker events and unit commands."""
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt}")

    total_steps = max(1, int(math.ceil(max(1, duration_sec) / dt)))
    units: dict[int, _SimUnit] = {}
    upgrades_by_pid: dict[int, set[str]] = {}
    speed_cache: dict[tuple[int, str, bool, bool], float] = {}
    range_cache: dict[tuple[int, str], float] = {}

    def _cached_range(pid: int, type_name: str) -> float:
        r_key = (pid, type_name)
        val = range_cache.get(r_key)
        if val is None:
            val = get_effective_range(type_name, upgrades_by_pid.get(pid, frozenset()))
            range_cache[r_key] = val
        return val

    # Bucket tracker events and commands by simulation step index
    events_by_step: dict[int, list[Any]] = {}
    for evt in tracker_events:
        frame = int(getattr(evt, "frame", 0) or 0)
        step = min(total_steps, max(0, int(round((frame / FRAMES_PER_REAL_SEC) / dt))))
        events_by_step.setdefault(step, []).append(evt)

    cmds_by_step: dict[int, list[UnitCommand]] = {}
    for cmd in commands:
        step = min(total_steps, max(0, int(math.ceil((cmd.frame / FRAMES_PER_REAL_SEC) / dt))))
        cmds_by_step.setdefault(step, []).append(cmd)

    active_units: dict[int, _SimUnit] = {}
    active_dynamic: dict[int, _SimUnit] = {}
    in_cargo_uids: set[int] = set()
    moving_uids: set[int] = set()
    recent_deaths: dict[int, list[tuple[int, float, float]]] = {}
    inv_bucket = 1.0 / 16.0
    static_grids_by_pid: dict[int, dict[tuple[int, int], list[tuple[float, float]]]] = {}

    def _add_static_to_grid(su: _SimUnit) -> None:
        if su.pid <= 0:
            return
        p_grid = static_grids_by_pid.get(su.pid)
        if p_grid is None:
            p_grid = {}
            static_grids_by_pid[su.pid] = p_grid
        cell = (int(su.x * inv_bucket), int(su.y * inv_bucket))
        bucket = p_grid.get(cell)
        if bucket is None:
            p_grid[cell] = [(su.x, su.y)]
        else:
            bucket.append((su.x, su.y))

    def _remove_static_from_grid(su: _SimUnit) -> None:
        if su.pid <= 0:
            return
        p_grid = static_grids_by_pid.get(su.pid)
        if p_grid is None:
            return
        cell = (int(su.x * inv_bucket), int(su.y * inv_bucket))
        bucket = p_grid.get(cell)
        if bucket:
            try:
                bucket.remove((su.x, su.y))
            except ValueError:
                pass

    # Pass 1: Forward discrete-time simulation
    for k in range(total_steps + 1):
        t = k * dt
        pending_anchors: list[tuple[int, float, float]] = []

        # 1a. Process tracker lifecycle events in (t - dt, t]
        for evt in events_by_step.get(k, ()):
            ename = type(evt).__name__
            if ename in {"UnitBornEvent", "UnitInitEvent"}:
                unit = getattr(evt, "unit", None)
                owner = getattr(unit, "owner", None) if unit else None
                if not unit or not owner:
                    continue
                if _is_ignored(unit.name, ignored_unit_names):
                    continue
                loc = getattr(evt, "location", None) or getattr(unit, "location", None)
                if not loc or len(loc) < 2:
                    continue
                ux = _clamp(float(loc[0]), 0.0, map_width)
                uy = _clamp(float(loc[1]), 0.0, map_height)
                if unit.id not in units:
                    pid = int(owner.pid)
                    is_static = _is_static_building(unit.name, unit)
                    sim_u = _SimUnit(
                        uid=unit.id,
                        pid=pid,
                        type_name=unit.name,
                        x=ux,
                        y=uy,
                        born_step=k,
                        is_static=is_static,
                        attack_range=_cached_range(pid, unit.name),
                    )
                    if is_static:
                        _add_static_to_grid(sim_u)
                    else:
                        sim_u.anchors.append((k, ux, uy))
                        active_dynamic[unit.id] = sim_u
                    units[unit.id] = sim_u
                    active_units[unit.id] = sim_u

            elif ename == "UnitTypeChangeEvent":
                unit = getattr(evt, "unit", None)
                if unit and unit.id in units:
                    new_name = getattr(evt, "unit_type_name", None) or unit.name
                    if not _is_ignored(new_name, ignored_unit_names):
                        u = units[unit.id]
                        u.type_name = new_name
                        u.attack_range = _cached_range(u.pid, new_name)
                        if u.is_static and not _is_static_building(new_name, unit):
                            _remove_static_from_grid(u)
                            elapsed_steps = max(0, k - u.born_step)
                            u.xs = [u.x] * elapsed_steps
                            u.ys = [u.y] * elapsed_steps
                            u.anchors.append((k, u.x, u.y))
                            u.is_static = False
                            active_dynamic[u.uid] = u
                        if resolve_unit_name(new_name) in _IMMOBILE_MORPH_TYPES:
                            u.waypoints.clear()
                            u.is_attack_move = False

            elif ename == "UnitOwnerChangeEvent":
                unit = getattr(evt, "unit", None)
                if unit and unit.id in units:
                    new_pid = getattr(evt, "control_pid", None) or getattr(
                        getattr(unit, "owner", None), "pid", None
                    )
                    if new_pid is not None:
                        u = units[unit.id]
                        if u.is_static:
                            _remove_static_from_grid(u)
                        u.pid = int(new_pid)
                        u.attack_range = _cached_range(u.pid, u.type_name)
                        if u.is_static:
                            _add_static_to_grid(u)

            elif ename == "UpgradeCompleteEvent":
                pid = getattr(evt, "pid", None)
                up_name = getattr(evt, "upgrade_type_name", "")
                if pid is not None and up_name and not up_name.startswith("Spray"):
                    pid_int = int(pid)
                    norm_up = UPGRADE_ALIASES.get(up_name, up_name)
                    pid_ups = upgrades_by_pid.setdefault(pid_int, set())
                    pid_ups.add(norm_up)
                    for key in [ck for ck in speed_cache if ck[0] == pid_int]:
                        del speed_cache[key]
                    for key in [rk for rk in range_cache if rk[0] == pid_int]:
                        del range_cache[key]
                    for au in active_units.values():
                        if au.pid == pid_int:
                            au.attack_range = _cached_range(pid_int, au.type_name)

            elif ename == "UnitPositionsEvent":
                units_pos = getattr(evt, "units", None) or {}
                for unit, loc in units_pos.items():
                    if unit and unit.id in units and loc and len(loc) >= 2:
                        u = units[unit.id]
                        if u.is_static:
                            continue
                        ax = _clamp(float(loc[0]), 0.0, map_width)
                        ay = _clamp(float(loc[1]), 0.0, map_height)
                        pending_anchors.append((unit.id, ax, ay))

            elif ename == "UnitDiedEvent":
                unit = getattr(evt, "unit", None)
                if not unit or unit.id not in units:
                    continue
                u = units[unit.id]
                if u.is_static:
                    _remove_static_from_grid(u)
                loc = getattr(evt, "location", None) or (u.x, u.y)
                if loc and len(loc) >= 2:
                    u.x = _clamp(float(loc[0]), 0.0, map_width)
                    u.y = _clamp(float(loc[1]), 0.0, map_height)
                if u.pid > 0:
                    recent_deaths.setdefault(k, []).append((u.pid, u.x, u.y))
                if u.is_static:
                    u.xs = [u.x]
                    u.ys = [u.y]
                else:
                    # Record final death position at step k before deactivating
                    if len(u.xs) == k - u.born_step:
                        u.xs.append(u.x)
                        u.ys.append(u.y)
                    elif u.xs:
                        u.xs[-1] = u.x
                        u.ys[-1] = u.y
                    u.anchors.append((k, u.x, u.y))
                    u.window_commanded[k] = u.commanded_in_window
                u.is_alive = False
                u.end_step = k
                active_units.pop(unit.id, None)
                active_dynamic.pop(unit.id, None)
                moving_uids.discard(unit.id)
                in_cargo_uids.discard(unit.id)

                if u.in_cargo_of is not None:
                    host = units.get(u.in_cargo_of)
                    if host is not None:
                        host.cargo = [cid for cid in host.cargo if cid != u.uid]
                    u.in_cargo_of = None
                if u.cargo:
                    for cid in u.cargo:
                        c = units.get(cid)
                        if c is not None:
                            c.in_cargo_of = None
                            in_cargo_uids.discard(cid)
                    u.cargo.clear()

        # 1b. Apply player commands in (t - dt, t]
        for cmd in cmds_by_step.get(k, ()):
            _apply_command(cmd, t, units, nav_grid, map_width, map_height, moving_uids)
            if cmd.action in {"load", "unload_all", "unload_at"}:
                for uid in cmd.unit_ids:
                    cu = units.get(uid)
                    if cu is not None:
                        if cu.in_cargo_of is not None:
                            in_cargo_uids.add(uid)
                        else:
                            in_cargo_uids.discard(uid)

        # 1c. Advance moving units
        if k > 0 and moving_uids:
            dyn_grids_by_pid: dict[int, dict[tuple[int, int], list[tuple[float, float]]]] | None = (
                None
            )
            for uid in moving_uids:
                mu = units[uid]
                if (
                    mu.is_attack_move
                    and mu.attack_range > 0.0
                    and mu.waypoints
                    and mu.in_cargo_of is None
                ):
                    dyn_grids_by_pid = {}
                    break

            if dyn_grids_by_pid is not None:
                for au in active_dynamic.values():
                    if au.in_cargo_of is not None or au.pid <= 0:
                        continue
                    p_grid = dyn_grids_by_pid.get(au.pid)
                    if p_grid is None:
                        p_grid = {}
                        dyn_grids_by_pid[au.pid] = p_grid
                    cell = (int(au.x * inv_bucket), int(au.y * inv_bucket))
                    bucket = p_grid.get(cell)
                    if bucket is None:
                        p_grid[cell] = [(au.x, au.y)]
                    else:
                        bucket.append((au.x, au.y))
                for step_d in (k, k - 1):
                    for d_pid, dx, dy in recent_deaths.get(step_d, ()):
                        p_grid = dyn_grids_by_pid.get(d_pid)
                        if p_grid is None:
                            p_grid = {}
                            dyn_grids_by_pid[d_pid] = p_grid
                        cell = (int(dx * inv_bucket), int(dy * inv_bucket))
                        bucket = p_grid.get(cell)
                        if bucket is None:
                            p_grid[cell] = [(dx, dy)]
                        else:
                            bucket.append((dx, dy))

            for uid in list(moving_uids):
                u = units[uid]
                if u.in_cargo_of is not None or not u.is_alive:
                    moving_uids.discard(uid)
                    continue

                if u.load_target_uid is not None:
                    target = units.get(u.load_target_uid)
                    if target is None or not target.is_alive:
                        u.load_target_uid = None
                    elif math.hypot(target.x - u.x, target.y - u.y) <= LOAD_RANGE_TILES:
                        if _try_load_unit(u, target, units):
                            in_cargo_uids.add(u.uid)
                        if u.in_cargo_of is not None:
                            moving_uids.discard(uid)
                            continue
                    else:
                        if (
                            not u.waypoints
                            or math.hypot(target.x - u.waypoints[-1][0], target.y - u.waypoints[-1][1])
                            > 1.5
                        ):
                            u.waypoints = _compute_load_waypoints(
                                u.x, u.y, target.x, target.y, nav_grid
                            )

                if u.load_passenger_uid is not None:
                    passenger = units.get(u.load_passenger_uid)
                    if (
                        passenger is None
                        or not passenger.is_alive
                        or passenger.in_cargo_of is not None
                    ):
                        u.load_passenger_uid = None
                    elif math.hypot(passenger.x - u.x, passenger.y - u.y) <= LOAD_RANGE_TILES:
                        if _try_load_unit(passenger, u, units):
                            in_cargo_uids.add(passenger.uid)
                        u.load_passenger_uid = None
                    else:
                        u.waypoints = [(passenger.x, passenger.y)]

                if u.waypoints:
                    paused_for_combat = False
                    if u.is_attack_move and u.attack_range > 0.0 and dyn_grids_by_pid is not None:
                        u_pid = u.pid
                        for e_pid, e_grid in dyn_grids_by_pid.items():
                            if e_pid != u_pid and _has_enemy_in_range(u, e_grid, inv_bucket):
                                paused_for_combat = True
                                break
                        if not paused_for_combat:
                            for e_pid, s_grid in static_grids_by_pid.items():
                                if e_pid != u_pid and _has_enemy_in_range(u, s_grid, inv_bucket):
                                    paused_for_combat = True
                                    break
                    if not paused_for_combat:
                        is_stim = t < u.stim_until
                        is_boost = t < u.boost_until
                        s_key = (u.pid, u.type_name, is_stim, is_boost)
                        speed = speed_cache.get(s_key)
                        if speed is None:
                            speed = get_effective_speed(
                                u.type_name,
                                upgrades_by_pid.get(u.pid, frozenset()),
                                is_stimmed=is_stim,
                                is_medivac_boosted=is_boost,
                            )
                            speed_cache[s_key] = speed
                        if speed > 0.0:
                            nx, ny = _advance_along_waypoints(u.x, u.y, u.waypoints, speed * dt)
                            if nx < 0.0:
                                nx = 0.0
                            elif nx > map_width:
                                nx = map_width
                            if ny < 0.0:
                                ny = 0.0
                            elif ny > map_height:
                                ny = map_height
                            u.x = nx
                            u.y = ny

                if u.unload_target is not None:
                    utx, uty = u.unload_target
                    if math.hypot(utx - u.x, uty - u.y) <= UNLOAD_RANGE_TILES or not u.waypoints:
                        _unload_all(u, units, nav_grid, map_width, map_height)

                if (
                    not u.waypoints
                    and u.load_target_uid is None
                    and u.load_passenger_uid is None
                    and u.unload_target is None
                ):
                    moving_uids.discard(uid)

        # Prune old deaths outside the 2-step window
        recent_deaths.pop(k - 1, None)

        # 1d. Sync cargo coordinates and record step positions (pre-anchor snap)
        if in_cargo_uids:
            for cid in list(in_cargo_uids):
                cu = units[cid]
                if cu.in_cargo_of is None:
                    in_cargo_uids.discard(cid)
                    continue
                host = units.get(cu.in_cargo_of)
                if host is not None and host.is_alive:
                    cu.x, cu.y = host.x, host.y
                    cu.cargo_steps.append((k, host.uid))
                else:
                    cu.in_cargo_of = None
                    in_cargo_uids.discard(cid)

        for u in active_dynamic.values():
            u.xs.append(u.x)
            u.ys.append(u.y)

        # 1e. Snap forward state to UnitPositionsEvent anchors after recording pre-snap sim pos
        for uid, ax, ay in pending_anchors:
            u = units.get(uid)
            if u is None or not u.is_alive or u.is_static or u.in_cargo_of is not None:
                continue
            u.anchors.append((k, ax, ay))
            u.window_commanded[k] = u.commanded_in_window
            u.commanded_in_window = False
            u.x, u.y = ax, ay

    # Pass 2: Backward residual smoothing across anchor windows
    tracks: dict[int, SimulatedUnitTrack] = {}
    cargo_units: list[_SimUnit] = []
    use_nav_pass2 = nav_grid is not None and not nav_grid.is_fallback

    for uid, u in units.items():
        if u.is_static:
            end_step = u.end_step if u.end_step is not None else total_steps
            tracks[uid] = SimulatedUnitTrack(
                uid=uid,
                born_step=u.born_step,
                end_step=end_step,
                xs=[u.x],
                ys=[u.y],
                is_static=True,
            )
            continue

        if u.end_step is None:
            u.end_step = u.born_step + len(u.xs) - 1

        # Deduplicate anchors by step_k (anchors are already appended in step order)
        sorted_anchors: list[tuple[int, float, float]] = []
        for ak, ax, ay in u.anchors:
            if u.born_step <= ak <= u.end_step:
                if sorted_anchors and sorted_anchors[-1][0] == ak:
                    sorted_anchors[-1] = (ak, ax, ay)
                else:
                    sorted_anchors.append((ak, ax, ay))

        spec = get_unit_spec(u.type_name)
        is_ground = spec is None or not spec.is_flying

        for i in range(len(sorted_anchors) - 1):
            k0, x0, y0 = sorted_anchors[i]
            k1, x1, y1 = sorted_anchors[i + 1]
            if k1 <= k0:
                continue

            idx0 = k0 - u.born_step
            idx1 = k1 - u.born_step
            if idx0 < 0 or idx1 >= len(u.xs):
                continue

            u.xs[idx0] = x0
            u.ys[idx0] = y0

            sim_x1, sim_y1 = u.xs[idx1], u.ys[idx1]
            dx = x1 - sim_x1
            dy = y1 - sim_y1
            if -1e-6 < dx < 1e-6 and -1e-6 < dy < 1e-6:
                continue

            moved_in_sim = math.hypot(sim_x1 - x0, sim_y1 - y0)
            residual = math.hypot(dx, dy)
            span = k1 - k0

            # If unit moved significantly without tracked commands (e.g. rally/mining),
            # route ground units along NavGrid so they don't clip through walls.
            if (
                use_nav_pass2
                and is_ground
                and not u.window_commanded.get(k1, False)
                and moved_in_sim < 0.1
                and residual > 3.0
            ):
                path = nav_grid.find_path(x0, y0, x1, y1)  # type: ignore[union-attr]
                for k in range(k0 + 1, k1 + 1):
                    alpha = (k - k0) / span
                    px, py = _interpolate_along_path(path, alpha)
                    idx = k - u.born_step
                    u.xs[idx] = _clamp(px, 0.0, map_width)
                    u.ys[idx] = _clamp(py, 0.0, map_height)
            else:
                for k in range(k0 + 1, k1 + 1):
                    alpha = (k - k0) / span
                    idx = k - u.born_step
                    px = u.xs[idx] + alpha * dx
                    py = u.ys[idx] + alpha * dy
                    if px < 0.0:
                        px = 0.0
                    elif px > map_width:
                        px = map_width
                    if py < 0.0:
                        py = 0.0
                    elif py > map_height:
                        py = map_height
                    u.xs[idx] = px
                    u.ys[idx] = py

        if u.cargo_steps:
            cargo_units.append(u)

        tracks[uid] = SimulatedUnitTrack(
            uid=uid,
            born_step=u.born_step,
            end_step=u.end_step,
            xs=u.xs,
            ys=u.ys,
            cargo_step_set=frozenset(step for step, _ in u.cargo_steps),
        )

    # Sync cargo passenger positions to smoothed transport positions
    for u in cargo_units:
        track = tracks[u.uid]
        for step, host_uid in u.cargo_steps:
            host_track = tracks.get(host_uid)
            if host_track is None:
                continue
            p_idx = step - track.born_step
            h_idx = step - host_track.born_step
            if 0 <= p_idx < len(track.xs) and 0 <= h_idx < len(host_track.xs):
                track.xs[p_idx] = host_track.xs[h_idx]
                track.ys[p_idx] = host_track.ys[h_idx]

    return SimulatedMatch(tracks=tracks, dt=dt, duration_sec=duration_sec)


def simulate_replay(
    replay: Any,
    nav_grid: NavGrid | None = None,
    dt: float = 0.5,
) -> SimulatedMatch:
    """Build ``NavGrid`` (if needed), extract commands, and simulate ``replay``."""
    duration_sec = max(1, int(getattr(getattr(replay, "game_length", None), "seconds", 0) or 1))
    map_info = getattr(getattr(replay, "map", None), "map_info", None)
    map_width = float(getattr(map_info, "width", 200) or 200)
    map_height = float(getattr(map_info, "height", 200) or 200)

    if nav_grid is None:
        nav_grid = NavGrid.from_replay(replay)

    commands = extract_unit_commands(replay)
    tracker_events = list(getattr(replay, "tracker_events", ()) or ())

    return simulate_match(
        duration_sec=duration_sec,
        tracker_events=tracker_events,
        commands=commands,
        nav_grid=nav_grid,
        map_width=map_width,
        map_height=map_height,
        dt=dt,
    )
