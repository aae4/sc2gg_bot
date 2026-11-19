import io
from pathlib import Path
import struct
from types import SimpleNamespace

from PIL import Image
import pytest

from app.parser.hd_map import find_local_hd_map, resolve_hd_map
from app.parser.replay_parser import parse_replay_file
from app.parser.tactical_map import get_camera_bounds, render_tactical_map_png

FILES_DIR = Path(__file__).resolve().parent.parent / "files"


def test_find_local_hd_map_matches_icons_maps():
    assert find_local_hd_map(["2000 Atmospheres LE"]) == "2000_Atmospheres.jpg"
    assert find_local_hd_map(["Beckett Industries LE"]) == "Beckett_Industries.jpg"
    assert find_local_hd_map(["Blackburn LE"]) == "Blackburn.jpg"
    assert find_local_hd_map(["NonExistentMap LE"]) is None


def test_resolve_hd_map_local_vs_missing():
    fn, raw = resolve_hd_map(["2000 Atmospheres LE", "2000 атмосфер РВ"], "2000_map", allow_network=False)
    assert fn == "2000_Atmospheres.jpg"
    assert raw is None

    fn2, raw2 = resolve_hd_map(["Unknown Custom Map"], "unknown_custom", allow_network=False)
    assert fn2 is None
    assert raw2 is None


def test_render_tactical_map_png_synthetic():
    w, h = 64, 64
    cliff_vals = [128 if (16 <= x < 48 and 16 <= y < 48) else 64 for y in range(h) for x in range(w)]
    cliff_vals[20 * w + 20] = 96  # ramp cell
    clif_bytes = b"CLIF" + b"\x00" * 28 + struct.pack(f"<{w*h}H", *cliff_vals)

    flag_vals = [3 if (x < 8 or y < 8) else 2 for y in range(h) for x in range(w)]
    lfct_bytes = b"LFCT" + b"\x00" * 28 + struct.pack(f"<{w*h}B", *flag_vals)

    objs_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<PlacedObjects>"
        '<ObjectUnit UnitType="MineralField750" Position="24.5,24.5,0"/>'
        '<ObjectUnit UnitType="VespeneGeyser" Position="30.5,26.5,0"/>'
        '<ObjectUnit UnitType="XelNagaTower" Position="32.0,32.0,0"/>'
        "</PlacedObjects>"
    ).encode("utf-8")

    files = {
        "t3SyncCliffLevel": clif_bytes,
        "t3CellFlags": lfct_bytes,
        "Objects": objs_xml,
    }
    archive = SimpleNamespace(read_file=lambda name: files.get(name))
    map_info = SimpleNamespace(
        width=w,
        height=h,
        camera_left=8,
        camera_bottom=8,
        camera_right=56,
        camera_top=56,
    )
    replay = SimpleNamespace(map=SimpleNamespace(archive=archive, map_info=map_info, minimap=None))

    assert get_camera_bounds(replay) == (8, 8, 56, 56)
    png = render_tactical_map_png(replay, target_max_dim=512)
    assert png is not None
    with Image.open(io.BytesIO(png)) as img:
        assert max(img.size) >= 480


def test_parse_real_replay_populates_bounds_and_hd_map():
    replay_path = FILES_DIR / "2000 атмосфер РВ (15).SC2Replay"
    if not replay_path.is_file():
        pytest.skip("Sample replay missing")

    bundle = parse_replay_file(replay_path)
    assert bundle.data.meta.map_bounds == [40, 35, 184, 169]
    assert bundle.data.meta.hd_map_filename == "2000_Atmospheres.jpg"
    assert bundle.minimap_png is not None
    with Image.open(io.BytesIO(bundle.minimap_png)) as img:
        assert max(img.size) >= 900
