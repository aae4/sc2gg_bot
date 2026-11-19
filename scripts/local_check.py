from __future__ import annotations

import argparse
import functools
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.domain.models import ParsedReplayBundle  # noqa: E402
from app.parser.replay_parser import ReplayParseError, parse_replay_file  # noqa: E402
from app.renderer.summary_card import render_summary_card  # noqa: E402


class NoCacheHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Serve local viewer/data files without browser caching."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _format_duration(seconds: int) -> str:
    mins, secs = divmod(max(0, seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _resolve_replay_paths(replay_arg: str | None, *, parse_all: bool) -> list[Path]:
    files_dir = ROOT_DIR / "files"

    if parse_all:
        paths = sorted(files_dir.glob("*.SC2Replay"))
        if not paths:
            raise FileNotFoundError(f"В папке {files_dir} не найдено ни одного .SC2Replay файла.")
        return paths

    if replay_arg:
        candidate = Path(replay_arg)
        if candidate.is_file():
            return [candidate.resolve()]
        in_files = files_dir / replay_arg
        if in_files.is_file():
            return [in_files.resolve()]
        matches = sorted(
            p for p in files_dir.glob("*.SC2Replay") if replay_arg.lower() in p.name.lower()
        )
        if len(matches) == 1:
            return [matches[0].resolve()]
        if len(matches) > 1:
            names = ", ".join(p.name for p in matches)
            raise FileNotFoundError(
                f"Найдено несколько реплеев по '{replay_arg}': {names}. Укажите точнее."
            )
        raise FileNotFoundError(f"Файл реплея не найден: {replay_arg}")

    paths = sorted(files_dir.glob("*.SC2Replay"))
    if not paths:
        raise FileNotFoundError(
            f"Не указан файл реплея, и в {files_dir} не найдено ни одного .SC2Replay."
        )
    return [paths[0].resolve()]


def _save_bundle(bundle: ParsedReplayBundle, data_dir: Path, *, render_card: bool) -> list[Path]:
    meta = bundle.data.meta
    replays_dir = data_dir / "replays"
    minimaps_dir = data_dir / "minimaps"
    cards_dir = data_dir / "cards"

    replays_dir.mkdir(parents=True, exist_ok=True)
    minimaps_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    json_path = replays_dir / f"{meta.replay_id}.json"
    json_path.write_text(bundle.data.model_dump_json(), encoding="utf-8")
    written.append(json_path)

    if bundle.minimap_png:
        minimap_path = minimaps_dir / meta.minimap_filename
        minimap_path.write_bytes(bundle.minimap_png)
        written.append(minimap_path)

    if bundle.hd_map_bytes and meta.hd_map_filename:
        hd_path = minimaps_dir / meta.hd_map_filename
        hd_path.write_bytes(bundle.hd_map_bytes)
        written.append(hd_path)

    if render_card:
        cards_dir.mkdir(parents=True, exist_ok=True)
        card_path = cards_dir / f"{meta.replay_id}.png"
        card_path.write_bytes(render_summary_card(bundle.data))
        written.append(card_path)

    return written


def _print_summary(replay_path: Path, bundle: ParsedReplayBundle, viewer_url: str) -> None:
    data = bundle.data
    meta = data.meta
    print(f"\n=== {replay_path.name} ===")
    print(f"Replay ID : {meta.replay_id}")
    print(f"Карта     : {meta.map_name} ({meta.map_width}x{meta.map_height})")
    print(f"Длительн. : {_format_duration(meta.duration_sec)}  |  Версия: {meta.version}")
    print(f"Кадры/Битвы: {len(data.frames)} кадров, {len(data.battles)} битв")
    print(
        f"Миникарта : {meta.minimap_filename}"
        + (f" + HD ({meta.hd_map_filename})" if meta.hd_map_filename and bundle.hd_map_bytes else "")
    )
    for player in data.players:
        arch = f" • {player.build_archetype}" if player.build_archetype else ""
        print(
            f"  - [{player.result}] {player.name} ({player.race}{arch}) | "
            f"APM {player.apm} | SQ {player.spending_quotient} | "
            f"Workers {player.workers_peak}"
        )
    print(f"Viewer URL: {viewer_url}")


def _serve(host: str, port: int, open_url: str | None) -> None:
    handler = functools.partial(NoCacheHTTPRequestHandler, directory=str(ROOT_DIR))
    server = ReusableThreadingHTTPServer((host, port), handler)
    print(f"\nЛокальный сервер запущен: http://{host}:{port}/viewer/")
    print("Нажмите Ctrl+C для остановки.")
    if open_url:
        webbrowser.open(open_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Локальный парсинг .SC2Replay и запуск 2D-плеера viewer/."
    )
    parser.add_argument(
        "replay",
        nargs="?",
        help="Путь к .SC2Replay файлу (или имя/часть имени из папки files/). По умолчанию берётся первый файл из files/.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Распарсить все .SC2Replay файлы в папке files/.",
    )
    parser.add_argument(
        "--sample-step",
        type=int,
        default=3,
        help="Шаг сэмплирования кадров в секундах (по умолчанию 3).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Хост локального HTTP-сервера (по умолчанию 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Порт локального HTTP-сервера (по умолчанию 8765).",
    )
    parser.add_argument(
        "--no-card",
        action="store_true",
        help="Не генерировать PNG-карточку матча в data/cards/.",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Только распарсить реплей и сохранить файлы в data/, без запуска HTTP-сервера.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Не открывать браузер автоматически.",
    )

    args = parser.parse_args()

    try:
        replay_paths = _resolve_replay_paths(args.replay, parse_all=args.all)
    except FileNotFoundError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    data_dir = ROOT_DIR / "data"
    first_url: str | None = None

    for replay_path in replay_paths:
        print(f"Парсинг {replay_path.name}...")
        try:
            bundle = parse_replay_file(replay_path, sample_step_sec=args.sample_step)
        except ReplayParseError as exc:
            print(f"Ошибка парсинга {replay_path.name}: {exc}", file=sys.stderr)
            if not args.all:
                return 1
            continue

        _save_bundle(bundle, data_dir, render_card=not args.no_card)
        url = f"http://{args.host}:{args.port}/viewer/?startapp={bundle.data.meta.replay_id}"
        if first_url is None:
            first_url = url
        _print_summary(replay_path, bundle, url)

    if first_url is None:
        return 1

    if not args.no_serve:
        _serve(args.host, args.port, None if args.no_open else first_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
