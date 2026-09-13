from __future__ import annotations

from typing import Any

from flows.context import AppContext
from flows.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig


def run(
    ctx: AppContext,
    prompt: str,
    chat: bool = True,
    max_tokens: int = 128,
) -> dict[str, Any]:
    llama_config = LlamaCppConfig.from_config(ctx.config, ctx.project_root)
    client = LlamaCppClient(llama_config)

    result: dict[str, Any] = {
        "llamacpp": {
            "base_url": llama_config.base_url,
            "model": llama_config.model,
        },
    }

    health, models = client.ensure_server()
    client.assert_model_available(models)
    result["llamacpp"]["health"] = health
    result["llamacpp"]["available_models"] = client.model_ids(models)

    if chat:
        result["answer"] = client.chat(prompt, max_tokens=max_tokens)

    return result
