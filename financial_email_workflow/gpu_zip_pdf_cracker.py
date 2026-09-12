"""旧附件破解入口兼容层；请改用根目录 financial_attachment_crack.py。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.modules.financial_attachment_cracker import main


if __name__ == "__main__":
    raise SystemExit(main())
