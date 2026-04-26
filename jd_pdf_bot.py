# -*- coding: utf-8 -*-
"""
JD order page PDF exporter.

Renders JD order pages in Chromium and writes PDFs directly. It does not use
mouse clicks, Ctrl+P, or the system print dialog.

Dependencies:
    pip install playwright pyyaml python-dotenv
    python -m playwright install chromium
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from logging_config import get_logger, setup_logger


JD_ORDER_URL_TEMPLATE = "https://order.jd.com/center/list.action?d={year}&s=4096&page={page}"
CONFIG_PATH = Path("config.yaml")
ENV_PATH = Path("common.env")

DEFAULT_BROWSER_USER_DATA_DIR = Path("raw_data") / "jd_browser_profile"
DEFAULT_HEADLESS = False
DEFAULT_WAIT_SECONDS = 5.0
DEFAULT_LOGIN_TIMEOUT_SECONDS = 300

logger = get_logger(__name__)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误，顶层必须是 YAML mapping: {path}")

    return data


def resolve_placeholders(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        env_value = os.getenv(env_name)
        if env_value is None:
            raise ValueError(f"环境变量未配置: {env_name}")
        return env_value

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, value)


def resolve_path(value: Any, default: Path | None = None) -> Path:
    if not value:
        if default is None:
            raise ValueError("路径配置不能为空")
        path = default
    elif isinstance(value, dict) and len(value) == 1:
        env_name = next(iter(value))
        env_value = os.getenv(str(env_name))
        if env_value is None:
            raise ValueError(f"环境变量未配置: {env_name}")
        path = Path(env_value)
    else:
        path = Path(resolve_placeholders(str(value)))

    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path

    return path


def get_output_dir(config: dict[str, Any]) -> Path:
    path = resolve_path(config.get("jd_pdf_output_dir"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_browser_user_data_dir(config: dict[str, Any]) -> Path:
    path = resolve_path(
        config.get("jd_browser_user_data_dir"),
        default=DEFAULT_BROWSER_USER_DATA_DIR,
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def get_float(config: dict[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    return float(value)


def get_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    return int(value)


def get_order_pages(config: dict[str, Any]) -> list[tuple[int, int]]:
    order_pages = config.get("jd_order_pages")
    if not order_pages:
        return [(2025, 2)]

    if not isinstance(order_pages, dict):
        raise ValueError("config.yaml 中 jd_order_pages 必须是年份到页数的 mapping")

    jobs: list[tuple[int, int]] = []
    for year, pages in order_pages.items():
        year_int = int(year)
        jobs.extend((year_int, page) for page in normalize_pages(pages))

    return sorted(jobs)


def normalize_pages(pages: Any) -> list[int]:
    if isinstance(pages, int):
        if pages < 1:
            raise ValueError("页数必须大于等于 1")
        return list(range(1, pages + 1))

    if isinstance(pages, list):
        page_numbers = [int(page) for page in pages]
        if any(page < 1 for page in page_numbers):
            raise ValueError("页码必须大于等于 1")
        return page_numbers

    raise ValueError("jd_order_pages 的值必须是整数页数，或页码列表")


def build_order_url(year: int, page: int) -> str:
    return JD_ORDER_URL_TEMPLATE.format(year=year, page=page)


def build_output_file(output_dir: Path, year: int, page: int) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"jd_orders_{year}_page{page:02d}_{timestamp}.pdf"


def build_custom_output_file(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"jd_orders_custom_{timestamp}.pdf"


def render_jobs_to_pdf(
    jobs: list[tuple[str, Path]],
    browser_user_data_dir: Path,
    headless: bool,
    wait_seconds: float,
    login_timeout_seconds: int,
) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖 playwright。请先运行: pip install playwright; "
            "python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(browser_user_data_dir),
            headless=headless,
            locale="zh-CN",
            viewport={"width": 1440, "height": 1200},
        )
        page = context.new_page()

        try:
            for index, (url, output_file) in enumerate(jobs, start=1):
                logger.info("开始渲染第 %s/%s 个页面: %s", index, len(jobs), url)
                render_one_page_to_pdf(
                    page=page,
                    url=url,
                    output_file=output_file,
                    wait_seconds=wait_seconds,
                    login_timeout_seconds=login_timeout_seconds,
                    timeout_error=PlaywrightTimeoutError,
                )
        finally:
            context.close()


def render_one_page_to_pdf(
    page: Any,
    url: str,
    output_file: Path,
    wait_seconds: float,
    login_timeout_seconds: int,
    timeout_error: type[Exception],
) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait_for_jd_login_if_needed(page, login_timeout_seconds, timeout_error)

    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except timeout_error:
        logger.warning("页面网络请求未完全静默，继续等待固定时间后导出 PDF。")

    time.sleep(wait_seconds)
    page.emulate_media(media="screen")
    page.pdf(
        path=str(output_file),
        format="A4",
        print_background=True,
        prefer_css_page_size=True,
    )
    logger.info("PDF 已保存: %s", output_file)


def wait_for_jd_login_if_needed(
    page: Any,
    login_timeout_seconds: int,
    timeout_error: type[Exception],
) -> None:
    current_url = page.url
    if "passport.jd.com" not in current_url and "login" not in current_url:
        return

    logger.warning("当前跳转到京东登录页，请在打开的 Chromium 窗口中完成登录。")
    try:
        page.wait_for_url(
            re.compile(r"https://order\.jd\.com/.*"),
            timeout=login_timeout_seconds * 1000,
        )
    except timeout_error as exc:
        raise RuntimeError("等待京东登录超时，未导出 PDF。") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render JD order pages and save them as PDFs.")
    parser.add_argument(
        "--url",
        default=None,
        help="只打印指定的京东订单 URL；传入后会忽略 config.yaml 的 jd_order_pages。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="使用无头浏览器。首次登录京东时不要使用该选项。",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="强制显示浏览器窗口。",
    )
    return parser.parse_args()


def build_jobs(args: argparse.Namespace, config: dict[str, Any], output_dir: Path) -> list[tuple[str, Path]]:
    if args.url:
        return [(args.url, build_custom_output_file(output_dir))]

    return [
        (build_order_url(year, page), build_output_file(output_dir, year, page))
        for year, page in get_order_pages(config)
    ]


def main() -> int:
    setup_logger(log_level="INFO")
    args = parse_args()

    try:
        load_dotenv(ENV_PATH)
        config = load_config()
        output_dir = get_output_dir(config)
        browser_user_data_dir = get_browser_user_data_dir(config)
        jobs = build_jobs(args, config, output_dir)

        headless = get_bool(config, "jd_pdf_headless", DEFAULT_HEADLESS)
        if args.headless:
            headless = True
        if args.headed:
            headless = False

        wait_seconds = get_float(config, "jd_pdf_wait_seconds", DEFAULT_WAIT_SECONDS)
        login_timeout_seconds = get_int(
            config,
            "jd_login_timeout_seconds",
            DEFAULT_LOGIN_TIMEOUT_SECONDS,
        )

        logger.info("=" * 50)
        logger.info("京东订单 PDF 渲染导出脚本已启动")
        logger.info("输出目录: %s", output_dir)
        logger.info("浏览器用户目录: %s", browser_user_data_dir)
        logger.info("待导出页数: %s", len(jobs))
        logger.info("无头模式: %s", headless)
        logger.info("=" * 50)

        render_jobs_to_pdf(
            jobs=jobs,
            browser_user_data_dir=browser_user_data_dir,
            headless=headless,
            wait_seconds=wait_seconds,
            login_timeout_seconds=login_timeout_seconds,
        )
        return 0
    except KeyboardInterrupt:
        logger.info("检测到 Ctrl+C，脚本已退出。")
        return 130
    except Exception as exc:
        logger.exception("导出失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
