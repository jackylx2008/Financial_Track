from __future__ import annotations

from typing import Any

from localai.context import AppContext
from localai.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig
from localai.modules.system_checks import CommandResult, check_nvidia_smi


def run(
    ctx: AppContext,
    prompt: str,
    chat: bool = True,
    max_tokens: int = 128,
) -> dict[str, Any]:
    cuda_check = _run_cuda_check()
    llama_config = LlamaCppConfig.from_config(ctx.config, ctx.project_root)
    client = LlamaCppClient(llama_config)

    result: dict[str, Any] = {
        "cuda_check": cuda_check,
        "llamacpp": {
            "base_url": llama_config.base_url,
            "model": llama_config.model,
        },
    }

    try:
        health, models = client.ensure_server()
        client.assert_model_available(models)
        result["llamacpp"]["health"] = health
        result["llamacpp"]["available_models"] = client.model_ids(models)

        if chat:
            result["answer"] = client.chat(prompt, max_tokens=max_tokens)
    finally:
        client.shutdown_server()

    return result


def _run_cuda_check() -> dict[str, Any]:
    try:
        return _command_result_to_dict(check_nvidia_smi())
    except Exception as exc:
        return {
            "command": ["nvidia-smi"],
            "ok": False,
            "error": str(exc),
        }


def _command_result_to_dict(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "ok": result.ok,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
