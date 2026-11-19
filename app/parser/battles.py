from dataclasses import dataclass
import math
from app.domain.models import BattleEvent


@dataclass(frozen=True)
class UnitDeathRecord:
    time_sec: int
    pid: int
    unit_name: str
    x: float
    y: float
    minerals: int
    vespene: int


def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x1 - x2, y1 - y2)


def detect_battles(
    deaths: list[UnitDeathRecord],
    window_sec: int = 12,
    radius: float = 18.0,
    min_resource_value: int = 150,
) -> list[BattleEvent]:
    """Cluster unit deaths in time and space into meaningful battle events."""
    if not deaths:
        return []

    sorted_deaths = sorted(deaths, key=lambda d: d.time_sec)
    clusters: list[list[UnitDeathRecord]] = []

    for death in sorted_deaths:
        placed = False
        # Search recent clusters backwards for efficiency
        for cluster in reversed(clusters):
            last_time = cluster[-1].time_sec
            if death.time_sec - last_time > window_sec:
                break
            cx = sum(d.x for d in cluster) / len(cluster)
            cy = sum(d.y for d in cluster) / len(cluster)
            if _dist(death.x, death.y, cx, cy) <= radius:
                cluster.append(death)
                placed = True
                break
        if not placed:
            clusters.append([death])

    battles: list[BattleEvent] = []
    for cluster in clusters:
        pids_involved = {d.pid for d in cluster}
        total_value = sum(d.minerals + d.vespene for d in cluster)
        if len(pids_involved) < 2 and total_value < min_resource_value * 2:
            continue
        if total_value < min_resource_value:
            continue

        lost_minerals: dict[int, int] = {}
        lost_gas: dict[int, int] = {}
        units_lost: dict[int, dict[str, int]] = {}

        for d in cluster:
            lost_minerals[d.pid] = lost_minerals.get(d.pid, 0) + d.minerals
            lost_gas[d.pid] = lost_gas.get(d.pid, 0) + d.vespene
            p_units = units_lost.setdefault(d.pid, {})
            p_units[d.unit_name] = p_units.get(d.unit_name, 0) + 1

        winner_pid: int | None = None
        if len(pids_involved) == 2:
            p1, p2 = sorted(pids_involved)
            v1 = lost_minerals.get(p1, 0) + lost_gas.get(p1, 0)
            v2 = lost_minerals.get(p2, 0) + lost_gas.get(p2, 0)
            if v1 < v2 * 0.8:
                winner_pid = p1
            elif v2 < v1 * 0.8:
                winner_pid = p2

        battles.append(
            BattleEvent(
                start_sec=cluster[0].time_sec,
                end_sec=cluster[-1].time_sec,
                x=round(sum(d.x for d in cluster) / len(cluster), 1),
                y=round(sum(d.y for d in cluster) / len(cluster), 1),
                lost_minerals=lost_minerals,
                lost_gas=lost_gas,
                units_lost=units_lost,
                winner_pid=winner_pid,
            )
        )

    return battles
