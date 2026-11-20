"""StarCraft II LotV unit, transport, and upgrade specifications for replay simulation.

All movement speeds are expressed in map tiles per real-time second at LotV
"Faster" game speed (1 real second = 22.4 game frames = 1.4 game seconds).
"""

from __future__ import annotations

from dataclasses import dataclass

IGNORED_UNIT_NAMES: frozenset[str] = frozenset(
    {
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
)


@dataclass(frozen=True, slots=True)
class UnitSpec:
    """Static physical and combat parameters of a StarCraft II unit or structure."""

    name: str
    race: str
    speed: float
    is_flying: bool = False
    is_building: bool = False
    radius: float = 0.5
    attack_range: float = 0.0
    max_hp: float = 50.0
    cargo_capacity: int = 0
    cargo_size: int = 0
    creep_speed_mult: float = 1.0


# Canonical unit aliases emitted by different sc2reader / SC2 patch versions
UNIT_NAME_ALIASES: dict[str, str] = {
    "VikingFighter": "Viking",
    "ThorAP": "Thor",
    "HellionTank": "Hellbat",
    "LurkerMP": "Lurker",
    "LurkerMPBurrowed": "LurkerBurrowed",
    "SwarmHostMP": "SwarmHost",
    "RavagerCocoon": "Ravager",
    "BanelingCocoon": "Baneling",
    "BroodLordCocoon": "Corruptor",
    "OverlordCocoon": "Overlord",
    "OverseerSiegeMode": "Overseer",
    "ObserverSiegeMode": "Observer",
    "CommandCenterFlying": "CommandCenter",
    "OrbitalCommandFlying": "OrbitalCommand",
    "BarracksFlying": "Barracks",
    "FactoryFlying": "Factory",
    "StarportFlying": "Starport",
    "SupplyDepotLowered": "SupplyDepot",
}


_RAW_SPECS: list[UnitSpec] = [
    # --- Terran ---
    UnitSpec("SCV", "Terran", speed=3.94, radius=0.375, attack_range=0.1, max_hp=45.0, cargo_size=1),
    UnitSpec("MULE", "Terran", speed=3.94, radius=0.375, max_hp=60.0),
    UnitSpec("Marine", "Terran", speed=3.15, radius=0.375, attack_range=5.0, max_hp=45.0, cargo_size=1),
    UnitSpec("Marauder", "Terran", speed=3.15, radius=0.5625, attack_range=6.0, max_hp=125.0, cargo_size=2),
    UnitSpec("Reaper", "Terran", speed=5.25, radius=0.375, attack_range=5.0, max_hp=60.0, cargo_size=1),
    UnitSpec("Ghost", "Terran", speed=3.94, radius=0.375, attack_range=6.0, max_hp=100.0, cargo_size=2),
    UnitSpec("Hellion", "Terran", speed=5.95, radius=0.625, attack_range=5.0, max_hp=90.0, cargo_size=2),
    UnitSpec("Hellbat", "Terran", speed=3.15, radius=0.625, attack_range=2.0, max_hp=135.0, cargo_size=2),
    UnitSpec("WidowMine", "Terran", speed=3.94, radius=0.5, max_hp=90.0, cargo_size=2),
    UnitSpec("WidowMineBurrowed", "Terran", speed=0.0, radius=0.5, attack_range=5.0, max_hp=90.0),
    UnitSpec("SiegeTank", "Terran", speed=3.15, radius=0.875, attack_range=7.0, max_hp=175.0, cargo_size=4),
    UnitSpec("SiegeTankSieged", "Terran", speed=0.0, radius=0.875, attack_range=13.0, max_hp=175.0),
    UnitSpec("Cyclone", "Terran", speed=4.72, radius=0.75, attack_range=5.0, max_hp=120.0, cargo_size=4),
    UnitSpec("Thor", "Terran", speed=2.62, radius=0.8125, attack_range=10.0, max_hp=400.0, cargo_size=8),
    UnitSpec("Viking", "Terran", speed=3.85, is_flying=True, radius=0.75, attack_range=9.0, max_hp=135.0),
    UnitSpec("VikingAssault", "Terran", speed=3.15, radius=0.75, attack_range=6.0, max_hp=135.0, cargo_size=4),
    UnitSpec("Medivac", "Terran", speed=3.50, is_flying=True, radius=0.75, max_hp=150.0, cargo_capacity=8),
    UnitSpec("Liberator", "Terran", speed=4.72, is_flying=True, radius=0.75, attack_range=5.0, max_hp=180.0),
    UnitSpec("LiberatorAG", "Terran", speed=0.0, is_flying=True, radius=0.75, attack_range=10.0, max_hp=180.0),
    UnitSpec("Raven", "Terran", speed=4.13, is_flying=True, radius=0.625, max_hp=140.0),
    UnitSpec("Banshee", "Terran", speed=3.85, is_flying=True, radius=0.75, attack_range=6.0, max_hp=140.0),
    UnitSpec("Battlecruiser", "Terran", speed=2.62, is_flying=True, radius=1.25, attack_range=6.0, max_hp=550.0),
    UnitSpec("Bunker", "Terran", speed=0.0, is_building=True, radius=1.5, attack_range=6.0, max_hp=400.0, cargo_capacity=4),
    UnitSpec("CommandCenter", "Terran", speed=0.0, is_building=True, radius=2.5, max_hp=1500.0, cargo_capacity=5),
    UnitSpec("PlanetaryFortress", "Terran", speed=0.0, is_building=True, radius=2.5, attack_range=6.0, max_hp=1500.0, cargo_capacity=5),

    # --- Zerg ---
    UnitSpec("Drone", "Zerg", speed=3.94, radius=0.375, attack_range=0.1, max_hp=40.0, cargo_size=1, creep_speed_mult=1.0),
    UnitSpec("Queen", "Zerg", speed=1.31, radius=0.875, attack_range=7.0, max_hp=175.0, cargo_size=2, creep_speed_mult=2.67),
    UnitSpec("Zergling", "Zerg", speed=4.13, radius=0.375, attack_range=0.1, max_hp=35.0, cargo_size=1, creep_speed_mult=1.3),
    UnitSpec("ZerglingBurrowed", "Zerg", speed=0.0, radius=0.375, max_hp=35.0),
    UnitSpec("Baneling", "Zerg", speed=3.50, radius=0.375, attack_range=0.25, max_hp=30.0, cargo_size=1, creep_speed_mult=1.3),
    UnitSpec("BanelingBurrowed", "Zerg", speed=0.0, radius=0.375, max_hp=30.0),
    UnitSpec("Roach", "Zerg", speed=3.15, radius=0.5, attack_range=4.0, max_hp=145.0, cargo_size=2, creep_speed_mult=1.3),
    UnitSpec("RoachBurrowed", "Zerg", speed=0.0, radius=0.5, max_hp=145.0),
    UnitSpec("Ravager", "Zerg", speed=3.85, radius=0.75, attack_range=6.0, max_hp=120.0, cargo_size=4, creep_speed_mult=1.3),
    UnitSpec("RavagerBurrowed", "Zerg", speed=0.0, radius=0.75, max_hp=120.0),
    UnitSpec("Hydralisk", "Zerg", speed=3.15, radius=0.625, attack_range=6.0, max_hp=90.0, cargo_size=2, creep_speed_mult=1.3),
    UnitSpec("HydraliskBurrowed", "Zerg", speed=0.0, radius=0.625, max_hp=90.0),
    UnitSpec("Lurker", "Zerg", speed=4.13, radius=0.75, max_hp=200.0, cargo_size=4, creep_speed_mult=1.3),
    UnitSpec("LurkerBurrowed", "Zerg", speed=0.0, radius=0.75, attack_range=8.0, max_hp=200.0),
    UnitSpec("Infestor", "Zerg", speed=3.15, radius=0.75, max_hp=90.0, cargo_size=2, creep_speed_mult=1.3),
    UnitSpec("InfestorBurrowed", "Zerg", speed=2.0, radius=0.75, max_hp=90.0, creep_speed_mult=1.3),
    UnitSpec("SwarmHost", "Zerg", speed=3.15, radius=0.75, max_hp=160.0, cargo_size=4, creep_speed_mult=1.3),
    UnitSpec("SwarmHostBurrowed", "Zerg", speed=0.0, radius=0.75, max_hp=160.0),
    UnitSpec("Ultralisk", "Zerg", speed=4.13, radius=1.0, attack_range=1.0, max_hp=500.0, creep_speed_mult=1.3),
    UnitSpec("UltraliskBurrowed", "Zerg", speed=0.0, radius=1.0, max_hp=500.0),
    UnitSpec("Overlord", "Zerg", speed=0.902, is_flying=True, radius=1.0, max_hp=200.0),
    UnitSpec("OverlordTransport", "Zerg", speed=0.902, is_flying=True, radius=1.0, max_hp=200.0, cargo_capacity=8),
    UnitSpec("Overseer", "Zerg", speed=2.62, is_flying=True, radius=1.0, max_hp=200.0),
    UnitSpec("Mutalisk", "Zerg", speed=5.60, is_flying=True, radius=0.5, attack_range=3.0, max_hp=120.0),
    UnitSpec("Corruptor", "Zerg", speed=4.72, is_flying=True, radius=0.625, attack_range=6.0, max_hp=200.0),
    UnitSpec("BroodLord", "Zerg", speed=1.97, is_flying=True, radius=1.0, attack_range=10.0, max_hp=225.0),
    UnitSpec("Viper", "Zerg", speed=4.13, is_flying=True, radius=1.0, max_hp=150.0),
    UnitSpec("NydusCanal", "Zerg", speed=0.0, is_building=True, radius=1.5, max_hp=200.0, cargo_capacity=999),

    # --- Protoss ---
    UnitSpec("Probe", "Protoss", speed=3.94, radius=0.375, attack_range=0.1, max_hp=40.0, cargo_size=1),
    UnitSpec("Zealot", "Protoss", speed=3.15, radius=0.5, attack_range=0.1, max_hp=150.0, cargo_size=2),
    UnitSpec("Stalker", "Protoss", speed=4.13, radius=0.625, attack_range=6.0, max_hp=160.0, cargo_size=2),
    UnitSpec("Sentry", "Protoss", speed=3.15, radius=0.5, attack_range=5.0, max_hp=80.0, cargo_size=2),
    UnitSpec("Adept", "Protoss", speed=3.50, radius=0.5, attack_range=4.0, max_hp=140.0, cargo_size=2),
    UnitSpec("HighTemplar", "Protoss", speed=2.62, radius=0.375, attack_range=6.0, max_hp=80.0, cargo_size=2),
    UnitSpec("DarkTemplar", "Protoss", speed=3.94, radius=0.375, attack_range=0.1, max_hp=120.0, cargo_size=2),
    UnitSpec("Archon", "Protoss", speed=3.94, radius=1.0, attack_range=3.0, max_hp=360.0, cargo_size=4),
    UnitSpec("Observer", "Protoss", speed=2.63, is_flying=True, radius=0.5, max_hp=60.0),
    UnitSpec("WarpPrism", "Protoss", speed=4.13, is_flying=True, radius=0.75, max_hp=180.0, cargo_capacity=8),
    UnitSpec("WarpPrismPhasing", "Protoss", speed=0.0, is_flying=True, radius=0.75, max_hp=180.0, cargo_capacity=8),
    UnitSpec("Immortal", "Protoss", speed=3.15, radius=0.75, attack_range=6.0, max_hp=300.0, cargo_size=4),
    UnitSpec("Colossus", "Protoss", speed=3.15, radius=1.0, attack_range=7.0, max_hp=350.0),
    UnitSpec("Disruptor", "Protoss", speed=3.15, radius=0.625, max_hp=200.0, cargo_size=4),
    UnitSpec("Phoenix", "Protoss", speed=5.95, is_flying=True, radius=0.75, attack_range=5.0, max_hp=180.0),
    UnitSpec("VoidRay", "Protoss", speed=3.85, is_flying=True, radius=1.0, attack_range=6.0, max_hp=250.0),
    UnitSpec("Oracle", "Protoss", speed=5.60, is_flying=True, radius=0.75, attack_range=4.0, max_hp=160.0),
    UnitSpec("Tempest", "Protoss", speed=3.15, is_flying=True, radius=1.25, attack_range=14.0, max_hp=300.0),
    UnitSpec("Carrier", "Protoss", speed=2.62, is_flying=True, radius=1.25, attack_range=8.0, max_hp=450.0),
    UnitSpec("Mothership", "Protoss", speed=2.62, is_flying=True, radius=1.375, attack_range=7.0, max_hp=700.0),
]

UNIT_SPECS: dict[str, UnitSpec] = {spec.name: spec for spec in _RAW_SPECS}


# Upgrade name aliases from sc2reader -> canonical upgrade keys
UPGRADE_ALIASES: dict[str, str] = {
    "zerglingmovementspeed": "MetabolicBoost",
    "EvolveMuscularAugments": "MuscularAugments",
    "hydraliskspeed": "MuscularAugments",
    "OverlordSpeed": "PneumatizedCarapace",
    "ObserverGraviticBooster": "GraviticBoosters",
    "WarpPrismSpeed": "GraviticDrive",
    "VoidRaySpeedUpgrade": "FluxVanes",
    "BansheeCloak": "BansheeCloak",
    "BansheeSpeed": "HyperflightRotors",
    "HighCapacityBarrels": "InfernalPreigniter",
}

# Passive speed overrides or multipliers granted by completed upgrades
SPEED_UPGRADES: dict[str, dict[str, float]] = {
    # Exact target speeds in tiles/sec (Faster)
    "MetabolicBoost": {"Zergling": 6.58},
    "GlialReconstitution": {"Roach": 4.20, "RoachBurrowed": 2.80},
    "CentrificalHooks": {"Baneling": 4.13},
    "MuscularAugments": {"Hydralisk": 3.94},
    "AnabolicSynthesis": {"Ultralisk": 4.55},
    "PneumatizedCarapace": {"Overlord": 2.63, "OverlordTransport": 2.63, "Overseer": 4.72},
    "Charge": {"Zealot": 4.72},
    "GraviticDrive": {"WarpPrism": 5.36},
    "GraviticBoosters": {"Observer": 3.94},
    "FluxVanes": {"VoidRay": 4.65},
    "HyperflightRotors": {"Banshee": 5.25},
    "SmartServos": {"Viking": 3.85, "Hellion": 5.95},
}

RANGE_UPGRADES: dict[str, dict[str, float]] = {
    "ExtendedThermalLance": {"Colossus": 2.0},
    "PhoenixRangeUpgrade": {"Phoenix": 2.0},
    "EvolveGroovedSpines": {"Hydralisk": 1.0},
    "DiggingClaws": {"LurkerBurrowed": 1.0},
    "LurkerRange": {"LurkerBurrowed": 2.0},
    "HiSecAutoTracking": {"Bunker": 1.0, "PlanetaryFortress": 1.0},
}

HP_UPGRADES: dict[str, dict[str, float]] = {
    "ShieldWall": {"Marine": 10.0},
    "CentrificalHooks": {"Baneling": 5.0},
}


def resolve_unit_name(unit_name: str) -> str:
    """Normalize sc2reader unit type names to canonical UNIT_SPECS keys."""
    return UNIT_NAME_ALIASES.get(unit_name, unit_name)


def normalize_upgrades(upgrades: set[str] | frozenset[str] | list[str]) -> set[str]:
    """Normalize raw sc2reader upgrade names to canonical upgrade keys."""
    return {UPGRADE_ALIASES.get(u, u) for u in upgrades}


def get_unit_spec(unit_name: str) -> UnitSpec | None:
    """Return UnitSpec for a unit type name, or None if unknown."""
    return UNIT_SPECS.get(resolve_unit_name(unit_name))


def get_effective_speed(
    unit_name: str,
    upgrades: set[str] | frozenset[str] | list[str] = frozenset(),
    *,
    is_stimmed: bool = False,
    is_medivac_boosted: bool = False,
    on_creep: bool = False,
) -> float:
    """Compute effective movement speed in tiles/real-sec for a unit."""
    canon = resolve_unit_name(unit_name)
    spec = UNIT_SPECS.get(canon)
    if spec is None or spec.speed <= 0.0:
        return 0.0

    speed = spec.speed
    norm_upgrades = normalize_upgrades(upgrades)
    for upg in norm_upgrades:
        overrides = SPEED_UPGRADES.get(upg)
        if overrides and canon in overrides:
            speed = max(speed, overrides[canon])

    if on_creep and not spec.is_flying and spec.creep_speed_mult > 1.0:
        speed *= spec.creep_speed_mult

    if is_stimmed and canon in {"Marine", "Marauder"}:
        speed *= 1.5

    if is_medivac_boosted and canon == "Medivac":
        speed = 5.94

    return round(speed, 3)


def get_effective_range(
    unit_name: str,
    upgrades: set[str] | frozenset[str] | list[str] = frozenset(),
) -> float:
    """Compute effective attack range in tiles including completed upgrades."""
    canon = resolve_unit_name(unit_name)
    spec = UNIT_SPECS.get(canon)
    if spec is None or spec.attack_range <= 0.0:
        return 0.0

    attack_range = spec.attack_range
    for upg in normalize_upgrades(upgrades):
        bonus = RANGE_UPGRADES.get(upg, {}).get(canon, 0.0)
        attack_range += bonus
    return attack_range


def get_effective_max_hp(
    unit_name: str,
    upgrades: set[str] | frozenset[str] | list[str] = frozenset(),
) -> float:
    """Compute effective max HP (+ shields) including completed upgrades."""
    canon = resolve_unit_name(unit_name)
    spec = UNIT_SPECS.get(canon)
    if spec is None:
        return 50.0

    max_hp = spec.max_hp
    for upg in normalize_upgrades(upgrades):
        max_hp += HP_UPGRADES.get(upg, {}).get(canon, 0.0)
    return max_hp


def can_load_into(passenger_name: str, transport_name: str) -> bool:
    """Return True if passenger_name can be loaded into transport_name."""
    p_spec = get_unit_spec(passenger_name)
    t_spec = get_unit_spec(transport_name)
    if p_spec is None or t_spec is None:
        return False
    if t_spec.cargo_capacity <= 0 or p_spec.cargo_size <= 0:
        return False
    if p_spec.cargo_size > t_spec.cargo_capacity:
        return False
    if p_spec.race != t_spec.race:
        return False
    # Bunkers and Command Centers only hold Terran biological/SCV units, not mechanical vehicles
    if t_spec.name in {"Bunker", "CommandCenter", "PlanetaryFortress"}:
        if p_spec.name not in {"SCV", "Marine", "Marauder", "Reaper", "Ghost"}:
            return False
    return True
