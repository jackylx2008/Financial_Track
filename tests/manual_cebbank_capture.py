"""人工测试入口：清空旧图后采集三页光大银行流水截图。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flows.android_transaction_capture import run  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "manual_android_capture" / "cebbank"


def clear_test_screenshots(output_dir: Path = OUTPUT_DIR) -> int:
    """只清理人工测试目录中的 PNG，不影响其他测试文件。"""
    if not output_dir.exists():
        return 0
    deleted = 0
    for screenshot in output_dir.glob("*.png"):
        if screenshot.is_file():
            screenshot.unlink()
            deleted += 1
    return deleted


def main() -> int:
    deleted = clear_test_screenshots()
    print(f"cleared_test_screenshots={deleted}")
    return run(
        [
            "capture-scroll",
            "--app",
            "cebbank",
            "--pages",
            "3",
            "--output-dir",
            str(OUTPUT_DIR),
            "--wait",
            "1.5",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
