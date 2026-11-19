"""Procedural tactical map renderer from StarCraft II .s2ma archive data."""

from __future__ import annotations

import io
import logging
import struct
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Dark esports observer palette (matches viewer #06090f background)
_COLOR_UNPATHABLE = np.array([10, 14, 23], dtype=np.uint8)
_CLIFF_PALETTE = [
    np.array([20, 29, 46], dtype=np.uint8),   # Level 0 (low ground)
    np.array([30, 44, 68], dtype=np.uint8),   # Level 1
    np.array([42, 61, 94], dtype=np.uint8),   # Level 2
    np.array([56, 80, 122], dtype=np.uint8),  # Level 3 (high ground)
]
_COLOR_RAMP = np.array([52, 72, 102], dtype=np.uint8)
_COLOR_CLIFF_EDGE = np.array([8, 11, 18], dtype=np.uint8)
_COLOR_CLIFF_HIGHLIGHT = np.array([78, 108, 152], dtype=np.uint8)


def get_camera_bounds(replay: Any) -> tuple[int, int, int, int] | None:
    """Return playable (left, bottom, right, top) bounds from MapInfo, if valid."""
    sc2_map = getattr(replay, "map", None)
    mi = getattr(sc2_map, "map_info", None) if sc2_map else None
    if not mi:
        return None
    w = int(getattr(mi, "width", 0) or 0)
    h = int(getattr(mi, "height", 0) or 0)
    left = int(getattr(mi, "camera_left", 0) or 0)
    bottom = int(getattr(mi, "camera_bottom", 0) or 0)
    right = int(getattr(mi, "camera_right", w) or w)
    top = int(getattr(mi, "camera_top", h) or h)
    if w <= 0 or h <= 0 or right <= left or top <= bottom:
        return None
    left = max(0, min(left, w - 1))
    bottom = max(0, min(bottom, h - 1))
    right = max(left + 1, min(right, w))
    top = max(bottom + 1, min(top, h))
    return (left, bottom, right, top)


def _read_cliff_grid(archive: Any, width: int, height: int) -> np.ndarray | None:
    data = archive.read_file("t3SyncCliffLevel")
    expected_bytes = 32 + width * height * 2
    if not data or len(data) < expected_bytes:
        return None
    arr = np.frombuffer(data, dtype="<u2", count=width * height, offset=32)
    return arr.reshape((height, width))


def _read_cell_flags(archive: Any, width: int, height: int) -> np.ndarray | None:
    data = archive.read_file("t3CellFlags")
    expected_bytes = 32 + width * height
    if not data or len(data) < expected_bytes:
        return None
    arr = np.frombuffer(data, dtype=np.uint8, count=width * height, offset=32)
    return arr.reshape((height, width))


def _parse_map_objects(archive: Any) -> list[tuple[str, float, float]]:
    """Extract (category, x, y) for minerals, geysers, watchtowers, and rocks."""
    raw = archive.read_file("Objects")
    if not raw:
        return []
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="ignore"))
    except ET.ParseError:
        return []

    items: list[tuple[str, float, float]] = []
    for elem in root.findall("ObjectUnit"):
        utype = elem.attrib.get("UnitType", "")
        pos_str = elem.attrib.get("Position", "")
        if not utype or not pos_str:
            continue
        parts = pos_str.split(",")
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            continue

        lower = utype.lower()
        if "mineral" in lower:
            cat = "rich_mineral" if "rich" in lower else "mineral"
        elif "geyser" in lower:
            cat = "rich_geyser" if "rich" in lower else "geyser"
        elif "xelnagatower" in lower:
            cat = "watchtower"
        elif "destructible" in lower or "unbuildablerocks" in lower:
            cat = "rock"
        else:
            continue
        items.append((cat, x, y))
    return items


def render_tactical_map_png(replay: Any, target_max_dim: int = 1024) -> bytes | None:
    """Render a crisp high-resolution tactical map PNG from .s2ma terrain & objects.

    Falls back to an upscaled Minimap.tga if terrain layers are unavailable.
    """
    sc2_map = getattr(replay, "map", None)
    if not sc2_map:
        return None

    archive = getattr(sc2_map, "archive", None)
    mi = getattr(sc2_map, "map_info", None)
    if archive is None or mi is None:
        return _fallback_minimap_upscale(sc2_map, target_max_dim)

    width = int(getattr(mi, "width", 0) or 0)
    height = int(getattr(mi, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return _fallback_minimap_upscale(sc2_map, target_max_dim)

    bounds = get_camera_bounds(replay) or (0, 0, width, height)
    left, bottom, right, top = bounds

    cliff = _read_cliff_grid(archive, width, height)
    flags = _read_cell_flags(archive, width, height)
    if cliff is None or flags is None:
        return _fallback_minimap_upscale(sc2_map, target_max_dim)

    # Crop to playable camera bounds (note: SC2 y=0 is bottom, image y=0 is top)
    cliff_crop = cliff[bottom:top, left:right]
    flags_crop = flags[bottom:top, left:right]
    ch, cw = cliff_crop.shape
    if ch <= 0 or cw <= 0:
        return _fallback_minimap_upscale(sc2_map, target_max_dim)

    # Discrete cliff level (0..3) and ramp detection (non-multiple of 64)
    cliff_lvl = np.clip(np.round(cliff_crop / 64.0).astype(np.int32), 0, len(_CLIFF_PALETTE) - 1)
    is_ramp = (cliff_crop % 64) != 0
    is_unpathable = (flags_crop & 1) != 0

    rgb = np.zeros((ch, cw, 3), dtype=np.uint8)
    for lvl, color in enumerate(_CLIFF_PALETTE):
        rgb[cliff_lvl == lvl] = color

    # Highlight walkable ramps
    ramp_walkable = is_ramp & (~is_unpathable)
    rgb[ramp_walkable] = _COLOR_RAMP

    # Darken unpathable cells
    rgb[is_unpathable] = _COLOR_UNPATHABLE

    # Detect cliff edges (sharp transitions where neither cell is a ramp)
    edge_h = np.zeros((ch, cw), dtype=bool)
    edge_v = np.zeros((ch, cw), dtype=bool)
    non_ramp = ~is_ramp
    edge_h[1:, :] = (cliff_lvl[1:, :] != cliff_lvl[:-1, :]) & non_ramp[1:, :] & non_ramp[:-1, :]
    edge_v[:, 1:] = (cliff_lvl[:, 1:] != cliff_lvl[:, :-1]) & non_ramp[:, 1:] & non_ramp[:, :-1]
    cliff_edges = edge_h | edge_v

    # Flip vertically so row 0 is top (north) and row ch-1 is bottom (south)
    rgb = np.flipud(rgb)
    cliff_edges = np.flipud(cliff_edges)
    is_unpathable_flipped = np.flipud(is_unpathable)

    scale = max(4, int(round(target_max_dim / max(cw, ch))))
    out_w = cw * scale
    out_h = ch * scale

    img = Image.fromarray(rgb, mode="RGB").resize((out_w, out_h), resample=Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(img)

    # Draw subtle grid lines every 16 game cells
    grid_step = 16
    for gx in range(grid_step - (left % grid_step), cw, grid_step):
        px = gx * scale
        draw.line([(px, 0), (px, out_h)], fill=(255, 255, 255, 10) if img.mode == "RGBA" else (24, 33, 50), width=1)
    for gy in range(grid_step - (bottom % grid_step), ch, grid_step):
        py = (ch - gy) * scale
        draw.line([(0, py), (out_w, py)], fill=(24, 33, 50), width=1)

    # Draw crisp cliff contour lines
    edge_ys, edge_xs = np.where(cliff_edges)
    for cy, cx in zip(edge_ys.tolist(), edge_xs.tolist()):
        x0, y0 = cx * scale, cy * scale
        draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=tuple(_COLOR_CLIFF_EDGE.tolist()))

    # Subtle border around playable/unpathable boundary
    path_edge_y, path_edge_x = np.where(
        np.pad(is_unpathable_flipped[:-1, :] != is_unpathable_flipped[1:, :], ((1, 0), (0, 0)))
        | np.pad(is_unpathable_flipped[:, :-1] != is_unpathable_flipped[:, 1:], ((0, 0), (1, 0)))
    )
    for cy, cx in zip(path_edge_y.tolist(), path_edge_x.tolist()):
        if not cliff_edges[cy, cx]:
            x0, y0 = cx * scale, cy * scale
            draw.rectangle([x0, y0, x0 + max(1, scale // 2), y0 + max(1, scale // 2)], fill=tuple(_COLOR_CLIFF_HIGHLIGHT.tolist()))

    # Draw map objects (minerals, geysers, watchtowers, destructible rocks)
    for cat, ox, oy in _parse_map_objects(archive):
        if not (left <= ox <= right and bottom <= oy <= top):
            continue
        px = (ox - left) * scale
        py = (top - oy) * scale
        if cat == "mineral":
            r = max(3, int(scale * 0.65))
            draw.rectangle([px - r, py - r * 0.7, px + r, py + r * 0.7], fill=(56, 189, 248), outline=(12, 74, 110))
        elif cat == "rich_mineral":
            r = max(3, int(scale * 0.65))
            draw.rectangle([px - r, py - r * 0.7, px + r, py + r * 0.7], fill=(245, 158, 11), outline=(120, 53, 15))
        elif cat == "geyser":
            r = max(4, int(scale * 0.85))
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(34, 197, 94), outline=(20, 83, 45))
        elif cat == "rich_geyser":
            r = max(4, int(scale * 0.85))
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(168, 85, 247), outline=(88, 28, 135))
        elif cat == "watchtower":
            r = max(5, int(scale * 1.1))
            draw.ellipse([px - r, py - r, px + r, py + r], outline=(226, 232, 240), width=2)
            draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(56, 189, 248))
        elif cat == "rock":
            r = max(4, int(scale * 0.9))
            draw.rectangle([px - r, py - r, px + r, py + r], fill=(120, 113, 108), outline=(68, 64, 60))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _fallback_minimap_upscale(sc2_map: Any, target_max_dim: int) -> bytes | None:
    raw = getattr(sc2_map, "minimap", None)
    if not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
            bbox = rgb.getbbox()
            cropped = rgb.crop(bbox) if bbox else rgb
            w, h = cropped.size
            if max(w, h) < target_max_dim:
                scale = target_max_dim / max(w, h)
                cropped = cropped.resize(
                    (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                    resample=Image.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            cropped.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception:
        return None
