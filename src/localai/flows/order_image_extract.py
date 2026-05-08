from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from localai.context import AppContext
from localai.modules.json_extractor import parse_json_from_text
from localai.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig
from localai.modules.order_image_prompt import build_order_image_prompt


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    platform: str,
    image_paths: list[Path],
    output_dir: Path,
    max_tokens: int,
    progress_callback: Callable[[int, int, Path, str], None] | None = None,
) -> list[dict[str, Any]]:
    llama_config = LlamaCppConfig.from_config(ctx.config, ctx.project_root)
    client = LlamaCppClient(llama_config)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    try:
        logger.info(
            "Starting order image extraction: platform=%s images=%s output_dir=%s max_tokens=%s",
            platform,
            len(image_paths),
            output_dir,
            max_tokens,
        )
        _health, models = client.ensure_server()
        client.assert_model_available(models)

        total = len(image_paths)
        for index, image_path in enumerate(image_paths, start=1):
            _notify_progress(progress_callback, index, total, image_path, "start")
            logger.info("Extracting image %s/%s: %s", index, total, image_path)
            try:
                result = extract_one_image(client, platform, image_path, output_dir, max_tokens)
            except Exception:
                _notify_progress(progress_callback, index, total, image_path, "error")
                logger.exception("Failed extracting image %s/%s: %s", index, total, image_path)
                raise
            results.append(result)
            _notify_progress(progress_callback, index, total, image_path, "done")
            logger.info(
                "Extracted image %s/%s: output=%s orders_count=%s warnings=%s",
                index,
                total,
                result["output"],
                result["orders_count"],
                result["warnings"],
            )
    finally:
        client.shutdown_server()

    logger.info("Finished order image extraction: platform=%s images=%s", platform, len(image_paths))
    return results


def extract_one_image(
    client: LlamaCppClient,
    platform: str,
    image_path: Path,
    output_dir: Path,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = build_order_image_prompt(platform=platform, source_image=image_path.name)
    raw_output = client.chat_with_image(prompt, image_path=image_path, max_tokens=max_tokens)

    try:
        parsed = parse_json_from_text(raw_output)
    except Exception as exc:
        parsed = {
            "platform": platform,
            "source_image": image_path.name,
            "orders": [],
            "warnings": [f"parse_error: {exc}"],
            "raw_model_output": raw_output,
        }

    parsed.setdefault("platform", platform)
    parsed.setdefault("source_image", image_path.name)
    parsed.setdefault("orders", [])
    parsed.setdefault("warnings", [])

    output_path = output_dir / f"{image_path.stem}.json"
    output_path.write_text(_to_json_text(parsed), encoding="utf-8")
    return {
        "image": str(image_path),
        "output": str(output_path),
        "orders_count": len(parsed.get("orders", [])),
        "warnings": parsed.get("warnings", []),
    }


def _to_json_text(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def _notify_progress(
    progress_callback: Callable[[int, int, Path, str], None] | None,
    index: int,
    total: int,
    image_path: Path,
    status: str,
) -> None:
    if progress_callback is not None:
        progress_callback(index, total, image_path, status)
