from __future__ import annotations

from typing import Any

from localai.context import AppContext
from localai.logging_config import get_logger
from localai.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig
from localai.modules.system_checks import check_nvidia_smi


logger = get_logger(__name__)


def run(ctx: AppContext, prompt: str, chat: bool = True, max_tokens: int | None = None) -> dict[str, Any]:
    logger.info("Running AI self check")

    nvidia = check_nvidia_smi()
    llama_config = LlamaCppConfig.from_config(ctx.config, ctx.project_root)
    client = LlamaCppClient(llama_config)

    try:
        health, models = client.ensure_server()
        client.assert_model_available(models)

        result: dict[str, Any] = {
            "cuda_check": {
                "command": " ".join(nvidia.command),
                "ok": nvidia.ok,
                "returncode": nvidia.returncode,
                "summary": _first_non_empty_line(nvidia.stdout or nvidia.stderr),
            },
            "llamacpp": {
                "base_url": llama_config.base_url,
                "model": llama_config.model,
                "server_path": llama_config.server_path,
                "extra_dll_dirs": llama_config.extra_dll_dirs,
                "n_gpu_layers": llama_config.n_gpu_layers,
                "ctx_size": llama_config.ctx_size,
                "health": health,
                "available_models": client.model_ids(models),
            },
        }

        if chat:
            result["prompt"] = prompt
            result["answer"] = client.chat(prompt, max_tokens=max_tokens)

        return result
    finally:
        client.shutdown_server()


def _first_non_empty_line(value: str) -> str:
    for line in value.splitlines():
        if line.strip():
            return line.strip()
    return ""
