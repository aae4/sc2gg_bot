import math
from typing import Iterable

from app.domain.models import BuildOrderItem

TOWNHALL_BY_RACE = {
    "Zerg": {"Hatchery", "Lair", "Hive"},
    "Terran": {"CommandCenter", "OrbitalCommand", "PlanetaryFortress"},
    "Protoss": {"Nexus"},
}

TECH_MILESTONES_BY_RACE: dict[str, dict[str, str]] = {
    "Zerg": {
        "SpawningPool": "pool",
        "Lair": "lair",
        "RoachWarren": "roach_warren",
        "BanelingNest": "bane_nest",
        "Spire": "spire",
        "HydraliskDen": "hydra_den",
        "InfestationPit": "infestation_pit",
        "LurkerDenMP": "lurker_den",
        "Hive": "hive",
    },
    "Terran": {
        "Barracks": "barracks",
        "Factory": "factory",
        "Starport": "starport",
        "Stimpack": "stim",
        "CombatShield": "combat_shield",
        "Armory": "armory",
        "FusionCore": "fusion_core",
    },
    "Protoss": {
        "CyberneticsCore": "cyber_core",
        "TwilightCouncil": "twilight",
        "RoboticsFacility": "robo",
        "Stargate": "stargate",
        "TemplarArchive": "templar_archive",
        "DarkShrine": "dark_shrine",
        "FleetBeacon": "fleet_beacon",
        "BlinkTech": "blink",
    },
}


def compute_spending_quotient(avg_unspent: float, avg_income: float) -> int:
    """Compute StarCraft II Spending Quotient (SQ) from average unspent & collection rate."""
    if avg_income <= 0:
        return 0
    safe_unspent = max(1.0, avg_unspent)
    sq = 35.0 * (0.00137 * avg_income - math.log(safe_unspent)) + 240.0
    return max(0, int(round(sq)))


def compute_supply_block_sec(samples: Iterable[tuple[int, float, float]]) -> int:
    """Estimate total seconds spent supply-blocked from (time_sec, food_used, food_made) samples."""
    ordered = sorted(samples, key=lambda item: item[0])
    if len(ordered) < 2:
        return 0

    blocked_sec = 0
    for idx in range(1, len(ordered)):
        prev_t, prev_used, prev_made = ordered[idx - 1]
        cur_t, _, _ = ordered[idx]
        dt = max(0, cur_t - prev_t)
        if dt == 0:
            continue
        # Ignore opening 30s and max-supply (200) states
        if prev_t >= 30 and 0 < prev_made < 200 and prev_used >= prev_made:
            blocked_sec += min(dt, 30)
    return blocked_sec


def extract_key_timings(
    build_order: Iterable[BuildOrderItem],
    pid: int,
    race: str,
) -> dict[str, int]:
    """Extract key expansion and tech timings (in seconds) for a player."""
    timings: dict[str, int] = {}
    townhalls = TOWNHALL_BY_RACE.get(race, set())
    tech_map = TECH_MILESTONES_BY_RACE.get(race, {})

    expansion_count = 0
    for item in build_order:
        if item.pid != pid:
            continue
        if item.name in townhalls and item.kind == "building":
            expansion_count += 1
            if expansion_count == 1 and "natural" not in timings:
                timings["natural"] = item.time_sec
            elif expansion_count == 2 and "third" not in timings:
                timings["third"] = item.time_sec
        milestone_key = tech_map.get(item.name)
        if milestone_key and milestone_key not in timings:
            timings[milestone_key] = item.time_sec

    return timings


def detect_build_archetype(
    build_order: Iterable[BuildOrderItem],
    pid: int,
    race: str,
    key_timings: dict[str, int],
) -> str:
    """Heuristically classify a player's opening build archetype."""
    early_items = [
        item for item in build_order if item.pid == pid and item.time_sec <= 330
    ]
    if not early_items:
        return ""

    counts: dict[str, int] = {}
    for item in early_items:
        counts[item.name] = counts.get(item.name, 0) + 1

    nat = key_timings.get("natural")
    third = key_timings.get("third")

    if race == "Zerg":
        pool_t = key_timings.get("pool")
        if pool_t is not None and pool_t <= 65 and (nat is None or nat > pool_t):
            return "Early Pool"
        if third is not None and third <= 240:
            return "3-Base Macro"
        if nat is not None and nat <= 105:
            return "Hatch First"
        if "Spire" in counts:
            return "Mutalisk Tech"
        if "RoachWarren" in counts:
            return "Roach Opening"
        return "Standard Zerg"

    if race == "Terran":
        rax = counts.get("Barracks", 0)
        fac = counts.get("Factory", 0)
        port = counts.get("Starport", 0)
        if rax >= 2 and fac == 0 and port == 0 and (nat is None or nat > 180):
            return "Multi-Rax Aggro"
        if rax >= 2 and port >= 1:
            return "2-1-1 Bio"
        if rax >= 1 and fac >= 1 and port >= 1:
            return "1-1-1"
        if nat is not None and nat <= 135:
            return "Fast Expand"
        return "Standard Terran"

    if race == "Protoss":
        if counts.get("PhotonCannon", 0) >= 2 and early_items[0].time_sec <= 150:
            return "Cannon Rush"
        if "Stargate" in counts:
            return "Stargate Opening"
        if "DarkShrine" in counts:
            return "DT Rush"
        if "TwilightCouncil" in counts:
            return "Twilight Opening"
        if "RoboticsFacility" in counts:
            return "Robo Opening"
        if nat is not None and nat <= 125:
            return "Fast Expand"
        return "Standard Protoss"

    return ""
