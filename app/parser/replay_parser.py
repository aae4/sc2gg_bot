import asyncio
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
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

IGNORED_UNIT_NAMES = {
    "Egg",
    "Larva",
    "Broodling",
    "BroodlingEscort",
    "Interceptor",
    "LocustMP",
    "LocustMPFlying",
    "AutoTurret",
    "PointDefenseDrone",
    "KD8Charge",
    "AdeptPhaseShift",
    "DisruptorPhased",
    "MULE",
}

WORKER_NAMES = {"SCV", "Probe", "Drone"}

# Morphing unit types that should not count as unit deaths when replaced by a building/cocoon
ZERG_MORPH_EXCLUSIONS = {"Drone"}


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


def _extract_minimap_png(replay: sc2reader.resources.Replay) -> bytes | None:
    try:
        replay.load_map()
        if not getattr(replay, "map", None) or not replay.map.minimap:
            return None
        with Image.open(io.BytesIO(replay.map.minimap)) as img:
            rgb = img.convert("RGB")
            bbox = rgb.getbbox()
            cropped = img.crop(bbox) if bbox else img
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            return buf.getvalue()
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


def parse_replay_file(path: Path, sample_step_sec: int = 3) -> ParsedReplayBundle:
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
    minimap_filename = f"{_sanitize_filename(replay.map_name)}.png"

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
    build_order: list[BuildOrderItem] = []

    # Group tracker events by real second for timeline sampling
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
                # Skip Drone death if it was killed by morphing into a building (no killer player)
                if unit.name in ZERG_MORPH_EXCLUSIONS and getattr(evt, "killing_player", None) is None:
                    continue
                if unit.name in WORKER_NAMES:
                    workers_lost[owner.pid] += 1
                    killer = getattr(evt, "killing_player", None)
                    k_pid = killer.pid if killer is not None else getattr(evt, "killer_pid", None)
                    if k_pid in workers_killed and k_pid != owner.pid:
                        workers_killed[k_pid] += 1
                loc = getattr(evt, "location", None) or (state[2], state[3]) if state else getattr(unit, "location", None)
                if not loc:
                    continue
                deaths.append(
                    UnitDeathRecord(
                        time_sec=sec,
                        pid=owner.pid,
                        unit_name=unit.name,
                        x=float(loc[0]),
                        y=float(loc[1]),
                        minerals=int(getattr(unit, "minerals", 0) or 0),
                        vespene=int(getattr(unit, "vespene", 0) or 0),
                    )
                )

            elif ename == "UpgradeCompleteEvent":
                pid = getattr(evt, "pid", None)
                up_name = getattr(evt, "upgrade_type_name", "")
                if pid in army_value and sec > 5 and up_name and not up_name.startswith("Spray"):
                    build_order.append(BuildOrderItem(time_sec=sec, pid=pid, name=up_name, kind="upgrade"))

        if sec >= next_sample_sec:
            is_keyframe = (sample_idx % 20 == 0)  # full snapshot every ~60s for fast seeking
            if is_keyframe:
                snapshot = [[uid, st[0], st[1], st[2], st[3]] for uid, st in active_units.items()]
                frames.append(TimelineFrame(time_sec=sec, is_keyframe=True, units=snapshot))
            else:
                changed = []
                for uid, st in active_units.items():
                    cur = (st[0], st[1], st[2], st[3])
                    if last_sent_units.get(uid) != cur:
                        changed.append([uid, st[0], st[1], st[2], st[3]])
                removed = [uid for uid in last_sent_units if uid not in active_units]
                frames.append(TimelineFrame(time_sec=sec, is_keyframe=False, units=changed, removed=removed))

            last_sent_units = {uid: (st[0], st[1], st[2], st[3]) for uid, st in active_units.items()}
            sample_idx += 1
            next_sample_sec += sample_step_sec

    battles = detect_battles(deaths)

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
            minimap_filename=minimap_filename,
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
    )

    return ParsedReplayBundle(data=data, minimap_png=minimap_png)


async def parse_replay_async(path: Path, sample_step_sec: int = 3) -> ParsedReplayBundle:
    """Offload CPU-bound replay parsing to a worker thread."""
    return await asyncio.to_thread(parse_replay_file, path, sample_step_sec)
