from pydantic import BaseModel, Field


class MatchMeta(BaseModel):
    replay_id: str
    sha256: str
    map_name: str
    map_width: int
    map_height: int
    minimap_filename: str
    duration_sec: int
    version: str
    played_at: str


class PlayerInfo(BaseModel):
    pid: int
    name: str
    race: str
    color_hex: str
    result: str
    apm: int = 0
    workers_peak: int = 0
    army_value_peak: int = 0
    minerals_lost: int = 0
    vespene_lost: int = 0


class BattleEvent(BaseModel):
    start_sec: int
    end_sec: int
    x: float
    y: float
    lost_minerals: dict[int, int] = Field(default_factory=dict)
    lost_gas: dict[int, int] = Field(default_factory=dict)
    units_lost: dict[int, dict[str, int]] = Field(default_factory=dict)
    winner_pid: int | None = None


class BuildOrderItem(BaseModel):
    time_sec: int
    pid: int
    name: str
    kind: str  # "unit" | "building" | "upgrade"


class ChartSeries(BaseModel):
    times_sec: list[int] = Field(default_factory=list)
    army_value: dict[int, list[int]] = Field(default_factory=dict)
    workers: dict[int, list[int]] = Field(default_factory=dict)
    unspent_resources: dict[int, list[int]] = Field(default_factory=dict)
    supply_used: dict[int, list[int]] = Field(default_factory=dict)


class TimelineFrame(BaseModel):
    time_sec: int
    is_keyframe: bool = False
    # Compact tuple per unit: [uid, pid, type_id, x, y]
    units: list[list[int | float]] = Field(default_factory=list)
    removed: list[int] = Field(default_factory=list)


class ReplayData(BaseModel):
    meta: MatchMeta
    players: list[PlayerInfo]
    unit_dict: dict[int, str]
    frames: list[TimelineFrame]
    battles: list[BattleEvent]
    build_order: list[BuildOrderItem]
    charts: ChartSeries


class ParsedReplayBundle(BaseModel):
    data: ReplayData
    minimap_png: bytes | None = None
