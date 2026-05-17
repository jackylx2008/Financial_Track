# -*- coding: utf-8 -*-
"""Android 订单截图采集工具

用途：
  通过 ADB 截取手机或模拟器中的订单页面截图，支持拼多多和美团平台，提供单次截图、固定次数滚动截图、
  以及滚动到页面内容不再变化的采集流程。

配置文件：
  本入口不读取 `config.yaml` 或 `.env`。ADB 路径优先使用 `--adb` 指定值，其次使用系统 PATH，
  再尝试常见模拟器自带 ADB。平台默认输出目录固定为 `raw_data/pdd` 或 `raw_data/meituan`。

必填参数：
  platform  平台名称，可选 `pdd`、`pinduoduo`、`meituan`、`mt`。
  command   采集命令，可选 `capture`、`capture-scroll`、`capture-until-end`。

可选参数：
  --device            ADB 设备序列号，多设备连接时使用。
  --adb               adb.exe 路径。
  --output-dir        截图输出目录，默认按平台写入 `raw_data/<platform>`。
  --keep-existing     保留输出目录中已有的同平台截图。
  --pages             `capture-scroll` 的截图页数，默认 5。
  --max-pages         `capture-until-end` 的最大截图页数，默认 50。
  --wait              滑动后等待秒数，默认 1.5。
  --stable-threshold  判定页面不再变化的相似度阈值，默认 0.995。

示例：
  python android_order_bot.py pdd capture --device 10CF8C17KP004G0
  python android_order_bot.py meituan capture-until-end --device 10CF8C17KP004G0

输出：
  将 PNG 截图写入输出目录，并在控制台打印生成的截图路径、相似度和停止原因等运行信息。
"""

from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageChops, ImageStat

from order_capture.capture_screen import (
    build_output_path,
    capture_screen,
    resolve_adb_path,
)


@dataclass(frozen=True)
class PlatformConfig:
    name: str
    filename_prefix: str
    output_dir: Path
    default_swipe: tuple[int, int, int, int, int]


DEFAULT_SWIPE = (540, 1700, 540, 500, 600)
PDD_DEFAULT_SWIPE = (540, 1700, 540, 850, 600)
PLATFORMS = {
    "pdd": PlatformConfig("pdd", "pinduoduo", Path("raw_data") / "pdd", PDD_DEFAULT_SWIPE),
    "pinduoduo": PlatformConfig("pdd", "pinduoduo", Path("raw_data") / "pdd", PDD_DEFAULT_SWIPE),
    "meituan": PlatformConfig("meituan", "meituan", Path("raw_data") / "meituan", DEFAULT_SWIPE),
    "mt": PlatformConfig("meituan", "meituan", Path("raw_data") / "meituan", DEFAULT_SWIPE),
}
DEFAULT_STABLE_THRESHOLD = 0.995


def resolve_platform(value: str) -> PlatformConfig:
    platform = PLATFORMS.get(value.strip().lower())
    if platform is None:
        choices = ", ".join(sorted(PLATFORMS))
        raise ValueError(f"Unsupported platform: {value}. Choices: {choices}")
    return platform


def add_common_adb_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", help="ADB device serial, for example 10CF8C17KP004G0")
    parser.add_argument("--adb", help="adb.exe path. Defaults to PATH, then MuMu bundled ADB.")


def add_capture_parser(subparsers: argparse._SubParsersAction, platform: PlatformConfig) -> None:
    capture_parser = subparsers.add_parser("capture", help="capture current phone screen")
    add_common_adb_args(capture_parser)
    capture_parser.add_argument(
        "--output-dir",
        default=str(platform.output_dir),
        help=f"screenshot output directory, default {platform.output_dir}",
    )
    add_cleanup_args(capture_parser)


def add_scroll_parser(subparsers: argparse._SubParsersAction, platform: PlatformConfig) -> None:
    scroll_parser = subparsers.add_parser("capture-scroll", help="capture and swipe up N times")
    add_common_adb_args(scroll_parser)
    scroll_parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="number of screenshots, default 5",
    )
    scroll_parser.add_argument(
        "--wait",
        type=float,
        default=1.5,
        help="seconds to wait after each swipe, default 1.5",
    )
    scroll_parser.add_argument(
        "--output-dir",
        default=str(platform.output_dir),
        help=f"screenshot output directory, default {platform.output_dir}",
    )
    add_cleanup_args(scroll_parser)
    add_swipe_args(scroll_parser, platform)


def add_until_end_parser(subparsers: argparse._SubParsersAction, platform: PlatformConfig) -> None:
    until_end_parser = subparsers.add_parser(
        "capture-until-end",
        help="capture and swipe until screen content stops changing",
    )
    add_common_adb_args(until_end_parser)
    until_end_parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="safety limit for screenshots, default 50",
    )
    until_end_parser.add_argument(
        "--wait",
        type=float,
        default=1.5,
        help="seconds to wait after each swipe, default 1.5",
    )
    until_end_parser.add_argument(
        "--output-dir",
        default=str(platform.output_dir),
        help=f"screenshot output directory, default {platform.output_dir}",
    )
    until_end_parser.add_argument(
        "--stable-threshold",
        type=float,
        default=DEFAULT_STABLE_THRESHOLD,
        help=f"stop when image similarity reaches this value, default {DEFAULT_STABLE_THRESHOLD}",
    )
    until_end_parser.add_argument(
        "--keep-duplicate-end",
        action="store_true",
        help="keep the final duplicate screenshot that triggered stop",
    )
    until_end_parser.add_argument(
        "--stop-on-stable",
        action="store_true",
        help="stop immediately when screen content stops changing; disables the continue prompt",
    )
    add_cleanup_args(until_end_parser)
    add_swipe_args(until_end_parser, platform)


def add_cleanup_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="keep existing screenshots instead of clearing the output directory first",
    )


def add_swipe_args(parser: argparse.ArgumentParser, platform: PlatformConfig) -> None:
    parser.add_argument("--start-x", type=int, default=platform.default_swipe[0], help=f"default {platform.default_swipe[0]}")
    parser.add_argument("--start-y", type=int, default=platform.default_swipe[1], help=f"default {platform.default_swipe[1]}")
    parser.add_argument("--end-x", type=int, default=platform.default_swipe[2], help=f"default {platform.default_swipe[2]}")
    parser.add_argument("--end-y", type=int, default=platform.default_swipe[3], help=f"default {platform.default_swipe[3]}")
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=platform.default_swipe[4],
        help=f"swipe duration in milliseconds, default {platform.default_swipe[4]}",
    )


def parse_args(
    argv: Sequence[str] | None = None,
    default_platform: str | None = None,
) -> argparse.Namespace:
    if default_platform:
        platform = resolve_platform(default_platform)
        parser = argparse.ArgumentParser(description=f"{platform.name} Android order capture")
    else:
        bootstrap = argparse.ArgumentParser(add_help=False)
        bootstrap.add_argument("platform")
        bootstrap_args, remaining = bootstrap.parse_known_args(argv)
        platform = resolve_platform(bootstrap_args.platform)
        argv = remaining
        parser = argparse.ArgumentParser(description="Android order capture")
        parser.set_defaults(platform=platform)

    subparsers = parser.add_subparsers(dest="command", required=True)
    add_capture_parser(subparsers, platform)
    add_scroll_parser(subparsers, platform)
    add_until_end_parser(subparsers, platform)
    parser.set_defaults(platform=platform)
    return parser.parse_args(argv)


def run_capture(args: argparse.Namespace) -> Path:
    adb_path = resolve_adb_path(args.adb)
    output_path = build_output_path(args.platform.filename_prefix, Path(args.output_dir))
    capture_screen(adb_path=adb_path, output_path=output_path, device=args.device)
    return output_path


def clear_existing_screenshots(platform: PlatformConfig, output_dir: Path) -> int:
    if not output_dir.exists():
        return 0

    deleted_count = 0
    for screenshot_path in output_dir.glob(f"{platform.filename_prefix}_*.png"):
        if screenshot_path.is_file():
            screenshot_path.unlink()
            deleted_count += 1
    return deleted_count


def build_scroll_output_path(
    platform: PlatformConfig,
    output_dir: Path,
    session_id: str,
    index: int,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{platform.filename_prefix}_{session_id}_{index:03d}.png"


def swipe_up(
    adb_path: Path,
    device: str | None,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int,
) -> None:
    command = [str(adb_path)]
    if device:
        command.extend(["-s", device])
    command.extend(
        [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ]
    )

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        error_text = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Swipe failed: {error_text}")


def run_capture_scroll(args: argparse.Namespace) -> list[Path]:
    if args.pages < 1:
        raise ValueError("--pages must be greater than or equal to 1")
    if args.wait < 0:
        raise ValueError("--wait cannot be less than 0")

    adb_path = resolve_adb_path(args.adb)
    output_dir = Path(args.output_dir)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_paths: list[Path] = []

    for index in range(1, args.pages + 1):
        output_path = build_scroll_output_path(args.platform, output_dir, session_id, index)
        capture_screen(adb_path=adb_path, output_path=output_path, device=args.device)
        output_paths.append(output_path)
        print(output_path)

        if index < args.pages:
            swipe_up(
                adb_path=adb_path,
                device=args.device,
                start_x=args.start_x,
                start_y=args.start_y,
                end_x=args.end_x,
                end_y=args.end_y,
                duration_ms=args.duration_ms,
            )
            time.sleep(args.wait)

    return output_paths


def calculate_image_similarity(
    first_path: Path,
    second_path: Path,
    crop_top_ratio: float = 0.12,
    crop_bottom_ratio: float = 0.10,
) -> float:
    with Image.open(first_path) as first_image, Image.open(second_path) as second_image:
        first = first_image.convert("RGB")
        second = second_image.convert("RGB")

        width = min(first.width, second.width)
        height = min(first.height, second.height)
        top = int(height * crop_top_ratio)
        bottom = int(height * (1 - crop_bottom_ratio))
        crop_box = (0, top, width, bottom)

        first_sample = first.crop(crop_box).resize((96, 160))
        second_sample = second.crop(crop_box).resize((96, 160))
        diff = ImageChops.difference(first_sample, second_sample)
        channel_means = ImageStat.Stat(diff).mean
        mean_diff = sum(channel_means) / len(channel_means)
        return 1 - (mean_diff / 255)


def ask_continue_after_stable(output_path: Path, keep_duplicate: bool) -> bool:
    print("Screen content did not change after swipe.")
    print("If the phone shows a button such as '显示更多历史订单', tap it on the phone now.")
    choice = input("Enter c to continue after manual action, or press Enter to stop: ")
    should_continue = choice.strip().lower() in {"c", "continue", "y", "yes"}
    if should_continue and not keep_duplicate:
        output_path.unlink(missing_ok=True)
        print(f"removed_duplicate={output_path}")
    return should_continue


def run_capture_until_end(args: argparse.Namespace) -> list[Path]:
    if args.max_pages < 1:
        raise ValueError("--max-pages must be greater than or equal to 1")
    if args.wait < 0:
        raise ValueError("--wait cannot be less than 0")
    if not 0 < args.stable_threshold < 1:
        raise ValueError("--stable-threshold must be between 0 and 1")

    adb_path = resolve_adb_path(args.adb)
    output_dir = Path(args.output_dir)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_paths: list[Path] = []
    previous_path: Path | None = None

    for index in range(1, args.max_pages + 1):
        skip_swipe = False
        output_path = build_scroll_output_path(args.platform, output_dir, session_id, index)
        capture_screen(adb_path=adb_path, output_path=output_path, device=args.device)
        output_paths.append(output_path)
        print(output_path)

        if previous_path is not None:
            similarity = calculate_image_similarity(previous_path, output_path)
            print(f"similarity={similarity:.5f}")
            if similarity >= args.stable_threshold:
                if args.stop_on_stable:
                    print("Stopped: screen content did not change after swipe.")
                else:
                    should_continue = ask_continue_after_stable(
                        output_path=output_path,
                        keep_duplicate=args.keep_duplicate_end,
                    )
                    if should_continue:
                        if not args.keep_duplicate_end:
                            output_paths.pop()
                        time.sleep(args.wait)
                        skip_swipe = True
                    else:
                        print("Stopped by user.")
                        if not args.keep_duplicate_end:
                            output_path.unlink(missing_ok=True)
                            output_paths.pop()
                            print(f"removed_duplicate={output_path}")

                if args.stop_on_stable and not args.keep_duplicate_end:
                    output_path.unlink(missing_ok=True)
                    output_paths.pop()
                    print(f"removed_duplicate={output_path}")

                if args.stop_on_stable or not should_continue:
                    break

        if index < args.max_pages:
            if skip_swipe:
                continue
            previous_path = output_path
            swipe_up(
                adb_path=adb_path,
                device=args.device,
                start_x=args.start_x,
                start_y=args.start_y,
                end_x=args.end_x,
                end_y=args.end_y,
                duration_ms=args.duration_ms,
            )
            time.sleep(args.wait)

    return output_paths


def dispatch(args: argparse.Namespace) -> int:
    if not args.keep_existing:
        deleted_count = clear_existing_screenshots(args.platform, Path(args.output_dir))
        if deleted_count:
            print(f"cleared_existing_screenshots={deleted_count}")

    if args.command == "capture":
        output_path = run_capture(args)
        print(output_path)
        return 0
    if args.command == "capture-scroll":
        run_capture_scroll(args)
        return 0
    if args.command == "capture-until-end":
        run_capture_until_end(args)
        return 0

    raise ValueError(f"Unknown command: {args.command}")


def main(
    argv: Sequence[str] | None = None,
    default_platform: str | None = None,
) -> int:
    args = parse_args(argv=argv, default_platform=default_platform)
    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
