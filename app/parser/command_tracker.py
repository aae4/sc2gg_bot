"""Extract per-unit commands from StarCraft II replay game events.

Maintains per-player active selection and control groups (0..9) across
``SelectionEvent`` and ``ControlGroupEvent`` streams so that unit-less
command events (``Move``, ``Attack``, ``UseStimpack``, ``UnloadAll``, etc.)
are resolved to the exact ``unit_ids`` that were selected when issued.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.parser.unit_specs import IGNORED_UNIT_NAMES


@dataclass(frozen=True, slots=True)
class UnitCommand:
    """Normalized command issued by a player to a specific set of units."""

    frame: int
    pid: int
    unit_ids: tuple[int, ...]
    action: str
    target_x: float | None = None
    target_y: float | None = None
    target_uid: int | None = None
    is_queued: bool = False


# Explicit mapping from sc2reader / SC2 patch ability_name -> canonical action.
ABILITY_ACTION_MAP: dict[str, str] = {
    # Movement & basic combat
    "Move": "move",
    "RightClick": "move",
    "Attack": "attack_move",
    "AttackMove": "attack_move",
    "ScanMove": "attack_move",
    "BattlecruiserAttack": "attack_move",
    "Stop": "stop",
    "HoldPosition": "hold",
    "Hold": "hold",
    "Patrol": "patrol",
    "MovePatrol": "patrol",
    # Mobility & active unit buffs
    "Blink": "blink",
    "DarkTemplarBlink": "blink",
    "ShadowStride": "blink",
    "Hyperjump": "tactical_jump",
    "TacticalJump": "tactical_jump",
    "UseStimpack": "stim",
    "Stimpack": "stim",
    "Stim": "stim",
    "StimpackMarauder": "stim",
    "MarauderStimpack": "stim",
    "MarineStimpack": "stim",
    "MedivacSpeedBoost": "medivac_boost",
    "MedivacBoost": "medivac_boost",
    "IgniteAfterburners": "medivac_boost",
    # Transports
    "Load": "load",
    "MedivacLoad": "load",
    "WarpPrismLoad": "load",
    "BunkerLoad": "load",
    "OverlordLoad": "load",
    "OverlordTransportLoad": "load",
    "VentralSacsLoad": "load",
    "CommandCenterLoad": "load",
    "LoadAll": "load",
    "NydusNetworkLoad": "load",
    "NydusCanalLoad": "load",
    "UnloadAll": "unload_all",
    "MedivacUnloadAll": "unload_all",
    "WarpPrismUnloadAll": "unload_all",
    "BunkerUnloadAll": "unload_all",
    "UnloadAllBunker": "unload_all",
    "OverlordUnloadAll": "unload_all",
    "CommandCenterUnloadAll": "unload_all",
    "UnloadAllAt": "unload_at",
    "MedivacUnloadAllAt": "unload_at",
    "WarpPrismUnloadAllAt": "unload_at",
    "OverlordUnloadAllAt": "unload_at",
    "UnloadTargetMedivac": "unload_at",
    "UnloadTargetWarpPrism": "unload_at",
    "UnloadTargetOverlord": "unload_at",
    "UnloadUnitBunker": "unload_at",
    # Mode transformations (Siege / Liberator / Viking / Thor / Observers / Warp Prism)
    "SiegeMode": "siege",
    "LiberatorAGTarget": "siege",
    "AssaultMode": "siege",
    "VikingAssaultMode": "siege",
    "ThorAPMode": "siege",
    "ObserverMorphtoObserverSiege": "siege",
    "OverseerMorphtoOverseerSiegeMode": "siege",
    "TankMode": "unsiege",
    "Unsiege": "unsiege",
    "LiberatorAATarget": "unsiege",
    "FighterMode": "unsiege",
    "ThorNormalMode": "unsiege",
    "ObserverSiegeMorphtoObserver": "unsiege",
    "OverseerSiegeModeMorphtoOverseer": "unsiege",
    "PhasingMode": "phasing",
    "WarpPrismPhasingMode": "phasing",
    "TransportMode": "transport_mode",
    "WarpPrismTransportMode": "transport_mode",
    # Burrow / Unburrow
    "Burrow": "burrow",
    "BurrowWidowMine": "burrow",
    "BurrowInfestor": "burrow",
    "BurrowZergling": "burrow",
    "BurrowBaneling": "burrow",
    "BurrowRoach": "burrow",
    "BurrowHydralisk": "burrow",
    "BurrowLurker": "burrow",
    "BurrowLurkerMP": "burrow",
    "BurrowQueen": "burrow",
    "BurrowDrone": "burrow",
    "BurrowUltralisk": "burrow",
    "BurrowSwarmHost": "burrow",
    "Unburrow": "unburrow",
    "UnburrowWidowMine": "unburrow",
    "UnburrowInfestor": "unburrow",
    "UnburrowZergling": "unburrow",
    "UnburrowBaneling": "unburrow",
    "UnburrowRoach": "unburrow",
    "UnburrowHydralisk": "unburrow",
    "UnburrowLurker": "unburrow",
    "UnburrowLurkerMP": "unburrow",
    "UnburrowQueen": "unburrow",
    "UnburrowDrone": "unburrow",
    "UnburrowUltralisk": "unburrow",
    "UnburrowSwarmHost": "unburrow",
}

_COMMAND_EVENT_NAMES = frozenset(
    {
        "BasicCommandEvent",
        "TargetPointCommandEvent",
        "TargetUnitCommandEvent",
        "UpdateTargetPointCommandEvent",
        "UpdateTargetUnitCommandEvent",
        "DataCommandEvent",
    }
)


def normalize_ability_action(ability_name: str | None) -> str | None:
    """Map an SC2 ``ability_name`` to its canonical action, or ``None`` if untracked."""
    if not ability_name:
        return None
    return ABILITY_ACTION_MAP.get(ability_name)


def _resolve_pid(event: Any) -> int | None:
    """Return the player.pid (1-based) for a game event, or None for global events."""
    if getattr(event, "is_local", True) is False:
        return None
    player = getattr(event, "player", None)
    if player is not None and getattr(player, "pid", None) is not None:
        return int(player.pid)
    pid = getattr(event, "pid", None)
    if pid is None or pid == 16:
        return None
    return int(pid)


def _apply_selection_mask(
    selection: list[int],
    mask_type: str | None,
    mask_data: Any,
) -> list[int]:
    """Apply an SC2 selection removal/subset mask without mutating ``selection``."""
    if not mask_type or mask_type == "None" or mask_data is None:
        return list(selection)

    n = len(selection)
    if mask_type == "Mask":
        mask = list(mask_data)
        return [
            uid
            for idx, uid in enumerate(selection)
            if not (idx < len(mask) and mask[idx])
        ]
    if mask_type == "OneIndices":
        deselect_indices = set(mask_data)
        return [uid for idx, uid in enumerate(selection) if idx not in deselect_indices]
    if mask_type == "ZeroIndices":
        return [selection[idx] for idx in mask_data if 0 <= idx < n]
    return list(selection)


def _extract_added_unit_ids(event: Any) -> list[int]:
    """Extract unit IDs added by a SelectionEvent."""
    new_unit_ids = getattr(event, "new_unit_ids", None)
    if new_unit_ids:
        return [int(uid) for uid in new_unit_ids]

    new_units = getattr(event, "new_units", None) or getattr(event, "objects", None)
    if new_units:
        return [int(u.id if hasattr(u, "id") else u) for u in new_units]

    return []


def _is_event_queued(event: Any) -> bool:
    """Check whether a command event has the Shift-queued flag set."""
    flag = getattr(event, "flag", None)
    if isinstance(flag, dict) and "queued" in flag:
        return bool(flag["queued"])

    command_flag = getattr(event, "command_flag", None)
    if isinstance(command_flag, dict):
        return bool(command_flag.get("queued", False))
    if isinstance(command_flag, int):
        return (command_flag & 0x2) != 0

    flags = getattr(event, "flags", None)
    if isinstance(flags, int):
        return (flags & 0x2) != 0

    queued = getattr(event, "queued", None)
    if queued is not None:
        return bool(queued)

    return False


def _filter_active_unit_ids(
    unit_ids: list[int],
    frame: int,
    objects: dict[int, Any],
) -> tuple[int, ...]:
    """Filter out dead or ignored units when ``replay.objects`` has metadata for them."""
    if not unit_ids:
        return ()
    if not objects:
        return tuple(unit_ids)

    kept: list[int] = []
    for uid in unit_ids:
        unit = objects.get(uid)
        if unit is not None:
            died_at = getattr(unit, "died_at", None)
            if died_at is not None and died_at <= frame:
                continue
            name = getattr(unit, "name", "") or ""
            if name in IGNORED_UNIT_NAMES or name.startswith("Beacon"):
                continue
        kept.append(uid)
    return tuple(kept)


def extract_unit_commands(replay: Any) -> list[UnitCommand]:
    """Reconstruct per-unit commands from ``replay.game_events``.

    Tracks ``selections[pid]`` and ``hotkeys[pid][0..9]`` for every player
    and resolves each supported command event to the currently selected
    living, non-ignored ``unit_ids``.
    """
    game_events = getattr(replay, "game_events", None) or []
    objects: dict[int, Any] = getattr(replay, "objects", None) or {}

    selections: dict[int, list[int]] = {}
    hotkeys: dict[int, dict[int, list[int]]] = {}
    commands: list[UnitCommand] = []

    def _ensure_player(pid: int) -> None:
        if pid not in selections:
            selections[pid] = []
            hotkeys[pid] = {i: [] for i in range(10)}

    for event in game_events:
        pid = _resolve_pid(event)
        if pid is None:
            continue
        _ensure_player(pid)

        ev_name = getattr(event, "name", None) or type(event).__name__

        if ev_name == "SelectionEvent":
            cg = getattr(event, "control_group", 10)
            if cg is None:
                cg = 10
            mask_type = getattr(event, "mask_type", None)
            mask_data = getattr(event, "mask_data", None)
            added = _extract_added_unit_ids(event)

            if cg == 10:
                base = _apply_selection_mask(selections[pid], mask_type, mask_data)
                selections[pid] = sorted(set(base) | set(added))
            elif 0 <= cg <= 9:
                base = _apply_selection_mask(hotkeys[pid][cg], mask_type, mask_data)
                hotkeys[pid][cg] = sorted(set(base) | set(added))
            continue

        if ev_name == "SetControlGroupEvent":
            cg = getattr(event, "control_group", None)
            if cg is not None and 0 <= cg <= 9:
                hotkeys[pid][cg] = list(selections[pid])
            continue

        if ev_name == "GetControlGroupEvent":
            cg = getattr(event, "control_group", None)
            if cg is not None and 0 <= cg <= 9:
                mask_type = getattr(event, "mask_type", None)
                mask_data = getattr(event, "mask_data", None)
                selections[pid] = _apply_selection_mask(
                    hotkeys[pid][cg], mask_type, mask_data
                )
            continue

        if ev_name == "AddToControlGroupEvent":
            cg = getattr(event, "control_group", None)
            if cg is not None and 0 <= cg <= 9:
                mask_type = getattr(event, "mask_type", None)
                mask_data = getattr(event, "mask_data", None)
                base = _apply_selection_mask(hotkeys[pid][cg], mask_type, mask_data)
                hotkeys[pid][cg] = sorted(set(base) | set(selections[pid]))
            continue

        if ev_name == "DeleteControlGroupEvent":
            cg = getattr(event, "control_group", None)
            if cg is not None and 0 <= cg <= 9:
                hotkeys[pid][cg] = []
            continue

        if ev_name == "StealFromControlGroupEvent":
            cg = getattr(event, "control_group", None)
            if cg is not None and 0 <= cg <= 9:
                stolen = set(selections[pid])
                for other_cg in range(10):
                    if other_cg != cg and hotkeys[pid][other_cg]:
                        hotkeys[pid][other_cg] = [
                            uid for uid in hotkeys[pid][other_cg] if uid not in stolen
                        ]
                if getattr(event, "update_type", 4) == 5:
                    hotkeys[pid][cg] = sorted(set(hotkeys[pid][cg]) | stolen)
                else:
                    hotkeys[pid][cg] = list(selections[pid])
            continue

        if ev_name not in _COMMAND_EVENT_NAMES:
            continue

        action = normalize_ability_action(getattr(event, "ability_name", None))
        if action is None:
            continue

        frame = int(getattr(event, "frame", 0))
        unit_ids = _filter_active_unit_ids(selections[pid], frame, objects)
        if not unit_ids:
            continue

        target_x: float | None = None
        target_y: float | None = None
        x_val = getattr(event, "x", None)
        y_val = getattr(event, "y", None)
        if x_val is not None and y_val is not None:
            target_x = float(x_val)
            target_y = float(y_val)
        else:
            loc = getattr(event, "location", None)
            if isinstance(loc, (tuple, list)) and len(loc) >= 2:
                target_x = float(loc[0])
                target_y = float(loc[1])

        raw_target_uid = getattr(event, "target_unit_id", None)
        target_uid = int(raw_target_uid) if raw_target_uid else None

        commands.append(
            UnitCommand(
                frame=frame,
                pid=pid,
                unit_ids=unit_ids,
                action=action,
                target_x=target_x,
                target_y=target_y,
                target_uid=target_uid,
                is_queued=_is_event_queued(event),
            )
        )

    commands.sort(key=lambda cmd: cmd.frame)
    return commands
