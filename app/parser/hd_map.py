"""HD map image resolver (local icons/maps/ + optional Liquipedia fallback)."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

ICONS_MAPS_DIR = Path(__file__).resolve().parent.parent.parent / "icons" / "maps"
_SUFFIX_RE = re.compile(r"\s+(LE|TE|SE|CE|РВ)$", re.IGNORECASE)
_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def _normalize_key(name: str) -> str:
    stripped = _SUFFIX_RE.sub("", name.strip())
    return _CLEAN_RE.sub("_", stripped.lower()).strip("_")


def find_local_hd_map(map_names: list[str]) -> str | None:
    """Return the filename inside icons/maps/ matching any of map_names, if present."""
    if not ICONS_MAPS_DIR.is_dir():
        return None

    by_key: dict[str, str] = {}
    for path in ICONS_MAPS_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        if path.name.lower().endswith("_mini.png"):
            continue
        by_key[_normalize_key(path.stem)] = path.name

    for name in map_names:
        if not name:
            continue
        key = _normalize_key(name)
        if key in by_key:
            return by_key[key]
    return None


def _pick_map_file_title(image_titles: list[str], target_key: str) -> str | None:
    """Pick the best matching File:... title for a map from Liquipedia page images."""
    scored: list[tuple[int, str]] = []
    for title in image_titles:
        stem = title.removeprefix("File:").rsplit(".", 1)[0]
        ext = title.rsplit(".", 1)[-1].lower() if "." in title else ""
        if ext not in {"jpg", "jpeg", "png", "webp"}:
            continue
        key = _normalize_key(stem)
        if key == target_key:
            scored.append((0 if ext in {"jpg", "jpeg"} else 1, title))
        elif target_key and key.startswith(target_key):
            scored.append((2 if ext in {"jpg", "jpeg"} else 3, title))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


def fetch_liquipedia_hd_map(
    map_name: str,
    expected_aspect: float | None = None,
    timeout_sec: float = 8.0,
) -> bytes | None:
    """Best-effort fetch of a top-down HD map image from Liquipedia StarCraft 2."""
    if not map_name:
        return None

    base = _SUFFIX_RE.sub("", map_name.strip())
    target_key = _normalize_key(map_name)
    titles = list(dict.fromkeys([map_name.strip().replace(" ", "_"), base.replace(" ", "_")]))
    headers = {"User-Agent": "sc2gg-bot/2.0 (SC2 replay viewer)"}

    try:
        with httpx.Client(timeout=timeout_sec, headers=headers, follow_redirects=True) as client:
            file_title: str | None = None
            for title in titles:
                resp = client.get(
                    "https://liquipedia.net/starcraft2/api.php",
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "images",
                        "imlimit": 30,
                        "format": "json",
                    },
                )
                if resp.status_code != 200:
                    continue
                pages = resp.json().get("query", {}).get("pages", {})
                for pid, pdata in pages.items():
                    if pid == "-1":
                        continue
                    imgs = [im.get("title", "") for im in pdata.get("images", [])]
                    file_title = _pick_map_file_title(imgs, target_key)
                    if file_title:
                        break
                if file_title:
                    break

            if not file_title:
                return None

            info_resp = client.get(
                "https://liquipedia.net/starcraft2/api.php",
                params={
                    "action": "query",
                    "titles": file_title,
                    "prop": "imageinfo",
                    "iiprop": "url|size",
                    "iiurlwidth": 1200,
                    "format": "json",
                },
            )
            if info_resp.status_code != 200:
                return None

            info_pages = info_resp.json().get("query", {}).get("pages", {})
            img_url: str | None = None
            for pid, pdata in info_pages.items():
                if pid == "-1":
                    continue
                ii = (pdata.get("imageinfo") or [{}])[0]
                img_url = ii.get("thumburl") or ii.get("url")
                if img_url:
                    break

            if not img_url:
                return None

            img_resp = client.get(img_url)
            if img_resp.status_code != 200:
                return None
            return _validate_and_encode_jpeg(img_resp.content, expected_aspect)
    except Exception as exc:
        logger.debug("Liquipedia HD map lookup skipped for %r: %s", map_name, exc)
    return None


def _validate_and_encode_jpeg(raw: bytes, expected_aspect: float | None) -> bytes | None:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            w, h = img.size
            if w < 400 or h < 400:
                return None
            if expected_aspect:
                actual_aspect = w / h
                if abs(actual_aspect - expected_aspect) / expected_aspect > 0.12:
                    return None
            rgb = img.convert("RGB")
            if max(w, h) > 1200:
                rgb.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=88, optimize=True)
            return buf.getvalue()
    except Exception:
        return None


def resolve_hd_map(
    map_names: list[str],
    sanitized_base: str,
    expected_aspect: float | None = None,
    allow_network: bool = True,
) -> tuple[str | None, bytes | None]:
    """Resolve HD map image.

    Returns (hd_map_filename, hd_map_bytes_to_upload).
    When found in icons/maps/, bytes_to_upload is None (already bundled with viewer).
    """
    local_name = find_local_hd_map(map_names)
    if local_name:
        return local_name, None

    if allow_network and map_names:
        for name in map_names:
            if not name:
                continue
            jpg = fetch_liquipedia_hd_map(name, expected_aspect=expected_aspect)
            if jpg:
                return f"hd_{sanitized_base}.jpg", jpg

    return None, None
