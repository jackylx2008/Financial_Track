from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.ai_self_check import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local CUDA and llama.cpp AI availability.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--prompt",
        default="请直接回答，不要输出推理过程：本地模型是否可用？",
        help="Prompt sent to the local model.",
    )
    parser.add_argument("--max-tokens", type=int, default=128, help="Max tokens for the self-check chat request.")
    parser.add_argument("--no-chat", action="store_true", help="Start/check server but skip chat completion.")
    args = parser.parse_args()

    ctx = bootstrap_context(__file__, args.config)
    result = run(ctx, prompt=args.prompt, chat=not args.no_chat, max_tokens=args.max_tokens)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
