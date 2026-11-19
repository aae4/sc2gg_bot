import asyncio
from datetime import datetime
from io import BytesIO
from pathlib import Path

from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PIL import Image, ImageDraw, ImageFont

from app.domain.models import PlayerInfo, ReplayData

CARD_WIDTH = 1200
CARD_HEIGHT = 780

BG_COLOR = "#0d1117"
PANEL_COLOR = "#161b22"
BORDER_COLOR = "#30363d"
TEXT_PRIMARY = "#f0f6fc"
TEXT_SECONDARY = "#8b949e"
WIN_BG = "#238636"
LOSS_BG = "#21262d"
LOSS_TEXT = "#8b949e"
ACCENT_GOLD = "#d29922"

DEFAULT_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "icons" / "races"


def _load_font(bold: bool = False, size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    mpl_font_dir = Path(font_manager.findfont("DejaVu Sans")).parent
    font_path = mpl_font_dir / font_name
    if font_path.is_file():
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def _format_duration(seconds: int) -> str:
    mins, secs = divmod(max(0, seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _format_played_at(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso_str[:16]


def _ensure_readable_color(hex_color: str) -> str:
    """Lighten dark player colors so lines and accents remain crisp on #161b22."""
    raw = hex_color.lstrip("#")
    if len(raw) != 6:
        return "#58a6ff"
    try:
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return "#58a6ff"

    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if luminance < 95:
        boost = (95 - luminance) / 160.0 + 0.35
        r = min(255, int(r + (255 - r) * boost))
        g = min(255, int(g + (255 - g) * boost))
        b = min(255, int(b + (255 - b) * boost))
    return f"#{r:02x}{g:02x}{b:02x}"


def _truncate_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and draw.textlength(trimmed + ellipsis, font=font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _load_race_icon(race: str, icons_dir: Path, size: int = 52) -> Image.Image | None:
    icon_path = icons_dir / f"{race}Icon.png"
    if not icon_path.is_file():
        return None
    with Image.open(icon_path) as img:
        rgba = img.convert("RGBA")
        return rgba.resize((size, size), Image.Resampling.LANCZOS)


def _render_charts_image(data: ReplayData, player_colors: dict[int, str]) -> Image.Image:
    fig = Figure(figsize=(11.36, 4.30), dpi=100, facecolor=BG_COLOR)
    canvas = FigureCanvasAgg(fig)
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.06, right=0.985, top=0.86, bottom=0.14, wspace=0.18)

    times = data.charts.times_sec
    time_formatter = FuncFormatter(lambda x, _pos: _format_duration(int(x)))

    chart_specs = [
        (axes[0], "Army Value", data.charts.army_value),
        (axes[1], "Workers", data.charts.workers),
    ]

    for ax, title, series_map in chart_specs:
        ax.set_facecolor(PANEL_COLOR)
        ax.set_title(title, color=TEXT_PRIMARY, fontsize=13, fontweight="bold", loc="left", pad=10)
        ax.grid(True, axis="y", color=BORDER_COLOR, linestyle="--", linewidth=0.8, alpha=0.65)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER_COLOR)
        ax.spines["bottom"].set_color(BORDER_COLOR)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9.5)
        ax.xaxis.set_major_formatter(time_formatter)

        if times:
            ax.set_xlim(0, max(times[-1], 1))
            for player in data.players:
                values = series_map.get(player.pid, [])
                if not values:
                    continue
                n = min(len(times), len(values))
                color = player_colors[player.pid]
                ax.plot(times[:n], values[:n], color=color, linewidth=2.2, label=player.name)
                ax.fill_between(times[:n], values[:n], color=color, alpha=0.13)

            ax.set_ylim(bottom=0)
            if any(series_map.get(p.pid) for p in data.players):
                legend = ax.legend(
                    loc="upper left",
                    frameon=True,
                    facecolor=BG_COLOR,
                    edgecolor=BORDER_COLOR,
                    fontsize=9,
                )
                for text in legend.get_texts():
                    text.set_color(TEXT_PRIMARY)

    canvas.draw()
    rgba_buf = canvas.buffer_rgba()
    width, height = canvas.get_width_height()
    return Image.frombuffer("RGBA", (width, height), rgba_buf, "raw", "RGBA", 0, 1).copy()


def _draw_player_card(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    player: PlayerInfo,
    color: str,
    box: tuple[int, int, int, int],
    icons_dir: Path,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=14, fill=PANEL_COLOR, outline=BORDER_COLOR, width=1)
    # Left color accent bar
    draw.rounded_rectangle((x0, y0, x0 + 8, y1), radius=4, fill=color)

    icon = _load_race_icon(player.race, icons_dir, size=52)
    text_x = x0 + 24
    if icon is not None:
        img.paste(icon, (x0 + 20, y0 + 18), icon)
        text_x = x0 + 84

    is_win = player.result.lower() == "win"
    badge_text = "WIN" if is_win else ("LOSS" if player.result.lower() == "loss" else player.result.upper())
    badge_bg = WIN_BG if is_win else LOSS_BG
    badge_fg = TEXT_PRIMARY if is_win else LOSS_TEXT
    badge_w = int(draw.textlength(badge_text, font=fonts["badge"])) + 22
    badge_x0 = x1 - badge_w - 18
    badge_y0 = y0 + 18
    draw.rounded_rectangle(
        (badge_x0, badge_y0, badge_x0 + badge_w, badge_y0 + 28),
        radius=8,
        fill=badge_bg,
    )
    draw.text((badge_x0 + 11, badge_y0 + 5), badge_text, font=fonts["badge"], fill=badge_fg)

    max_name_w = max(80, badge_x0 - text_x - 12)
    display_name = _truncate_text(draw, player.name, fonts["player_name"], max_name_w)
    draw.text((text_x, y0 + 16), display_name, font=fonts["player_name"], fill=TEXT_PRIMARY)
    draw.text((text_x, y0 + 46), player.race, font=fonts["race"], fill=color)

    # Stats row
    stats_y = y0 + 88
    draw.line((x0 + 20, stats_y - 10, x1 - 18, stats_y - 10), fill=BORDER_COLOR, width=1)
    stats = [
        ("APM", f"{player.apm}"),
        ("WORKERS", f"{player.workers_peak}"),
        ("ARMY PEAK", f"{player.army_value_peak:,}"),
        ("LOST (M/G)", f"{player.minerals_lost:,} / {player.vespene_lost:,}"),
    ]
    col_w = (x1 - x0 - 40) // len(stats)
    for idx, (label, value) in enumerate(stats):
        cx = x0 + 22 + idx * col_w
        draw.text((cx, stats_y), label, font=fonts["stat_label"], fill=TEXT_SECONDARY)
        draw.text((cx, stats_y + 18), value, font=fonts["stat_value"], fill=TEXT_PRIMARY)


def render_summary_card(data: ReplayData, *, icons_dir: Path | None = None) -> bytes:
    """Render a dark-themed PNG match summary card from ReplayData."""
    resolved_icons_dir = icons_dir or DEFAULT_ICONS_DIR

    fonts = {
        "title": _load_font(bold=True, size=28),
        "subtitle": _load_font(bold=False, size=15),
        "matchup": _load_font(bold=True, size=16),
        "player_name": _load_font(bold=True, size=22),
        "race": _load_font(bold=False, size=14),
        "badge": _load_font(bold=True, size=13),
        "stat_label": _load_font(bold=True, size=11),
        "stat_value": _load_font(bold=True, size=16),
        "vs": _load_font(bold=True, size=18),
        "footer": _load_font(bold=False, size=13),
    }

    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Header
    matchup = "v".join(p.race[0].upper() for p in data.players if p.race) or "1v1"
    map_text = _truncate_text(draw, data.meta.map_name, fonts["title"], 720)
    draw.text((32, 24), map_text, font=fonts["title"], fill=TEXT_PRIMARY)

    map_w = int(draw.textlength(map_text, font=fonts["title"]))
    pill_x0 = 32 + map_w + 14
    pill_w = int(draw.textlength(matchup, font=fonts["matchup"])) + 20
    draw.rounded_rectangle((pill_x0, 27, pill_x0 + pill_w, 55), radius=8, fill="#1f6feb")
    draw.text((pill_x0 + 10, 31), matchup, font=fonts["matchup"], fill=TEXT_PRIMARY)

    duration_str = f"Duration: {_format_duration(data.meta.duration_sec)}"
    played_str = _format_played_at(data.meta.played_at)
    right_top = duration_str
    right_bottom = f"{played_str}  •  #{data.meta.replay_id}" if played_str else f"#{data.meta.replay_id}"

    rt_w = draw.textlength(right_top, font=fonts["matchup"])
    rb_w = draw.textlength(right_bottom, font=fonts["subtitle"])
    draw.text((CARD_WIDTH - 32 - rt_w, 24), right_top, font=fonts["matchup"], fill=ACCENT_GOLD)
    draw.text((CARD_WIDTH - 32 - rb_w, 48), right_bottom, font=fonts["subtitle"], fill=TEXT_SECONDARY)

    # Player cards
    player_colors: dict[int, str] = {}
    for p in data.players:
        player_colors[p.pid] = _ensure_readable_color(p.color_hex)

    if len(data.players) >= 2:
        _draw_player_card(
            img, draw, data.players[0], player_colors[data.players[0].pid],
            (32, 86, 574, 232), resolved_icons_dir, fonts,
        )
        _draw_player_card(
            img, draw, data.players[1], player_colors[data.players[1].pid],
            (626, 86, 1168, 232), resolved_icons_dir, fonts,
        )
        # VS badge
        draw.ellipse((580, 139, 620, 179), fill=BG_COLOR, outline=BORDER_COLOR, width=2)
        vs_w = draw.textlength("VS", font=fonts["vs"])
        draw.text((600 - vs_w / 2, 148), "VS", font=fonts["vs"], fill=TEXT_SECONDARY)

    # Charts
    charts_img = _render_charts_image(data, player_colors)
    img.paste(charts_img, (32, 252), charts_img)

    # Footer
    footer_y = 740
    draw.line((32, footer_y - 10, CARD_WIDTH - 32, footer_y - 10), fill=BORDER_COLOR, width=1)
    left_footer = f"Battles: {len(data.battles)}   •   Patch {data.meta.version}"
    right_footer = "SC2GG Bot"
    rf_w = draw.textlength(right_footer, font=fonts["footer"])
    draw.text((32, footer_y), left_footer, font=fonts["footer"], fill=TEXT_SECONDARY)
    draw.text((CARD_WIDTH - 32 - rf_w, footer_y), right_footer, font=fonts["footer"], fill=TEXT_SECONDARY)

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


async def render_summary_card_async(data: ReplayData, *, icons_dir: Path | None = None) -> bytes:
    """Run CPU-bound summary card rendering in a worker thread."""
    return await asyncio.to_thread(render_summary_card, data, icons_dir=icons_dir)
