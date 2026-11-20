from pathlib import Path
from types import SimpleNamespace

import pytest
import sc2reader

from app.parser.command_tracker import (
    ABILITY_ACTION_MAP,
    UnitCommand,
    extract_unit_commands,
    normalize_ability_action,
)

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def _player(pid: int) -> SimpleNamespace:
    return SimpleNamespace(pid=pid)


def _sel(
    frame: int,
    pid: int,
    *,
    mask_type: str = "None",
    mask_data=None,
    new_unit_ids=None,
    new_units=None,
    control_group: int = 10,
) -> SimpleNamespace:
    return SimpleNamespace(
        name="SelectionEvent",
        frame=frame,
        pid=pid - 1,
        player=_player(pid),
        is_local=True,
        control_group=control_group,
        mask_type=mask_type,
        mask_data=mask_data,
        new_unit_ids=list(new_unit_ids or []),
        new_units=new_units,
    )


def _cg(
    name: str,
    frame: int,
    pid: int,
    control_group: int,
    *,
    mask_type: str = "None",
    mask_data=None,
    update_type: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        frame=frame,
        pid=pid - 1,
        player=_player(pid),
        is_local=True,
        control_group=control_group,
        mask_type=mask_type,
        mask_data=mask_data,
        update_type=update_type,
    )


def _cmd(
    name: str,
    frame: int,
    pid: int,
    ability_name: str,
    *,
    x: float | None = None,
    y: float | None = None,
    target_unit_id: int | None = None,
    queued: bool = False,
    flags: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        frame=frame,
        pid=pid - 1,
        player=_player(pid),
        is_local=True,
        ability_name=ability_name,
        x=x,
        y=y,
        target_unit_id=target_unit_id,
        flag={"queued": queued} if flags is None else {},
        flags=flags if flags is not None else (0x2 if queued else 0x0),
    )


def test_selection_masks_and_replacement():
    replay = SimpleNamespace(
        objects={},
        game_events=[
            # Select [10, 20, 30]
            _sel(10, 1, mask_type="ZeroIndices", mask_data=[], new_unit_ids=[30, 10, 20]),
            _cmd("TargetPointCommandEvent", 12, 1, "Move", x=50.0, y=60.0),
            # Deselect index 1 (20) via Mask
            _sel(20, 1, mask_type="Mask", mask_data=[False, True, False]),
            _cmd("TargetPointCommandEvent", 22, 1, "Attack", x=70.0, y=80.0),
            # Add 40 and 50
            _sel(30, 1, mask_type="None", new_unit_ids=[40, 50]),
            # Deselect index 0 (10) and 2 (40) via OneIndices
            _sel(40, 1, mask_type="OneIndices", mask_data=[0, 2]),
            _cmd("BasicCommandEvent", 42, 1, "Stop"),
            # Keep only index 1 (50) via ZeroIndices
            _sel(50, 1, mask_type="ZeroIndices", mask_data=[1]),
            _cmd("BasicCommandEvent", 52, 1, "HoldPosition"),
        ],
    )

    cmds = extract_unit_commands(replay)
    assert cmds == [
        UnitCommand(frame=12, pid=1, unit_ids=(10, 20, 30), action="move", target_x=50.0, target_y=60.0),
        UnitCommand(frame=22, pid=1, unit_ids=(10, 30), action="attack_move", target_x=70.0, target_y=80.0),
        UnitCommand(frame=42, pid=1, unit_ids=(30, 50), action="stop"),
        UnitCommand(frame=52, pid=1, unit_ids=(50,), action="hold"),
    ]


def test_control_groups_set_get_add_delete_steal():
    replay = SimpleNamespace(
        objects={},
        game_events=[
            # Player 1 selects [1, 2] and sets hotkey 1
            _sel(10, 1, mask_type="ZeroIndices", mask_data=[], new_unit_ids=[1, 2]),
            _cg("SetControlGroupEvent", 11, 1, 1),
            # Select [3] and add to hotkey 1 -> hotkey 1 has [1, 2, 3]
            _sel(20, 1, mask_type="ZeroIndices", mask_data=[], new_unit_ids=[3]),
            _cg("AddToControlGroupEvent", 21, 1, 1),
            # Clear active selection, then recall hotkey 1 with mask removing index 1 (unit 2)
            _sel(30, 1, mask_type="ZeroIndices", mask_data=[]),
            _cg("GetControlGroupEvent", 31, 1, 1, mask_type="Mask", mask_data=[False, True, False]),
            _cmd("TargetPointCommandEvent", 32, 1, "RightClick", x=10.0, y=20.0),
            # Steal unit 3 into hotkey 2 -> removes 3 from hotkey 1, sets hotkey 2 to [3]
            _sel(40, 1, mask_type="ZeroIndices", mask_data=[], new_unit_ids=[3]),
            _cg("StealFromControlGroupEvent", 41, 1, 2, update_type=4),
            _cg("GetControlGroupEvent", 42, 1, 1),
            _cmd("BasicCommandEvent", 43, 1, "UseStimpack"),
            _cg("GetControlGroupEvent", 44, 1, 2),
            _cmd("BasicCommandEvent", 45, 1, "UseStimpack"),
            # Delete hotkey 2 -> recalling it leaves empty selection, so Stop is ignored
            _cg("DeleteControlGroupEvent", 50, 1, 2),
            _cg("GetControlGroupEvent", 51, 1, 2),
            _cmd("BasicCommandEvent", 52, 1, "Stop"),
        ],
    )

    cmds = extract_unit_commands(replay)
    assert cmds == [
        UnitCommand(frame=32, pid=1, unit_ids=(1, 3), action="move", target_x=10.0, target_y=20.0),
        UnitCommand(frame=43, pid=1, unit_ids=(1, 2), action="stim"),
        UnitCommand(frame=45, pid=1, unit_ids=(3,), action="stim"),
    ]


def test_filters_dead_ignored_and_handles_unknown_events_and_flags():
    objects = {
        1: SimpleNamespace(id=1, name="Marine", died_at=None),
        2: SimpleNamespace(id=2, name="Marine", died_at=25),
        3: SimpleNamespace(id=3, name="Larva", died_at=None),
    }
    replay = SimpleNamespace(
        objects=objects,
        game_events=[
            SimpleNamespace(name="CameraEvent", frame=5, pid=0, player=_player(1), is_local=True),
            SimpleNamespace(name="GameStartEvent", frame=0, pid=16, player=None, is_local=False),
            # Command with empty selection is skipped
            _cmd("BasicCommandEvent", 8, 1, "Stop"),
            # Select [1, 2, 3] via new_units fallback
            _sel(
                10,
                1,
                mask_type="ZeroIndices",
                mask_data=[],
                new_units=[SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)],
            ),
            # At frame 20, unit 2 is alive, unit 3 (Larva) is ignored
            _cmd("TargetPointCommandEvent", 20, 1, "Blink", x=30.0, y=40.0, queued=True),
            # At frame 30, unit 2 is dead (died_at=25), only unit 1 remains
            _cmd(
                "TargetUnitCommandEvent",
                30,
                1,
                "Attack",
                x=35.0,
                y=45.0,
                target_unit_id=0,  # shrouded target -> None
                flags=0x2,
            ),
            # Unmapped ability is ignored
            _cmd("BasicCommandEvent", 35, 1, "TrainMarine"),
        ],
    )

    cmds = extract_unit_commands(replay)
    assert cmds == [
        UnitCommand(
            frame=20,
            pid=1,
            unit_ids=(1, 2),
            action="blink",
            target_x=30.0,
            target_y=40.0,
            is_queued=True,
        ),
        UnitCommand(
            frame=30,
            pid=1,
            unit_ids=(1,),
            action="attack_move",
            target_x=35.0,
            target_y=45.0,
            target_uid=None,
            is_queued=True,
        ),
    ]


def test_ability_action_aliases():
    assert normalize_ability_action("Attack") == "attack_move"
    assert normalize_ability_action("AttackMove") == "attack_move"
    assert normalize_ability_action("RightClick") == "move"
    assert normalize_ability_action("MovePatrol") == "patrol"
    assert normalize_ability_action("MedivacLoad") == "load"
    assert normalize_ability_action("WarpPrismLoad") == "load"
    assert normalize_ability_action("BunkerLoad") == "load"
    assert normalize_ability_action("MedivacUnloadAll") == "unload_all"
    assert normalize_ability_action("UnloadAllAt") == "unload_at"
    assert normalize_ability_action("UnloadTargetMedivac") == "unload_at"
    assert normalize_ability_action("UseStimpack") == "stim"
    assert normalize_ability_action("Stimpack") == "stim"
    assert normalize_ability_action("MedivacSpeedBoost") == "medivac_boost"
    assert normalize_ability_action("Hyperjump") == "tactical_jump"
    assert normalize_ability_action("UnknownAbilityXYZ") is None
    assert len(set(ABILITY_ACTION_MAP.values())) == 18


@pytest.mark.parametrize(
    "filename",
    [
        "2000 атмосфер РВ (15).SC2Replay",
        "Blackburn LE (9) ZergCheese.SC2Replay",
        "Беккетт Индастриз РВ (42).SC2Replay",
    ],
)
def test_extract_unit_commands_on_sample_replays(filename: str):
    replay_path = FILES_DIR / filename
    if not replay_path.is_file():
        pytest.skip(f"Sample replay missing: {replay_path}")

    replay = sc2reader.load_replay(str(replay_path), load_level=4)
    commands = extract_unit_commands(replay)

    assert len(commands) > 100
    assert [c.frame for c in commands] == sorted(c.frame for c in commands)

    valid_pids = {p.pid for p in replay.players}
    for cmd in commands:
        assert cmd.pid in valid_pids
        assert len(cmd.unit_ids) > 0
        if cmd.action in ("move", "attack_move"):
            assert cmd.target_x is not None
            assert cmd.target_y is not None

    actions_seen = {c.action for c in commands}
    assert "move" in actions_seen
    assert "attack_move" in actions_seen
    # Each of these replays has micro abilities / transports / siege / burrow
    assert len(actions_seen) >= 4
