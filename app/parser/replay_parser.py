import asyncio
import hashlib
import logging
import math
import re
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import sc2reader

from app.domain.models import (
    BuildOrderItem,
    ChartSeries,
    MatchMeta,
    ParsedReplayBundle,
    PlayerInfo,
    ReplayData,
    TimelineFrame,
)
from app.parser.analytics import (
    compute_spending_quotient,
    compute_supply_block_sec,
    detect_build_archetype,
    extract_key_timings,
)
from app.parser.battles import UnitDeathRecord, detect_battles
from app.parser.hd_map import resolve_hd_map
from app.parser.tactical_map import get_camera_bounds, render_tactical_map_png
from app.parser.unit_specs import IGNORED_UNIT_NAMES

if TYPE_CHECKING:
    from app.parser.simulator import SimulatedMatch

logger = logging.getLogger(__name__)

# In LotV Faster speed, 1 real second = 22.4 game frames (16 * 1.4).
FRAMES_PER_REAL_SEC = 22.4

RACE_MAP = {
    "저그": "Zerg",
    "异虫": "Zerg",
    "蟲族": "Zerg",
    "Зерги": "Zerg",
    "Zerg": "Zerg",
    "테란": "Terran",
    "人類": "Terran",
    "人类": "Terran",
    "Terraner": "Terran",
    "Терраны": "Terran",
    "Terran": "Terran",
    "프로토스": "Protoss",
    "神族": "Protoss",
    "Protosi": "Protoss",
    "星灵": "Protoss",
    "Протоссы": "Protoss",
    "Protoss": "Protoss",
}

WORKER_NAMES = {"SCV", "Probe", "Drone"}

# Morphing/merging unit types that should not count as unit deaths when replaced by a building/Archon
ZERG_MORPH_EXCLUSIONS = {"Drone", "HighTemplar", "DarkTemplar"}

ABILITY_COMMAND_EVENTS = {
    "TargetPointCommandEvent",
    "TargetUnitCommandEvent",
    "BasicCommandEvent",
}

# Maps raw sc2reader ability names to canonical names for compact storage and UI rendering
TRACKED_ABILITY_MAP: dict[str, str] = {
    # Combat abilities
    "UseStimpack": "Stimpack",
    "Stimpack": "Stimpack",
    "StimpackRedirect": "Stimpack",
    "StimpackMarauderRedirect": "Stimpack",
    "Stim": "Stimpack",
    "PsionicStorm": "PsiStorm",
    "PsiStorm": "PsiStorm",
    "ForceField": "ForceField",
    "GuardianShield": "GuardianShield",
    "EMPRound": "EMP",
    "EMP": "EMP",
    "ChannelSnipe": "Snipe",
    "Snipe": "Snipe",
    "YamatoGun": "YamatoGun",
    "Blink": "Blink",
    "DarkTemplarBlink": "Blink",
    "PurificationNovaTargeted": "PurificationNova",
    "PurificationNova": "PurificationNova",
    "FungalGrowth": "FungalGrowth",
    "RavagerCorrosiveBile": "CorrosiveBile",
    "CorrosiveBile": "CorrosiveBile",
    "QueenTransfusion": "Transfuse",
    "Transfusion": "Transfuse",
    "Transfuse": "Transfuse",
    "BlindingCloud": "BlindingCloud",
    "ParasiticBomb": "ParasiticBomb",
    "RavenShredderMissile": "AntiArmorMissile",
    "AntiArmorMissile": "AntiArmorMissile",
    "RavenScramblerMissile": "InterferenceMatrix",
    "InterferenceMatrix": "InterferenceMatrix",
    "Feedback": "Feedback",
    "Abduct": "Abduct",
    # Utility / macro abilities
    "ScannerSweep": "ScannerSweep",
    "SpawnLarva": "InjectLarva",
    "InjectLarva": "InjectLarva",
    "ChronoBoostEnergyCost": "ChronoBoost",
    "ChronoBoost": "ChronoBoost",
}


class ReplayParseError(Exception):
    """Base error raised when a replay cannot be parsed."""


class UnsupportedGameTypeError(ReplayParseError):
    """Raised when the replay is not a standard 1v1 game."""


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_ignored_unit(name: str) -> bool:
    return name in IGNORED_UNIT_NAMES or name.startswith("Beacon")


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("_")
    if not cleaned or cleaned != name.strip().replace(" ", "_"):
        suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
        return f"{cleaned or 'map'}_{suffix}"
    return cleaned


def _frame_to_sec(frame: int) -> int:
    return max(0, int(round(frame / FRAMES_PER_REAL_SEC)))


def _frame_to_exact_sec(frame: int) -> float:
    return round(max(0.0, frame / FRAMES_PER_REAL_SEC), 2)


def _extract_minimap_png(replay: sc2reader.resources.Replay) -> bytes | None:
    try:
        replay.load_map()
        return render_tactical_map_png(replay)
    except Exception:
        return None


def _compute_apm(replay: sc2reader.resources.Replay, duration_sec: int) -> dict[int, int]:
    if duration_sec <= 0:
        return {p.pid: 0 for p in replay.players}
    counts: dict[int, int] = {p.pid: 0 for p in replay.players}
    for evt in getattr(replay, "game_events", ()):
        player = getattr(evt, "player", None)
        if player and player.pid in counts:
            name = type(evt).__name__
            if name in {"SelectionEvent", "ControlGroupEvent", "CommandEvent", "BasicCommandEvent", "TargetPointCommandEvent", "TargetUnitCommandEvent"}:
                counts[player.pid] += 1
    minutes = duration_sec / 60.0
    return {pid: int(round(cnt / minutes)) for pid, cnt in counts.items()}


def _extract_ability_casts(
    replay: sc2reader.resources.Replay,
    valid_pids: set[int],
) -> tuple[dict[int, str], list[list[int | float | None]]]:
    """Extract deduplicated combat and key macro ability casts from replay.game_events."""
    ability_name_to_id: dict[str, int] = {}
    ability_dict: dict[int, str] = {}
    ability_casts: list[list[int | float | None]] = []

    last_non_target_cast: dict[tuple[int, int], float] = {}
    recent_target_casts: dict[tuple[int, int], list[tuple[float, float, float]]] = {}

    def get_ability_id(name: str) -> int:
        if name not in ability_name_to_id:
            aid = len(ability_name_to_id) + 1
            ability_name_to_id[name] = aid
            ability_dict[aid] = name
        return ability_name_to_id[name]

    for evt in getattr(replay, "game_events", ()):
        if type(evt).__name__ not in ABILITY_COMMAND_EVENTS:
            continue
        player = getattr(evt, "player", None)
        if not player or player.pid not in valid_pids:
            continue

        raw_name = getattr(evt, "ability_name", None) or getattr(getattr(evt, "ability", None), "name", None)
        if not raw_name:
            continue
        canonical = TRACKED_ABILITY_MAP.get(raw_name)
        if not canonical:
            continue

        time_sec = _frame_to_exact_sec(evt.frame)
        loc = getattr(evt, "location", None)
        if loc is None:
            target_unit = getattr(evt, "target_unit", None)
            loc = getattr(target_unit, "location", None) if target_unit is not None else None

        if loc is not None and len(loc) >= 2:
            x: float | None = round(float(loc[0]), 1)
            y: float | None = round(float(loc[1]), 1)
        else:
            x = None
            y = None

        aid = get_ability_id(canonical)
        key = (player.pid, aid)

        if x is None or y is None:
            prev_t = last_non_target_cast.get(key)
            if prev_t is not None and abs(time_sec - prev_t) < 1.0:
                continue
            last_non_target_cast[key] = time_sec
        else:
            recent = recent_target_casts.get(key, [])
            # Keep only recent casts within 1.0s to bound per-key check
            recent = [(pt, px, py) for pt, px, py in recent if abs(time_sec - pt) <= 1.0]
            if any(abs(time_sec - pt) < 0.5 and (x - px) ** 2 + (y - py) ** 2 < 2.25 for pt, px, py in recent):
                recent_target_casts[key] = recent
                continue
            recent.append((time_sec, x, y))
            recent_target_casts[key] = recent

        ability_casts.append([time_sec, player.pid, aid, x, y])

    ability_casts.sort(key=lambda item: float(item[0]))
    return ability_dict, ability_casts


LONG_RANGE_KILLER_NAMES = {
    "SiegeTankSieged",
    "Tempest",
    "Carrier",
    "BroodLord",
    "Thor",
    "ThorAP",
    "LiberatorAG",
    "LurkerMPBurrowed",
    "Battlecruiser",
}

MELEE_KILLER_NAMES = {
    "SCV",
    "Probe",
    "Drone",
    "Zergling",
    "Baneling",
    "Zealot",
    "DarkTemplar",
    "Ultralisk",
    "BattleHellion",
    "HellionTank",
}


def _get_killer_max_tracer_dist(killer_name: str | None) -> float:
    if killer_name in LONG_RANGE_KILLER_NAMES:
        return 18.0
    if killer_name in MELEE_KILLER_NAMES:
        return 3.5
    return 9.5


def _build_unit_position_tracks(
    tracker_events: list,
) -> dict[int, tuple[list[int], list[tuple[float, float]]]]:
    """Build per-unit (frames, coords) tracks from tracker_events for accurate killer interpolation."""
    raw_tracks: dict[int, list[tuple[int, float, float]]] = {}

    for evt in tracker_events:
        ename = type(evt).__name__
        frame = int(getattr(evt, "frame", 0) or 0)
        if ename in {"UnitBornEvent", "UnitInitEvent", "UnitDiedEvent"}:
            unit = getattr(evt, "unit", None)
            loc = getattr(evt, "location", None) or (getattr(unit, "location", None) if unit else None)
            if unit and loc and len(loc) >= 2:
                raw_tracks.setdefault(unit.id, []).append((frame, float(loc[0]), float(loc[1])))
        elif ename == "UnitPositionsEvent":
            units_pos = getattr(evt, "units", None) or {}
            for unit, loc in units_pos.items():
                if unit and loc and len(loc) >= 2:
                    raw_tracks.setdefault(unit.id, []).append((frame, float(loc[0]), float(loc[1])))

    tracks: dict[int, tuple[list[int], list[tuple[float, float]]]] = {}
    for uid, pts in raw_tracks.items():
        pts.sort(key=lambda item: item[0])
        frames = [p[0] for p in pts]
        coords = [(p[1], p[2]) for p in pts]
        tracks[uid] = (frames, coords)
    return tracks


def _interpolate_track_pos(
    track: tuple[list[int], list[tuple[float, float]]],
    target_frame: int,
    max_before_frames: int | None = None,
    max_after_frames: int | None = None,
) -> tuple[float, float] | None:
    """Linearly interpolate a unit's (x, y) position at target_frame from its sorted track."""
    frames, coords = track
    if not frames:
        return None

    idx = bisect_right(frames, target_frame)
    has_before = idx > 0 and (
        max_before_frames is None or (target_frame - frames[idx - 1]) <= max_before_frames
    )
    has_after = idx < len(frames) and (
        max_after_frames is None or (frames[idx] - target_frame) <= max_after_frames
    )

    if has_before and has_after:
        f0 = frames[idx - 1]
        f1 = frames[idx]
        x0, y0 = coords[idx - 1]
        x1, y1 = coords[idx]
        if f1 > f0:
            t = (target_frame - f0) / (f1 - f0)
            return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        return x0, y0
    if has_after:
        return coords[idx]
    if has_before:
        return coords[idx - 1]
    return None


def _sample_unit_pos(
    tracks: dict[int, tuple[list[int], list[tuple[float, float]]]],
    uid: int,
    sample_frame: int,
    fallback: tuple[float, float],
    sim_match: "SimulatedMatch | None" = None,
) -> tuple[float, float]:
    """Return rounded (x, y) for uid at sample_frame using simulator or track fallback."""
    if sim_match is not None:
        pos = sim_match.get_unit_pos(uid, sample_frame)
        if pos is not None:
            return round(pos[0], 1), round(pos[1], 1)

    track = tracks.get(uid)
    if not track:
        return fallback
    pos = _interpolate_track_pos(track, sample_frame)
    if pos is None:
        return fallback
    return round(pos[0], 1), round(pos[1], 1)


def _resolve_killer_pos(
    tracks: dict[int, tuple[list[int], list[tuple[float, float]]]],
    killer_uid: int | None,
    killer_name: str | None,
    death_frame: int,
    victim_x: float,
    victim_y: float,
    sim_match: "SimulatedMatch | None" = None,
) -> tuple[float | None, float | None]:
    """Interpolate killer position at death_frame and validate it against attack range."""
    if killer_uid is None:
        return None, None

    pos: tuple[float, float] | None = None
    if sim_match is not None:
        pos = sim_match.get_unit_pos(killer_uid, death_frame, max_outside_sec=4.0)

    if pos is None and killer_uid in tracks:
        pos = _interpolate_track_pos(
            tracks[killer_uid],
            death_frame,
            max_before_frames=int(5.0 * FRAMES_PER_REAL_SEC),
            max_after_frames=int(4.0 * FRAMES_PER_REAL_SEC),
        )
    if pos is None:
        return None, None
    kx, ky = pos

    dist = math.hypot(victim_x - kx, victim_y - ky)
    if dist <= 0.4 or dist > _get_killer_max_tracer_dist(killer_name):
        return None, None

    return round(kx, 1), round(ky, 1)


def parse_replay_file(
    path: Path,
    sample_step_sec: int = 3,
    use_simulator: bool = True,
) -> ParsedReplayBundle:
    """Parse a 1v1 .SC2Replay file into a domain ParsedReplayBundle."""
    if not path.is_file():
        raise ReplayParseError(f"Replay file not found: {path}")

    sha256 = _compute_sha256(path)
    replay_id = sha256[:12]

    try:
        replay = sc2reader.load_replay(str(path), load_level=4)
    except Exception as exc:
        raise ReplayParseError(f"Failed to load replay: {exc}") from exc

    if replay.game_type != "1v1" or len(replay.players) != 2:
        raise UnsupportedGameTypeError(
            f"Only 1v1 games are supported (got: {replay.game_type}, players: {len(replay.players)})"
        )

    duration_sec = max(1, int(replay.game_length.seconds))
    minimap_png = _extract_minimap_png(replay)
    map_width = getattr(getattr(getattr(replay, "map", None), "map_info", None), "width", 200)
    map_height = getattr(getattr(getattr(replay, "map", None), "map_info", None), "height", 200)
    bounds = get_camera_bounds(replay)
    map_bounds = list(bounds) if bounds else None
    sanitized_base = _sanitize_filename(replay.map_name)
    minimap_filename = f"{sanitized_base}.png"
    expected_aspect = (
        (bounds[2] - bounds[0]) / (bounds[3] - bounds[1])
        if bounds and (bounds[3] - bounds[1]) > 0
        else (map_width / map_height if map_height else None)
    )
    en_map_name = getattr(getattr(replay, "map", None), "name", "") or ""
    hd_map_filename, hd_map_bytes = resolve_hd_map(
        [en_map_name, replay.map_name],
        sanitized_base=sanitized_base,
        expected_aspect=expected_aspect,
    )

    played_at = datetime.fromtimestamp(replay.unix_timestamp, tz=timezone.utc).isoformat()
    apm_by_pid = _compute_apm(replay, duration_sec)

    # Extract PlayerStatsEvent series & player peaks
    times_sec: list[int] = []
    army_value: dict[int, list[int]] = {p.pid: [] for p in replay.players}
    workers_series: dict[int, list[int]] = {p.pid: [] for p in replay.players}
    unspent_series: dict[int, list[int]] = {p.pid: [] for p in replay.players}
    supply_series: dict[int, list[int]] = {p.pid: [] for p in replay.players}

    last_stats: dict[int, object] = {}
    stats_by_time: dict[int, dict[int, object]] = {}
    supply_samples: dict[int, list[tuple[int, float, float]]] = {p.pid: [] for p in replay.players}
    unspent_samples: dict[int, list[float]] = {p.pid: [] for p in replay.players}
    income_samples: dict[int, list[float]] = {p.pid: [] for p in replay.players}

    for evt in replay.tracker_events:
        if type(evt).__name__ == "PlayerStatsEvent" and evt.pid in army_value:
            sec = _frame_to_sec(evt.frame)
            bucket = (sec // 5) * 5
            stats_by_time.setdefault(bucket, {})[evt.pid] = evt
            last_stats[evt.pid] = evt
            supply_samples[evt.pid].append(
                (
                    sec,
                    float(getattr(evt, "food_used", 0) or 0),
                    float(getattr(evt, "food_made", 0) or 0),
                )
            )
            unspent_samples[evt.pid].append(
                float(getattr(evt, "minerals_current", 0) or 0)
                + float(getattr(evt, "vespene_current", 0) or 0)
            )
            income_samples[evt.pid].append(
                float(getattr(evt, "minerals_collection_rate", 0) or 0)
                + float(getattr(evt, "vespene_collection_rate", 0) or 0)
            )

    for t in sorted(stats_by_time.keys()):
        if len(stats_by_time[t]) < 2:
            continue
        times_sec.append(t)
        for pid in army_value:
            st = stats_by_time[t][pid]
            army_val = int(getattr(st, "minerals_used_current_army", 0) + getattr(st, "vespene_used_current_army", 0))
            army_value[pid].append(army_val)
            workers_series[pid].append(int(getattr(st, "workers_active_count", 0)))
            unspent_series[pid].append(int(getattr(st, "minerals_current", 0) + getattr(st, "vespene_current", 0)))
            supply_series[pid].append(int(round(getattr(st, "food_used", 0))))

    workers_killed: dict[int, int] = {p.pid: 0 for p in replay.players}
    workers_lost: dict[int, int] = {p.pid: 0 for p in replay.players}

    # Track unit positions, deaths, and build order
    unit_name_to_id: dict[str, int] = {}
    unit_dict: dict[int, str] = {}

    def get_type_id(name: str) -> int:
        if name not in unit_name_to_id:
            tid = len(unit_name_to_id) + 1
            unit_name_to_id[name] = tid
            unit_dict[tid] = name
        return unit_name_to_id[name]

    # Active unit state: uid -> (pid, type_id, x, y)
    active_units: dict[int, list] = {}
    last_sent_units: dict[int, tuple[int, int, float, float]] = {}
    deaths: list[UnitDeathRecord] = []
    death_events: list[list[int | float | None]] = []
    build_order: list[BuildOrderItem] = []

    # Group tracker events by real second for timeline sampling
    unit_tracks = _build_unit_position_tracks(replay.tracker_events)
    sim_match: "SimulatedMatch | None" = None
    if use_simulator:
        try:
            from app.parser.simulator import simulate_replay

            sim_match = simulate_replay(replay, dt=0.5)
        except Exception as exc:
            logger.warning("Hybrid simulator failed, falling back to linear tracks: %s", exc)
            sim_match = None

    events_by_sec: dict[int, list] = {}
    for evt in replay.tracker_events:
        sec = _frame_to_sec(evt.frame)
        events_by_sec.setdefault(sec, []).append(evt)

    frames: list[TimelineFrame] = []
    next_sample_sec = 0
    sample_idx = 0

    for sec in range(0, duration_sec + 1):
        for evt in events_by_sec.get(sec, ()):
            ename = type(evt).__name__
            if ename in {"UnitBornEvent", "UnitInitEvent"}:
                unit = getattr(evt, "unit", None)
                owner = getattr(unit, "owner", None) if unit else None
                if not unit or not owner or owner.pid not in army_value:
                    continue
                if _is_ignored_unit(unit.name):
                    continue
                loc = getattr(evt, "location", None) or getattr(unit, "location", None)
                if not loc:
                    continue
                tid = get_type_id(unit.name)
                active_units[unit.id] = [owner.pid, tid, round(float(loc[0]), 1), round(float(loc[1]), 1)]

                if sec > 2 and unit.name not in WORKER_NAMES:
                    kind = "building" if getattr(unit, "is_building", False) else "unit"
                    build_order.append(BuildOrderItem(time_sec=sec, pid=owner.pid, name=unit.name, kind=kind))

            elif ename == "UnitTypeChangeEvent":
                unit = getattr(evt, "unit", None)
                if unit and unit.id in active_units:
                    new_name = getattr(evt, "unit_type_name", None) or unit.name
                    if not _is_ignored_unit(new_name):
                        active_units[unit.id][1] = get_type_id(new_name)

            elif ename == "UnitPositionsEvent":
                units_pos = getattr(evt, "units", None) or {}
                for unit, loc in units_pos.items():
                    if unit.id in active_units and loc:
                        active_units[unit.id][2] = round(float(loc[0]), 1)
                        active_units[unit.id][3] = round(float(loc[1]), 1)

            elif ename == "UnitOwnerChangeEvent":
                unit = getattr(evt, "unit", None)
                if unit and unit.id in active_units:
                    new_pid = getattr(evt, "control_pid", None) or getattr(getattr(unit, "owner", None), "pid", None)
                    if new_pid in army_value:
                        active_units[unit.id][0] = new_pid
                    else:
                        active_units.pop(unit.id, None)

            elif ename == "UnitDiedEvent":
                unit = getattr(evt, "unit", None)
                if not unit:
                    continue
                state = active_units.pop(unit.id, None)
                owner = getattr(unit, "owner", None)
                if not owner or owner.pid not in army_value:
                    continue
                if _is_ignored_unit(unit.name):
                    continue
                killer = getattr(evt, "killing_player", None)
                # Skip Drone death if it was killed by morphing into a building (no killer player)
                if unit.name in ZERG_MORPH_EXCLUSIONS and killer is None:
                    continue
                k_pid = killer.pid if killer is not None else getattr(evt, "killer_pid", None)
                if unit.name in WORKER_NAMES:
                    workers_lost[owner.pid] += 1
                    if k_pid in workers_killed and k_pid != owner.pid:
                        workers_killed[k_pid] += 1
                loc = getattr(evt, "location", None) or (state[2], state[3]) if state else getattr(unit, "location", None)
                if not loc:
                    continue
                minerals = int(getattr(unit, "minerals", 0) or 0)
                vespene = int(getattr(unit, "vespene", 0) or 0)
                dx = round(float(loc[0]), 1)
                dy = round(float(loc[1]), 1)
                deaths.append(
                    UnitDeathRecord(
                        time_sec=sec,
                        pid=owner.pid,
                        unit_name=unit.name,
                        x=float(loc[0]),
                        y=float(loc[1]),
                        minerals=minerals,
                        vespene=vespene,
                    )
                )
                k_unit = getattr(evt, "killing_unit", None)
                k_uid = getattr(k_unit, "id", None) if k_unit is not None else None
                k_name = getattr(k_unit, "name", None) if k_unit is not None else None
                k_type_id = get_type_id(k_name) if (k_name and not _is_ignored_unit(k_name)) else None
                valid_k_pid = k_pid if k_pid in army_value else None
                kx, ky = _resolve_killer_pos(
                    unit_tracks,
                    k_uid,
                    k_name,
                    int(getattr(evt, "frame", 0) or 0),
                    float(loc[0]),
                    float(loc[1]),
                    sim_match=sim_match,
                )
                death_events.append([
                    _frame_to_exact_sec(evt.frame),
                    unit.id,
                    owner.pid,
                    get_type_id(unit.name),
                    dx,
                    dy,
                    k_uid,
                    valid_k_pid,
                    k_type_id,
                    minerals + vespene,
                    kx,
                    ky,
                ])

            elif ename == "UpgradeCompleteEvent":
                pid = getattr(evt, "pid", None)
                up_name = getattr(evt, "upgrade_type_name", "")
                if pid in army_value and sec > 5 and up_name and not up_name.startswith("Spray"):
                    build_order.append(BuildOrderItem(time_sec=sec, pid=pid, name=up_name, kind="upgrade"))

        if sec >= next_sample_sec:
            sample_frame = int(round(sec * FRAMES_PER_REAL_SEC))
            sampled_units: dict[int, tuple[int, int, float, float]] = {}
            for uid, st in active_units.items():
                if sim_match is not None and sim_match.is_in_cargo(uid, sample_frame):
                    continue
                sx, sy = _sample_unit_pos(
                    unit_tracks,
                    uid,
                    sample_frame,
                    (st[2], st[3]),
                    sim_match=sim_match,
                )
                sampled_units[uid] = (st[0], st[1], sx, sy)

            is_keyframe = (sample_idx % 20 == 0)  # full snapshot every ~60s for fast seeking
            if is_keyframe:
                snapshot = [[uid, cur[0], cur[1], cur[2], cur[3]] for uid, cur in sampled_units.items()]
                frames.append(TimelineFrame(time_sec=sec, is_keyframe=True, units=snapshot))
            else:
                changed = [
                    [uid, cur[0], cur[1], cur[2], cur[3]]
                    for uid, cur in sampled_units.items()
                    if last_sent_units.get(uid) != cur
                ]
                removed = [uid for uid in last_sent_units if uid not in sampled_units]
                frames.append(TimelineFrame(time_sec=sec, is_keyframe=False, units=changed, removed=removed))

            last_sent_units = sampled_units
            sample_idx += 1
            next_sample_sec += sample_step_sec

    battles = detect_battles(deaths)
    ability_dict, ability_casts = _extract_ability_casts(replay, set(army_value.keys()))

    players: list[PlayerInfo] = []
    for p in replay.players:
        st = last_stats.get(p.pid)
        race = RACE_MAP.get(p.play_race, p.play_race)
        color_hex = f"#{p.color.hex}" if hasattr(p, "color") and p.color else "#ffffff"
        u_list = unspent_samples[p.pid]
        i_list = income_samples[p.pid]
        avg_unspent = sum(u_list) / len(u_list) if u_list else 0.0
        avg_income = sum(i_list) / len(i_list) if i_list else 0.0
        sq = compute_spending_quotient(avg_unspent, avg_income)
        sb_sec = compute_supply_block_sec(supply_samples[p.pid])
        timings = extract_key_timings(build_order, p.pid, race)
        archetype = detect_build_archetype(build_order, p.pid, race, timings)
        players.append(
            PlayerInfo(
                pid=p.pid,
                name=p.name,
                race=race,
                color_hex=color_hex,
                result=p.result or "Unknown",
                apm=apm_by_pid.get(p.pid, 0),
                workers_peak=max(workers_series[p.pid], default=0),
                army_value_peak=max(army_value[p.pid], default=0),
                minerals_lost=int(getattr(st, "minerals_lost", 0)) if st else 0,
                vespene_lost=int(getattr(st, "vespene_lost", 0)) if st else 0,
                spending_quotient=sq,
                supply_block_sec=sb_sec,
                workers_killed=workers_killed.get(p.pid, 0),
                workers_lost=workers_lost.get(p.pid, 0),
                avg_unspent=int(round(avg_unspent)),
                build_archetype=archetype,
                key_timings=timings,
            )
        )

    data = ReplayData(
        meta=MatchMeta(
            replay_id=replay_id,
            sha256=sha256,
            map_name=replay.map_name,
            map_width=map_width,
            map_height=map_height,
            map_bounds=map_bounds,
            minimap_filename=minimap_filename,
            hd_map_filename=hd_map_filename,
            duration_sec=duration_sec,
            version=replay.release_string,
            played_at=played_at,
        ),
        players=players,
        unit_dict=unit_dict,
        frames=frames,
        battles=battles,
        build_order=build_order,
        charts=ChartSeries(
            times_sec=times_sec,
            army_value=army_value,
            workers=workers_series,
            unspent_resources=unspent_series,
            supply_used=supply_series,
        ),
        deaths=death_events,
        ability_dict=ability_dict,
        ability_casts=ability_casts,
    )

    return ParsedReplayBundle(data=data, minimap_png=minimap_png, hd_map_bytes=hd_map_bytes)


async def parse_replay_async(path: Path, sample_step_sec: int = 3) -> ParsedReplayBundle:
    """Offload CPU-bound replay parsing to a worker thread."""
    return await asyncio.to_thread(parse_replay_file, path, sample_step_sec)
