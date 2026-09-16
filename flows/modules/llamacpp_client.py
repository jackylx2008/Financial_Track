from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flows.modules.config_loader import as_float, as_int


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlamaCppConfig:
    base_url: str
    model: str
    api_key: str
    timeout_sec: int
    max_tokens: int
    temperature: float

    @classmethod
    def from_config(cls, config: dict[str, Any], project_root: Path) -> "LlamaCppConfig":
        raw = config.get("llamacpp", {})
        return cls(
            base_url=str(raw.get("base_url", "http://127.0.0.1:8080/v1")).strip(),
            model=str(raw.get("model", "local-model")).strip() or "local-model",
            api_key=str(raw.get("api_key", "")).strip(),
            timeout_sec=as_int(raw.get("timeout_sec"), 120),
            max_tokens=as_int(raw.get("max_tokens"), 4096),
            temperature=as_float(raw.get("temperature"), 0.0),
        )


def normalize_urls(base_url: str) -> tuple[str, str]:
    parsed = urlparse(base_url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Invalid llamacpp.base_url: {base_url}")

    root_url = f"{parsed.scheme}://{parsed.netloc}"
    api_path = parsed.path.rstrip("/")
    api_url = f"{root_url}{api_path}" if api_path else root_url
    return root_url, api_url


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    method: str = "GET",
    timeout_sec: int = 120,
    api_key: str = "",
) -> dict[str, Any]:
    body = None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        content = response.read().decode("utf-8")
    return json.loads(content) if content else {}


class LlamaCppClient:
    def __init__(self, config: LlamaCppConfig) -> None:
        self.config = config
        self.root_url, self.api_url = normalize_urls(config.base_url)

    def check_health(self) -> dict[str, Any]:
        logger.info("Checking llama.cpp health endpoint: %s/health", self.root_url)
        return request_json(
            f"{self.root_url}/health",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )

    def list_models(self) -> dict[str, Any]:
        logger.info("Checking llama.cpp models endpoint: %s/models", self.api_url)
        return request_json(
            f"{self.api_url}/models",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )

    def check_server(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.check_health(), self.list_models()

    def ensure_server(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            health, models = self.check_server()
            logger.info("External AI service is available")
            return health, models
        except Exception as exc:
            raise RuntimeError(
                "外部 AI 服务不可用，请先在专用运行时项目中启动服务，"
                f"并检查 llamacpp.base_url={self.config.base_url}"
            ) from exc

    def model_ids(self, models_payload: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for item in models_payload.get("data", []):
            model_id = item.get("id")
            if model_id:
                ids.append(str(model_id))
        for item in models_payload.get("models", []):
            model_id = item.get("model") or item.get("name") or item.get("id")
            if model_id:
                ids.append(str(model_id))
        return list(dict.fromkeys(ids))

    def assert_model_available(self, models_payload: dict[str, Any]) -> None:
        model_ids = self.model_ids(models_payload)
        if self.config.model not in model_ids:
            raise RuntimeError(f"Configured model is not available: {self.config.model}. Available: {model_ids}")
        logger.info("Configured llama.cpp model is available: %s", self.config.model)

    def chat(self, prompt: str, max_tokens: int | None = None) -> str:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = request_json(
            f"{self.api_url}/chat/completions",
            payload=payload,
            method="POST",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )
        return response["choices"][0]["message"]["content"].strip()

    def chat_with_image(self, prompt: str, image_path: Path, max_tokens: int | None = None) -> str:
        image_url = image_to_data_url(image_path)
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
        response = request_json(
            f"{self.api_url}/chat/completions",
            payload=payload,
            method="POST",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )
        return response["choices"][0]["message"]["content"].strip()


def image_to_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
