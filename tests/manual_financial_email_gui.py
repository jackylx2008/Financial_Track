"""通过正式 Tk GUI 重复验证 126 邮箱完整账单处理流程。

示例：
  python tests/manual_financial_email_gui.py --all-history
  python tests/manual_financial_email_gui.py --all-history --close-on-finish
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_PATH = str(PROJECT_ROOT)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from flows.gui.app import FinancialTrackApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-history", action="store_true")
    parser.add_argument("--close-on-finish", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = tk.Tk()
    app = FinancialTrackApp(root, PROJECT_ROOT)
    panel = next(item for item in app.panels if item.spec.key == "email")
    panel.variables["all_history"].set(args.all_history)
    app.notebook.select(panel)

    started = False

    def launch() -> None:
        nonlocal started
        started = True
        app.start_workflow(panel)

    def poll_completion() -> None:
        if started and app.started_at is None and not app.runner.running:
            if args.screenshot:
                from PIL import ImageGrab

                ImageGrab.grab(window=root.winfo_id()).save(args.screenshot)
            if args.close_on_finish:
                root.destroy()
                return
        root.after(500, poll_completion)

    root.after(300, launch)
    root.after(800, poll_completion)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
