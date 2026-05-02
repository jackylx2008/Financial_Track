# -*- coding: utf-8 -*-
"""Extract visible order data from Android order screenshots with local AI vision."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.order_image_extract import run


PLATFORM_INPUT_DIRS = {
    "pdd": Path("raw_data") / "pdd",
    "pinduoduo": Path("raw_data") / "pdd",
    "meituan": Path("raw_data") / "meituan",
}
PLATFORM_OUTPUT_NAMES = {
    "pdd": "pdd",
    "pinduoduo": "pdd",
    "meituan": "meituan",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use local AI vision to extract order JSON from PNG screenshots.")
    parser.add_argument("platform", choices=sorted(PLATFORM_INPUT_DIRS), help="Order platform.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--image", help="Single screenshot image to parse.")
    parser.add_argument("--input-dir", help="Directory containing PNG screenshots. Defaults by platform.")
    parser.add_argument("--output-dir", help="Directory for parsed JSON. Defaults to raw_data/order_json/<platform>.")
    parser.add_argument("--all", action="store_true", help="Parse all PNG images from the input directory.")
    parser.add_argument("--max-images", type=int, help="Limit images processed when using --all.")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max tokens for each vision request.")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress display.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    platform = PLATFORM_OUTPUT_NAMES[args.platform]
    image_paths = resolve_image_paths(args, ctx.project_root)
    output_dir = resolve_output_dir(args, ctx.project_root, platform)
    progress = None if args.no_progress else ConsoleProgress(total=len(image_paths))
    try:
        results = run(
            ctx=ctx,
            platform=platform,
            image_paths=image_paths,
            output_dir=output_dir,
            max_tokens=args.max_tokens,
            progress_callback=progress.update if progress else None,
        )
    finally:
        if progress:
            progress.finish()
    print_json({"platform": platform, "results": results})
    return 0


def resolve_image_paths(args: argparse.Namespace, project_root: Path) -> list[Path]:
    if args.image:
        image_path = Path(args.image)
        if not image_path.is_absolute():
            image_path = project_root / image_path
        if not image_path.exists():
            raise FileNotFoundError(f"Image does not exist: {image_path}")
        return [image_path]

    input_dir = Path(args.input_dir) if args.input_dir else PLATFORM_INPUT_DIRS[args.platform]
    if not input_dir.is_absolute():
        input_dir = project_root / input_dir
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    images = sorted(input_dir.glob("*.png"), key=lambda path: path.stat().st_mtime)
    if not images:
        raise FileNotFoundError(f"No PNG screenshots found in: {input_dir}")

    if args.all:
        return images[: args.max_images] if args.max_images else images

    return [images[-1]]


def resolve_output_dir(args: argparse.Namespace, project_root: Path, platform: str) -> Path:
    output_dir = Path(args.output_dir) if args.output_dir else Path("raw_data") / "order_json" / platform
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    return output_dir


class ConsoleProgress:
    def __init__(self, total: int, width: int = 28) -> None:
        self.total = max(total, 1)
        self.width = width
        self.started_at = time.monotonic()
        self.enabled = sys.stderr.isatty()
        self._last_line_length = 0

    def update(self, index: int, total: int, image_path: Path, status: str) -> None:
        if not self.enabled:
            return

        done_count = index if status == "done" else index - 1
        done_count = max(0, min(done_count, total))
        ratio = done_count / max(total, 1)
        filled = int(self.width * ratio)
        bar = "#" * filled + "-" * (self.width - filled)
        percent = int(ratio * 100)
        elapsed = int(time.monotonic() - self.started_at)
        status_text = {"start": "RUN", "done": "DONE", "error": "ERROR"}.get(status, status)
        filename = _shorten(image_path.name, 36)
        line = f"\r[{bar}] {done_count}/{total} {percent:3d}% {status_text} {filename} elapsed={elapsed}s"
        padding = " " * max(0, self._last_line_length - len(line))
        sys.stderr.write(line + padding)
        sys.stderr.flush()
        self._last_line_length = len(line)

    def finish(self) -> None:
        if self.enabled:
            sys.stderr.write("\n")
            sys.stderr.flush()


def _shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
