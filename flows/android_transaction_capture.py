# -*- coding: utf-8 -*-
"""通过 USB 安卓实体机采集多个 App 的交易流水截图。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageChops, ImageStat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flows.modules.android_adb import AdbClient, ScreenSize, mask_device_serial, scale_swipe
from flows.modules.android_capture_config import AndroidAppConfig, load_android_app_configs, resolve_android_app
from flows.modules.android_connection import current_platform_key, initialize_adb
from flows.modules.config_loader import load_common_env
from logging_config import configure_utf8_stdio, get_logger, setup_logger


DEFAULT_STABLE_THRESHOLD = 0.995


def build_parser(apps: tuple[AndroidAppConfig, ...]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通过 USB 安卓实体机采集 App 交易流水截图")
    parser.add_argument("command", choices=("check", "capture", "capture-scroll", "capture-until-end"))
    parser.add_argument("--app", required=True, help="common.env 中配置的 App key 或名称")
    parser.add_argument("--device", help="ADB 设备序列号；单设备时可留空")
    parser.add_argument("--adb", help="ADB 程序路径；留空时按当前操作系统自动查找")
    parser.add_argument("--output-dir", help="临时覆盖 App 配置的截图输出目录")
    parser.add_argument("--keep-existing", action="store_true", help="保留已有的同 App 截图")
    parser.add_argument("--pages", type=int, default=5, help="固定截图数量，默认 5")
    parser.add_argument("--max-pages", type=int, default=50, help="自动到底最大截图数量，默认 50")
    parser.add_argument("--wait", type=float, default=1.5, help="每次滑动后等待秒数，默认 1.5")
    parser.add_argument("--stable-threshold", type=float, default=DEFAULT_STABLE_THRESHOLD)
    parser.add_argument("--stop-on-stable", action="store_true", help="页面稳定时直接停止")
    parser.epilog = "已配置 App：" + ("、".join(item.name for item in apps) or "无")
    return parser


def calculate_image_similarity(first_path: Path, second_path: Path) -> float:
    with Image.open(first_path) as first_image, Image.open(second_path) as second_image:
        first = first_image.convert("RGB")
        second = second_image.convert("RGB")
        width = min(first.width, second.width)
        height = min(first.height, second.height)
        crop_box = (0, int(height * 0.12), width, int(height * 0.90))
        first_sample = first.crop(crop_box).resize((96, 160))
        second_sample = second.crop(crop_box).resize((96, 160))
        diff = ImageChops.difference(first_sample, second_sample)
        mean_diff = sum(ImageStat.Stat(diff).mean) / 3
        return 1 - (mean_diff / 255)


def resolve_output_dir(app: AndroidAppConfig, override: str | None) -> Path:
    output_dir = Path(override).expanduser() if override else app.output_dir
    return output_dir if output_dir.is_absolute() else PROJECT_ROOT / output_dir


def build_output_path(app: AndroidAppConfig, output_dir: Path, session: str, index: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{app.filename_prefix}_{session}_{index:03d}.png"


def clear_existing(app: AndroidAppConfig, output_dir: Path) -> int:
    if not output_dir.exists():
        return 0
    count = 0
    for path in output_dir.glob(f"{app.filename_prefix}_*.png"):
        if path.is_file():
            path.unlink()
            count += 1
    return count


def validate_args(args: argparse.Namespace) -> None:
    if args.pages < 1 or args.max_pages < 1:
        raise ValueError("截图数量必须大于或等于 1")
    if args.wait < 0:
        raise ValueError("滑动等待秒数不能小于 0")
    if not 0 < args.stable_threshold < 1:
        raise ValueError("稳定度阈值必须大于 0 且小于 1")


def run(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    load_common_env(PROJECT_ROOT)
    apps = load_android_app_configs(os.environ)
    args = build_parser(apps).parse_args(argv)
    validate_args(args)
    if not apps:
        raise RuntimeError("common.env 未配置 ANDROID_CAPTURE_APPS_JSON")
    app = resolve_android_app(args.app, apps)

    platform_key = current_platform_key()
    setup_logger(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        entry_name=f"android_capture_{platform_key}",
        log_dir=PROJECT_ROOT / "logs",
    )
    logger = get_logger(__name__)
    try:
        logger.info("开始初始化安卓连接；os=%s", platform_key)
        _, adb_path = initialize_adb(args.adb)
        return _execute(args, app, platform_key, adb_path, logger)
    except Exception:
        logger.exception("安卓交易流水采集失败；app=%s", app.key)
        raise


def _execute(
    args: argparse.Namespace,
    app: AndroidAppConfig,
    platform_key: str,
    adb_path: Path,
    logger: logging.Logger,
) -> int:
    client = AdbClient(adb_path)
    device = client.select_authorized_device(args.device)
    masked_serial = mask_device_serial(device.serial)
    screen_size = client.get_screen_size(device.serial)
    swipe = scale_swipe(
        app.swipe,
        ScreenSize(app.reference_width, app.reference_height),
        screen_size,
    )
    logger.info(
        "安卓连接初始化成功；os=%s adb=%s device=%s screen=%sx%s",
        platform_key,
        adb_path,
        masked_serial,
        screen_size.width,
        screen_size.height,
    )
    logger.info(
        "App 已选择；app=%s output_dir=%s swipe=%s",
        app.key,
        resolve_output_dir(app, args.output_dir),
        swipe,
    )
    print(
        f"connected os={platform_key} device={masked_serial} "
        f"screen={screen_size.width}x{screen_size.height} app={app.name}"
    )
    if args.command == "check":
        return 0

    output_dir = resolve_output_dir(app, args.output_dir)
    if not args.keep_existing:
        deleted = clear_existing(app, output_dir)
        logger.info("已清理同 App 历史截图；app=%s count=%s", app.key, deleted)

    if args.command == "capture":
        _capture(client, device.serial, app, output_dir, logger, 1, datetime.now().strftime("%Y%m%d_%H%M%S"))
        return 0
    if args.command == "capture-scroll":
        _capture_fixed(client, device.serial, app, output_dir, swipe, args, logger)
        return 0
    _capture_until_end(client, device.serial, app, output_dir, swipe, args, logger)
    return 0


def _capture(
    client: AdbClient,
    serial: str,
    app: AndroidAppConfig,
    output_dir: Path,
    logger: logging.Logger,
    index: int,
    session: str,
) -> Path:
    output_path = build_output_path(app, output_dir, session, index)
    client.capture_screen(serial, output_path)
    logger.info("截图成功；app=%s index=%s file=%s", app.key, index, output_path)
    print(f"{index} saved={output_path}")
    return output_path


def _capture_fixed(
    client: AdbClient,
    serial: str,
    app: AndroidAppConfig,
    output_dir: Path,
    swipe: tuple[int, int, int, int, int],
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    session = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(1, args.pages + 1):
        _capture(client, serial, app, output_dir, logger, index, session)
        if index < args.pages:
            client.swipe(serial, swipe)
            logger.info("滑动成功；app=%s index=%s swipe=%s", app.key, index, swipe)
            time.sleep(args.wait)


def _capture_until_end(
    client: AdbClient,
    serial: str,
    app: AndroidAppConfig,
    output_dir: Path,
    swipe: tuple[int, int, int, int, int],
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    session = datetime.now().strftime("%Y%m%d_%H%M%S")
    previous: Path | None = None
    for index in range(1, args.max_pages + 1):
        current = _capture(client, serial, app, output_dir, logger, index, session)
        if previous is not None:
            similarity = calculate_image_similarity(previous, current)
            print(f"similarity={similarity:.5f}")
            if similarity >= args.stable_threshold:
                logger.info("页面稳定，采集停止；app=%s similarity=%.5f", app.key, similarity)
                current.unlink(missing_ok=True)
                if args.stop_on_stable or not _ask_continue():
                    break
                previous = None
                time.sleep(args.wait)
                continue
        if index < args.max_pages:
            previous = current
            client.swipe(serial, swipe)
            logger.info("滑动成功；app=%s index=%s swipe=%s", app.key, index, swipe)
            time.sleep(args.wait)


def _ask_continue() -> bool:
    choice = input("页面未变化。如已在手机上手动加载更多，输入 c 继续，否则回车停止：")
    return choice.strip().lower() in {"c", "continue", "y", "yes"}


def main() -> int:
    try:
        return run()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
