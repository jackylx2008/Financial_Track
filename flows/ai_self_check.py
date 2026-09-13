"""外部 AI 服务自检工具

用途：
  检查外部 OpenAI 兼容服务及模型聊天接口是否可用。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，`llamacpp` 负责外部服务连接参数。
  `common.env` 可为 `config.yaml` 中的环境变量占位提供本机覆盖值。

可选参数：
  --config      配置文件路径，默认 `config.yaml`。
  --prompt      发送给外部模型的测试提示词。
  --max-tokens  自检聊天请求最大输出 token 数，默认 128。
  --no-chat     只检查服务可达性，不发起聊天补全请求。

示例：
  python flows/ai_self_check.py
  python flows/ai_self_check.py --config config.yaml --no-chat

输出：
  在控制台输出 JSON 自检结果；运行日志按统一日志配置写入 `logs/` 目录。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_PATH = str(PROJECT_ROOT)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from flows.entrypoints import bootstrap_context, print_json
from flows.workflows.ai_self_check import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--prompt",
        default="请直接回答，不要输出推理过程：外部模型是否可用？",
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
